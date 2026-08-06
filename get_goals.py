import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

REFRESH_TOKEN = '3343705e-41cb-4df3-997b-81a5c4c3ce1f'
DEV_H = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'okhttp/5.1.0',
}

r = requests.post('https://id.magnit.ru/v1/auth/token/refresh',
                  headers={**DEV_H, 'Content-Type': 'application/json; charset=UTF-8'},
                  data=json.dumps({'aud': 'loyalty-mobile', 'refreshToken': REFRESH_TOKEN}), timeout=15)
at = r.json()['accessToken']
AUTH = {**DEV_H, 'Authorization': 'bearer ' + at}

g = requests.get('https://middle-api.magnit.ru/v1/goals/main', headers=AUTH, timeout=15)
j = g.json()
open(r'D:\gfe\goals_main.json', 'w', encoding='utf-8').write(json.dumps(j, ensure_ascii=False, indent=1))
print('saved. top keys:', list(j.keys()))
for sec in ('unseen', 'seen'):
    u = j.get(sec, {})
    gl = u.get('goals')
    if isinstance(gl, dict):
        print(sec, 'count:', gl.get('count'))
        for gg in gl.get('list', []):
            print('---', sec, 'goal', gg.get('id'), '| bonus', gg.get('crmBonusCount'), '| date', gg.get('dateStart'), '->', gg.get('dateEnd'))
            print('    keys:', list(gg.keys()))
