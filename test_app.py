"""Offline unit checks; run with python -m unittest -v test_app."""
import os
os.environ.setdefault('APP_PASSWORD', 'test-password-12345')
import unittest
from unittest.mock import patch
from app import app, auth_tokens, login_attempts, navigation_url, PublicNetwork

class AppTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SESSION_COOKIE_SECURE'] = False
        self.client = app.test_client()
        auth_tokens.clear()
        login_attempts.clear()

    def csrf(self):
        self.client.get('/login')
        with self.client.session_transaction() as s:
            return s['csrf']

    def unlock(self):
        return self.client.post('/login', data={'csrf':self.csrf(), 'password':os.environ['APP_PASSWORD']})

    def test_health(self):
        self.assertEqual(self.client.get('/healthz').json['status'], 'ok')

    def test_private_home(self):
        self.assertEqual(self.client.get('/').status_code, 302)
        self.assertEqual(self.client.get('/api/apps').status_code, 401)

    def test_csrf_required(self):
        self.assertEqual(self.client.post('/login', data={'password':os.environ['APP_PASSWORD']}).status_code, 400)

    def test_login_and_assets(self):
        self.assertEqual(self.unlock().status_code, 302)
        response = self.client.get('/')
        self.assertIn(b'Your world,', response.data)
        self.assertEqual(len(self.client.get('/api/apps').json['apps']), 8)
        for name in ['style.css','client.js','icon.svg','manifest.webmanifest']:
            with self.client.get('/'+name) as asset:
                self.assertEqual(asset.status_code, 200)
        self.assertEqual(self.client.get('/app.py').status_code, 404)
        self.assertIn('nosniff',response.headers['X-Content-Type-Options'])

    def test_bad_password(self):
        r = self.client.post('/login', data={'csrf':self.csrf(), 'password':'not-the-password'})
        self.assertIn(b'Incorrect', r.data)
        self.assertEqual(self.client.get('/api/apps').status_code, 401)

    def test_rate_limit(self):
        token = self.csrf()
        for _ in range(9):
            r = self.client.post('/login', data={'csrf':token,'password':'wrong'})
        self.assertIn(b'Too many attempts',r.data)

    def test_logout_revokes_token(self):
        self.unlock()
        with self.client.session_transaction() as s:
            token = s['auth']
        self.assertIn(token,auth_tokens)
        self.assertEqual(self.client.post('/logout',data={'csrf':self.csrf()}).status_code,302)
        self.assertNotIn(token,auth_tokens)
        self.assertEqual(self.client.get('/api/apps').status_code,401)

    def test_logout_csrf(self):
        self.unlock()
        self.assertEqual(self.client.post('/logout').status_code,400)

    def test_navigation_allowlist(self):
        for url in ['https://www.youtube.com/shorts','https://web.telegram.org/','https://accounts.google.com/']:
            self.assertEqual(navigation_url(url),url)
        for url in ['http://youtube.com/','https://127.0.0.1/','https://youtube.com.evil.test/', 'file:///etc/passwd','javascript:alert(1)','https://user:secret@youtube.com/','https://youtube.com:999/']:
            with self.assertRaises(ValueError, msg=url):
                navigation_url(url)

    def test_private_networks_denied(self):
        network = PublicNetwork()
        for url in ['http://127.0.0.1/','http://169.254.169.254/latest/meta-data/','http://[::1]/','http://10.1.1.1/','ftp://youtube.com/']:
            self.assertFalse(network.allowed(url),url)
        with patch('app.socket.getaddrinfo', return_value=[(2,1,6,'',('192.168.1.3',443))]):
            self.assertFalse(network.allowed('https://looks-public.test/'))
        with patch('app.socket.getaddrinfo', return_value=[(2,1,6,'',('8.8.8.8',443))]):
            self.assertTrue(network.allowed('https://public-test.test/'))

if __name__ == '__main__':
    unittest.main()
