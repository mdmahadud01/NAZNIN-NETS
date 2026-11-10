# Liquid Cloud — Flat Files Edition

A single-owner, password-protected Flask remote Chromium workspace. Includes a responsive liquid-glass home screen, illustrative social-app marks, native WebSocket JPEG streaming, keyboard/mouse/touch control, mobile viewport, presets, persistent website profile and clear-profile action. All source files are at ZIP root: no wrapper or nested folders.

## What runs where

The website runs inside Chromium ON YOUR SERVER. Its HTML, scripts and media are fetched by the server. This is not an iframe, reverse proxy, APK emulator, social API or a trick for using the internet without device data. Your device downloads the workspace and a sequence of JPEG screen images over WebSocket, and sends your input to the server. On fast-changing video, this can use MORE device data than directly watching a compressed video.

**VISUAL ONLY: NO REMOTE AUDIO.** Video is screen-captured at 5–20 FPS, not forwarded as a native compressed video stream. No smooth/HD playback guarantee. DRM, CAPTCHA, WebAuthn/passkeys, device-bound verification and automation restrictions may prevent playback or login. No file uploads/downloads, calls, microphone/camera forwarding, push notifications, drag-and-drop, clipboard reading or mobile IME forwarding. Use the Type / paste dialog for Bengali text or phone keyboards. Touch swipe scrolling is supported. Clicking a site's own fullscreen control only affects the remote viewport; the outer fullscreen button affects your device.

## Railway deployment from GitHub

1. Extract the ZIP. Upload ALL root files to the ROOT of a GitHub repository. Do not upload only the ZIP. Ensure Dockerfile, requirements.txt, app.py and start.sh are visible at the repository root. Dotfiles may be hidden by your file manager.
2. Railway → New Project → Deploy from GitHub repo → choose this repository. The included root Dockerfile installs Python, Playwright, Chromium and OS libraries. First build can take several minutes.
3. Set Railway Variables BEFORE starting: APP_PASSWORD (unique, at least 12 characters; recommend 20+), SECRET_KEY (random 64-character value), TRUST_PROXY=1, COOKIE_SECURE=1. Generate a secret with `python -c "import secrets; print(secrets.token_hex(32))"` on your own terminal. Never commit real secrets.
4. Generate a public domain in Railway networking. Open its HTTPS address and unlock the workspace. PORT is supplied by the host; the service binds to 0.0.0.0. Do not change to multiple replicas/workers.
5. Click an app. Chromium starts on demand. Website credentials are entered INSIDE the remote website, not into the Liquid access form. Telegram/WhatsApp QR or OTP flows depend on each platform.
6. Optional persistent profile: attach a volume, set PROFILE_DIR to a directory on it, and ensure UID 10001 can create/write that directory. Without a volume, profiles can disappear on rebuild/redeploy. With a volume they survive only while the volume remains intact. Never put cookies in GitHub.

There is no safe zero-configuration public deployment: you must set an access password. Browser dependencies are installed automatically by Docker, not manually on Railway. Use exactly one Gunicorn worker and one Railway replica. At most one cloud-browser connection is allowed, including connections on different devices. Return Home leaves the browser connected; use the X button to stop it before opening another tab. This is deliberately NOT a multi-user service: all password holders access the SAME website profile.

## VPS / Linux terminal

Docker is recommended (Linux container host):

```sh
docker build -t liquid-cloud .
docker volume create liquid-profile
# First ensure the mounted profile is writable by UID 10001:
docker run --rm --user root -v liquid-profile:/data --entrypoint sh liquid-cloud -c 'chown 10001:10001 /data'
docker run --rm --init --shm-size=1g -p 127.0.0.1:8080:8080 \
  -e APP_PASSWORD='YOUR_UNIQUE_LONG_PASSWORD' \
  -e SECRET_KEY='YOUR_RANDOM_SECRET' \
  -e PROFILE_DIR=/data/profile \
  -v liquid-profile:/data liquid-cloud
```

For local use open http://localhost:8080. For public VPS hosting put an HTTPS reverse proxy in front, support WebSocket Upgrade, set an adequate proxy read timeout, and add `-e TRUST_PROXY=1 -e COOKIE_SECURE=1`. Only enable TRUST_PROXY behind a trusted proxy; prevent clients from accessing the upstream directly. Never send social passwords over plain HTTP. Prefer an SSH tunnel or private VPN if this is for personal use.

