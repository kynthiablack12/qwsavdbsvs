import requests, sys, json, os, re, uuid
sys.stdout.reconfigure(encoding='utf-8')

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.json')

DEV_BASE = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; SM-S906N Build/PQ3A.190605.09261140)',
    'Content-Type': 'application/json; charset=UTF-8',
}


def make_device_headers():
    did = str(uuid.uuid4())
    tag = f'{uuid.uuid4().hex[:36].upper()}_L!{uuid.uuid4().hex[:36].upper()}'
    return {**DEV_BASE, 'x-device-id': did, 'x-device-tag': tag, 'x-device-id': did, 'x-device-tag': tag}

s = requests.Session()


def norm_phone(p):
    p = re.sub(r'\D', '', p)
    if p.startswith('8'):
        p = '7' + p[1:]
    elif not p.startswith('7'):
        p = '7' + p
    return p


def main():
    phone = norm_phone(input('Номер телефона (например 79123456789): ').strip())
    name = input('Имя аккаунта (label, например vasya): ').strip()
    DEV_H = make_device_headers()
    print('device_id:', DEV_H['x-device-id'])
    print('device_tag:', DEV_H['x-device-tag'])

    r = s.post('https://id.magnit.ru/v1/auth/otp', headers=DEV_H,
               data=json.dumps({"aud": "loyalty-mobile", "phone": phone,
                                "captcha-token": "captcha-token", "forceSMS": True}), timeout=15)
    print('OTP:', r.status_code, r.text[:200])
    r.raise_for_status()
    attempt_id = r.json()['attemptId']

    code = input('Код из SMS: ').strip()
    r = s.post('https://id.magnit.ru/v1/auth/otp/check', headers=DEV_H,
               data=json.dumps({"attemptId": attempt_id, "aud": "loyalty-mobile",
                                "code": code, "phone": phone}), timeout=15)
    print('CHECK:', r.status_code, r.text[:300])
    r.raise_for_status()
    ch = r.json()
    magnit_id = ch['magnitIDCode']
    user_id = ch.get('userId')
    print('  magnitIDCode:', magnit_id, '| userId:', user_id, '| isRegistered:', ch.get('isRegistered'))

    if not ch.get('isRegistered'):
        fname = input('Имя пользователя (для регистрации): ').strip() or 'Пользователь'
        bdate = input('Дата рождения (ГГГГ-ММ-ДД): ').strip() or '2000-01-01'
        r = s.post('https://id.magnit.ru/v1/profile/register/magnit-id-code', headers=DEV_H,
                   data=json.dumps({"magnitIDCode": magnit_id, "birthDate": bdate,
                                    "firstName": fname}), timeout=15)
        print('REGISTER:', r.status_code, r.text[:300])
        r.raise_for_status()

    r = s.post('https://id.magnit.ru/v1/auth/token', headers=DEV_H,
               data=json.dumps({"aud": "loyalty-mobile", "magnitIdCode": magnit_id}), timeout=15)
    print('TOKEN:', r.status_code, r.text[:200])
    r.raise_for_status()
    tokens = r.json()
    refresh_token = tokens['refreshToken']
    print('  refreshToken:', refresh_token)

    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    if any(a.get('name') == name for a in cfg['accounts']):
        print(f'аккаунт "{name}" уже есть, пропускаю')
        return
    cfg['accounts'].append({
        "name": name,
        "refresh_token": refresh_token,
        "device_id": DEV_H['x-device-id'],
        "device_tag": DEV_H['x-device-tag'],
        "event_id": "wX8CoYBu0OQzsA6DBwqlU",
    })
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    print(f'аккаунт "{name}" добавлен в accounts.json')


if __name__ == '__main__':
    main()
