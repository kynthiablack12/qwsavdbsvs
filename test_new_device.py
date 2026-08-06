import sys, json, requests, uuid
sys.stdout.reconfigure(encoding='utf-8')
acc = json.load(open(r'D:\gfe\accounts.json', encoding='utf-8'))['accounts'][0]
new_dev = {'x-app-version':'8.114.0','x-platform-version':'28','x-device-platform':'Android','User-Agent':'okhttp/5.1.0',
           'x-device-id':str(uuid.uuid4()),'x-device-tag':f'{uuid.uuid4().hex[:36].upper()}_L!{uuid.uuid4().hex[:36].upper()}'}
s = requests.Session(); s.cookies.clear()
r = s.post('https://id.magnit.ru/v1/auth/token/refresh',
           headers={**new_dev,'Content-Type':'application/json; charset=UTF-8'},
           data=json.dumps({'aud':'loyalty-mobile','refreshToken':acc['refresh_token']}), timeout=20)
at = r.json()['accessToken']
ev = acc['event_id']
r2 = s.get('https://middle-api.magnit.ru/v1/promo-games/' + ev + '/mobile',
           headers={**new_dev,'Authorization':'bearer '+at}, timeout=20)
print('game token with new device:', r2.status_code)
print(r2.text[:150])
