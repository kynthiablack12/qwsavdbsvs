import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DEV_H = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; SM-S906N Build/PQ3A.190605.09261140)',
    'Content-Type': 'application/json; charset=UTF-8',
    'X-Analytics-Session-Id': '759a32eb-845d-446d-a1f7-9c6b6b12f7bd',
    'X-Apps-Flyer-Id': '1785996392858-4192453017068239882',
    'X-Telemetry-Version': '1',
}

body = {"aud": "loyalty-mobile", "phone": "79990000000",
        "captcha-token": "captcha-token", "forceSMS": True}

# Вариант 1: garbage подпись и telemetry
h1 = {**DEV_H, 'X-Telemetry': 'garbage', 'x-request-sign': 'garbage'}
r1 = requests.post('https://id.magnit.ru/v1/auth/otp', headers=h1, data=json.dumps(body), timeout=15)
print('garbage sign:', r1.status_code, r1.text[:200])

# Вариант 2: вообще без подписи и telemetry
h2 = dict(DEV_H)
del h2['X-Analytics-Session-Id']
r2 = requests.post('https://id.magnit.ru/v1/auth/otp', headers=h2, data=json.dumps(body), timeout=15)
print('no sign/tel:', r2.status_code, r2.text[:200])
