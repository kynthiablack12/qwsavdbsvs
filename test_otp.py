import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DEV_H = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'okhttp/5.1.0',
    'Content-Type': 'application/json; charset=UTF-8',
}

# телефон из перехвата + фейковый для проверки валидации
for phone in ['79232017097', '79990000000']:
    r = requests.post('https://id.magnit.ru/v1/auth/otp', headers=DEV_H,
                      data=json.dumps({'phone': phone}), timeout=15)
    print(phone, '->', r.status_code, r.text[:300])
