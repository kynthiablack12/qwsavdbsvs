import requests, sys
sys.stdout.reconfigure(encoding='utf-8')

h = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'Content-Type': 'application/json; charset=UTF-8',
    'User-Agent': 'okhttp/5.1.0',
}
body = '{"aud":"loyalty-mobile","refreshToken":"3343705e-41cb-4df3-997b-81a5c4c3ce1f"}'

# without any auth header
r = requests.post('https://id.magnit.ru/v1/auth/token/refresh', headers=h, data=body, timeout=15)
print('no-auth-header:', r.status_code, r.text[:300])
