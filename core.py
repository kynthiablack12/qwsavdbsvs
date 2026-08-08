import requests, sys, json, os, re, uuid, hashlib, threading, time, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

# Railway: данные в PostgreSQL (DATABASE_URL) + файлы в каталоге DATA_DIR (Volume).
# Локально: DATABASE_URL нет -> SQLite, DATA_DIR не задан -> папка проекта.
DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
USE_PG = bool(DATABASE_URL)
if USE_PG:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        raise RuntimeError('DATABASE_URL задан, но пакет psycopg не установлен (pip install "psycopg[binary]")')

DATA_DIR = (os.environ.get('DATA_DIR') or os.path.dirname(os.path.abspath(__file__))).strip()
os.makedirs(DATA_DIR, exist_ok=True)

CONFIG = os.path.join(DATA_DIR, 'accounts.json')
DB = os.path.join(DATA_DIR, 'prizes.db')

DEV_BASE = {
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'okhttp/5.1.0',
}

s = requests.Session()
# id.magnit.ru валидирует устройство по cookies: любой сохранённый Set-Cookie
# от других запросов (refresh, купоны и т.п.) ломает OTP -> untrustedDevice.
otp_s = requests.Session()
otp_s.cookies.clear()


# ---------- prizes database (SQLite locally, PostgreSQL on Railway) ----------

def _ex(conn, sql, params=()):
    """Выполнить запрос, вернуть курсор. Строки — dict в обоих бэкендах."""
    if USE_PG:
        cur = conn.cursor(row_factory=dict_row)
        cur.execute(sql, params)
        return cur
    return conn.execute(sql.replace('%s', '?'), params)


