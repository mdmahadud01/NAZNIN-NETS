"""Liquid Cloud: a password-protected, single-owner remote Chromium desktop."""
import hmac
import ipaddress
import json
import logging
import os
import queue
import secrets
import shutil
import socket
import tempfile
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session
from flask_sock import Sock
from playwright.sync_api import sync_playwright
from werkzeug.middleware.proxy_fix import ProxyFix

ROOT = Path(__file__).resolve().parent
PASSWORD = os.environ.get('APP_PASSWORD', '')
if len(PASSWORD) < 12:
    raise RuntimeError('Set APP_PASSWORD to a unique password of at least 12 characters before starting.')
app = Flask(__name__, template_folder=str(ROOT), static_folder=None)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
if os.environ.get('TRUST_PROXY', '0') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12), MAX_CONTENT_LENGTH=16384,
    SOCK_SERVER_OPTIONS={'ping_interval': 20, 'max_message_size': 16384})
sock = Sock(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('liquid')
PROFILE = Path(os.environ.get('PROFILE_DIR', str(Path(tempfile.gettempdir()) / 'liquid-cloud-profile'))).resolve()
FPS = max(1, min(20, int(os.environ.get('STREAM_FPS', '10'))))
QUALITY = max(20, min(85, int(os.environ.get('STREAM_QUALITY', '55'))))
IDLE = max(60, int(os.environ.get('IDLE_TIMEOUT', '900')))
APPS = [
    {'id':'youtube','name':'YouTube','url':'https://www.youtube.com/','color':'#ff3857','glyph':'▶','tag':'Videos & Shorts'},
    {'id':'tiktok','name':'TikTok','url':'https://www.tiktok.com/','color':'#25e7dc','glyph':'♪','tag':'For your next obsession'},
    {'id':'telegram','name':'Telegram','url':'https://web.telegram.org/','color':'#42b8ff','glyph':'➤','tag':'Your conversations'},
    {'id':'facebook','name':'Facebook','url':'https://www.facebook.com/','color':'#548dff','glyph':'f','tag':'Friends & Reels'},
    {'id':'instagram','name':'Instagram','url':'https://www.instagram.com/','color':'#ff78b1','glyph':'◎','tag':'Stories & Reels'},
    {'id':'whatsapp','name':'WhatsApp','url':'https://web.whatsapp.com/','color':'#57df9d','glyph':'☎','tag':'Stay connected'},
    {'id':'reddit','name':'Reddit','url':'https://www.reddit.com/','color':'#ff895b','glyph':'r','tag':'Find your community'},
    {'id':'x','name':'X','url':'https://x.com/','color':'#e2e7ff','glyph':'𝕏','tag':'What is happening'},
]
APP_MAP = {a['id']: a for a in APPS}
NAV_DOMAINS = ('youtube.com','youtu.be','tiktok.com','telegram.org','facebook.com','instagram.com',
    'whatsapp.com','reddit.com','x.com','twitter.com','accounts.google.com','consent.google.com','accountscenter.meta.com')
active_lock = threading.Lock()
auth_lock = threading.Lock()
auth_tokens = {}
login_attempts = defaultdict(deque)


def authorized():
    with auth_lock:
        expires = auth_tokens.get(session.get('auth'), 0)
    return expires > time.time()


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(32)
    return session['csrf']


def valid_csrf():
    value = request.form.get('csrf') or request.headers.get('X-CSRF-Token', '')
    return bool(value) and hmac.compare_digest(value, session.get('csrf', ''))


@app.after_request
def secure_headers(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
    return response


@app.get('/healthz')
def health():
    return jsonify(status='ok', browser='started on demand', transport='websocket-jpeg')


@app.route('/login', methods=['GET','POST'])
def login():
    error = ''
    if request.method == 'POST':
        if not valid_csrf():
            abort(400)
        ip = request.remote_addr or 'unknown'
        now = time.monotonic()
        with auth_lock:
            # Bound in-memory bookkeeping even when clients rotate addresses.
            if len(login_attempts) > 4096:
                login_attempts.clear()
            attempts = login_attempts[ip]
            while attempts and now - attempts[0] > 600:
                attempts.popleft()
            limited = len(attempts) >= 8
            if not limited:
                attempts.append(now)
        if limited:
            error = 'Too many attempts. Try again in 10 minutes.'
        elif hmac.compare_digest(request.form.get('password','').encode(), PASSWORD.encode()):
            session.clear()
            session.permanent = True
            token = secrets.token_urlsafe(32)
            session['auth'] = token
            with auth_lock:
                for old in list(auth_tokens):
                    if auth_tokens[old] < time.time():
                        del auth_tokens[old]
                if len(auth_tokens) >= 128:
                    auth_tokens.clear()
                auth_tokens[token] = time.time() + 43200
                attempts.clear()
            return redirect('/')
        else:
            error = 'Incorrect access password.'
    return render_template('login.html', csrf=csrf_token(), error=error)


@app.get('/')
def index():
    if not authorized():
        return redirect('/login')
    return render_template('index.html', csrf=csrf_token())


@app.post('/logout')
def logout():
    if not valid_csrf():
        abort(400)
    with auth_lock:
        auth_tokens.pop(session.get('auth'), None)
    session.clear()
    return redirect('/login')


@app.get('/api/apps')
def apps():
    if not authorized():
        abort(401)
    return jsonify(apps=APPS, fps=FPS, quality=QUALITY)


@app.get('/<name>')
def assets(name):
    if name not in {'style.css','client.js','icon.svg','manifest.webmanifest'}:
        abort(404)
    return send_from_directory(ROOT, name)


def navigation_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ValueError('Invalid URL')
    parts = urlsplit(value.strip())
    host = (parts.hostname or '').lower().rstrip('.')
    if parts.scheme != 'https' or parts.username or parts.password or parts.port not in (None,443):
        raise ValueError('Use an HTTPS URL on a supported social website.')
    if not any(host == d or host.endswith('.' + d) for d in NAV_DOMAINS):
        raise ValueError('This single-owner browser only allows supported social websites.')
    return value.strip()


class PublicNetwork:
    """Defense in depth, not a substitute for network-level egress rules."""
    def __init__(self):
        self.cache = {}

    def allowed(self, url):
        try:
            parsed = urlsplit(url)
            if parsed.scheme in ('data', 'blob', 'about'):
                return True
            if parsed.scheme not in ('https','http','wss','ws') or parsed.username or parsed.password:
                return False
            host = parsed.hostname
            if not host or parsed.port not in (None,80,443):
                return False
            cached = self.cache.get(host)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            addresses = {r[4][0] for r in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)}
            result = bool(addresses) and all(ipaddress.ip_address(ip).is_global for ip in addresses)
            self.cache[host] = (time.monotonic() + 30, result)
            return result
        except (ValueError, OSError):
            return False


@sock.route('/stream')
def stream(ws):
    origin = urlsplit(request.headers.get('Origin', ''))
    if not authorized() or origin.netloc != request.host or origin.scheme not in ('https','http'):
        ws.close(reason='Unauthorized origin or session')
        return
    if not active_lock.acquire(blocking=False):
        ws.send(json.dumps({'type':'error','message':'Your cloud browser is already open. Close its other tab first.'}))
        ws.close()
        return
    token = session.get('auth')
    commands = queue.Queue(maxsize=128)
    stop = threading.Event()
    ack = threading.Event()
    ack.set()
    reset_profile = False
    receiver = None

    def send(data):
        ws.send(json.dumps(data))

    def receive():
        while not stop.is_set():
            try:
                data = ws.receive(timeout=2)
                if data is None:
                    if not ws.connected:
                        break
                    continue
                if not isinstance(data, str) or len(data) > 16384:
                    continue
                msg = json.loads(data)
                if not isinstance(msg, dict):
                    continue
                if msg.get('type') == 'ack':
                    ack.set()
                else:
                    commands.put_nowait(msg)
            except queue.Full:
                continue
            except Exception:
                break
        stop.set()

    try:
        PROFILE.mkdir(parents=True, exist_ok=True, mode=0o700)
        send({'type':'status','message':'Starting your private cloud browser…'})
        receiver = threading.Thread(target=receive, daemon=True)
        receiver.start()
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(str(PROFILE), headless=True,
                chromium_sandbox=os.environ.get('CHROMIUM_SANDBOX','0') == '1',
                viewport={'width':1280,'height':800}, accept_downloads=False,
                service_workers='block', permissions=[],
                args=['--disable-dev-shm-usage','--disable-quic','--disable-background-networking',
                      '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', '--mute-audio'])
            context.set_default_timeout(5000)
            context.set_default_navigation_timeout(20000)
            network = PublicNetwork()

            def route_request(route):
                req = route.request
                try:
                    allowed = network.allowed(req.url)
                    if req.is_navigation_request() and req.frame.parent_frame is None:
                        navigation_url(req.url)
                    if allowed:
                        route.continue_()
                    else:
                        route.abort('blockedbyclient')
                except Exception:
                    route.abort('blockedbyclient')

            context.route('**/*', route_request)

            def route_websocket(route):
                if network.allowed(route.url):
                    route.connect_to_server()
                else:
                    route.close(code=1008, reason='Private network denied')

            context.route_web_socket('**/*', route_websocket)
            pages = [p for p in context.pages if not p.is_closed()]
            page = pages[0] if pages else context.new_page()
            for old in pages[1:]:
                old.close()
            page.goto('about:blank')
            last_input = time.monotonic()
            last_frame = 0
            pending_frame = 0
            last_meta = 0
            quality, fps = QUALITY, FPS
            frame_count, byte_count = 0, 0
            send({'type':'ready','width':1280,'height':800})
            while not stop.is_set():
                with auth_lock:
                    if auth_tokens.get(token, 0) <= time.time():
                        break
                if time.monotonic() - last_input > IDLE:
                    send({'type':'status','message':'Paused after inactivity. Reconnect to continue.'})
                    break
                if page.is_closed():
                    alive = [p for p in context.pages if not p.is_closed()]
                    page = alive[-1] if alive else context.new_page()
                # Popups are rendered in this same remote surface, not on the client.
                alive = [p for p in context.pages if not p.is_closed()]
                if alive and alive[-1] != page:
                    page = alive[-1]
                for _ in range(20):
                    try:
                        msg = commands.get_nowait()
                    except queue.Empty:
                        break
                    last_input = time.monotonic()
                    kind = msg.get('type')
                    try:
                        if kind == 'open':
                            target = APP_MAP.get(msg.get('app'), {}).get('url') or navigation_url(msg.get('url',''))
                            page.goto(target, wait_until='domcontentloaded')
                        elif kind == 'click':
                            size = page.viewport_size
                            x = max(0, min(size['width']-1, float(msg.get('x',0))))
                            y = max(0, min(size['height']-1, float(msg.get('y',0))))
                            page.mouse.click(x,y,click_count=2 if msg.get('double') else 1)
                        elif kind == 'scroll':
                            size = page.viewport_size
                            page.mouse.move(max(0,min(size['width']-1,float(msg.get('x',size['width']/2)))),max(0,min(size['height']-1,float(msg.get('y',size['height']/2)))))
                            page.mouse.wheel(max(-2000,min(2000,float(msg.get('dx',0)))), max(-2000,min(2000,float(msg.get('dy',0)))))
                        elif kind == 'text':
                            text = str(msg.get('text',''))[:8000]
                            page.keyboard.insert_text(text)
                        elif kind == 'key':
                            key = str(msg.get('key',''))
                            valid = {'Enter','Backspace','Delete','Tab','Shift+Tab','Escape','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space','Home','End','PageDown','PageUp','Control+a','Meta+a'}
                            if key in valid:
                                page.keyboard.press(key)
                        elif kind == 'back':
                            page.go_back(wait_until='domcontentloaded')
                        elif kind == 'forward':
                            page.go_forward(wait_until='domcontentloaded')
                        elif kind == 'reload':
                            page.reload(wait_until='domcontentloaded')
                        elif kind == 'viewport':
                            w = max(360,min(1920,int(msg.get('width',1280))))
                            h = max(600,min(1200,int(msg.get('height',800))))
                            page.set_viewport_size({'width':w,'height':h})
                            send({'type':'resize','width':w,'height':h})
                        elif kind == 'quality':
                            quality = max(20,min(85,int(msg.get('quality',QUALITY))))
                            fps = max(1,min(20,int(msg.get('fps',FPS))))
                        elif kind == 'reset':
                            reset_profile = True
                            send({'type':'status','message':'Clearing all cloud-browser site logins…'})
                            stop.set()
                    except Exception as exc:
                        # Never send raw exception strings: URLs can contain login tokens.
                        log.warning('Remote action failed: %s', type(exc).__name__)
                        send({'type':'notice','message':'Action timed out or was blocked. Try again; some websites restrict cloud browsers.'})
                now = time.monotonic()
                if now - last_frame >= 1/fps and (ack.is_set() or now - pending_frame > 4):
                    try:
                        image = page.screenshot(type='jpeg', quality=quality, timeout=6000)
                        ack.clear()
                        pending_frame = time.monotonic()
                        ws.send(image)
                        last_frame = time.monotonic()
                        frame_count += 1
                        byte_count += len(image)
                    except Exception:
                        page.wait_for_timeout(50)
                if now - last_meta > 2:
                    send({'type':'meta','url':page.url,'title':page.title()[:180], 'frames':frame_count,'bytes':byte_count})
                    last_meta = now
                page.wait_for_timeout(10)
            context.close()
    except Exception as exc:
        log.exception('Cloud browser stopped (%s)', type(exc).__name__)
        try:
            send({'type':'error','message':'Cloud browser stopped. Check server logs, available RAM and Chromium installation.'})
        except Exception:
            pass
    finally:
        stop.set()
        try:
            ws.close()
        except Exception:
            pass
        if receiver:
            receiver.join(timeout=3)
        if reset_profile:
            shutil.rmtree(PROFILE, ignore_errors=True)
        active_lock.release()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT','8080')), threaded=True, debug=False)