Without Docker, use a supported Linux Python 3.10+ environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m playwright install --with-deps chromium
export APP_PASSWORD='YOUR_UNIQUE_LONG_PASSWORD'
export SECRET_KEY='YOUR_RANDOM_SECRET'
sh start.sh
```

Installing browser OS packages may require root/sudo. Standard Android Termux is NOT a supported Playwright Chromium host: use a VPS/Ubuntu environment rather than expecting bare Android to run this container. `python app.py` is for local development only. `.env.example` documents variables; simply creating a .env file does not load them.

## Security / hosting boundaries — read before publishing

- Use a dedicated, disposable VM/container, HTTPS and private access. This is a PERSONAL PROTOTYPE, not a hardened public remote-browser platform. Anyone with the access password can see/use saved website logins. The server owner/provider can access browser data. Do not use important accounts on an untrusted host. No credentials or screen frames are deliberately recorded by this app; the browser itself saves site data in PROFILE_DIR.
- By default CHROMIUM_SANDBOX=0 improves compatibility with constrained PaaS containers but disables Chromium's sandbox. Non-root Docker alone is NOT an equivalent sandbox. If your host supports namespaces/seccomp, set CHROMIUM_SANDBOX=1 and verify launch. Never weaken your main host's security to make it work. Follow Playwright's sandbox guidance and isolate the deployment from other secrets/services.
- Supported social domains are allowlisted for main-frame navigation. HTTP(S)/WebSocket requests resolving to non-public addresses are blocked at application level. Service workers are blocked, WebRTC non-proxied UDP is disabled, and downloads are disabled. These checks are defense in depth, NOT a complete SSRF/network isolation solution (DNS rebinding and browser background network behavior require network-level enforcement). Firewall all private, loopback, link-local, metadata and internal service destinations for the browser's network, apart from necessary isolated DNS. Do not run near internal services, credentials or a Docker socket.
- Browser automation is detectable. The code does not evade CAPTCHA, geographic restrictions, login protection or service terms. Websites may change. Test the sites you need before committing to paid hosting.
- Login has in-process IP rate limiting, CSRF protection and an HttpOnly/SameSite session cookie. Secrets rotate/in-memory sessions vanish on restart; log in again. The access password is loaded from an environment variable. Auth state is not a distributed database; hence one worker/replica only.
- Erase cloud website logins removes PROFILE_DIR after closing Chromium. Disconnect normally retains the profile. Profile erase does not delete third-party server-side account data.
- Icons are text/symbol approximations, not official logo image assets. No affiliation with social platforms. No external UI fonts, JavaScript CDN or image CDN is required.
- PWA manifest offers standalone display where supported, not an offline app or guaranteed install prompt. Offline use cannot load remote websites. Home navigation keeps a stream connected until you disconnect; idle shutdown defaults to 15 minutes after the last input.

## Resource and bandwidth planning

Start testing with approximately 2 GB RAM and a CPU core for a single browser; this is a practical estimate, not a measured minimum. Video-heavy pages may need more. Browser installation creates a relatively large image. Hosting plans may charge for CPU/RAM and egress. No free-hosting or unlimited-data promise is made.

FPS is capped at 20; maximum JPEG quality is 85. One frame is in flight until the client acknowledges decode (a 4-second recovery timeout prevents a permanent stall). Stream resolution defaults to 1280×800, or 430×880 in phone mode. Website player quality is still chosen inside the website; the stream preset only changes screenshot quality/rate. Example only: 60 KB/frame × 10 FPS is about 600 KB/s or 36 MB/min before overhead. Real usage depends on the screen; the UI counter measures received JPEG bytes, not all network traffic.

## Files

app.py; index.html; login.html; style.css; client.js; icon.svg; manifest.webmanifest; requirements.txt; Dockerfile; start.sh; railway.toml; Procfile; .env.example; .dockerignore; .gitignore; test_app.py; README.md; TEST_REPORT.txt.

## Checks

`APP_PASSWORD='test-password-12345' python -m unittest -v test_app`

The included tests cover access control, CSRF, auth revocation, supported navigation and blocked local URLs. TEST_REPORT.txt records what was actually executed during packaging. They do not promise successful login to YouTube, TikTok, Telegram, Facebook or Instagram. Third-party service accounts are not included.

## References

https://playwright.dev/python/docs/docker
https://playwright.dev/python/docs/browsers
https://docs.railway.com/guides/dockerfiles

This software is provided as-is. Use only for lawful personal browsing consistent with each website's terms.