def _db():
    if USE_PG:
        return psycopg.connect(DATABASE_URL)
    conn = sqlite3.connect(DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _db()
    try:
        if USE_PG:
            _ex(conn, '''
                CREATE TABLE IF NOT EXISTS prizes (
                    id SERIAL PRIMARY KEY,
                    account TEXT, game_id TEXT, level INTEGER, reward_id INTEGER,
                    name TEXT, expiration_date TEXT,
                    is_barcode INTEGER DEFAULT 0, is_button INTEGER DEFAULT 0,
                    items TEXT, icon_ref TEXT, obtained_at TEXT,
                    barcode TEXT, coupon_id TEXT, display_type TEXT
                )
            ''')
        else:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS prizes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account TEXT, game_id TEXT, level INTEGER, reward_id INTEGER,
                    name TEXT, expiration_date TEXT,
                    is_barcode INTEGER DEFAULT 0, is_button INTEGER DEFAULT 0,
                    items TEXT, icon_ref TEXT, obtained_at TEXT,
                    barcode TEXT, coupon_id TEXT, display_type TEXT
                )
            ''')
            cols = {r[1] for r in conn.execute('PRAGMA table_info(prizes)').fetchall()}
            for c, decl in [('barcode', 'TEXT'), ('coupon_id', 'TEXT'), ('display_type', 'TEXT')]:
                if c not in cols:
                    conn.execute(f'ALTER TABLE prizes ADD COLUMN {c} {decl}')
        conn.commit()
    finally:
        conn.close()


def save_prize(account, game_id, level, prize, barcode=None, coupon_id=None, display_type=None):
    conn = _db()
    try:
        _ex(conn, '''
            INSERT INTO prizes (account, game_id, level, reward_id, name, expiration_date,
                                is_barcode, is_button, items, icon_ref, obtained_at,
                                barcode, coupon_id, display_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ''', (
            account, game_id, level, prize.get('id'),
            (prize.get('info') or {}).get('name', ''),
            prize.get('expiration_date', ''),
            1 if prize.get('is_barcode') else 0,
            1 if prize.get('is_button') else 0,
            json.dumps(prize.get('items', []), ensure_ascii=False),
            (prize.get('info') or {}).get('icon_ref', ''),
            time.strftime('%Y-%m-%d %H:%M:%S'),
            barcode, coupon_id, display_type,
        ))
        conn.commit()
    finally:
        conn.close()


def list_prizes(account=None, limit=200):
    conn = _db()
    try:
        if account:
            cur = _ex(conn, 'SELECT * FROM prizes WHERE account=%s ORDER BY id DESC LIMIT %s', (account, limit))
        else:
            cur = _ex(conn, 'SELECT * FROM prizes ORDER BY id DESC LIMIT %s', (limit,))
        rows = cur.fetchall()
    finally:
        conn.close()
    return [dict(r) for r in rows]


def prize_stats(account=None):
    conn = _db()
    try:
        if account:
            cur = _ex(conn, 'SELECT COUNT(*) c, COUNT(DISTINCT game_id) g FROM prizes WHERE account=%s', (account,))
        else:
            cur = _ex(conn, 'SELECT COUNT(*) c, COUNT(DISTINCT game_id) g FROM prizes')
        row = cur.fetchone()
    finally:
        conn.close()
    return {'count': row['c'], 'games': row['g']}


init_db()


# ---------- accounts ----------

def load_accounts():
    try:
        with open(CONFIG, encoding='utf-8') as f:
            return json.load(f)['accounts']
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def save_accounts(accs):
    with open(CONFIG, 'w', encoding='utf-8') as f:
        json.dump({'accounts': accs}, f, ensure_ascii=False, indent=2)


# Разовая загрузка аккаунтов из env ACCOUNTS_JSON (Railway), если файла ещё нет.
# Удобно вместо ручного наполнения Volume. Значение — JSON-массив аккаунтов
# или объект {"accounts": [...]}.
if not os.path.exists(CONFIG):
    _seed = os.environ.get('ACCOUNTS_JSON', '').strip()
    if _seed:
        try:
            _data = json.loads(_seed)
            save_accounts(_data['accounts'] if isinstance(_data, dict) else _data)
            print(f'[core] ACCOUNTS_JSON применён -> создан {CONFIG}')
        except Exception as e:
            print(f'[core] ACCOUNTS_JSON не применён: {e}')


def make_device_headers():
    did = str(uuid.uuid4())
    tag = f'{uuid.uuid4().hex[:36].upper()}_L!{uuid.uuid4().hex[:36].upper()}'
    return {**DEV_BASE, 'x-device-id': did, 'x-device-tag': tag}


def dev_headers(acc):
    return {**DEV_BASE, 'x-device-id': acc['device_id'], 'x-device-tag': acc['device_tag']}


def norm_phone(p):
    p = re.sub(r'\D', '', p)
    if p.startswith('8'):
        p = '7' + p[1:]
    elif not p.startswith('7'):
        p = '7' + p
    return p


# ---------- magnit auth ----------

def refresh_magnit_token(acc):
    r = s.post('https://id.magnit.ru/v1/auth/token/refresh',
               headers={**dev_headers(acc), 'Content-Type': 'application/json; charset=UTF-8'},
               data=json.dumps({'aud': 'loyalty-mobile', 'refreshToken': acc['refresh_token']}), timeout=20)
    r.raise_for_status()
    j = r.json()
    new_rt = j.get('refreshToken')
    if new_rt and new_rt != acc.get('refresh_token'):
        acc['refresh_token'] = new_rt
        accs = load_accounts()
        for a in accs:
            if a.get('name') == acc.get('name'):
                a['refresh_token'] = new_rt
        save_accounts(accs)
        print(f'[{acc.get("name")}] refreshToken rotated, saved')
    return j['accessToken']


def request_otp(phone, device):
    otp_s.cookies.clear()
    r = otp_s.post('https://id.magnit.ru/v1/auth/otp',
                   headers={**device, 'Content-Type': 'application/json; charset=UTF-8'},
                   data=json.dumps({"aud": "loyalty-mobile", "phone": phone,
                                    "captcha-token": "captcha-token", "forceSMS": True}), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f'OTP {r.status_code}: {r.text[:200]}')
    return r.json()['attemptId']


def check_otp(phone, attempt_id, code, device):
    otp_s.cookies.clear()
    r = otp_s.post('https://id.magnit.ru/v1/auth/otp/check',
                   headers={**device, 'Content-Type': 'application/json; charset=UTF-8'},
                   data=json.dumps({"attemptId": attempt_id, "aud": "loyalty-mobile",
                                    "code": code, "phone": phone}), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f'CHECK {r.status_code}: {r.text[:200]}')
    return r.json()


def register_profile(device, magnit_id, first_name, birth_date):
    r = otp_s.post('https://id.magnit.ru/v1/profile/register/magnit-id-code',
                   headers={**device, 'Content-Type': 'application/json; charset=UTF-8'},
                   data=json.dumps({"magnitIDCode": magnit_id, "birthDate": birth_date,
                                    "firstName": first_name}), timeout=20)
    r.raise_for_status()


def get_tokens(device, magnit_id):
    r = otp_s.post('https://id.magnit.ru/v1/auth/token',
                   headers={**device, 'Content-Type': 'application/json; charset=UTF-8'},
                   data=json.dumps({"aud": "loyalty-mobile", "magnitIdCode": magnit_id}), timeout=20)
    r.raise_for_status()
    return r.json()


def add_account(phone, name=None, first_name=None, birth_date=None, event_id='wX8CoYBu0OQzsA6DBwqlU'):
    device = make_device_headers()
    attempt_id = request_otp(phone, device)
    if not name:
        name = 'acc_' + phone[-7:]
    return {'device': device, 'attempt_id': attempt_id, 'phone': phone, 'name': name,
            'first_name': first_name or 'Пользователь', 'birth_date': birth_date or '2000-01-01',
            'event_id': event_id}


def add_account_by_token(name, refresh_token, event_id='wX8CoYBu0OQzsA6DBwqlU'):
    """Добавить существующий аккаунт по refresh-токену (OTP для зарегистрированных
    номеров блокируется сервером untrustedDevice, поэтому только токен)."""
    name = name.strip()
    if not name:
        raise RuntimeError('имя аккаунта обязательно')
    accs = load_accounts()
    if any(a.get('name') == name for a in accs):
        raise RuntimeError(f'аккаунт "{name}" уже существует')
    device = make_device_headers()
    r = s.post('https://id.magnit.ru/v1/auth/token/refresh',
               headers={**device, 'Content-Type': 'application/json; charset=UTF-8'},
               data=json.dumps({'aud': 'loyalty-mobile', 'refreshToken': refresh_token.strip()}), timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f'невалидный refresh-токен ({r.status_code}): {r.text[:120]}')
    accs.append({
        "name": name,
        "refresh_token": refresh_token.strip(),
        "device_id": device['x-device-id'],
        "device_tag": device['x-device-tag'],
        "event_id": event_id,
    })
    save_accounts(accs)
    return accs


# pending registrations in memory (keyed by name)
PENDING = {}


def store_pending(reg):
    PENDING[reg['name']] = reg
    PENDING[reg['phone']] = reg


def get_pending(name):
    return PENDING.get(name)


def confirm_account(reg, code):
    phone, device = reg['phone'], reg['device']
    ch = check_otp(phone, reg['attempt_id'], code, device)
    magnit_id = ch['magnitIDCode']
    if not ch.get('isRegistered'):
        register_profile(device, magnit_id, reg['first_name'], reg['birth_date'])
    tokens = get_tokens(device, magnit_id)
    accs = load_accounts()
    if any(a.get('name') == reg['name'] for a in accs):
        raise RuntimeError(f'аккаунт "{reg["name"]}" уже существует')
    accs.append({
        "name": reg['name'],
        "refresh_token": tokens['refreshToken'],
        "device_id": device['x-device-id'],
        "device_tag": device['x-device-tag'],
        "event_id": reg.get('event_id') or 'wX8CoYBu0OQzsA6DBwqlU',
    })
    save_accounts(accs)
    return accs


# ---------- access sessions ----------

SESSIONS_FILE = os.path.join(DATA_DIR, 'sessions.json')


def load_sessions():
    try:
        with open(SESSIONS_FILE, encoding='utf-8') as f:
            return json.load(f).get('sessions', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_sessions(sess):
    with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'sessions': sess}, f, ensure_ascii=False, indent=2)


def create_session(name, account, hours=24):
    """Сессия доступа для стороннего человека: привязана к одному аккаунту,
    даёт доступ только к pickup-эндпоинтам. Возвращает токен-ключ."""
    name = (name or '').strip()
    account = (account or '').strip()
    if not name or not account:
        raise RuntimeError('name and account required')
    if not any(a.get('name') == account for a in load_accounts()):
        raise RuntimeError(f'аккаунт "{account}" не найден')
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    sess = load_sessions()
    sess[token] = {
        'name': name,
        'account': account,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + hours * 3600)),
        'last_seen': None,
        'active': True,
    }
    save_sessions(sess)
    return token


def get_session(token):
    if not token:
        return None
    s = load_sessions().get(token)
    if not s or not s.get('active'):
        return None
    if s.get('expires_at') and s['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        return None
    return s


def touch_session(token):
    sess = load_sessions()
    if token in sess:
        sess[token]['last_seen'] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_sessions(sess)


def revoke_session(token):
    sess = load_sessions()
    if token in sess:
        sess[token]['active'] = False
        save_sessions(sess)
        return True
    return False


# ---------- coupon share links ----------

COUPON_SHARES_FILE = os.path.join(DATA_DIR, 'coupon_shares.json')


def load_coupon_shares():
    try:
        with open(COUPON_SHARES_FILE, encoding='utf-8') as f:
            return json.load(f).get('shares', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_coupon_shares(shares):
    with open(COUPON_SHARES_FILE, 'w', encoding='utf-8') as f:
        json.dump({'shares': shares}, f, ensure_ascii=False, indent=2)


def create_coupon_share(account, coupon_id, hours=24, name=''):
    """Отдельная ссылка на купон аккаунта, действующая заданное число часов."""
    account = (account or '').strip()
    coupon_id = (coupon_id or '').strip()
    if not account or not coupon_id:
        raise RuntimeError('account и coupon_id обязательны')
    if not any(a.get('name') == account for a in load_accounts()):
        raise RuntimeError(f'аккаунт "{account}" не найден')
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    shares = load_coupon_shares()
    shares[token] = {
        'name': (name or '').strip(),
        'account': account,
        'coupon_id': coupon_id,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + int(hours) * 3600)),
        'active': True,
    }
    save_coupon_shares(shares)
    return token


def get_coupon_share(token):
    if not token:
        return None
    s = load_coupon_shares().get(token)
    if not s or not s.get('active'):
        return None
    if s.get('expires_at') and s['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        return None
    return s


def list_coupon_shares():
    return load_coupon_shares()


def revoke_coupon_share(token):
    shares = load_coupon_shares()
    if token in shares:
        shares[token]['active'] = False
        save_coupon_shares(shares)
        return True
    return False


# ---------- games ----------

# Игры Магнита: event_id -> домен игры
GAMES = {
    'wX8CoYBu0OQzsA6DBwqlU': 'magnit-prizoleto.ru',                      # Призолето
    'At99RuZXsCpnFRhpmEZCK': 'magnit-monstroplanetyane.ru-prod2.kts.studio',  # Монстро-планетяне
}
GAME_EVENTS = {
    'Призолето': 'wX8CoYBu0OQzsA6DBwqlU',
    'Монстро-планетяне': 'At99RuZXsCpnFRhpmEZCK',
}

def game_domain(acc):
    return GAMES.get(acc.get('event_id'), 'magnit-prizoleto.ru')


def get_game_token(acc, magnit_token, event_id=None):
    event_id = event_id or acc['event_id']
    r = s.get(f'https://middle-api.magnit.ru/v1/promo-games/{event_id}/mobile',
              headers={**dev_headers(acc), 'Authorization': 'bearer ' + magnit_token}, timeout=20)
    r.raise_for_status()
    return r.json()['url'].split('token=')[1]


def login_game(rs256_token):
    r = s.post('https://magnit-prizoleto.ru/api/v1/auth/login',
               headers={'Content-Type': 'application/json', 'User-Agent': 'okhttp/5.1.0'},
               data=json.dumps({'token': rs256_token}), timeout=20)
    r.raise_for_status()
    return r.json()


def game_headers(hs256_token, external_id):
    return {
        'Authorization': 'Bearer ' + hs256_token,
        'Cookie': f'External={external_id}; token_{external_id}={hs256_token}',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
    }


def start_game(h, level=1):
    r = s.post('https://magnit-prizoleto.ru/api/v1/game', headers=h,
               data=json.dumps({'level': level}), timeout=20)
    r.raise_for_status()
    return r.json()


def finish_game(h, game_id, turns=1, victory=True, duration='00:00:05'):
    body = {"duration": duration, "turns_count": turns,
            "lines_used": 0, "multipliers_used": 0, "blasts_used": 0,
            "is_victory": victory, "lose_reason": 1}
    r = s.put(f'https://magnit-prizoleto.ru/api/v1/game/{game_id}:finish',
              headers={**h, 'Content-Type': 'application/json'},
              data=json.dumps(body), timeout=20)
    r.raise_for_status()
    return r.json()


def pick_reward(h, reward_id):
    r = s.put(f'https://magnit-prizoleto.ru/api/v1/game/rewards/{reward_id}:choice',
              headers=h, data='', timeout=20)
    return r.status_code


def get_tasks_prizoleto(h):
    """POST /api/v1/tasks — список задач (ежедневный бонус и пр.)."""
    r = s.post('https://magnit-prizoleto.ru/api/v1/tasks', headers=h, data='', timeout=20)
    r.raise_for_status()
    return r.json().get('tasks', [])


def activate_task_prizoleto(h, task_id):
    """PUT /api/v1/tasks/{id}:activate — забрать награду за задачу."""
    h2 = dict(h)
    h2['Idempotency-Key'] = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    r = s.put(f'https://magnit-prizoleto.ru/api/v1/tasks/{task_id}:activate',
              headers=h2, data='', timeout=20)
    r.raise_for_status()
    return r.json()


def claim_prizoleto_daily(h, log=print):
    """Забрать все готовые задачи Призолето (в т.ч. ежедневный бонус за вход)."""
    total = 0
    tasks = get_tasks_prizoleto(h)
    for t in tasks:
        if not t.get('ready_for_activation'):
            continue
        tid = t.get('id')
        try:
            res = activate_task_prizoleto(h, tid)
        except Exception as e:
            log(f'   task {tid} activate error: {e}')
            continue
        got = res.get('attempts_count', 0)
        name = (t.get('name') or '').replace('&nbsp;', ' ')
        log(f'   task {tid} [{name[:40]}] +{got} attempts')
        total += got
    return total


# ---------- Монстро-планетяне (Монстриксы) ----------

def mh_headers(hs256_token):
    return {
        'Authorization': 'Bearer ' + hs256_token,
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9; SM-S906N Build/PQ3A.190605.09261140; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36',
    }


def auth_game_monstro(rs256_token):
    """POST /api/v1/users/auth — обмен RS256-токена на HS256-токен игры и профиль."""
    r = s.post('https://magnit-monstroplanetyane.ru-prod2.kts.studio/api/v1/users/auth',
               headers={'Content-Type': 'application/json',
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 9; SM-S906N Build/PQ3A.190605.09261140; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/120.0.0.0 Mobile Safari/537.36'},
               data=json.dumps({'token': rs256_token, 'refresh_only': False}), timeout=20)
    r.raise_for_status()
    return r.json()['data']


def claim_daily_reward_monstro(h, tasks):
    """POST /api/v1/tasks/reward — получить награду за задания (ежедневный бонус)."""
    r = s.post('https://magnit-monstroplanetyane.ru-prod2.kts.studio/api/v1/tasks/reward',
               headers=h, data=json.dumps({'tasks': tasks}), timeout=20)
    r.raise_for_status()
    return r.json().get('data', {})


def start_game_monstro(h):
    """POST /api/v1/game/start — начать партию."""
    r = s.post('https://magnit-monstroplanetyane.ru-prod2.kts.studio/api/v1/game/start',
               headers=h, data='', timeout=20)
    r.raise_for_status()
    return r.json().get('data', {})


def finish_game_monstro(h, game_timestamp, duration):
    """POST /api/v1/game/finish — завершить партию и получить приз."""
    body = {'game_timestamp': game_timestamp, 'duration': duration}
    r = s.post('https://magnit-monstroplanetyane.ru-prod2.kts.studio/api/v1/game/finish',
               headers=h, data=json.dumps(body), timeout=20)
    r.raise_for_status()
    return r.json().get('data', {})


# ---------- coupons sync ----------

def coupons_list(acc, magnit_token):
    r = s.get('https://middle-api.magnit.ru/v3/user/coupons/list?limit=100',
              headers={**dev_headers(acc), 'Authorization': 'bearer ' + magnit_token}, timeout=20)
    r.raise_for_status()
    return r.json().get('coupons', [])


def sync_coupons(acc, log=print):
    name = acc.get('name', '?')
    log(f'=== {name}: синхронизация купонов ===')
    at = refresh_magnit_token(acc)
    coupons = coupons_list(acc, at)
    event = acc.get('event_id', 'wX8CoYBu0OQzsA6DBwqlU')
    game_coupons = [c for c in coupons if c.get('category') == event]
    log(f'всего купонов: {len(coupons)}, игровых: {len(game_coupons)}')
    added = 0
    for c in game_coupons:
        coupon_id = c.get('favoriteId') or ''
        conn = _db()
        try:
            cur = _ex(conn, 'SELECT id FROM prizes WHERE account=%s AND coupon_id=%s', (name, coupon_id))
            dup = cur.fetchone()
        finally:
            conn.close()
        if dup:
            continue
        items = c.get('items') or []
        barcode = (items[0].get('couponCode') if items else None) or coupon_id
        fake = {'id': None, 'info': {'name': c.get('title', ''), 'icon_ref': c.get('smallImageUrl') or c.get('promoImageUrl') or ''},
                'expiration_date': c.get('expirationDate', ''),
                'is_barcode': c.get('displayType') == 'barcode',
                'is_button': bool(c.get('button')),
                'items': items}
        save_prize(name, '', 0, fake, barcode=barcode, coupon_id=coupon_id,
                   display_type=c.get('displayType'))
        added += 1
        log(f'   + {barcode} {c.get("title", "")[:50]}')
    log(f'добавлено купонов: {added}')
    return added


# ---------- balance & personal offers ----------
def get_balance(acc, magnit_token):
    r = s.get('https://middle-api.magnit.ru/v2/user/balance?includeExpiringBalances=false',
              headers={**dev_headers(acc), 'Authorization': 'bearer ' + magnit_token}, timeout=20)
    r.raise_for_status()
    j = r.json()
    return {
        'total': j.get('totalPointBalance', 0),
        'express': j.get('totalExpressPoints', 0),
        'items': j.get('items', []),
    }


def get_offers(acc, magnit_token):
    r = s.get('https://middle-api.magnit.ru/promoter-v2/v1/offers',
              headers={**dev_headers(acc), 'Authorization': 'bearer ' + magnit_token}, timeout=20)
    r.raise_for_status()
    return r.json().get('offers', [])


def sync_game_rewards(acc, log=print):
    name = acc.get('name', '?')
    log(f'=== {name}: синхронизация выигрышей ===')
    at = refresh_magnit_token(acc)
    rs = get_game_token(acc, at)
    login = login_game(rs)
    h = game_headers(login['token'], login['external_id'])
    r = s.get('https://magnit-prizoleto.ru/api/v1/rewards', headers=h, timeout=20)
    r.raise_for_status()
    received = r.json().get('received', [])
    log(f'выигрышей в списке: {len(received)}')
    added = 0
    for p in received:
        code = p.get('code') or ''
        conn = _db()
        try:
            cur = _ex(conn, 'SELECT id FROM prizes WHERE account=%s AND (barcode=%s OR coupon_id=%s)',
                      (name, code, code))
            dup = cur.fetchone()
        finally:
            conn.close()
        if dup:
            continue
        save_prize(name, '', 0, p, barcode=code, coupon_id=code,
                   display_type='barcode' if p.get('is_barcode') else 'text')
        added += 1
        log(f'   + {code or "?"} {p.get("info", {}).get("name", "")[:50]}')
    log(f'добавлено выигрышей: {added}')
    return added


# ---------- play orchestration ----------

class RunManager:
    def __init__(self):
        self._runs = {}
        self._lock = threading.Lock()

    def start(self, account_name):
        with self._lock:
            if account_name in self._runs and self._runs[account_name].is_alive():
                return None, 'already running'
            t = threading.Thread(target=self._worker, args=(account_name,), daemon=True)
            self._runs[account_name] = t
            t.start()
            return 'started', None

    def _worker(self, name):
        try:
            play_account(name, print)
        except Exception as e:
            print(f'[{name}] ERROR: {e}')

    def running(self):
        with self._lock:
            return [n for n, t in self._runs.items() if t.is_alive()]


def play_account(acc, log=print):
    if acc.get('event_id') == 'At99RuZXsCpnFRhpmEZCK':
        return play_monstro_account(acc, log)
    return play_prizoleto_account(acc, log)


def play_prizoleto_account(acc, log=print):
    name = acc.get('name', '?')
    log(f'=== {name} ===')
    at = refresh_magnit_token(acc)
    log('1. magnit token OK')
    rs = get_game_token(acc, at)
    login = login_game(rs)
    gt, ext = login['token'], login['external_id']
    h = game_headers(gt, ext)
    prof = s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=20).json()
    attempts = prof.get('attempts', {}).get('total_count', 0)
    log(f'   attempts: {attempts}')
    # ежедневный бонус за вход + готовые задачи
    got = claim_prizoleto_daily(h, log)
    if got:
        attempts += got
        log(f'   после забора задач: {attempts} attempts')
    level = prof.get('last_finished_map_level', 0) + 1
    games = 0
    while attempts > 0:
        try:
            game = start_game(h, level)
        except Exception as e:
            log(f'   start game error: {e}')
            break
        gid = game['id']
        ld = json.loads(game['level_data'])
        target = ld.get('targetScore')
        rows, cols = ld['grid']['rows'], ld['grid']['cols']
        log(f'   game {gid}: board {cols}x{rows} target {target}')
        fin = finish_game(h, gid, turns=1, victory=True)
        log(f'   finish -> {fin.get("attempt_type")}')
        for p in fin.get('rewards_preview', {}).get('current', []):
            st = pick_reward(h, p['id'])
            log(f'   reward {p["id"]} {p.get("info", {}).get("name", "")[:40]} -> {st}')
        if fin.get('attempt_type') == 'conditional':
            level += 1
        attempts -= 1
        games += 1
        time.sleep(0.5)
    try:
        sync_game_rewards(acc, log)
    except Exception as e:
        log(f'   sync rewards error: {e}')
    prof2 = s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=20).json()
    log(f'   done: {games} games, remaining {prof2.get("attempts", {}).get("total_count")}, '
        f'last level {prof2.get("last_finished_map_level")}')
    return games


def play_monstro_account(acc, log=print):
    name = acc.get('name', '?')
    log(f'=== {name} (Монстро-планетяне) ===')
    at = refresh_magnit_token(acc)
    log('1. magnit token OK')
    rs = get_game_token(acc, at)
    data = auth_game_monstro(rs)
    h = mh_headers(data['token'])
    user = data.get('user', {})
    attempts = user.get('attempts_count', 0)
    log(f'   attempts: {attempts}')
    # ежедневный бонус / pending rewards
    pending = data.get('pending_rewards') or []
    for task in pending:
        tid = task.get('task_id')
        if tid:
            rew = claim_daily_reward_monstro(h, [tid])
            got = (rew.get('reward') or {}).get('attempts', 0)
            log(f'   task {tid} reward: +{got} attempts')
            attempts += got
    games = 0
    while attempts > 0:
        try:
            st = start_game_monstro(h)
        except Exception as e:
            log(f'   start game error: {e}')
            break
        info = st.get('game_info', {})
        level = info.get('level')
        max_level = info.get('max_level')
        result = info.get('result')
        log(f'   start: level {level}/{max_level} result={result}')
        # game_timestamp — ms timestamp string, duration ms
        ts = str(int(time.time() * 1000))
        dur = 2000
        fin = finish_game_monstro(h, ts, dur)
        log(f'   finish: remaining attempts {fin.get("attempts_count")}, type {fin.get("attempts_type")}')
        for p in fin.get('prizes', []):
            title = p.get('title', '')
            ptype = p.get('type', 'text')
            # промокод/купон несёт код в value; посткарта — просто открытка без кода
            code = str(p.get('value') or '') or (str(p.get('id', '')) if ptype in ('promocode', 'barcode') else '')
            fake = {'id': p.get('id'), 'info': {'name': title, 'icon_ref': (p.get('image_url') or [''])[0]},
                    'expiration_date': '', 'is_barcode': ptype == 'barcode', 'is_button': False, 'items': []}
            save_prize(name, acc.get('event_id'), level or 0, fake, barcode=code or None, coupon_id=code or None,
                       display_type=ptype)
            log(f'   prize {p.get("id")} [{ptype}] {title[:50]}')
        attempts = fin.get('attempts_count', attempts - 1)
        games += 1
        time.sleep(0.5)
    log(f'   done: {games} games')
    return games


runs = RunManager()
