import sys, os, json, uuid, time, re, random, threading, urllib.parse, html, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
import requests

# ============================================================
#  Яндекс Еда: доставка.
#
#  Реальные эндпоинты получены из mitm-перехвата flows_eda.mitm
#  (приложение ru.foodfox.client 3.19.0).
#
#  Авторизация: OAuth Bearer-токен (из mobileproxy passport,
#  token_by_sessionid, живёт ~1 год) + x-yandex-uid + app-заголовки.
# ============================================================

EDA_ACCOUNTS_FILE = os.path.join(core.DATA_DIR, 'eda_accounts.json')
EDA_SESSIONS_FILE = os.path.join(core.DATA_DIR, 'eda_sessions.json')

# «Свои Плюсы»: ежедневные подарки (sp.yandex.ru/daily).
SP_GIFTS_FILE = os.path.join(core.DATA_DIR, 'sp_gifts.json')
SP_GRAPHQL_URL = 'https://egw.sp.plet.yandex.ru/graphql'
SP_DAILY_BASE = 'https://egw.daily.plus.yandex.ru'

# «Свои Плюсы»: Колесо Фортуны (sp.yandex.ru/wheel).
SP_WHEEL_FILE = os.path.join(core.DATA_DIR, 'sp_wheel.json')
SP_WHEEL_PAGE = 'https://sp.yandex.ru/wheel?retRoute=internal'
SP_WHEEL_API = 'https://egw.selo.plus.yandex.ru/api'

EDA_HOST = 'https://eda.yandex.ru'

# Вкладка «Еда» в Яндекс Go — WebView-приложение на tc.eats.yandex.ru
# (суперапп), а не api.eda.yandex.ru. Авторизация — cookie Session_id
# (Bearer не нужен). Промокоды лежат в informers_v2 лайаута.
GO_EATS_HOST = 'https://tc.eats.yandex.ru/4.0/eda-superapp'
GO_DEVICE_ID = 'z14561cd16b144d695f05886b6ff21e2'  # webviewuserid из захвата Go

# Дефолтная точка: Омск, проспект Мира, 33 (координаты из дампа).
DEFAULT_LAT = 55.02878527315827
DEFAULT_LON = 73.27583823706175

# Пул реальных моделей для device-профилей (антифрод: разные устройства).
# Каждая пара модель/версия ОС реалистична (версия не ниже той, с которой
# модель вышла) — несоответствия типа S22 на Android 9 палят эмулятор.
# Samsung-модели убраны: они сильнее фродятся антифродом Яндекса.
DEVICE_MODELS = [
    {'model': 'M391Q', 'brand': 'meizu', 'manufacturer': 'Meizu', 'os_version': '13',
     'density': 2.75, 'width': 1080, 'height': 2340},
    {'model': 'M181Q', 'brand': 'meizu', 'manufacturer': 'Meizu', 'os_version': '11',
     'density': 2.75, 'width': 1080, 'height': 2340},
    {'model': 'M971Q', 'brand': 'meizu', 'manufacturer': 'Meizu', 'os_version': '9',
     'density': 2.75, 'width': 1080, 'height': 2340},
    {'model': 'RMX3562', 'brand': 'realme', 'manufacturer': 'realme', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'RMX3363', 'brand': 'realme', 'manufacturer': 'realme', 'os_version': '12',
     'density': 2.0, 'width': 720, 'height': 1600},
    {'model': 'RMX1921', 'brand': 'realme', 'manufacturer': 'realme', 'os_version': '9',
     'density': 2.75, 'width': 1080, 'height': 2340},
    {'model': '23127PN0CC', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '14',
     'density': 2.0, 'width': 720, 'height': 1600},
    {'model': '2210132G', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': '2201117TG', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': '2107119DC', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '11',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'M2004J19C', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '10',
     'density': 2.0, 'width': 720, 'height': 1600},
    {'model': 'CPH2359', 'brand': 'oppo', 'manufacturer': 'OPPO', 'os_version': '13',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'CPH2387', 'brand': 'oppo', 'manufacturer': 'OPPO', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'V2134', 'brand': 'vivo', 'manufacturer': 'vivo', 'os_version': '12',
     'density': 2.0, 'width': 720, 'height': 1600},
    {'model': 'V2050', 'brand': 'vivo', 'manufacturer': 'vivo', 'os_version': '11',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'X663', 'brand': 'infinix', 'manufacturer': 'INFINIX', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'KH6j', 'brand': 'tecno', 'manufacturer': 'TECNO', 'os_version': '12',
     'density': 2.0, 'width': 720, 'height': 1600},
    {'model': 'LRA-NX9', 'brand': 'honor', 'manufacturer': 'HONOR', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'Pixel 7', 'brand': 'google', 'manufacturer': 'Google', 'os_version': '13',
     'density': 2.75, 'width': 1080, 'height': 2400},
    {'model': 'Pixel 6a', 'brand': 'google', 'manufacturer': 'Google', 'os_version': '12',
     'density': 2.75, 'width': 1080, 'height': 2400},
]

# Реальные версии Я.Еды (Play Store): 3.99.0 — 3.106.0
EDA_APP_VERSIONS = ['3.99.0', '3.100.0', '3.101.0', '3.102.0',
                    '3.103.0', '3.104.0', '3.105.0', '3.106.0']
# Коды сборки (x-code-version) — варьируются с версией
EDA_CODE_VERSIONS = ['249708', '250312', '251045', '251890', '252401']
# Реальные версии Яндекс Такси (superapp UA)
TAXI_VERSIONS = ['5.89.1.128364', '5.90.0.129102', '5.91.2.130450', '5.92.1.131200']
# Версии EatsKit
EATSKIT_VERSIONS = ['29.3.0', '29.4.0', '29.5.0', '29.6.0']
# Build-строки для superapp UA
ANDROID_BUILDS = ['V417IR', 'UP1A.231005.007', 'TP1A.220905.001',
                  'SQ3A.220705.003.A1', 'RD2A.220624.014']


def new_device_profile():
    """Свежий отпечаток «устройства» для аккаунта (аналог установки в Knox-папке).

    Каждый аккаунт получает уникальные device_id/appmetrica-идентификаторы,
    чтобы антифрод не видел «фарм» (много аккаунтов с одного устройства).
    """
    m = random.choice(DEVICE_MODELS)
    return {
        'device_id': str(uuid.uuid4()),
        'appmetrica_deviceid': uuid.uuid4().hex,
        'appmetrica_uuid': uuid.uuid4().hex,
        'mobile_ifa': str(uuid.uuid4()),
        'tracker_id': str(uuid.uuid4()),
        'yandex_device_id': str(uuid.uuid4()),
        'model': m['model'],
        'brand': m['brand'],
        'manufacturer': m['manufacturer'],
        'os_version': m['os_version'],
        'density': m.get('density', 2.75),
        'width': m.get('width', 1080),
        'height': m.get('height', 2400),
        'app_version': random.choice(EDA_APP_VERSIONS),
        'code_version': random.choice(EDA_CODE_VERSIONS),
        'android_build': random.choice(ANDROID_BUILDS),
        'taxi_version': random.choice(TAXI_VERSIONS),
        'eatskit_version': random.choice(EATSKIT_VERSIONS),
    }


def _dev(acc):
    """Device-профиль аккаунта: свои идентификаторы либо глобальные дефолты."""
    p = acc.get('device') or {}
    return {
        'device_id': p.get('device_id') or APP['x-device-id'],
        'appmetrica_deviceid': p.get('appmetrica_deviceid') or APP['x-appmetrica-deviceid'],
        'appmetrica_uuid': p.get('appmetrica_uuid') or APP['x-appmetrica-uuid'],
        'mobile_ifa': p.get('mobile_ifa') or APP.get('x-mobile-ifa', ''),
        'tracker_id': p.get('tracker_id') or APP.get('x-tracker-id', ''),
        'yandex_device_id': p.get('yandex_device_id') or str(uuid.uuid4()),
        'model': p.get('model') or APP['x-device-model'],
        'brand': p.get('brand') or APP['x-device-brand'],
        'manufacturer': p.get('manufacturer') or APP['x-device-manufacturer'],
        'os_version': p.get('os_version') or APP['x-os-version'],
        'density': p.get('density', 2.75),
        'width': p.get('width', 1080),
        'height': p.get('height', 2400),
        'app_version': p.get('app_version') or APP['x-app-version'],
        'code_version': p.get('code_version') or APP['x-code-version'],
        'android_build': p.get('android_build', 'V417IR'),
        'taxi_version': p.get('taxi_version', TAXI_VERSIONS[0]),
        'eatskit_version': p.get('eatskit_version', EATSKIT_VERSIONS[0]),
    }

# App-параметры (дефолт — реальная модель Meizu, а не эмуляторная
# S22+Android 9: такие несоответствия палят антифрод).
# x-app-version/user-agent: поднимаем до актуальной версии приложения — мобильный
# эндпоинт cart/promocode гейтит свежие промокоды (500go, FREE500) сообщением
# «Необходимо обновить приложение» по версии в user-agent (порог ~3.80, проверено:
# 3.19.0…3.70 — гейт, 3.80+ — реальный ответ). x-code-version на гейт не влияет.
APP = {
    'x-os-version': '13',
    'x-device-model': 'M391Q',
    'x-device-brand': 'meizu',
    'x-device-manufacturer': 'Meizu',
    'x-android-platform-services-type': 'google',
    'x-platform': 'android_app',
    'x-app-version': '3.99.0',
    'x-code-version': '249708',
    'x-device-id': 'dab454cb-f8f4-34cc-950c-91759cc19869',
    'x-appmetrica-deviceid': '1c1e4355a8142f9d52e1f218c928d7de',
    'x-appmetrica-uuid': 'c4a9b2f931aa4e78957a0669566685c9',
    'user-agent': 'android (3.99.0)',
    'accept-language': 'ru',
    'content-type': 'application/json',
}


# ---------- account storage (bearer-based) ----------

@contextlib.contextmanager
def _store_lock():
    """Межпроцессная блокировка файла хранилища (fcntl на Linux, msvcrt на Windows).

    Railway запускает несколько воркеров gunicorn в одном процессе/нескольких —
    без блокировки одновременные read-modify-write портят JSON и стирают данные.
    """
    lock_path = EDA_ACCOUNTS_FILE + '.lock'
    f = open(lock_path, 'a+')
    try:
        if os.name == 'nt':
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                f.write('\0')
                f.flush()
            f.seek(0)
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == 'nt':
            try:
                f.seek(0)
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except Exception:
                pass
        else:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
        f.close()


def _eda_read():
    try:
        with open(EDA_ACCOUNTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _eda_write(store):
    """Атомарная запись: сначала во временный файл, затем os.replace.

    Защищает от битого JSON при одновременных записях (иначе следующий
    save видел бы пустое хранилище и перезаписывал аккаунты на []).
    """
    tmp = EDA_ACCOUNTS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, EDA_ACCOUNTS_FILE)


def _eda_store():
    with _store_lock():
        return _eda_read()


def load_eda_accounts():
    return _eda_store().get('accounts', [])


def save_eda_accounts(accs):
    with _store_lock():
        store = _eda_read()
        store['accounts'] = accs
        _eda_write(store)


def _parse_keyvals(raw):
    """Разобрать 'k=v; k2=v2' или JSON-объект."""
    raw = (raw or '').strip()
    if not raw:
        return {}
    if raw.startswith('{'):
        try:
            d = json.loads(raw)
            return {str(k): str(v) for k, v in d.items()}
        except Exception:
            pass
    out = {}
    for part in raw.split(';'):
        part = part.strip()
        if '=' in part:
            k, v = part.split('=', 1)
            out[k.strip()] = v.strip()
    return out


def _extract_bearer(acc):
    """Bearer-токен из сохранённого аккаунта: прямой token, webviewtoken или Session_id."""
    t = (acc.get('token') or '').strip()
    if t:
        return t
    ck = acc.get('cookies') or {}
    wt = (ck.get('webviewtoken') or '').strip()
    if wt:
        return wt
    # Session_id от passport тоже можно обменять, но не храним raw token.
    return ''


# Client-id для обмена Session_id -> OAuth (mobileproxy passport).
# Пара из AlexxIT/YandexStation (рабочая для яндекс-сервисов).
PASSPORT_CLIENT_ID = 'c0ebe342af7d48fbbbfcf2d2eedb8f9e'
PASSPORT_CLIENT_SECRET = 'ad0a908f0aa341a182a37ecd75bc319e'


def exchange_sessionid(session_id, client_id=None, client_secret=None):
    """Обменять passport Session_id на OAuth Bearer-токен.

    Эндпоинт mobileproxy passport (token_by_sessionid) — тот же, что
    использует мобильное приложение при входе. Возвращает (token, uid)
    либо поднимает RuntimeError.
    """
    sid = (session_id or '').strip()
    if not sid:
        raise RuntimeError('Session_id пустой')
    url = 'https://mobileproxy.passport.yandex.net/1/bundle/oauth/token_by_sessionid'
    hdrs = {
        'User-Agent': 'android (9)',
        'Accept-Language': 'ru',
        'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8',
        'Ya-Client-Host': 'passport.yandex.ru',
        'Ya-Client-Cookie': f'Session_id={sid}',
    }
    data = {
        'client_id': client_id or PASSPORT_CLIENT_ID,
        'client_secret': client_secret or PASSPORT_CLIENT_SECRET,
    }
    try:
        r = requests.post(url, headers=hdrs, data=data, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Паспорт: сеть (token_by_sessionid): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Паспорт: HTTP {r.status_code} (token_by_sessionid): {r.text[:300]}')
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f'Паспорт: ответ не JSON: {r.text[:200]}')
    tok = (d.get('access_token') or '').strip()
    if not tok:
        raise RuntimeError(f'Паспорт: нет access_token в ответе: {d}')
    uid = str(d.get('uid') or '')
    return tok, uid


# ---------- QR-вход (passport magic link) ----------

# Протокол (вход по QR-ссылке, без сканирования):
#   GET  /pwl-yandex                       -> __CSRF__, cookies (yandexuid, ...)
#   POST /pwl-yandex/api/passport/auth/password/submit -> track_id, csrf_token
#   POST /pwl-yandex/api/passport/auth/magic/code      -> link (qrsecure?track_id&magic)
#   POST /pwl-yandex/api/passport/auth/magic/code/status (поллинг) -> otp_auth_finished
#   POST /pwl-yandex/api/passport/sessions/get_session -> Session_id в cookies
# Ссылку можно открыть в браузере/приложении, где уже залогинен Яндекс,
# — сканировать QR не обязательно.

PASSPORT_PWL = 'https://passport.yandex.ru/pwl-yandex'
QR_STATE = {}
QR_LOCK = threading.Lock()
QR_TTL = 600  # 10 минут — TTL QR-ссылки на стороне паспорта

def _qr_headers(csrf):
    return {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-CSRF-Token': csrf,
    }


def qr_start():
    """Создать QR-сессию входа. Возвращает (qr_id, link)."""
    s = requests.Session()
    try:
        r = s.get(PASSPORT_PWL, headers=_qr_headers(''), timeout=25)
        r.raise_for_status()
        m = re.search(r'__CSRF__\s*=\s*"([^"]+)"', r.text)
        if not m:
            raise RuntimeError('passport: CSRF не найден в странице')
        csrf = m.group(1)
        h = _qr_headers(csrf)
        r = s.post(PASSPORT_PWL + '/api/passport/auth/password/submit',
                   headers=h, data=json.dumps({'retpath': 'https://passport.yandex.ru/'}), timeout=25)
        r.raise_for_status()
        magic = r.json()
        track_id = magic.get('track_id') or ''
        csrf_token = magic.get('csrf_token') or ''
        if not track_id:
            raise RuntimeError('passport: нет track_id: ' + r.text[:200])
        r = s.post(PASSPORT_PWL + '/api/passport/auth/magic/code',
                   headers=h,
                   data=json.dumps({'location_id': '0', 'magic_track_id': track_id, 'track_id': ''}),
                   timeout=25)
        r.raise_for_status()
        link = r.json().get('link') or ''
        if not link:
            raise RuntimeError('passport: нет link: ' + r.text[:200])
    except requests.RequestException as e:
        raise RuntimeError(f'passport: сеть: {e}')
    qr_id = uuid.uuid4().hex
    with QR_LOCK:
        QR_STATE[qr_id] = {
            'session': s, 'csrf': csrf, 'magic_track_id': track_id,
            'csrf_token': csrf_token, 'link': link, 'created_at': time.time(),
        }
    return qr_id, link


def qr_status(qr_id):
    """Поллинг статуса QR-входа. Вернёт {'state': 'waiting'|'ok'|'error'|'expired', ...}."""
    with QR_LOCK:
        st = QR_STATE.get(qr_id)
    if not st:
        return {'state': 'error', 'message': 'сессия не найдена (сервер перезапущен?)'}
    if time.time() - st['created_at'] > QR_TTL:
        with QR_LOCK:
            QR_STATE.pop(qr_id, None)
        return {'state': 'expired', 'message': 'ссылка устарела — создайте новую'}
    s, h = st['session'], _qr_headers(st['csrf'])
    try:
        r = s.post(PASSPORT_PWL + '/api/passport/auth/magic/code/status',
                   headers=h, data=json.dumps({
                       'track_id': st['magic_track_id'], 'csrf_token': st['csrf_token'],
                       'yandexAllowedDomains': []}), timeout=25)
        r.raise_for_status()
        d = r.json()
    except requests.RequestException as e:
        return {'state': 'error', 'message': f'поллинг: {e}'}
    state = d.get('state')
    if state in (None, 'otp_auth_not_ready'):
        return {'state': 'waiting'}
    if state == 'otp_auth_finished':
        track_id = d.get('trackId')
        if not track_id:
            return {'state': 'error', 'message': f'нет trackId: {d}'}
        try:
            r = s.post(PASSPORT_PWL + '/api/passport/sessions/get_session',
                       headers=h, data=json.dumps({'track_id': track_id}), timeout=25)
            r.raise_for_status()
        except requests.RequestException as e:
            return {'state': 'error', 'message': f'get_session: {e}'}
        ck = {c.name: c.value for c in s.cookies}
        session_id = ck.get('Session_id') or ''
        if not session_id:
            return {'state': 'error', 'message': f'нет Session_id в cookies: {ck}'}
        with QR_LOCK:
            QR_STATE.pop(qr_id, None)
        return {'state': 'ok', 'session_id': session_id, 'yandexuid': ck.get('yandexuid', '')}
    if state == 'auth_challenge':
        return {'state': 'waiting', 'hint': 'нужно доп. подтверждение в Яндекс-приложении'}
    return {'state': 'waiting', 'hint': f'state={state}'}


def add_eda_account(name, cookies_raw, token=None, yandexuid='', session_id='', device=None):
    """Добавить аккаунт Я.Еды.

    Авторизация Я.Еды — Bearer-токен (OAuth). Его можно передать:
      - напрямую параметром `token`, либо
      - внутри cookie-строки как webviewtoken=..., либо
      - как сам token в поле cookies (если строка не 'k=v'), либо
      - как passport `session_id` (Session_id cookie) — тогда он будет
        обменян на OAuth-токен через mobileproxy passport.
    yandexuid (passport uid) — желателен для x-yandex-uid.
    device — device-профиль (свежие device_id/appmetrica/модель); если не
    передан — генерируется автоматически (антифрод: разное «устройство»
    на каждый аккаунт, как при установке в Knox-папке).
    """
    name = (name or '').strip()
    acc = {'name': name, 'device': dict(device or new_device_profile())}
    ck = _parse_keyvals(cookies_raw)
    # если передан token отдельно — берём его
    if token:
        acc['token'] = token.strip()
    # сырой Session_id храним отдельно — нужен для «Свои Плюсы» (sp.yandex.ru/daily)
    raw_sid = session_id.strip() if session_id else ck.get('Session_id', '')
    if raw_sid:
        acc['session_id'] = raw_sid
    if yandexuid:
        acc['yandexuid'] = yandexuid.strip()
    elif ck.get('yandexuid'):
        acc['yandexuid'] = ck['yandexuid']
    # cookie-строка может быть просто токеном (без '=')
    if not ck and cookies_raw and not token:
        acc['token'] = cookies_raw.strip()
    if ck:
        acc['cookies'] = ck
    bearer = _extract_bearer(acc)
    # если токена нет, но есть Session_id — обмениваем
    if not bearer and (session_id or (ck or {}).get('Session_id')):
        sid = session_id or (ck or {}).get('Session_id')
        tok, uid = exchange_sessionid(sid)
        acc['token'] = tok
        if not acc.get('yandexuid'):
            acc['yandexuid'] = uid
        bearer = tok
    if not bearer:
        raise RuntimeError('нужен Bearer-токен (параметр token, webviewtoken, Session_id или token_by_sessionid)')
    if not acc.get('yandexuid'):
        # попробуем вытащить uid из самого токена: Bearer 2.<uid>.<...>
        m = bearer.split('.')
        if len(m) >= 2 and m[1].isdigit():
            acc['yandexuid'] = m[1]
    # подтянем настоящее имя профиля (подтверждает, что токен рабочий)
    try:
        acc['profile_name'] = profile_name(acc)
    except Exception:
        pass
    # uid мог не прийти с обменом Session_id (токен y0_... без uid) —
    # профиль Я.Еды сам отдаёт passport_uid
    if not acc.get('yandexuid'):
        try:
            p = profile(acc)
            if isinstance(p, dict) and p.get('passport_uid'):
                acc['yandexuid'] = str(p['passport_uid'])
        except Exception:
            pass
    # если имя не задано — берём из профиля (или uid)
    if not acc['name']:
        acc['name'] = acc.get('profile_name') or acc.get('yandexuid') or 'аккаунт'
    # подтянем баллы Я.Плюс
    try:
        pb = plus_balance(acc)
        acc['plus_balance'] = pb.get('balance')
        acc['plus_status'] = pb.get('status')
    except Exception:
        pass
    accs = load_eda_accounts()
    # если имя уже занято — добавляем номер: Client, Client 2, Client 3…
    if any(a.get('name') == acc['name'] for a in accs):
        base, n = acc['name'], 2
        while any(a.get('name') == f'{base} {n}' for a in accs):
            n += 1
        acc['name'] = f'{base} {n}'
    acc['added'] = time.strftime('%Y-%m-%d %H:%M:%S')
    accs.append(acc)
    save_eda_accounts(accs)
    return accs


def delete_eda_account(name):
    accs = load_eda_accounts()
    accs = [a for a in accs if a.get('name') != name]
    save_eda_accounts(accs)


def refresh_eda_account(name):
    """Обновить имя профиля и баллы Плюса у существующего аккаунта."""
    accs = load_eda_accounts()
    for a in accs:
        if a.get('name') == name:
            a['profile_name'] = profile_name(a)
            try:
                pb = plus_balance(a)
                a['plus_balance'] = pb.get('balance')
                a['plus_status'] = pb.get('status')
            except Exception:
                pass
            save_eda_accounts(accs)
            return {'profile_name': a.get('profile_name', ''),
                    'plus_balance': a.get('plus_balance'),
                    'plus_status': a.get('plus_status', '')}
    raise RuntimeError(f'аккаунт "{name}" не найден')


def set_plus_balance(name, balance, status=''):
    """Сохранить баланс/статус Я.Плюс в конфиг аккаунта (без сетевых вызовов)."""
    accs = load_eda_accounts()
    for a in accs:
        if a.get('name') == name:
            a['plus_balance'] = balance
            a['plus_status'] = status
            save_eda_accounts(accs)
            return
    raise RuntimeError(f'аккаунт "{name}" не найден')


def rotate_eda_device(name):
    """Сменить device-профиль аккаунта (новые device_id/appmetrica/модель).

    Эквивалент «переустановки приложения» / установки в Knox-папке: если
    антифрод забанил старый отпечаток, новые промокоды могут пройти.
    """
    with _store_lock():
        store = _eda_read()
        accs = store.get('accounts') or []
        for a in accs:
            if a.get('name') == name:
                a['device'] = new_device_profile()
                store['accounts'] = accs
                _eda_write(store)
                return dict(a['device'])
    raise RuntimeError(f'аккаунт "{name}" не найден')


def check_eda_accounts(progress=None):
    """Проверить все аккаунты Я.Еды: токен и Session_id живы ли.

    - Токен Я.Еды проверяется запросом профиля. Если он битый, но есть
      Session_id — пробуем перевыпустить токен и проверить снова.
    - Session_id проверяется загрузкой страницы Колеса Фортуны (жива ли
      сессия для «Свои Плюсы»/колеса).
    - Если токена нет, но Session_id живой — обмениваем на OAuth-токен
      и проверяем; рабочий токен и недостающий uid сохраняются.

    Возвращает список отчётов {name, ok, message, has_token, has_sid,
    token, session}.
    """
    accs = load_eda_accounts()
    reports = []
    total = max(len(accs), 1)
    for i, acc in enumerate(accs):
        if progress:
            progress(f'Проверяю {acc.get("name")}', i / total)
        r = {'name': acc.get('name'), 'ok': False, 'message': '',
             'has_token': bool(_extract_bearer(acc)), 'has_sid': bool(sp_session_id(acc)),
             'token': '', 'session': ''}
        try:
            if sp_session_id(acc):
                try:
                    wheel_page_state(acc)
                    r['session'] = 'ок'
                except Exception as e:
                    r['session'] = f'недоступна: {e}'
            tok = _extract_bearer(acc)
            if tok:
                try:
                    acc['profile_name'] = profile_name(acc)
                    r['token'] = 'ок'
                except Exception as e:
                    r['token'] = str(e)
                    if sp_session_id(acc):
                        try:
                            new_tok, new_uid = exchange_sessionid(sp_session_id(acc))
                            probe = dict(acc)
                            probe['token'] = new_tok
                            if new_uid:
                                probe['yandexuid'] = new_uid
                            acc['profile_name'] = profile_name(probe)
                            acc['token'] = new_tok
                            if new_uid:
                                acc['yandexuid'] = new_uid
                            r['token'] = 'ок (перевыпущен из Session_id)'
                        except Exception as e2:
                            r['token'] += f'; обмен не помог: {e2}'
            elif sp_session_id(acc):
                try:
                    new_tok, new_uid = exchange_sessionid(sp_session_id(acc))
                    probe = dict(acc)
                    probe['token'] = new_tok
                    if new_uid:
                        probe['yandexuid'] = new_uid
                    acc['profile_name'] = profile_name(probe)
                    acc['token'] = new_tok
                    if new_uid:
                        acc['yandexuid'] = new_uid
                    r['token'] = 'ок (из Session_id)'
                except Exception as e:
                    r['token'] = f'Session_id не обменялся: {e}'
            else:
                r['token'] = 'нет токена и нет Session_id'
            # если сессия жива, но uid не сохранён — достаём (обменом или
            # через веб-паспорт) и сохраняем, чтобы спин работал без обмена.
            if sp_session_id(acc) and not (acc.get('yandexuid') or '').strip():
                uid = _session_uid(acc)
                if uid:
                    acc['yandexuid'] = uid
            if _extract_bearer(acc):
                try:
                    pb = plus_balance(acc)
                    acc['plus_balance'] = pb.get('balance')
                    acc['plus_status'] = pb.get('status')
                except Exception:
                    pass
            problems = []
            if r['token'] and r['token'] not in ('ок', 'ок (из Session_id)', 'ок (перевыпущен из Session_id)'):
                problems.append('токен: ' + r['token'])
            if r['session'] and r['session'] != 'ок':
                problems.append('сессия: ' + r['session'])
            r['ok'] = not problems
            r['message'] = '; '.join(problems) if problems else 'всё живо'
        except Exception as e:
            r['message'] = str(e)
        reports.append(r)
    save_eda_accounts(accs)
    if progress:
        progress('Готово', 1.0)
    return reports


def get_eda_account(name):
    return next((a for a in load_eda_accounts() if a.get('name') == name), None)


# ---------- delivery access sessions ----------

# Сколько ждать с момента создания сессии (новое «устройство»),
# чтобы заказ с промокодом не отменил антифрод Я.Еды.
DEVICE_WAIT_SECONDS = 22 * 60

def load_eda_sessions():
    try:
        with open(EDA_SESSIONS_FILE, encoding='utf-8') as f:
            return json.load(f).get('sessions', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_eda_sessions(sess):
    with open(EDA_SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'sessions': sess}, f, ensure_ascii=False, indent=2)


def create_eda_session(name, account, hours=24):
    name = (name or '').strip()
    account = (account or '').strip()
    if not name or not account:
        raise RuntimeError('name and account required')
    acc = get_eda_account(account)
    if not acc:
        raise RuntimeError(f'аккаунт "{account}" не найден')
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    now = time.time()
    sess = load_eda_sessions()
    # переиспользуем device аккаунта, если он прогрет/зафиксирован —
    # иначе таймер отлёжки 22 мин сбросился бы на каждом входе.
    if acc.get('device'):
        device = dict(acc['device'])
        promo_ready_at = acc.get('promo_ready_at') or (now + DEVICE_WAIT_SECONDS)
    else:
        device = new_device_profile()
        promo_ready_at = now + DEVICE_WAIT_SECONDS
    sess[token] = {
        'name': name,
        'account': account,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now + hours * 3600)),
        'last_seen': None,
        'active': True,
        'address': None,
        # каждая сессия — свежее «устройство» (свои device_id/модель),
        # поэтому таймер 22 мин считаем с момента создания сессии.
        'device': device,
        'device_at': now,
        'promo_ready_at': promo_ready_at,
    }
    save_eda_sessions(sess)
    return token


def get_eda_session(token):
    if not token:
        return None
    s = load_eda_sessions().get(token)
    if not s or not s.get('active'):
        return None
    if s.get('expires_at') and s['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        return None
    return s


def set_eda_session_address(token, address):
    """Сохранить выбранный пользователем адрес доставки в сессии."""
    if not token:
        raise RuntimeError('token required')
    sess = load_eda_sessions()
    if token not in sess:
        raise RuntimeError('сессия не найдена')
    sess[token]['address'] = address or None
    save_eda_sessions(sess)
    return sess[token]['address']


# ------------------------------------------------------------
#  Продажа доступа к сессии: ключ активации.
#  Ключ многоразовый: каждый, кто его введёт, получает ссылку
#  на сессию (если сессия активна и не истекла).
# ------------------------------------------------------------

SALE_KEY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # без 0/O/1/I
SALE_KEY_FORMAT = 'ED-XXXX-XXXX-XXXX'


def _gen_sale_key():
    import secrets
    def chunk(n):
        return ''.join(secrets.choice(SALE_KEY_ALPHABET) for _ in range(n))
    return 'ED-' + '-'.join(chunk(4) for _ in range(3))


def get_sale_key(token):
    """Вернуть ключ продажи сессии; если его нет — сгенерировать."""
    if not token:
        raise RuntimeError('token required')
    sess = load_eda_sessions()
    if token not in sess:
        raise RuntimeError('сессия не найдена')
    if not sess[token].get('sale_key'):
        sess[token]['sale_key'] = _gen_sale_key()
        save_eda_sessions(sess)
    return sess[token]['sale_key']


def regenerate_sale_key(token):
    """Перегенерировать ключ продажи (старый перестаёт работать)."""
    if not token:
        raise RuntimeError('token required')
    sess = load_eda_sessions()
    if token not in sess:
        raise RuntimeError('сессия не найдена')
    sess[token]['sale_key'] = _gen_sale_key()
    save_eda_sessions(sess)
    return sess[token]['sale_key']


def activate_sale_key(key, base_url='', user_id=None):
    """Активировать ключ: закрепить за первым пользователем.

    Ключ одноразовый — после первой активации закрепляется за
    пользователем (user_id). Повторная активация тем же пользователем
    возвращает ту же ссылку, другим — отказ. Возвращает dict
    {token, url, name, expires_at, first} или бросает RuntimeError.
    """
    if not key:
        raise RuntimeError('введите ключ')
    norm = str(key).strip().upper().replace(' ', '').replace('-', '')
    if not norm:
        raise RuntimeError('ключ пустой')
    sess = load_eda_sessions()
    now = time.strftime('%Y-%m-%d %H:%M:%S')
    for token, s in sess.items():
        sk = str(s.get('sale_key') or '').strip().upper().replace(' ', '').replace('-', '')
        if sk and sk == norm:
            if not s.get('active'):
                raise RuntimeError('сессия отозвана')
            if s.get('expires_at') and s['expires_at'] < now:
                raise RuntimeError('срок сессии истёк')
            owner = s.get('sale_key_owner') or ''
            first = not bool(owner)
            if owner and user_id and owner != str(user_id):
                raise RuntimeError('ключ уже использован')
            if first:
                s['sale_key_owner'] = str(user_id or '')
                s['sale_key_activated_at'] = now
                save_eda_sessions(sess)
            base = (base_url or '').rstrip('/')
            return {
                'token': token,
                'url': f'{base}/d/{token}',
                'name': s.get('name', ''),
                'expires_at': s.get('expires_at', ''),
                'first': first,
            }
    raise RuntimeError('ключ не найден')


def get_eda_session_account(token):
    """Сессия + аккаунт, у которого device подменён на device сессии."""
    s = get_eda_session(token)
    if not s:
        return None, None
    acc = get_eda_account(s.get('account') or '')
    if not acc:
        return s, None
    if s.get('device'):
        acc = dict(acc)
        acc['device'] = dict(s['device'])
    return s, acc


def account_warmup(name, wait_seconds=DEVICE_WAIT_SECONDS):
    """Прогреть аккаунт: зафиксировать device-профиль и запустить таймер отлёжки.

    Главная идея «отлёжки»: антифрод Я.Еды считает 22 минуты с момента
    ПОЯВЛЕНИЯ устройства (первого запроса с этим device_id/моделью), а не
    с момента входа в аккаунт. Поэтому:
      1) сохраняем ОДИН фиксированный device-профиль на аккаунт,
      2) делаем лёгкий запрос профиля — Яндекс запоминает это «устройство»
         и запускает 22-мин таймер,
      3) потом любая сессия на этом аккаунте переиспользует тот же device →
         таймер НЕ сбрасывается, заказ можно делать сразу после отлёжки.
    """
    acc = get_eda_account(name)
    if not acc:
        raise RuntimeError(f'аккаунт "{name}" не найден')
    with _store_lock():
        store = _eda_read()
        accs = store.get('accounts') or []
        target = next((a for a in accs if a.get('name') == name), None)
        if not target:
            raise RuntimeError(f'аккаунт "{name}" не найден')
        # фиксируем device-профиль, если его ещё нет
        if not target.get('device'):
            target['device'] = new_device_profile()
        target['warmup_at'] = time.time()
        target['promo_ready_at'] = time.time() + wait_seconds
        store['accounts'] = accs
        _eda_write(store)
        dev = dict(target['device'])
    # регистрируем устройство у Яндекса лёгким запросом (запуск таймера)
    _eda_call(target, 'GET', '/api/v1/user/profile')
    return {'name': name, 'device': dev,
            'ready_in': max(0, target['promo_ready_at'] - time.time())}


def warmup_eda_accounts(names=None, wait_seconds=DEVICE_WAIT_SECONDS):
    """Прогреть несколько аккаунтов разом (по умолчанию — все с токеном)."""
    accs = load_eda_accounts()
    if names:
        accs = [a for a in accs if a.get('name') in names]
    out = []
    for a in accs:
        try:
            out.append(account_warmup(a.get('name'), wait_seconds))
        except Exception as e:
            out.append({'name': a.get('name'), 'error': str(e)[:140]})
    return out


def account_ready_in(name):
    """Сколько секунд осталось до готовности аккаунта к заказу (0 — готов)."""
    acc = get_eda_account(name)
    if not acc:
        return 0
    ready = acc.get('promo_ready_at')
    if not ready:
        return 0
    return max(0, ready - time.time())


def promo_ready_in(token):
    """Сколько секунд осталось до готовности промокода сессии (0 — готов)."""
    s = get_eda_session(token)
    if not s:
        return 0
    ready = s.get('promo_ready_at')
    if not ready:
        return 0
    return max(0, ready - time.time())


def guard_promo_ready(token):
    """Бросить исключение, если устройство сессии ещё «свежее» (менее 22 мин)."""
    n = promo_ready_in(token)
    if n > 0:
        e = RuntimeError(
            f'устройство свежее: промокод можно применить через '
            f'{int(n // 60)} мин {int(n % 60)} сек')
        e.promo_ready_in = n
        raise e


def touch_eda_session(token):
    sess = load_eda_sessions()
    if token in sess:
        sess[token]['last_seen'] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_eda_sessions(sess)


def revoke_eda_session(token):
    sess = load_eda_sessions()
    if token in sess:
        sess[token]['active'] = False
        save_eda_sessions(sess)
        return True
    return False


# ---------- API client ----------

def _hdrs(acc, lat=None, lon=None):
    """Заголовки запроса к Я.Еде (по образцу из дампа)."""
    lat = lat if lat is not None else float(acc.get('lat', DEFAULT_LAT))
    lon = lon if lon is not None else float(acc.get('lon', DEFAULT_LON))
    d = _dev(acc)
    h = dict(APP)
    ua_ver = d['app_version']
    h.update({
        'x-device-id': d['device_id'],
        'x-appmetrica-deviceid': d['appmetrica_deviceid'],
        'x-appmetrica-uuid': d['appmetrica_uuid'],
        'x-device-model': d['model'],
        'x-device-brand': d['brand'],
        'x-device-manufacturer': d['manufacturer'],
        'x-os-version': d['os_version'],
        'x-app-version': ua_ver,
        'x-code-version': d['code_version'],
        'user-agent': f'android ({ua_ver})',
        'x-screen-density': str(d['density']),
        'x-screen-width': str(d['width']),
        'x-screen-height': str(d['height']),
    })
    if d.get('mobile_ifa'):
        h['x-mobile-ifa'] = d['mobile_ifa']
    if d.get('tracker_id'):
        h['x-tracker-id'] = d['tracker_id']
    if d.get('yandex_device_id'):
        h['x-yandex-deviceid'] = d['yandex_device_id']
    h['authorization'] = 'Bearer ' + _extract_bearer(acc)
    h['x-yandex-uid'] = str(acc.get('yandexuid', ''))
    h['x-ya-coordinates'] = f'latitude={lat},longitude={lon}'
    h['x-ya-user-location'] = f'latitude={lat},longitude={lon}'
    ck = acc.get('cookies') or {}
    if ck:
        h['Cookie'] = '; '.join(f'{k}={v}' for k, v in ck.items())
    return h


def _eda_call(account, method, path, lat=None, lon=None, json_body=None, params=None, timeout=25):
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not acc:
        raise RuntimeError(f'аккаунт "{account}" не найден')
    hdrs = _hdrs(acc, lat, lon)
    url = EDA_HOST + path
    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        r = requests.request(method, url, headers=hdrs, json=json_body,
                             params=params, timeout=timeout, proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Еда: сеть ({method} {path}): {e}')
    if r.status_code in (401, 403):
        raise RuntimeError(f'Я.Еда: авторизация отклонена ({r.status_code}): токен устарел/невалиден')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Еда: HTTP {r.status_code} на {method} {path}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def _coords(acc, lat, lon):
    lat = lat if lat is not None else float(acc.get('lat', DEFAULT_LAT))
    lon = lon if lon is not None else float(acc.get('lon', DEFAULT_LON))
    return lat, lon


def profile(account, lat=None, lon=None):
    """Профиль пользователя."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', '/api/v1/user/profile', lat, lon)


def plus_balance(account, lat=None, lon=None):
    """Баллы и статус Я.Плюс через GraphQL api.plus.yandex.net (PlusState).

    Запрос — копия из перехвата flows_eda.mitm. Возвращает dict:
    {balance: float|None, currency: str, status: str}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    bearer = _extract_bearer(acc)
    if not bearer:
        raise RuntimeError('нет Bearer-токена')
    uid = str(acc.get('yandexuid') or '')
    body = {
        "operationName": "PlusState",
        "variables": {
            "uid": uid,
            "locationInput": {"geoPinPosition": {"accuracy": 0.0, "latitude": lat, "longitude": lon}},
        },
        "query": "query PlusState($uid: ID, $locationInput: LocationInput) { user(id: $uid) { __typename "
                 "loyaltyInfo(location: $locationInput) { __typename amount currency } status } }",
    }
    hdrs = {
        'Accept': 'application/json',
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': f'OAuth {bearer}',
        'X-Yandex-Plus-AppId': 'ru.foodfox.client',
        'X-Yandex-Plus-HostAppVersion': _dev(acc)['app_version'],
        'X-Yandex-DeviceID': _dev(acc)['device_id'],
        'X-Yandex-Plus-Platform': 'Android',
        'X-Yandex-PUID': uid,
        'X-Yandex-Plus-SdkVersion': '52.0.0',
        'X-Yandex-Plus-Service': 'eda',
        'X-Yandex-Plus-Source': 'PlusSdk',
        'X-Yandex-UUID': _dev(acc)['appmetrica_uuid'],
        'User-Agent': 'okhttp/4.11.0',
    }
    try:
        r = requests.post('https://api.plus.yandex.net/graphql', headers=hdrs,
                          json=body, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Плюс: сеть (graphql PlusState): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Плюс: HTTP {r.status_code} (PlusState): {r.text[:300]}')
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f'Я.Плюс: ответ не JSON: {r.text[:200]}')
    user = ((d.get('data') or {}).get('user') or {})
    li = user.get('loyaltyInfo') or []
    if isinstance(li, dict):
        li = [li]
    item = li[0] if li else {}
    return {
        'balance': item.get('amount'),
        'currency': item.get('currency') or '',
        'status': user.get('status') or '',
    }


def profile_name(account, lat=None, lon=None):
    """Настоящее имя владельца аккаунта (first_name, либо email/телефон)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    d = _eda_call(acc, 'GET', '/api/v1/user/profile', lat, lon)
    if not isinstance(d, dict):
        return ''
    fn = (d.get('first_name') or '').strip()
    if fn:
        return fn
    for k in ('email', 'phone_number'):
        v = (d.get(k) or '').strip()
        if v:
            return v
    return str(d.get('passport_uid') or '')


def addresses(account, lat=None, lon=None):
    """Сохранённые адреса пользователя."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', '/api/v3/user/addresses', lat, lon)


def saved_addresses(account, lat=None, lon=None):
    """Сохранённые адреса аккаунта, нормализованные для UI и checkout.

    Возвращает список {id, title, type, city, street, house, short_text,
    full_text, location{latitude,longitude}, uri}. Ошибки полей отбрасываются.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    d = addresses(acc, lat=lat, lon=lon)
    out = []
    if not isinstance(d, list):
        return out
    for a in d:
        if not isinstance(a, dict):
            continue
        loc = a.get('location') or {}
        if not isinstance(loc, dict):
            loc = {}
        entry = {
            'id': a.get('id') or '',
            'title': a.get('title') or '',
            'type': (a.get('type') or {}).get('name') if isinstance(a.get('type'), dict) else '',
            'city': a.get('city') or '',
            'street': a.get('street') or '',
            'house': a.get('house') or '',
            'short_text': a.get('short_text') or '',
            'full_text': a.get('full_text') or '',
            'uri': a.get('uri') or '',
            'location': {
                'latitude': loc.get('latitude'),
                'longitude': loc.get('longitude'),
            },
        }
        out.append(entry)
    return out


def saved_cities(account, lat=None, lon=None):
    """Города из сохранённых адресов аккаунта.

    Сначала веб-флоу (Session_id), при ошибке — мобильный (Bearer).
    Возвращает список {city, addresses: [...]}. Координаты города берутся
    из первого адреса в нём (для поиска ресторанов).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    try:
        addrs = web_saved_addresses(acc, lat=lat, lon=lon)
    except RuntimeError:
        addrs = saved_addresses(acc, lat=lat, lon=lon)
    cities = {}
    order = []
    for a in addrs:
        c = (a.get('city') or '').strip() or 'Город'
        if c not in cities:
            cities[c] = []
            order.append(c)
        cities[c].append(a)
    return [{'city': c, 'addresses': cities[c]} for c in order]


def checkout_address(saved, flat='', entrance='', floor='', intercom='', comment=''):
    """Собрать dict адреса для checkout из сохранённого адреса + полей квартиры.

    Поля flat/entrance/floor/intercom/comment добавляются только если заданы
    (Я.Еда их принимает как address.comment / address.house + доп. строки).
    """
    a = dict(saved or {})
    loc = a.get('location') or {}
    if not isinstance(loc, dict):
        loc = {}
    addr = {
        'city': a.get('city') or 'Омск',
        'street': a.get('street') or '',
        'house': a.get('house') or '',
        'country': a.get('country') or 'Россия',
        'short_text': a.get('short_text') or '',
        'full_text': a.get('full_text') or '',
        'location': {
            'latitude': loc.get('latitude') or DEFAULT_LAT,
            'longitude': loc.get('longitude') or DEFAULT_LON,
        },
    }
    if a.get('uri'):
        addr['uri'] = a['uri']
    if a.get('id'):
        addr['id'] = a['id']
    parts = []
    if flat:
        parts.append(f'кв {flat}')
    if entrance:
        parts.append(f'под {entrance}')
    if floor:
        parts.append(f'эт {floor}')
    if intercom:
        parts.append(f'домофон {intercom}')
    if comment:
        parts.append(comment)
    if parts:
        addr['comment'] = '; '.join(parts)
    return addr


def search_restaurants(account, query='', lat=None, lon=None):
    """Поиск ресторанов/каталог (full-text-search).

    Для аккаунтов без Bearer (только Session_id) — тот же эндпоинт
    через веб-флоу (cookie-авторизация).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    body = {'location': {'latitude': lat, 'longitude': lon},
            'text': query or '',
            'shipping_type': 'delivery',
            'selector': ''}
    if _use_web(acc):
        return _web_call(acc, 'POST', '/eats/v1/full-text-search/v1/search', body)
    return _eda_call(acc, 'POST', '/eats/v1/full-text-search/v1/search',
                     lat, lon, json_body=body)


def restaurant_menu(account, slug, lat=None, lon=None, shipping='delivery'):
    """Меню ресторана по slug (категории, товары).

    Для аккаунтов без Bearer (только Session_id) — веб-флоу.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {'latitude': lat, 'longitude': lon, 'shippingType': shipping}
    if _use_web(acc):
        return _web_call(acc, 'GET', f'/api/v2/menu/retrieve/{slug}', params=params)
    return _eda_call(acc, 'GET', f'/api/v2/menu/retrieve/{slug}',
                     lat, lon, params=params)


def restaurant_info(account, slug, lat=None, lon=None, shipping='delivery'):
    """Карточка ресторана (название, рейтинг, время)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'GET', f'/api/v2/catalog/{slug}',
                     lat, lon,
                     params={'latitude': lat, 'longitude': lon,
                             'shippingType': shipping, 'is_ad': 'true'})


def layout(account, view=None, lat=None, lon=None):
    """Главный экран / раздел (layout-constructor).

    view — dict вида {'type': 'collection', 'slug': 'restaurants'} для раздела
    (food_department, cosmetic_department, flowers_department). Без view — главный.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    body = {'location': {'latitude': lat, 'longitude': lon},
            'filters_v2': {'filters': []}}
    if view:
        body['view'] = view
    return _eda_call(acc, 'POST', '/eats/v1/layout-constructor/v1/layout',
                     lat, lon, json_body=body)


def shop_categories(account, slug, lat=None, lon=None):
    """Дерево категорий магазина (menu/goods, maxDepth=1)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST', '/api/v2/menu/goods', lat, lon, json_body={
        'slug': slug, 'latitude': lat, 'longitude': lon,
        'maxDepth': 1, 'filters': {}, 'shippingType': 'delivery'})


def shop_category(account, slug, category_uid, lat=None, lon=None):
    """Поддерево категории магазина (провал внутрь, как в приложении)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST', '/api/v2/menu/goods', lat, lon, json_body={
        'slug': slug, 'latitude': lat, 'longitude': lon,
        'category_uid': str(category_uid), 'maxDepth': 100,
        'filters': {}, 'shippingType': 'delivery'})


def shop_info(account, slug, lat=None, lon=None):
    """Карточка магазина: рейтинг, время доставки, адрес, логотип."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'GET', f'/api/v2/catalog/{slug}',
                     lat, lon,
                     params={'latitude': lat, 'longitude': lon,
                             'shippingType': 'delivery', 'is_ad': 'true'})


def shop_search(account, slug, text='', lat=None, lon=None):
    """Поиск внутри магазина (часто ищут + результаты)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST', '/api/v1/menu/search', lat, lon,
                     json_body={'place_slug': slug, 'text': text or ''})


def shop_goods(account, slug, category_uids, lat=None, lon=None):
    """Товары магазина по категориям (get-categories, до 25 шт на категорию)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    cats = [{'uid': str(u), 'min_items_count': 1, 'max_items_count': 25}
            for u in category_uids]
    return _eda_call(acc, 'POST', '/api/v2/menu/goods/get-categories',
                     lat, lon, json_body={'slug': slug, 'categories': cats})


def cart(account, slug=None, lat=None, lon=None, shipping='delivery', screen='menu'):
    """Текущая корзина. slug — ресторан, к которому привязана корзина.

    Для аккаунтов без Bearer (только Session_id) — веб-флоу.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {'latitude': lat, 'longitude': lon,
              'screen': screen, 'shippingType': shipping}
    if slug:
        params['placeSlug'] = slug
    if _use_web(acc):
        return _web_call(acc, 'POST', '/eats/v1/cart/v2/full-carts',
                         {}, params=params)
    return _eda_call(acc, 'POST', '/eats/v1/cart/v2/full-carts',
                     lat, lon, params=params, json_body={})


def all_carts(account, lat=None, lon=None, shipping='delivery', screen='catalog'):
    """Все корзины (для каталога/списка)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {'latitude': lat, 'longitude': lon,
              'screen': screen, 'shippingType': shipping}
    if _use_web(acc):
        return _web_call(acc, 'POST', '/eats/v1/cart/v2/multi-carts',
                         {'need_items_icons': False}, params=params)
    return _eda_call(acc, 'POST', '/eats/v1/cart/v2/multi-carts',
                     lat, lon, params=params,
                     json_body={'need_items_icons': False})


def add_to_cart(account, slug, item_id, qty=1, item_options=None, lat=None, lon=None, shipping='delivery', business='restaurant'):
    """Добавить товар в корзину. business — 'restaurant' или 'shop'.

    Для аккаунтов без Bearer (только Session_id) — веб-флоу.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    body = {
        'item_id': str(item_id),
        'quantity': int(qty or 1),
        'item_options': item_options or [],
        'place_business': business,
        'place_slug': slug,
        'shipping_type': shipping,
    }
    params = {'latitude': lat, 'longitude': lon,
              'screen': 'menu', 'shippingType': shipping,
              'soft_multi': 'true'}
    if _use_web(acc):
        return _web_call(acc, 'POST', '/api/v1/cart', body, params=params)
    return _eda_call(acc, 'POST', '/api/v1/cart',
                     lat, lon,
                     params={'latitude': lat, 'longitude': lon,
                             'screen': 'menu', 'shippingType': shipping,
                             'soft_multi': 'true'},
                     json_body=body)


def checkout(account, slug, address, lat=None, lon=None):
    """Оформление: детали заказа, offers, способы оплаты.

    address — dict из адреса (city, street, house, country, uri, short_text,
    full_text, location{latitude,longitude}).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    body = {'address': address, 'place_slug': slug,
            'payment': {'recently_link_cards': False}}
    return _eda_call(acc, 'POST', '/api/v2/cart/go-checkout',
                     lat, lon, json_body=body)


def payment_methods(account, lat=None, lon=None):
    """Доступные способы оплаты в регионе."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST',
                     '/eats/v1/eats-payment-methods-availability/v1/payment-methods/side-list',
                     lat, lon, json_body={'location': [lon, lat]})


def create_order(account, address_id, payment_id, items):
    """Создать заказ. Требует досъёмки финального шага из приложения."""
    raise NotImplementedError(
        'создание заказа Я.Еды: нужен досъём финального шага оформления '
        '(подтверждение заказа/оплата) из приложения')


# ============================================================
#  Автозаказ: веб-флоу eda.yandex.ru (desktop_web, cookie Session_id).
#
#  Эндпоинты и тела запросов подтверждены митм-перехватом браузера и
#  JS-бандлами desktop-фронта:
#    chunk 8278 — enum payment_method: EATS_PAYMENTS=5 (оплата на сайте),
#                 вызов createOrder{paymentMethodId:5, requestId: offer.requestId};
#    chunk 52038 — модель checkout: go-checkout, promocodeParams, createOrder,
#                 requestId оффера = cart_id.offer_identity;
#    chunk 67919 — order/tracking: {order_id} -> order.payment.payload.
# ============================================================

WEB_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
          '(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36')
WEB_DEVICE_ID = 'mihhc5ty-e22czsd3bl6-cr2qbh6hwbe-unsat9s5u1'

# payment_method_id для оплаты на сайте (СБП и др.) — фиксированная
# константа веб-фронта (enum EATS_PAYMENTS), не из ответов API.
WEB_PAYMENT_METHOD_EATS = 5

# Привязка карт — Trust-флоу (YandexTrustWebSDK, суперапп).
#   v2: POST trust.yandex.ru/web/create_form_url?service_token=… →
#       {form_url} — форма Траста: пользователь вводит данные карты,
#       Траст сам проводит SMS/OTP-челлендж и по success привязывает
#       карту к аккаунту (метод tokenize, flow card, integration
#       profile «yandex_default» для RU). Тела/поля взяты из
#       eats.superapp.PaymentOptions-*.js (bindCardV2 → jg → Og).
TRUST_HOST = 'https://trust.yandex.ru'
TRUST_INTEGRATION_PROFILE_RU = 'yandex_default'
TRUST_BIND_LAYOUT = 'compact'
TRUST_BIND_METHOD = 'tokenize'
TRUST_BIND_FLOW = 'card'
# Service-токен Еды (пища/руб) — тот же, что приходит в go-checkout
# (cardBindingServiceToken / add_new_card.offer.bindingServiceToken):
# fallback на захардкоженный из перехвата flows_eda_mumu.mitm.
DEFAULT_FOOD_SERVICE_TOKEN = 'food_payment_c808ddc93ffec050bf0624a4d3f3707c'


def _web_cookies(acc):
    ck = {}
    sid = (acc.get('session_id') or '').strip() or (acc.get('cookies') or {}).get('Session_id', '').strip()
    if sid:
        ck['Session_id'] = sid
    yuid = (acc.get('yandexuid') or '').strip()
    if yuid:
        ck['yandexuid'] = yuid
    return ck


def _use_web(acc):
    """True, если для аккаунта надёжнее веб-флоу (Session_id без Bearer).

    Мобильные эндпоинты (menu/cart/add_to_cart/search) принимают те же
    пути и тела с cookie Session_id (x-platform: desktop_web).
    """
    if not (acc.get('session_id') or (acc.get('cookies') or {}).get('Session_id')):
        return False
    return not _extract_bearer(acc)


def _web_hdrs(acc, lat=None, lon=None):
    lat = lat if lat is not None else float(acc.get('lat', DEFAULT_LAT))
    lon = lon if lon is not None else float(acc.get('lon', DEFAULT_LON))
    d = _dev(acc)
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://eda.yandex.ru',
        'referer': 'https://eda.yandex.ru/checkout',
        'user-agent': WEB_UA,
        'x-app-version': d['app_version'],
        'x-client-session': uuid.uuid4().hex[:32],
        'x-device-id': d['device_id'],
        'x-platform': 'desktop_web',
        'x-yandex-deviceid': d['yandex_device_id'],
        'x-retpath-y': 'https://eda.yandex.ru/checkout',
        'x-taxi': f'{WEB_UA} platform=eats_desktop_web',
        'x-ya-coordinates': f'latitude={lat},longitude={lon}',
        'x-ya-user-location': f'latitude={lat},longitude={lon}',
    }


def _web_call(acc, method, path, json_body=None, params=None, timeout=25):
    """Запрос к веб-API eda.yandex.ru с cookie Session_id (desktop_web)."""
    hdrs = _web_hdrs(acc)
    ck = _web_cookies(acc)
    url = EDA_HOST + path
    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        r = requests.request(method, url, headers=hdrs, cookies=ck,
                             json=json_body, params=params, timeout=timeout,
                             proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Еда (веб): сеть ({method} {path}): {e}')
    if r.status_code in (401, 403):
        raise RuntimeError(f'Я.Еда (веб): авторизация отклонена ({r.status_code}): Session_id невалиден')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Еда (веб): HTTP {r.status_code} на {method} {path}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def web_saved_addresses(account, lat=None, lon=None):
    """Сохранённые адреса аккаунта через веб-флоу (cookie Session_id).

    GET /api/v3/user/addresses — как это делает сайт. Возвращает список
    {id, city, street, house, country, short_text, full_text, uri,
    location{latitude,longitude}, areas, districts}. Не требует Bearer.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    d = _web_call(acc, 'GET', '/api/v3/user/addresses')
    out = []
    if not isinstance(d, list):
        return out
    for a in d:
        if not isinstance(a, dict):
            continue
        loc = a.get('location') or {}
        if not isinstance(loc, dict):
            loc = {}
        entry = {
            'id': a.get('id') or '',
            'title': a.get('title') or '',
            'type': (a.get('type') or {}).get('name') if isinstance(a.get('type'), dict) else '',
            'city': a.get('city') or '',
            'street': a.get('street') or '',
            'house': a.get('house') or '',
            'country': a.get('country') or '',
            'short_text': a.get('short_text') or '',
            'full_text': a.get('full_text') or '',
            'uri': a.get('uri') or '',
            'location': {
                'latitude': loc.get('latitude'),
                'longitude': loc.get('longitude'),
            },
        }
        if a.get('areas'):
            entry['areas'] = a['areas']
        if a.get('districts'):
            entry['districts'] = a['districts']
        out.append(entry)
    return out


def web_checkout(account, slug, address, lat=None, lon=None, payment_id='sbp_qr', payment_type='sbp'):
    """Оформление (веб): go-checkout.

    Возвращает offers — каждый с offer_identity, requestId
    (= cart_id.offer_identity) и possiblePayment{id,type,costForCustomer}.
    Пред-выбор способа (selected_payment_type) шлём только если payment_id
    задан — иначе сервер фильтрует офферы под невалидный способ.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    if isinstance(payment_id, dict):
        payment_id = payment_id.get('id') or payment_id.get('type') or 'sbp_qr'
        payment_type = payment_type or payment_id.get('type') or 'sbp'
    if isinstance(payment_type, dict):
        payment_type = payment_type.get('type') or payment_type.get('id') or 'sbp'
    body = {
        'address': address,
        'place_slug': slug,
        'payment': {
            'recently_link_cards': False,
        },
    }
    if payment_id:
        body['payment']['selected_payment_type'] = {'id': payment_id,
                                                    'type': payment_type}
    return _web_call(acc, 'POST', '/api/v2/cart/go-checkout', body,
                     params={'longitude': lon, 'latitude': lat})


def go_apply_promocode(account, slug, code, offer_identity='', lat=None, lon=None,
                       receiving_type='delivery'):
    """Применить промокод к корзине (POST /api/v2/cart/promocode).

    Идёт мобильным флоу (Bearer + device сессии) — это и есть «через go»;
    для аккаунтов без Bearer — веб-флоу (cookie Session_id). go-checkout сам
    промокоды в теле не принимает (promocodeParams всегда null), поэтому
    применяем через cart/promocode — скидка оседает в корзине и подхватывается
    последующим go-checkout.

    Ответ: {status: 'ok'|'error', err, promocode, displayStatus, discount...}.
    Причины отказа (например «Не соблюдены условия акции», «Неверный промокод»)
    приходят в err.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {
        'placeSlug': slug,
        'soft_multi': 'true',
        'shippingType': 'delivery',
        'receiving_type': receiving_type,
        'is_delivery_without_address': 'false',
    }
    if offer_identity:
        params['offer_identity'] = offer_identity
    if _use_web(acc):
        return _web_call(acc, 'POST', '/api/v2/cart/promocode',
                         {'code': code}, params=params)
    res = _eda_call(acc, 'POST', '/api/v2/cart/promocode',
                    lat, lon, params=params, json_body={'code': code})
    # Мобильный флоу для свежих промокодов (500go, FREE500 и т.п.) прячет
    # реальную причину за гейтом «Необходимо обновить приложение» — он не
    # зависит от заголовка x-app-version (проверено на 3.19.0…100.0.0),
    # а привязан к фингерпринту/каналу. Веб-флоу (Session_id) отвечает
    # честно и применяет код — при этом гейте уточняем причину через него.
    if isinstance(res, dict) and 'обновить приложение' in (res.get('err') or '') and (
            acc.get('session_id') or (acc.get('cookies') or {}).get('Session_id')):
        wr = _web_call(acc, 'POST', '/api/v2/cart/promocode',
                       {'code': code}, params=params)
        if isinstance(wr, dict) and wr.get('err'):
            wr['via'] = 'web'
            return wr
    return res


def promo_apply_checkout(account, slug, code, address, lat=None, lon=None,
                         payment_id='sbp_qr', payment_type='sbp', offer_identity=''):
    """Применить промокод (go_apply_promocode) и пересчитать корзину go-checkout.

    Скидка оседает в корзине (cart/promocode), поэтому повторный go-checkout
    без кода в теле приходит уже со свежими offers/discounts. Возвращает
    {'result': ответ cart/promocode, 'checkout', 'payment', 'available'} —
    если промокод не применился (result.status == 'error'), пересчёт пропускается.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    res = go_apply_promocode(acc, slug, code, offer_identity=offer_identity,
                             lat=lat, lon=lon)
    out = {'result': res}
    if not (isinstance(res, dict) and res.get('status') == 'error'):
        try:
            d = web_checkout(acc, slug, address, lat=lat, lon=lon,
                             payment_id=payment_id, payment_type=payment_type)
            offer, pp = web_offer(d, payment_id, payment_type)
            if not offer or not pp:
                avail = [a for a in web_available_payments(d)
                         if a.get('type') != 'add_new_card']
                if avail:
                    first = avail[0]
                    offer, pp = web_offer(d, first.get('id') or first.get('type'),
                                          first.get('type'))
            payment = None
            if offer and pp:
                cfc = pp.get('costForCustomer') or {}
                if isinstance(cfc, dict):
                    cfc = cfc.get('value') or ''
                request_id = offer.get('requestId') or ''
                payment = {
                    'id': pp.get('id'), 'type': pp.get('type'),
                    'title': pp.get('title'),
                    'costForCustomer': cfc,
                    'serviceFee': pp.get('serviceFee'),
                    'offer_identity': offer.get('offer_identity'),
                    'requestId': request_id,
                    'cart_id': request_id.split('.')[0] if '.' in request_id else '',
                }
            out.update({'checkout': d, 'payment': payment,
                        'available': web_available_payments(d)})
        except Exception:
            pass
    return out


def web_offer(d, payment_id='sbp_qr', payment_type=None):
    """Оффер из go-checkout по способу оплаты. (offer, possiblePayment) или (None, None).

    sbp_qr — собирательный id из paymentTypeConfig: реальный оффер приходит
    с type sbp/sbp_token (например «СБП • Яндекс»), поэтому матчим и его.
    """
    for o in (d.get('offers') or []):
        pp = o.get('possiblePayment') or {}
        pid = pp.get('id')
        ptype = pp.get('type')
        if payment_id and pid and payment_id == pid:
            return o, pp
        if payment_id == 'sbp_qr' and ptype in ('sbp', 'sbp_token'):
            return o, pp
        if payment_type and ptype and payment_type == ptype:
            return o, pp
    return None, None


def web_offer_sbp(d, payment_id='sbp_qr'):
    """Оффер с СБП из go-checkout. Возвращает (offer, possiblePayment) или (None, None)."""
    return web_offer(d, payment_id, 'sbp')


def web_available_payments(d):
    """Способы оплаты из go-checkout (id, type, title, costForCustomer). Уникальные.

    Объединяет offers[].possiblePayment и верхнеуровневый paymentTypeConfig
    (список, которым пользуется сайт — там СБП есть даже когда в офферах нет).
    costForCustomer — сумма к оплате данным способом (с учётом скидки).
    """
    out = []
    seen = set()

    def add(pid, ptype, title, cfc=None):
        if title and not (pid or ptype) and 'карту' in title.lower():
            ptype = 'add_new_card'
        if pid and not ptype and pid == 'sbp_qr':
            ptype = 'sbp'
        k = pid or ptype
        if not k or k in seen:
            return
        seen.add(k)
        e = {'id': pid, 'type': ptype, 'title': title}
        if cfc is not None:
            if isinstance(cfc, dict):
                cfc = cfc.get('value') or cfc.get('amount') or ''
            e['costForCustomer'] = cfc
        out.append(e)

    for o in (d.get('offers') or []):
        pp = o.get('possiblePayment') or {}
        if pp:
            add(pp.get('id'), pp.get('type'), pp.get('title'),
                pp.get('costForCustomer'))
    for cfg in (d.get('paymentTypeConfig') or []):
        add(cfg.get('id'), cfg.get('type'), cfg.get('title'))
    return out


def order_payment_pick(d, payment_id='sbp_qr', payment_type=None):
    """Выбрать (offer, possiblePayment) для создания заказа.

    Ищем оффер под запрошенный способ (web_offer). Форсировать способ, для
    которого нет своего оффера, нельзя: сервер отвечает code 59 («спрос
    вырос, доставка подорожала») — это маскировка невалидной пары
    request_id/способ оплаты. Поэтому при отсутствии оффера возвращаем
    (None, None, meta) — маршрут отдаст честную ошибку 'недоступен'.
    Возвращает (offer, pp, meta) — meta с диагностикой.
    """
    offer, pp = web_offer(d, payment_id, payment_type)
    pays = []
    for o in (d.get('offers') or []):
        m = o.get('possiblePayment') or {}
        pays.append((m.get('id'), m.get('type')))
    meta = {'offers_pays': pays, 'fallback': False}
    if offer and pp:
        return offer, pp, meta
    meta['sbp_in_config'] = any(
        c.get('id') == 'sbp_qr' or c.get('type') in ('sbp', 'sbp_token')
        for c in (d.get('paymentTypeConfig') or []))
    return None, None, meta


def web_apply_promocode(account, slug, code, offer_identity='', lat=None, lon=None,
                        receiving_type='delivery'):
    """Применить промокод к корзине (POST /api/v2/cart/promocode)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {
        'placeSlug': slug,
        'soft_multi': 'true',
        'shippingType': 'delivery',
        'receiving_type': receiving_type,
        'is_delivery_without_address': 'false',
    }
    if offer_identity:
        params['offer_identity'] = offer_identity
    return _web_call(acc, 'POST', '/api/v2/cart/promocode',
                     {'code': code}, params=params)


def web_promocodes(account, cart_id, receiving_type='delivery'):
    """Доступные промокоды для корзины (POST /api/v1/user/promocodes/checkout).

    Ответ: {promocodes: [{code, discount, isUsed, ...}]}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _web_call(acc, 'POST', '/api/v1/user/promocodes/checkout',
                     {'cart_id': cart_id, 'receiving_type': receiving_type})


def web_create_order(account, slug, address, offer_identity, payment_info, phone='',
                     code=None, lat=None, lon=None, request_id=None, cart_id=None,
                     extended_options=None, recently_link_cards=False,
                     plus_subscription_toggle_state=False, user_address_id=None,
                     spend_plus=None):
    """Создать заказ с оплатой СБП (POST /api/v1/orders, веб-флоу).

    payment_info — possiblePayment из go-checkout (id='sbp_qr',
    type='sbp', costForCustomer.value, currency). request_id по умолчанию
    = cart_id + '.' + offer_identity (как offer.requestId на фронте).
    Ответ: {orderNr, firstOrder, ...} — orderNr используется для tracking.
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    if not request_id and cart_id:
        request_id = f'{cart_id}.{offer_identity}'
    cfc = payment_info.get('costForCustomer') or {}
    if isinstance(cfc, dict):
        currency = cfc.get('currency') or ''
        cfc = cfc.get('value') or cfc.get('amount') or ''
    else:
        currency = payment_info.get('currency') or ''
    try:
        cfc_str = f'{float(cfc):.2f}'
    except (TypeError, ValueError):
        cfc_str = str(cfc)
    body = {
        'payment_method_id': WEB_PAYMENT_METHOD_EATS,
        'phone': phone,
        'change_on': 0,
        'persons_quantity': 0,
        'payment_information': {
            'type': payment_info.get('type') or 'sbp',
            'costForCustomer': cfc_str,
            'id': payment_info.get('id') or 'sbp_qr',
            'currency': currency or 'RUB',
        },
        'extended_options': _with_spend_plus(
            extended_options if extended_options is not None else
            [{'type': 'delivery_options', 'leave_at_the_door': False}],
            spend_plus),
        'payment': {'recently_link_cards': recently_link_cards},
        'place_slug': slug,
        'address': address,
        'plus_subscription_toggle_state': plus_subscription_toggle_state,
        'request_id': request_id or '',
    }
    if code:
        body['code'] = code
    if user_address_id:
        body['user_address_id'] = user_address_id
    return _web_call(acc, 'POST', '/api/v1/orders', body)


def web_order_tracking(account, order_id):
    """Статус оплаты и данные для QR СБП (POST eats-payments order/tracking).

    Ответ: {order: {order_id, ...}, payment: {status, payload,
    error_message}, meta}. В payload для СБП — purchase_token
    (и service_token); QR рисуется в платёжной форме Trust.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _web_call(acc, 'POST', '/eats/v1/eats-payments/v1/order/tracking',
                     {'order_id': order_id})


def web_sbp_qr(account, order_id, attempts=15, delay=1.5):
    """QR для СБП по заказу.

    Поллит order/tracking пока не придёт payment.payload.purchase_token
    (изначально payment.status='pending' без payload), затем дёргает
    trust.yandex.ru/web/get_payment и возвращает processing_payment_form_url
    — контент QR (https://qr.nspk.ru/...) + токены.

    Возвращает {order_id, payment, qr_url, purchase_token, service_token}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    ck = _web_cookies(acc)
    purchase_token = service_token = ''
    tracking = None
    for _ in range(attempts):
        tracking = _web_call(acc, 'POST', '/eats/v1/eats-payments/v1/order/tracking',
                             {'order_id': order_id})
        pay = (tracking or {}).get('payment')
        if pay is None:
            pay = ((tracking or {}).get('order') or {}).get('payment') or {}
        payload = pay.get('payload') or {}
        purchase_token = payload.get('purchase_token') or ''
        service_token = payload.get('service_token') or ''
        if purchase_token:
            break
        time.sleep(delay)
    order = (tracking or {}).get('order') or {}
    out = {
        'order_id': (order.get('order') or {}).get('order_id') or order_id,
        'title': order.get('title'),
        'description': order.get('description'),
        'payment': pay if tracking else {},
        'purchase_token': purchase_token,
        'service_token': service_token,
    }
    if purchase_token:
        try:
            r = requests.get(
                'https://trust.yandex.ru/web/get_payment',
                headers={
                    'user-agent': WEB_UA,
                    'accept': '*/*',
                    'referer': 'https://trust.yandex.ru/web/payment?template_tag=desktop%2Fform',
                },
                cookies=ck,
                params={'purchase_token': purchase_token},
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                out['qr_url'] = data.get('processing_payment_form_url') or ''
                out['amount'] = data.get('amount')
                out['currency'] = data.get('currency')
                out['trust_status'] = data.get('status')
        except (requests.RequestException, ValueError) as e:
            out['trust_error'] = str(e)
    return out


# ---------- Мобильный канал (api.eda.yandex.ru, Bearer, android_app) ----------
#
#  Нативный мобильный клиент: те же пути /api/v2/cart/go-checkout и
#  /api/v1/orders, но авторизация Bearer-токеном (OAuth) и x-platform
#  android_app. Промокоды тут честно «оседают» в корзине через
#  cart/promocode (мобильный флоу), поэтому code в /api/v1/orders НЕ
#  передаём — иначе сервер перепроверяет акцию при создании заказа и
#  отдаёт 58 «Promo %promo_name% is not available anymore» (как было на
#  desktop_web). Скидка из корзины подхватывается сама.

def _ensure_bearer(acc):
    """Если у аккаунта нет Bearer, но есть Session_id — обменять на OAuth."""
    if _extract_bearer(acc):
        return acc
    sid = ((acc.get('session_id') or '').strip()
           or (acc.get('cookies') or {}).get('Session_id', '').strip())
    if not sid:
        raise RuntimeError('у аккаунта нет Bearer-токена и Session_id для обмена')
    tok, uid = exchange_sessionid(sid)
    acc['token'] = tok
    if not acc.get('yandexuid'):
        acc['yandexuid'] = uid
    return acc


def mob_checkout(account, slug, address, lat=None, lon=None,
                 payment_id='sbp_qr', payment_type='sbp'):
    """Оформление мобильным каналом: POST /api/v2/cart/go-checkout.

    Тело и формат адреса — как у веб-флоу (мобильный клиент использует
    тот же go-checkout API); авторизация Bearer + x-platform android_app.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    _ensure_bearer(acc)
    lat, lon = _coords(acc, lat, lon)
    if isinstance(payment_id, dict):
        payment_id = payment_id.get('id') or ''
        payment_type = payment_type or payment_id.get('type') or 'sbp'
    if isinstance(payment_type, dict):
        payment_type = payment_type.get('type') or 'sbp'
    body = {
        'address': address,
        'place_slug': slug,
        'payment': {
            'recently_link_cards': False,
        },
    }
    # Пред-выбор способа заставляет сервер фильтровать офферы: если способ
    # невалиден, возвращаются только карты. Для честной проверки доступности
    # и получения всех офферов пред-выбор опускаем (payment_id пустой).
    if payment_id:
        body['payment']['selected_payment_type'] = {'id': payment_id,
                                                    'type': payment_type}
    return _eda_call(acc, 'POST', '/api/v2/cart/go-checkout', lat, lon,
                     json_body=body, params={'longitude': lon, 'latitude': lat})


def mob_apply_promocode(account, slug, code, offer_identity='', lat=None, lon=None,
                        receiving_type='delivery'):
    """Применить промокод мобильным каналом: POST /api/v2/cart/promocode."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    _ensure_bearer(acc)
    lat, lon = _coords(acc, lat, lon)
    params = {
        'placeSlug': slug,
        'soft_multi': 'true',
        'shippingType': 'delivery',
        'receiving_type': receiving_type,
        'is_delivery_without_address': 'false',
    }
    if offer_identity:
        params['offer_identity'] = offer_identity
    return _eda_call(acc, 'POST', '/api/v2/cart/promocode', lat, lon,
                     params=params, json_body={'code': code})


def _with_spend_plus(extended_options, spend_plus):
    """Добавить cashback_participation (списание баллов) в extended_options.

    spend_plus — количество баллов (int/str/None). None — без списания.
    """
    if not spend_plus:
        return extended_options
    base = extended_options if extended_options is not None else []
    try:
        amt = str(int(float(spend_plus)))
    except (TypeError, ValueError):
        amt = str(spend_plus)
    out = [o for o in base
           if not (isinstance(o, dict) and o.get('type') == 'cashback_participation')]
    out.append({'type': 'cashback_participation', 'action': 'use', 'amount': amt})
    return out


def mob_create_order(account, slug, address, offer_identity, payment_info, phone='',
                     lat=None, lon=None,
                     request_id=None, cart_id=None, extended_options=None,
                     recently_link_cards=False,
                     plus_subscription_toggle_state=False, spend_plus=None):
    """Создать заказ мобильным каналом: POST /api/v1/orders (без code!).

    code не передаём: промокод уже применён к корзине через cart/promocode,
    передача code заново вызывает перепроверку акции и ошибку 58.
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    _ensure_bearer(acc)
    lat, lon = _coords(acc, lat, lon)
    if not request_id and cart_id:
        request_id = f'{cart_id}.{offer_identity}'
    cfc = payment_info.get('costForCustomer') or {}
    if isinstance(cfc, dict):
        currency = cfc.get('currency') or ''
        cfc = cfc.get('value') or cfc.get('amount') or ''
    else:
        currency = payment_info.get('currency') or ''
    try:
        cfc_str = f'{float(cfc):.2f}'
    except (TypeError, ValueError):
        cfc_str = str(cfc)
    body = {
        'payment_method_id': WEB_PAYMENT_METHOD_EATS,
        'phone': phone,
        'change_on': 0,
        'persons_quantity': 0,
        'payment_information': {
            'type': payment_info.get('type') or 'sbp',
            'costForCustomer': cfc_str,
            'id': payment_info.get('id') or 'sbp_qr',
            'currency': currency or 'RUB',
        },
        'extended_options': _with_spend_plus(
            extended_options if extended_options is not None else
            [{'type': 'delivery_options', 'leave_at_the_door': False}],
            spend_plus),
        'payment': {'recently_link_cards': recently_link_cards},
        'place_slug': slug,
        'address': address,
        'plus_subscription_toggle_state': plus_subscription_toggle_state,
        'request_id': request_id or '',
    }
    return _eda_call(acc, 'POST', '/api/v1/orders', lat, lon, json_body=body)


def mob_order_with_retry(account, slug, address, phone='',
                         payment_id='sbp_qr', payment_type='sbp',
                         lat=None, lon=None, recently_link_cards=False,
                         attempts=3, delays=(0.6, 2.5), spend_plus=None):
    """Создать заказ мобильным каналом с повторами при изменении цены.

    go-checkout → выбор оффера → /api/v1/orders. Если сервер отвечает
    code 59 («стоимость доставки временно увеличилась» / «спрос вырос»),
    оффер устарел — перезапрашиваем go-checkout (новая цена и request_id)
    и пробуем ещё раз. Возвращает (res, meta):
      res — ответ /api/v1/orders, либо None;
      meta — диагностика; при финальном code 59 содержит 'code59',
        '_d' (свежий go-checkout), 'payment' (подобранный способ/оффер) —
        маршрут отдаёт их фронту, чтобы он показал новую сумму и дал
        подтвердить заказ ещё раз (без спама быстрых повторов).
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    meta = {}
    last = None
    for i in range(max(1, attempts)):
        meta['attempts'] = i + 1
        try:
            d = mob_checkout(acc, slug, address, lat=lat, lon=lon,
                             payment_id=None, payment_type=None)
            offer, pp, m = order_payment_pick(d, payment_id, payment_type)
            meta.update({k: v for k, v in m.items() if k != '_d'})
            if not offer or not pp:
                meta['_d'] = d
                return None, meta
            meta['_d'] = d
            meta['payment'] = {
                'id': pp.get('id'), 'type': pp.get('type'),
                'title': pp.get('title'),
                'costForCustomer': pp.get('costForCustomer'),
                'serviceFee': pp.get('serviceFee'),
                'offer_identity': offer.get('offer_identity'),
                'requestId': offer.get('requestId'),
            }
            res = mob_create_order(
                acc, slug, address, offer.get('offer_identity'), pp,
                phone=phone, lat=lat, lon=lon,
                request_id=offer.get('requestId') or None,
                recently_link_cards=recently_link_cards,
                spend_plus=spend_plus)
            meta['created'] = True
            return res, meta
        except RuntimeError as e:
            last = e
            meta['last_error'] = str(e)[:300]
            is59 = bool(re.search(r'"code"\s*:\s*59', str(e)))
            if not is59:
                raise
            meta['code59'] = True
            if i < attempts - 1:
                dl = delays[i] if isinstance(delays, (list, tuple)) and i < len(delays) else delays
                time.sleep(dl)
                continue
            return None, meta
    if last:
        raise last
    return None, meta


def payment_config_brief(d):
    """Краткая сводка способов оплаты из go-checkout для диагностики.

    Возвращает paymentTypeConfig (id/type/title каждой записи) и
    offers[].possiblePayment — чтобы понять, что сервер реально отдал.
    raw_has_sbp: True, если подстрока 'sbp_qr' встречается в сыром JSON
    вообще (в т.ч. во вложенных структурах, которые мы не парсим).
    """
    raw = json.dumps(d, ensure_ascii=False)
    out = {'config': [], 'offers': [], 'raw_has_sbp': 'sbp_qr' in raw,
           'keys': list((d or {}).keys())}
    for c in (d.get('paymentTypeConfig') or []):
        if isinstance(c, dict):
            out['config'].append((c.get('id'), c.get('type'),
                                  (c.get('title') or '')[:40]))
        else:
            out['config'].append(('?', '?', str(c)[:40]))
    for o in (d.get('offers') or []):
        pp = (o or {}).get('possiblePayment') or {}
        out['offers'].append((pp.get('id'), pp.get('type'),
                              (pp.get('title') or '')[:40]))
    return out


def is_sbp_payment(payment_id, payment_type=None):
    """True, если запрошенный способ оплаты — СБП (по QR / токен)."""
    return (payment_id in ('sbp_qr', 'sbp', 'sbp_token')
            or payment_type in ('sbp', 'sbp_token'))


def web_order_with_retry(account, slug, address, phone='',
                         payment_id='sbp_qr', payment_type='sbp',
                         lat=None, lon=None, recently_link_cards=False,
                         attempts=2, delays=(1.0,), spend_plus=None):
    """Создать заказ веб-флоу (оплата на сайте, payment_method_id EATS).

    Аналог mob_order_with_retry, но каналом eda.yandex.ru (cookie Session_id,
    desktop_web). На сайте СБП-оплата даётся единым способом EATS_PAYMENTS —
    независимо от мобильных офферов, поэтому это запасной путь для СБП.
    Возвращает (res, meta) как mob_order_with_retry, meta['channel']='web'.
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    meta = {'channel': 'web'}
    last = None
    for i in range(max(1, attempts)):
        meta['attempts'] = i + 1
        try:
            d = web_checkout(acc, slug, address, lat=lat, lon=lon,
                             payment_id=payment_id, payment_type=payment_type)
            offer, pp, m = order_payment_pick(d, payment_id, payment_type)
            meta.update({k: v for k, v in m.items() if k not in ('_d',)})
            if not offer or not pp:
                meta['_d'] = d
                return None, meta
            meta['_d'] = d
            meta['payment'] = {
                'id': pp.get('id'), 'type': pp.get('type'),
                'title': pp.get('title'),
                'costForCustomer': pp.get('costForCustomer'),
                'serviceFee': pp.get('serviceFee'),
                'offer_identity': offer.get('offer_identity'),
                'requestId': offer.get('requestId'),
            }
            res = web_create_order(
                acc, slug, address, offer.get('offer_identity'), pp,
                phone=phone, code=None, lat=lat, lon=lon,
                request_id=offer.get('requestId') or None,
                recently_link_cards=recently_link_cards,
                spend_plus=spend_plus)
            meta['created'] = True
            return res, meta
        except RuntimeError as e:
            last = e
            meta['last_error'] = str(e)[:300]
            if not re.search(r'"code"\s*:\s*59', str(e)):
                raise
            meta['code59'] = True
            if i < attempts - 1:
                dl = delays[i] if isinstance(delays, (list, tuple)) and i < len(delays) else delays
                time.sleep(dl)
                continue
            return None, meta
    if last:
        raise last
    return None, meta


def eda_order_create(account, slug, address, phone='',
                     payment_id='sbp_qr', payment_type='sbp',
                     lat=None, lon=None, recently_link_cards=False,
                     spend_plus=None):
    """Создать заказ, выбирая канал: мобильный → (для СБП) веб.

    Сначала пробуем мобильный флоу (mob_order_with_retry). Если СБП в нём
    недоступно (нет оффера/конфига — бывает для некоторых аккаунтов на
    старом клиенте Foodfox) или мобильный ловит постоянный code 59, а
    способ СБП — повторяем через веб-флоу (оплата «на сайте»).
    Возвращает (res, meta); res None — заказ не создан, meta['channel']
    = 'mob'|'web', в meta диагностика для маршрута.
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not is_sbp_payment(payment_id, payment_type):
        return mob_order_with_retry(
            acc, slug, address, phone=phone,
            payment_id=payment_id, payment_type=payment_type,
            lat=lat, lon=lon, recently_link_cards=recently_link_cards,
            spend_plus=spend_plus)
    try:
        res, meta = mob_order_with_retry(
            acc, slug, address, phone=phone,
            payment_id=payment_id, payment_type=payment_type,
            lat=lat, lon=lon, recently_link_cards=recently_link_cards,
            spend_plus=spend_plus)
    except RuntimeError as e:
        res, meta = None, {'last_error': str(e)[:300]}
    if res:
        meta['channel'] = 'mob'
        return res, meta
    meta['channel'] = 'mob'
    try:
        res, wmeta = web_order_with_retry(
            acc, slug, address, phone=phone,
            payment_id=payment_id, payment_type=payment_type,
            lat=lat, lon=lon, recently_link_cards=recently_link_cards,
            spend_plus=spend_plus)
    except RuntimeError as e:
        meta['web_error'] = str(e)[:300]
        return None, meta
    if res:
        return res, wmeta
    wmeta['mob_meta'] = meta
    return None, wmeta


def mob_order_tracking(account, order_id):
    """Статус оплаты мобильным каналом: POST /eats/v1/eats-payments/v1/order/tracking."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    _ensure_bearer(acc)
    return _eda_call(acc, 'POST', '/eats/v1/eats-payments/v1/order/tracking',
                     json_body={'order_id': order_id})


def mob_sbp_qr(account, order_id, attempts=15, delay=1.5):
    """QR для СБП по заказу (мобильный канал). Аналог web_sbp_qr, но _eda_call."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    _ensure_bearer(acc)
    purchase_token = service_token = ''
    tracking = None
    for _ in range(attempts):
        tracking = _eda_call(acc, 'POST',
                             '/eats/v1/eats-payments/v1/order/tracking',
                             json_body={'order_id': order_id})
        pay = (tracking or {}).get('payment')
        if pay is None:
            pay = ((tracking or {}).get('order') or {}).get('payment') or {}
        payload = pay.get('payload') or {}
        purchase_token = payload.get('purchase_token') or ''
        service_token = payload.get('service_token') or ''
        if purchase_token:
            break
        time.sleep(delay)
    order = (tracking or {}).get('order') or {}
    out = {
        'order_id': (order.get('order_id') or order_id),
        'title': order.get('title'),
        'description': order.get('description'),
        'payment': pay if tracking else {},
        'purchase_token': purchase_token,
        'service_token': service_token,
    }
    if purchase_token:
        for hdrs, ck in (
            ({'user-agent': WEB_UA, 'accept': '*/*',
              'referer': 'https://trust.yandex.ru/web/payment?template_tag=desktop%2Fform'},
             _web_cookies(acc)),
            ({'user-agent': WEB_UA, 'accept': '*/*',
              'referer': 'https://trust.yandex.ru/web/payment?template_tag=desktop%2Fform',
              'authorization': 'OAuth ' + (_extract_bearer(acc) or '')},
             {}),
        ):
            try:
                r = requests.get(
                    'https://trust.yandex.ru/web/get_payment',
                    headers=hdrs, cookies=ck,
                    params={'purchase_token': purchase_token},
                    timeout=20,
                )
                if r.status_code == 200:
                    data = r.json()
                    out['qr_url'] = data.get('processing_payment_form_url') or ''
                    out['amount'] = data.get('amount')
                    out['currency'] = data.get('currency')
                    out['trust_status'] = data.get('status')
                    if out['qr_url']:
                        break
                    out['trust_body'] = str(data)[:300]
            except (requests.RequestException, ValueError) as e:
                out['trust_error'] = str(e)
    return out


def mob_promo_apply_checkout(account, slug, code, address, lat=None, lon=None,
                             payment_id='sbp_qr', payment_type='sbp',
                             offer_identity=''):
    """Применить промокод мобильным каналом и пересчитать корзину.

    Аналог promo_apply_checkout, но целиком на мобильном канале (Bearer).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    res = mob_apply_promocode(acc, slug, code, offer_identity=offer_identity,
                              lat=lat, lon=lon)
    out = {'result': res}
    if not (isinstance(res, dict) and res.get('status') == 'error'):
        try:
            d = mob_checkout(acc, slug, address, lat=lat, lon=lon,
                             payment_id=None, payment_type=None)
            offer, pp = web_offer(d, payment_id, payment_type)
            if not offer or not pp:
                avail = [a for a in web_available_payments(d)
                         if a.get('type') != 'add_new_card']
                if avail:
                    first = avail[0]
                    offer, pp = web_offer(d, first.get('id') or first.get('type'),
                                          first.get('type'))
            payment = None
            if offer and pp:
                cfc = pp.get('costForCustomer') or {}
                if isinstance(cfc, dict):
                    cfc = cfc.get('value') or ''
                request_id = offer.get('requestId') or ''
                payment = {
                    'id': pp.get('id'), 'type': pp.get('type'),
                    'title': pp.get('title'),
                    'costForCustomer': cfc,
                    'serviceFee': pp.get('serviceFee'),
                    'offer_identity': offer.get('offer_identity'),
                    'requestId': request_id,
                    'cart_id': request_id.split('.')[0] if '.' in request_id else '',
                }
            out.update({'checkout': d, 'payment': payment,
                        'available': web_available_payments(d)})
        except Exception:
            pass
    return out


# ---------- Привязка банковских карт (Trust web-флоу) ----------

def _trust_call(acc, method, path, json_body=None, params=None,
                service_token='', timeout=25):
    """Запрос к trust.yandex.ru (веб-флоу привязки/оплаты).

    Куки передаются как у веб-флоу еды (Session_id/yandexuid живут на
    общем домене yandex.ru, Траст их видит). service_token уходит либо
    заголовком X-Service-Token, либо query-параметром.
    """
    hdrs = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://eda.yandex.ru',
        'referer': 'https://eda.yandex.ru/checkout',
        'user-agent': WEB_UA,
    }
    if service_token:
        hdrs['X-Service-Token'] = service_token
    url = TRUST_HOST + path
    try:
        r = requests.request(method, url, headers=hdrs,
                             cookies=_web_cookies(acc),
                             json=json_body, params=params, timeout=timeout)
    except requests.RequestException as e:
        raise RuntimeError(f'Траст: сеть ({method} {path}): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Траст: HTTP {r.status_code} на {method} {path}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def web_binding_token(d):
    """Service-токен для привязки карты из ответа go-checkout.

    Сначала верхнеуровневый cardBindingServiceToken (его шлёт сайт в
    add_new_card), иначе bindingServiceToken из оффера add_new_card.
    """
    if not isinstance(d, dict):
        return ''
    token = d.get('cardBindingServiceToken') or ''
    if token:
        return token
    for o in (d.get('offers') or []):
        pp = o.get('possiblePayment') or {}
        if not isinstance(pp, dict):
            continue
        if (pp.get('type') in ('add_new_card', 'card')
                and pp.get('bindingServiceToken')):
            return pp.get('bindingServiceToken')
    return ''


def web_food_service_token(account, slug, address, lat=None, lon=None):
    """Токен сервиса Еды для Траста (берётся из go-checkout)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    try:
        d = web_checkout(acc, slug, address, lat=lat, lon=lon)
        return web_binding_token(d)
    except Exception:
        return ''


def web_bind_form_url(account, service_token='', theme='light', operation_id=''):
    """Начать привязку карты: POST trust.yandex.ru/web/create_form_url.

    Возвращает {form_url, integration_profile_id, service_token}: форма
    Траста, где пользователь вводит данные карты и код из SMS; на
    success карта привязана к аккаунту. Затем карта видна в
    web/payment_methods и в offers go-checkout.

    operation_id — идентификатор операции (обязателен для Траста,
    min 1); фронт генерирует свой, для нас достаточно uuid.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    token = service_token or DEFAULT_FOOD_SERVICE_TOKEN
    body = {
        'operation_id': operation_id or uuid.uuid4().hex,
        'anonymously': False,
        'integration_profile_id': TRUST_INTEGRATION_PROFILE_RU,
        'flow': TRUST_BIND_FLOW,
        'theme': theme or 'light',
        'lang': 'ru',
        'layout': TRUST_BIND_LAYOUT,
        'method': TRUST_BIND_METHOD,
    }
    d = _trust_call(acc, 'POST', '/web/create_form_url',
                    json_body=body, params={'service_token': token})
    form_url = d.get('form_url') or ''
    return {
        'form_url': form_url,
        'integration_profile_id': TRUST_INTEGRATION_PROFILE_RU,
        'service_token': token,
        '_status': d.get('_status') if '_status' in d else (200 if form_url else 204),
    }


def web_payment_methods(account, service_token=''):
    """Привязанные карты/способы оплаты через Траст.

    GET trust.yandex.ru/web/payment_methods?show_sbp_tokens=true с
    заголовком X-Service-Token (как loadCards в супераппе). Возвращает
    список {id: 'card-…'|'sbp-…', method_id, number, payment_system,
    card_bank, exp, ...} — только карты и СБП.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    token = service_token or DEFAULT_FOOD_SERVICE_TOKEN
    d = _trust_call(acc, 'GET', '/web/payment_methods',
                    params={'show_sbp_tokens': 'true'}, service_token=token)
    out = []
    for key, val in (d.get('payment_methods') or {}).items():
        if not isinstance(val, dict):
            continue
        if not (key.startswith('card') or key.startswith('sbp')):
            continue
        item = dict(val)
        item['id'] = key
        item['method_id'] = item.get('id')
        out.append(item)
    return out


def web_card_payments(d):
    """Карты из go-checkout (для сохранения): {id, type, title, bank?}."""
    out = []
    seen = set()
    for o in (d.get('offers') or []):
        pp = o.get('possiblePayment') or {}
        if not isinstance(pp, dict):
            continue
        if pp.get('type') != 'card' or not pp.get('id'):
            continue
        if pp['id'] in seen:
            continue
        seen.add(pp['id'])
        out.append({
            'id': pp.get('id'),
            'type': 'card',
            'title': pp.get('title') or pp.get('shortTitle') or 'Карта',
            'number': pp.get('number') or pp.get('short_number') or '',
            'description': pp.get('description') or '',
        })
    return out


def eda_cards(account):
    """Сохранённые карты аккаунта (кэш в eda_accounts.json)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    cards = acc.get('cards') or []
    return cards if isinstance(cards, list) else []


def eda_save_cards(account, cards):
    """Сохранить список карт аккаунта (кэш для UI/заказов)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not isinstance(cards, list):
        return acc.get('cards') or []
    with _store_lock():
        store = _eda_read()
        for a in store.get('accounts', []):
            if a.get('name') == acc.get('name'):
                a['cards'] = cards
                _eda_write(store)
                return cards
    return acc.get('cards') or []


# ---------- глобальные сохранённые карты (выбор в админке) ----------

EDA_CARDS_FILE = os.path.join(core.DATA_DIR, 'eda_cards.json')


def load_eda_cards():
    """Глобальный список сохранённых карт: [{id, label, card, ...}].

    Карта хранится сырой строкой вида "4276 4013 9880 1234 12/27 123" —
    тот же формат, что принимает plus_parse_card/plus_subscribe.
    """
    try:
        with open(EDA_CARDS_FILE, encoding='utf-8') as f:
            cards = json.load(f)
        return cards if isinstance(cards, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_eda_cards(cards):
    """Атомарно записать глобальный список карт (см. _eda_write)."""
    if not isinstance(cards, list):
        return
    tmp = EDA_CARDS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, EDA_CARDS_FILE)


def eda_card_add(label, card):
    """Валидировать и сохранить новую карту. Возвращает запись карты.

    Принимает строку "4276… 12/27 123" или dict {number, expiry, csc}.
    Бросает RuntimeError с понятным сообщением, если карта не распознаётся
    (plus_parse_card). В запись кладутся маска номера и срок для отображения.
    """
    parsed = plus_parse_card(card)
    cards = load_eda_cards()
    cid = 'card%d' % int(time.time() * 1000)
    while any(c.get('id') == cid for c in cards):
        cid = 'card%d' % (int(cid[4:]) + 1)
    num = parsed.get('number', '')
    csc = parsed.get('csc', '')
    canon = num
    if parsed.get('exp_month') and parsed.get('exp_year'):
        canon += ' %s/%s' % (parsed['exp_month'], parsed['exp_year'][2:])
    if csc:
        canon += ' ' + csc
    entry = {
        'id': cid,
        'label': (label or '').strip() or ('**** ' + num[-4:]),
        'card': canon,
        'mask': num[-4:] if len(num) >= 4 else num,
        'exp': '%s/%s' % (parsed.get('exp_month', ''), parsed.get('exp_year', '')[2:]),
    }
    cards.append(entry)
    save_eda_cards(cards)
    return entry


def eda_card_delete(cid):
    """Удалить сохранённую карту по id. Возвращает True, если была удалена."""
    cards = load_eda_cards()
    out = [c for c in cards if c.get('id') != cid]
    if len(out) == len(cards):
        return False
    save_eda_cards(out)
    return True


# ============================================================
#  Подключение подписки «Яндекс Плюс» (акция в Едадиле).
#
#  Эндпоинты из перехвата флоу в com.edadeal.android:
#    0) trigger-proxy.edadeal.ru/triggers/<promo_id>?krokenUuid=<uuid>
#       — колбек акции; ВЫЗЫВАТЬ ПЕРЕД подключением подписки
#       на КАЖДОМ аккаунте (требование флоу);
#    1) api.plus.yandex.ru/generate-csrf-token   — csrf для plus-API;
#    2) diehard.yandex.ru/web/bin_info           — инфо по BIN карты;
#    3) trust.yandex.ru/web/update_payment?purchase_token=payment_…
#       — привязать карту к покупке подписки;
#    4) trust.yandex.ru/web/start_payment_json?purchase_token=…
#       — запустить платёж (здесь SMS/3DS-подтверждение);
#    5) api.plus.yandex.ru/graphql (query_name=invoiceStatus) — статус;
#    6) trust.yandex.ru/web/check_payment?purchase_token=…      — статус.
#
#  Авторизация везде — passport-куки аккаунта (Session_id/yandexuid).
#  purchase_token создаётся стороной Плюса ДО update_payment (см.
#  plus_purchase_init: если источника в ответах нет — заявлен, где брать).
# ============================================================

PLUS_API = 'https://api.plus.yandex.ru'
PLUS_ACQ_API = 'https://api.acquisition-gwe.plus.yandex.ru'
MEDIA_BILLING_API = 'https://external-api.mediabilling.yandex.ru'
PLUS_DIEHARD = 'https://diehard.yandex.ru'
EDADEAL_TRIGGER = 'https://trigger-proxy.edadeal.ru'
# UA и Origin из реального перехвата веб-флоу виджета оплаты Плюса.
PLUS_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
           '(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36')
CARD_WIDGET_ORIGIN = 'https://payment-widget.plus.yandex.ru'
CARD_FORM_ORIGIN = 'https://card-form.diehard.yandex.net'
# Реальный target виджета из захвата (лэндинг plus.yandex.ru с
# target=plus-web → виджет идёт на plus-web-random-trial с тариффикатором).
PLUS_WIDGET_TARGET = 'plus-web-random-trial'
# experimentFlags из createInvoice (захват seq 49).
PLUS_EXP_FLAGS = [
    'isUpsaleEnabled', 'isUserContactsEnabled', 'isSkipUserContactButton',
    'isMailingOfferEnabled', 'isAddToFamilyEnabled', 'enableMetricaAnalytics',
    'sbpNew', 'sbpWeb', 'sbpTrustSDK', 'applePayPayment', 'yabankNew',
    'isCounterOfferEnabled', 'counterOfferNoPromocode', 'isTokenizationEnabled',
    'disableSuccessScreenAppsBlock', 'mergeAvailableAndUsefulAppsBlocks',
    'showPayPromoBannerOnSuccessScreen', 'bynToNewSymbol', 'closingOffer',
    'tarifficatorDWHLogging', 'showCheckoutAdditionalOffers',
    'plus_year_checkout_onsale', 'closeButtonToSuccessScreen', 'payAutoCompletion',
    'payCashbackScreen', 'useBackCounterOffer', 'iboLinksFlowEnabled',
    'iboS7LinksFlowEnabled', 'swapIboLinksFlow', 'webvisorEnabled',
    'useTrustSDKChallenge', 'pay_topup_bonus', 'all_user',
    'bdo_points_option_samokat_200', 'bdo_points_option_s7boost_200',
    'bdo_points_option_start_250', 'bdo_points_option_kion_299',
]
# testIds виджета (expTestIds контекста /api/v2/offers и testIds URL виджета).
PLUS_TEST_IDS = [
    1578231, 1580963, 1626195, 1554861, 569477, 569856, 672411, 715832,
    779148, 810164, 810169, 836427, 836669, 838877, 851965, 852000, 880638,
    880686, 895424, 895743, 901564, 901570, 906324, 907765, 936992, 957923,
    964666, 980751, 980753, 980760, 980761, 926142, 997729, 1011102, 1035877,
    1035967, 1051228, 1058076, 1069038, 1083166, 1083948, 1084809, 1086269,
    1108667, 1108698, 1116768, 1119104, 1121702, 1139468, 1140734, 1145181,
    1148680, 1154610, 1156185, 1165865, 1166347, 1169606, 1172554, 1173405,
    1190297, 1194584, 1197107, 1202942, 1211602, 1215427, 1215871, 1202437,
    1220101, 1237332, 1244840, 1250082, 1251904, 1267588, 1285288, 1296335,
    1296337, 1298931, 1305631, 1306698, 1309750, 1314801, 1320626, 1326631,
    1328540, 1330700, 1346232, 1353400, 1354129, 1355983, 1356368, 1365803,
    1370472, 1371180, 1383152, 1384874, 1389210, 1389433, 1392712, 1402212,
    1407183, 1407674, 1409768, 1421934, 1451655, 1458975, 1437356, 1469561,
    1469562, 1470184, 1477988, 1481993, 1495568, 1514931, 1521814, 1524588,
    1524590, 1531492, 1546847, 1547927, 1556590, 1550674, 1563194, 1563199,
    1569325, 1569399, 1580377, 1594336, 1594361, 1594345, 1594356, 1594346,
    1594348, 1600045, 1600047, 1600048, 1603403, 1603414, 1604548, 1607083,
    1615430, 1644634, 1644647, 1653662, 1653610, 1658261, 1658264, 1658267,
    1658278, 1658297, 1658298, 1658300, 1642650, 1643165, 1643172, 1660860,
    1512508, 1493967, 1657285, 1581847, 1640046, 1650325, 1596305, 1644919,
    1622326, 1616775, 1639742, 1643648, 1657260, 1647289, 1655582, 1578349,
    1643410, 1520984, 1522650, 1533851, 1643342, 1631482, 1639440, 1639886,
    1520213, 1640605, 1627997, 1619947, 1641187, 1645657, 1645923, 1645946,
    1646373, 1646385, 1647102, 1647110, 1655158, 1493578, 1639752, 1539361,
    1614668, 1639571, 1541054, 1571287, 1396102, 1367248, 1501812, 1472059,
    1639284, 1518957, 1633468, 1643282, 1638489, 1640510, 1523992, 1396143,
    1614361, 1658058, 1656450, 1527189, 1656456, 1656458, 1492688, 1540879,
    1561995, 1607091, 1657550, 1649396, 1632816, 1652378, 1643215, 1644297,
    1632365, 1482939, 1391742, 1398168, 1448219, 1406911, 1422897, 1433625,
    1495612,
]
# promo_id и krokenUuid из перехвата (акция «подписка Плюс» в Едадиле).
# krokenUuid уникален для аккаунта; promo_id — константа акции.
PLUS_TRIGGER_ID = '7964dad0-5589-4c5f-8594-aa227deba4b8'
PLUS_TRIGGER_REFERER = 'https://eda.yandex.ru/'
# Офферы лендингов Плюса для подключения подписки. Пробуются по очереди:
# если первый недоступен аккаунту — следующие (пользователь: "Если один не
# доступен — пробовать другой"). Перед каждым — via /api/v2/offers.
PLUS_LANDING_PERF = ('https://plus.yandex.ru/perf/plus'
                     '?utm_source=direct_search&utm_medium=paid_performance'
                     '&utm_campaign=704139747|MSCAMP-62_%5BPL-P%5D_%7BWS%3AS%7D_RU-225_goal-PL_upc-BRAND-LP%2F%2Fstrategy-test%20maxCPC'
                     '&utm_term=%D1%8F%D0%BD%D0%B4%D0%B5%D0%BA%D1%81%20%D0%BF%D0%BB%D1%8E%D1%81'
                     '&utm_content=cid|704139747|gid|5664383735|aid|17354566575'
                     '&etext=2202.2ahaDfty1dut2LIJvnafGZSQbEsfP4kYzdNpqOvPcFR6cW15b2xtZXlyY2Zwd2pi.13bd4db11cd3c9156abde2f7f52ac2679d425e42'
                     '&yclid=12948877443478847487')
PLUS_LANDING_DEFAULT = 'https://plus.yandex.ru/?ysclid=mswuugft6z635156719'
PLUS_LANDING_OFFERS = [PLUS_LANDING_PERF, PLUS_LANDING_DEFAULT]


def _plus_hdrs(acc, csrf='', referer='', extra=None):
    hdrs = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/json;charset=UTF-8',
        'user-agent': PLUS_UA,
    }
    if referer:
        hdrs['referer'] = referer
    if csrf:
        # Реальный заголовок api.plus.yandex.ru из перехвата виджета
        # (createInvoice/startInvoice) — x-ya-csrf-token.
        hdrs['x-ya-csrf-token'] = csrf
    if extra:
        hdrs.update(extra)
    return hdrs


def _plus_call(acc, host, method, path, json_body=None, data=None,
               params=None, csrf='', referer='', extra_headers=None,
               timeout=30):
    """Запрос к plus/diehard/trust с passport-куками аккаунта.

    json_body — тело JSON (Content-Type application/json),
    data — form-urlencoded тело (Content-Type переопределяется в headers).
    """
    hdrs = _plus_hdrs(acc, csrf, referer, extra_headers)
    url = host + path
    if params:
        sep = '&' if '?' in url else '?'
        url += sep + urllib.parse.urlencode({k: v for k, v in params.items()
                                             if v is not None and v != ''})
    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        r = requests.request(method, url, headers=hdrs, cookies=_web_cookies(acc),
                             json=json_body, data=data, timeout=timeout,
                             proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Плюс: сеть ({method} {path}): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Плюс: HTTP {r.status_code} на {method} {path}: {r.text[:400]}')
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def _dig(d, *keys):
    for k in keys:
        if isinstance(d, dict):
            d = d.get(k)
        else:
            return None
    return d


def _plus_token(data):
    """Вытащить искомый токен/переменную из JSON-ответа (в т.ч. вложенного)."""
    import json as _json
    stack, found = [data], []
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                kl = (k or '').lower()
                if any(s in kl for s in ('csrf', 'token')):
                    if isinstance(v, str) and v:
                        found.append(v)
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(cur)
    seen, out = set(), []
    for v in found:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def edadeal_authenticate(account):
    """Авторизация в Едадиле (по флоу edadil_bot): обмен Yandex OAuth-токена
    на JWT Едадила.

    1) Регистрация анонимного устройства: POST /api/usr/auth/v1/device
       -> анонимный JWT (заголовок Authorization) + edadeal-duid.
    2) Обмен: POST /api/usr/auth/v1/auth {"duid", "provider":"am",
       "token": <yandex OAuth token>} -> JWT + edadeal-uid + edadeal-duid.

    Возвращает {'ok': True, 'jwt':…, 'duid':…, 'uid':…, 'login':…}
    либо {'ok': False, 'error':…}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    tok = _extract_bearer(acc)
    if not tok:
        return {'ok': False, 'error': 'нет OAuth-токена Яндекса (token/webviewtoken)'}
    hdrs = {
        'User-Agent': 'okhttp/4.11.0 Edadeal/26.28.0',
        'Accept': 'application/json',
        'Accept-Language': 'ru_RU',
        'Content-Type': 'application/json',
        'x-platform': 'android',
        'x-os-version': '12.0.0',
        'x-app-version': '26.28.0',
        'x-app-id': 'edadeal',
        'x-locality-geoid': '66',
        'x-locality-countrygeoid': '225',
        'x-real-locality-geoid': '66',
        'x-real-locality-countrygeoid': '225',
        'x-position-latitude': '54.98934200',
        'x-position-longitude': '73.36821200',
        'x-device-timezone': 'Asia/Omsk',
        'x-device-manufacturer': 'SAMSUNG',
        'x-device-model': 'SM-F711B',
        'x-device-ram-class': '3',
        'amversion': '7.54.1',
    }
    try:
        # 1) анонимное устройство
        r1 = requests.post(
            'https://api.edadeal.ru/api/usr/auth/v1/device',
            headers={**hdrs, 'x-device-init-timestamp': str(int(time.time()))},
            json={'platform': 'android', 'device_id': uuid.uuid4().hex,
                  'uuid': uuid.uuid4().hex},
            timeout=20)
        if r1.status_code != 200:
            return {'ok': False,
                    'error': f'Регистрация устройства Едадил: HTTP {r1.status_code}: {r1.text[:200]}'}
        anon_jwt = r1.headers.get('authorization', '')
        anon_duid = r1.headers.get('edadeal-duid', '')
        if not anon_jwt:
            return {'ok': False, 'error': 'Едадил: нет анонимного JWT'}
        # 2) обмен на JWT аккаунта
        r2 = requests.post(
            'https://api.edadeal.ru/api/usr/auth/v1/auth',
            headers={**hdrs, 'Authorization': anon_jwt,
                     'edadeal-duid': anon_duid},
            json={'duid': anon_duid, 'provider': 'am', 'token': tok},
            timeout=20)
        if r2.status_code != 200:
            err = r2.headers.get('Www-Authenticate', r2.text[:200])
            return {'ok': False, 'error': f'Авторизация Едадил: HTTP {r2.status_code}: {err}'}
        jwt = r2.headers.get('authorization', '')
        uid = r2.headers.get('edadeal-uid', '')
        duid = r2.headers.get('edadeal-duid', anon_duid)
        if not jwt:
            return {'ok': False, 'error': 'Едадил: нет JWT в ответе auth'}
        login = ''
        try:
            m = jwt.split('.')
            if len(m) == 3:
                import base64 as _b64
                p = m[1] + '=' * (4 - len(m[1]) % 4)
                d = json.loads(_b64.urlsafe_b64decode(p))
                login = d.get('sub', uid)
        except Exception:
            pass
        return {'ok': True, 'jwt': jwt, 'duid': duid, 'uid': uid, 'login': login}
    except requests.RequestException as e:
        return {'ok': False, 'error': f'Едадил: сеть: {e}'}


def edadeal_check_yandex_token(account):
    """Проверка OAuth-токена Яндекса аккаунта через login.yandex.ru/info."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    tok = _extract_bearer(acc)
    if not tok:
        return {'ok': False, 'error': 'нет OAuth-токена Яндекса'}
    try:
        r = requests.get('https://login.yandex.ru/info',
                         headers={'Authorization': f'OAuth {tok}'}, timeout=20)
        if r.status_code != 200:
            return {'ok': False, 'error': f'Яндекс: HTTP {r.status_code}'}
        d = r.json()
        return {'ok': True, 'login': d.get('login', ''),
                'name': d.get('display_name', d.get('real_name', ''))}
    except requests.RequestException as e:
        return {'ok': False, 'error': f'Яндекс: сеть: {e}'}


def edadeal_trigger(account, promo_id='', kroken_uuid=''):
    """Колбек акции Едадила на аккаунте: вызов перед подключением Плюса.

    trigger_proxy.edadeal.ru/triggers/<promo_id>?krokenUuid=<uuid4>.
    Должен выполняться на каждом аккаунте перед подпиской.
    Авторизация — JWT Едадила (edadeal_authenticate), не паспорт-куки.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    pid = promo_id or PLUS_TRIGGER_ID
    ku = kroken_uuid or uuid.uuid4().hex
    auth = edadeal_authenticate(acc)
    if not auth.get('ok'):
        raise RuntimeError(f'Плюс: триггер Едадила: авторизация: {auth.get("error")}')
    params = {'krokenUuid': ku}
    url = f'{EDADEAL_TRIGGER}/triggers/{pid}'
    if params:
        url += '?' + urllib.parse.urlencode({k: v for k, v in params.items()
                                              if v is not None and v != ''})
    hdrs = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'user-agent': PLUS_UA,
        'referer': PLUS_TRIGGER_REFERER,
        'Authorization': auth['jwt'],
        'edadeal-duid': auth['duid'],
        'edadeal-uid': auth['uid'],
    }
    try:
        r = requests.get(url, headers=hdrs, timeout=25, allow_redirects=False)
    except requests.RequestException as e:
        raise RuntimeError(f'Плюс: триггер Едадила: сеть: {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Плюс: триггер Едадила: HTTP {r.status_code}: {r.text[:300]}')
    return {'ok': True, 'promo_id': pid, 'kroken_uuid': ku,
            'status': r.status_code,
            'response': {'_status': r.status_code,
                         '_text': r.text[:300] if r.text else ''}}


def _plus_widget_hdrs():
    """Заголовки payment-widget (api.plus + trust update/check_payment)."""
    return {
        'accept': '*/*',
        'content-type': 'application/json; utf-8',
        'origin': CARD_WIDGET_ORIGIN,
        'x-yandex-plus-brand': 'yandex',
        'x-yandex-plus-checkout-platform': 'WEB',
        'x-yandex-plus-widgetservice': 'landing_plus',
    }


def plus_csrf(account, method='GET'):
    """CSRF-токен для api.plus.yandex.ru (generate-csrf-token).

    Как в перехвате: GET без тела, Origin/Referer payment-widget.plus.yandex.ru,
    заголовки x-yandex-plus-* (в curl запрос не показывал метод — сервер
    отдаёт 405 на POST, значит это GET). Возвращает строку токена; ищем по
    именам csrf/token.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    d = _plus_call(acc, PLUS_API, method, '/generate-csrf-token',
                   referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    toks = _plus_token(d)
    csrf = next((t for t in toks if 'csrf' in t.lower()), toks[0] if toks else '')
    if not csrf:
        raise RuntimeError(f'Плюс: generate-csrf-token не вернул токен: {str(d)[:300]}')
    return csrf


def plus_card_bin(account, number, bin_last='', csc_hint=(0, 0), avail_pub_key=''):
    """Инфо по карте через diehard: POST diehard.yandex.ru/web/bin_info.

    Как в реальном перехвате: тело JSON {"params":{"prefix":"<первые 8 цифр>"}},
    Origin/Referer card-form.diehard.yandex.net, заголовок X-Request-Id.
    (bin_last/csc_hint/avail_pub_key оставлены для совместимости — в перехвате
    не используются.)
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    number = re.sub(r'\D', '', (number or ''))
    prefix8 = number[:8]
    req_id = uuid.uuid4().hex[:16]
    body = {'params': {'prefix': prefix8}}
    try:
        d = _plus_call(acc, PLUS_DIEHARD, 'POST', '/web/bin_info',
                       json_body=body,
                       referer=CARD_FORM_ORIGIN + '/',
                       extra_headers={
                           'accept': '*/*',
                           'origin': CARD_FORM_ORIGIN,
                           'x-request-id': req_id,
                       })
    except RuntimeError as e:
        raise RuntimeError(f'Плюс: bin_info: {e}')
    if isinstance(d, dict):
        card = d.get('card')
        if isinstance(card, dict):
            return {
                'payment_system': card.get('payment_system')
                                 or _dig(d, 'payment_system') or '',
                'bank': card.get('bank') or card.get('card_bank') or '',
                'title': card.get('title') or '',
                'country': card.get('country') or card.get('holder_country') or '',
                'allows_3ds': (bool(card.get('allows_3ds'))
                               if card.get('allows_3ds') is not None else None),
                'bin': prefix8,
                'last_digits': bin_last or number[-4:],
                '_raw': d,
            }
    return {'payment_system': _dig(d, 'payment_system') or '',
            'bin': prefix8,
            'last_digits': bin_last or number[-4:],
            '_raw': d}


def plus_parse_card(raw):
    """Разобрать ввод карты в {'number','exp_month','exp_year','csc','holder'}.

    Принимает строку вида "4276 4013 9880 1234 12/27 123" (номер может
    быть слитно/группами, срок MM/YY со слешем, cvc 3-4 цифры) или dict
    с полями number/expiry/csc.
    """
    holder = ''
    if isinstance(raw, dict):
        num = re.sub(r'\D', '', str(raw.get('number', '')))
        exp = str(raw.get('expiry', raw.get('exp', ''))).strip().replace(' ', '')
        csc = re.sub(r'\D', '', str(raw.get('csc', raw.get('cvc', ''))))
        holder = str(raw.get('holder', ''))
    else:
        s = str(raw or '').strip()
        num, exp, csc = '', '', ''
        after = False
        for p in re.split(r'\s+', s):
            p = p.strip()
            if not p:
                continue
            if '/' in p and re.search(r'\d{1,2}/\d{2}$', p):
                exp = p
                after = True
                continue
            if after:
                if not csc and re.fullmatch(r'\d{3,4}', p):
                    csc = p
            else:
                num += re.sub(r'\D', '', p)
        # слитный ввод без пробелов: срок «догоняется» за номером
        if not exp and num:
            if not csc:
                for n in (16, 19, 15, 18, 14, 13):
                    if len(num) == n + 7:
                        num, ex, cv = num[:n], num[n:n + 4], num[n + 4:]
                        exp = f'{ex[0:2]}/{ex[2:4]}'
                        csc = cv
                        break
                    if len(num) == n + 4:
                        num, ex = num[:n], num[n:n + 4]
                        exp = f'{ex[0:2]}/{ex[2:4]}'
                        break
    if not num or len(num) < 13:
        raise RuntimeError('Плюс: не распознан номер карты')
    if not exp:
        raise RuntimeError('Плюс: не распознан срок действия (MM/YY)')
    try:
        mm, yy = [int(x) for x in exp.split('/')]
    except Exception:
        raise RuntimeError('Плюс: некорректный срок действия')
    if mm < 1 or mm > 12:
        raise RuntimeError('Плюс: некорректный месяц карты')
    return {'number': num, 'exp_month': f'{mm:02d}',
            'exp_year': str(2000 + yy) if yy < 100 else str(yy),
            'csc': csc, 'holder': holder}


def plus_update_payment(account, purchase_token, card, last_digits='',
                        avail_pub_key='', save=False, extra=None):
    """Шаг «подготовить привязку карты к покупке»:
    POST trust.yandex.ru/web/update_payment.

    Как в реальном перехвате: form-urlencoded тело
    purchase_token=<pt>&bind_card=true&email=&promocode=,
    purchase_token также в query, Origin/Referer payment-widget.plus.yandex.ru.
    Сами данные карты тут НЕ передаются — их отправляет отдельно виджет
    карты (card-form.diehard.yandex.net) после bin_info.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    send = {'purchase_token': purchase_token or '',
            'bind_card': 'true', 'email': '', 'promocode': ''}
    if extra:
        send.update(extra or {})
    params = {'purchase_token': purchase_token}
    try:
        d = _plus_call(acc, TRUST_HOST, 'POST', '/web/update_payment',
                       data=send, params=params,
                       referer=CARD_WIDGET_ORIGIN + '/',
                       extra_headers={
                           'accept': 'application/json',
                           'content-type': 'application/x-www-form-urlencoded;charset=UTF-8',
                           'origin': CARD_WIDGET_ORIGIN,
                       })
    except RuntimeError as e:
        raise RuntimeError(f'Плюс: update_payment: {e}')
    return {'_raw': d,
            'status': _dig(d, 'status') or '',
            'three_ds': _dig(d, 'threeDs') or _dig(d, '3ds') or _dig(d, 'auth3ds'),
            'purchase_token': _dig(d, 'purchase_token') or purchase_token}


def plus_start_payment(account, purchase_token, card='', sms_code='', extra=None):
    """Запустить платёж с картой: POST diehard.yandex.ru/web/start_payment_json.

    Как в реальном перехвате: purchase_token в query, тело JSON
    {"card_number":…,"cvn":…,"expiration_month":…,"expiration_year":…,
     "payment_method":"new_card"}, Origin/Referer card-form.diehard.yandex.net,
    X-Request-Id. При повторном проходе (ввод SMS/OTP) отправляется ещё раз
    с полем sms_code.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if isinstance(card, str):
        card = plus_parse_card(card)
    body = {}
    if isinstance(card, dict) and card.get('number'):
        body = {
            'card_number': card['number'],
            'cvn': card.get('csc', ''),
            'expiration_month': card.get('exp_month', ''),
            'expiration_year': str(int(card.get('exp_year', '0')) % 100),
            'payment_method': 'new_card',
        }
    if sms_code:
        body['sms_code'] = sms_code
    if extra:
        body.update(extra or {})
    params = {'purchase_token': purchase_token}
    try:
        d = _plus_call(acc, PLUS_DIEHARD, 'POST', '/web/start_payment_json',
                       json_body=body, params=params,
                       referer=CARD_FORM_ORIGIN + '/',
                       extra_headers={
                           'accept': '*/*',
                           'origin': CARD_FORM_ORIGIN,
                           'x-request-id': uuid.uuid4().hex[:16],
                       })
    except RuntimeError as e:
        raise RuntimeError(f'Плюс: start_payment: {e}')
    return {'_raw': d, 'status': _dig(d, 'status') or '',
            'purchase_token': _dig(d, 'purchase_token') or purchase_token}


def plus_check_payment(account, purchase_token):
    """Статус платежа: GET trust.yandex.ru/web/check_payment.

    Как в реальном перехвате: purchase_token в query, Origin/Referer
    payment-widget.plus.yandex.ru, accept: application/json.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    params = {'purchase_token': purchase_token}
    try:
        d = _plus_call(acc, TRUST_HOST, 'GET', '/web/check_payment', params=params,
                       referer=CARD_WIDGET_ORIGIN + '/',
                       extra_headers={
                           'accept': 'application/json',
                           'origin': CARD_WIDGET_ORIGIN,
                       })
    except RuntimeError as e:
        raise RuntimeError(f'Плюс: check_payment: {e}')
    return {'_raw': d, 'status': _dig(d, 'status') or '',
            'tr_status': d.get('tr_status') or _dig(d, 'purchase', 'tr_status') or ''}


def plus_agreement(account, status='ALLOW', csrf=''):
    """Принять добровольное согласие (автопродление подписки).

    api.plus.yandex.ru/graphql?query_name=changeStatus, мутация
    changeVoluntaryAgreementStatus(input: {status: ALLOW}) — как в перехвате
    payment-widget (заголовки x-yandex-plus-*, Origin payment-widget).
    Возвращает обновлённый статус.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not csrf:
        csrf = plus_csrf(acc)
    q = ('mutation changeStatus($input: ChangeVoluntaryAgreementInput!) {\n'
         '  changeVoluntaryAgreementStatus(input: $input) {\n'
         '    status\n'
         '  }\n'
         '}\n')
    body = {'query': q,
            'variables': {'input': {'status': status}},
            'operationName': 'changeStatus'}
    params = {'query_name': 'changeStatus'}
    d = _plus_call(acc, PLUS_API, 'POST', '/graphql', json_body=body, params=params,
                   csrf=csrf, referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    return {'_raw': d,
            'status': _dig(d, 'data', 'changeVoluntaryAgreementStatus', 'status')
            or _dig(d, 'changeVoluntaryAgreementStatus', 'status') or ''}


_COMPSITE_CHECKOUT_DOC = """query compositeOfferCheckout($input: CompositeOfferPurchaseInput!, $includeAdditionalOffers: Boolean!, $includeNewSbp: Boolean!, $includeBindedSbp: Boolean!, $includeNewYaBank: Boolean!, $includeNewAppleToken: Boolean!, $includeNewGoogleToken: Boolean!, $includeNewClickWallet: Boolean!, $includeBindedClickWallet: Boolean!, $usePaymentGroups: Boolean!) {
  compositeOfferCheckoutInfo(input: $input) {
    ...compositeOfferPurchaseBase
    ...compositePaymentMethodsFragment
    checkoutAdditionalOffers @include(if: $includeAdditionalOffers) {
      eventSessionId
      offers {
        additionalText
        benefits {
          text
        }
        disclaimer
        iconImages
        isAvailable
        isSelected
        offerName
        positionId
        text
        title
        upsaleStep
        upsaleType
        offersBatchId
        offersToReplace
        offerSwitchToggle {
          badgeText
          text
        }
      }
      passedUpsaleSteps
      offerSwitchToggle {
        badgeText
        text
      }
      title
    }
  }
}

fragment compositeOfferPurchaseBase on CompositeOfferPurchase {
  silentInvoiceAvailable
  accountCompensationEnable
  hasUserMuid
  invoices {
    ...CompositeOfferInvoiceFragment
  }
  legalInfo {
    ...LegalInfoFragment
  }
  tariffOffer {
    additionText
    description
    image
    offerName
    payload
    tariff {
      name
    }
    text
    title
    unfreezeAvailable
    accountCompensationInfo
    accountCompensationComment
  }
  optionOffers {
    additionText
    description
    image
    offerName
    option {
      name
    }
    payload
    text
    title
    unfreezeAvailable
    accountCompensationInfo
    accountCompensationComment
  }
  paymentText {
    firstPaymentText
    nextPaymentsText
  }
  successScreen {
    title
    message
  }
}

fragment compositePaymentMethodsFragment on CompositeOfferPurchase {
  paymentMethods {
    groups @include(if: $usePaymentGroups) {
      groupButtons
      groupTitle
    }
    mainPaymentMethodId
    trustServiceToken
    promoBadges {
      ... on PaymentPromoBadge {
        additionalTitle {
          ...CheckoutTitleFragment
        }
        backgroundColor {
          dark {
            ...CheckoutColorFragment
          }
          light {
            ...CheckoutColorFragment
          }
        }
        benefitTitle {
          ...CheckoutTitleFragment
        }
        iconImage {
          ...CheckoutThemedImageFragment
        }
        paymentMethodId
      }
    }
    promoLegalInfo {
      __typename
      legalText {
        ...CheckoutTitleFragment
      }
    }
    paymentButtons {
      ... on CardPaymentButton {
        __typename
        panMask {
          last4
        }
        paymentSystem
        yaBank
        bankName
        widgetUrls {
          ... on WidgetUrls {
            __typename
            darkTheme
            lightTheme
          }
        }
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on SbpPaymentButton @include(if: $includeBindedSbp) {
        __typename
        bankName
        darkIconUrl
        lightIconUrl
        dateAdded
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewSbpPaymentButton @include(if: $includeNewSbp) {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewCardPaymentButton {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewYBPaymentButton @include(if: $includeNewYaBank) {
        __typename
        widgetOpenCardUrls {
          ... on WidgetOpenCardUrls {
            __typename
            darkTheme
            lightTheme
          }
        }
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewAppleTokenPaymentButton @include(if: $includeNewAppleToken) {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on ClickWalletPaymentButton @include(if: $includeBindedClickWallet) {
        __typename
        lastPhoneNumberDigits
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewClickWalletPaymentButton @include(if: $includeNewClickWallet) {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewClickWalletWithBoundWalletsPaymentButton @include(if: $includeNewClickWallet) {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
      ... on NewGoogleTokenPaymentButton @include(if: $includeNewGoogleToken) {
        __typename
        ...CompositeOfferCommonPaymentMethodInfoFragment
      }
    }
  }
}

fragment CompositeOfferCommonPaymentMethodInfoFragment on PaymentButton {
  asset {
    badgeText {
      ...CheckoutTitleFragment
    }
    subtitleText {
      ...CheckoutTitleFragment
    }
  }
  darkTheme {
    backgroundColor
    iconUrl
    textColor
  }
  lightTheme {
    backgroundColor
    iconUrl
    textColor
  }
  id
  title
}

fragment CompositeOfferInvoiceFragment on CompositeOfferInvoice {
  timestamp
  totalPrice {
    amount
    currency
  }
  maxPoints {
    amount
    currency
  }
}

fragment LegalInfoFragment on LegalInfo {
  text
  items {
    key
    type
    data {
      text
      link
    }
  }
}

fragment richTextItem on CheckoutTitleItem {
  ... on CheckoutTitleColorItem {
    __typename
    text
    color {
      light {
        ...CheckoutColorFragment
      }
      dark {
        ...CheckoutColorFragment
      }
    }
    altText
    key
  }
  ... on CheckoutTitleHighlightItem {
    __typename
    text
    altText
    key
  }
  ... on CheckoutTitleIconItem {
    __typename
    image {
      light {
        url
      }
      dark {
        url
      }
    }
    altText
    key
  }
  ... on CheckoutTitleLinkItem {
    __typename
    text
    url
    altText
    key
  }
  ... on CheckoutTitleStrikeItem {
    text
    __typename
    altText
    key
  }
}

fragment CheckoutTitleFragment on CheckoutTitle {
  __typename
  text
  items {
    ...richTextItem
  }
}

fragment CheckoutColorFragment on CheckoutColor {
  ... on CheckoutDesignColor {
    __typename
    fallback {
      ... on CheckoutRgbaColor {
        __typename
        rgba
      }
    }
    name
  }
  ... on CheckoutLinearGradientColor {
    __typename
    angle
    colors {
      ... on ColorGradientStop {
        color {
          ... on CheckoutRgbaColor {
            __typename
            rgba
          }
        }
        location
      }
    }
  }
  ... on CheckoutRadialGradientColor {
    __typename
    angle
    colors {
      ... on ColorGradientStop {
        color {
          ... on CheckoutRgbaColor {
            __typename
            rgba
          }
        }
        location
      }
    }
    relativeCenter {
      x
      y
    }
    relativeRadius {
      x
      y
    }
  }
  ... on CheckoutRgbaColor {
    __typename
    rgba
  }
}

fragment CheckoutThemedImageFragment on CheckoutThemedImage {
  dark {
    ... on CheckoutImage {
      url
    }
  }
  light {
    ... on CheckoutImage {
      url
    }
  }
}
"""


def plus_offers(account, target='plus-web', utm='afisha'):
    """Получить конфиг виджета оплаты с лендинга плюса для аккаунта.

    Загружает https://plus.yandex.ru/?utm_source=afisha&target=plus-web с
    passport-куками аккаунта и вытаскивает из HTML (SSR-конфиг) URL виджета
    payment-widget.plus.yandex.ru и его query-поля: offerToken, eventSessionId,
    crossSessionId, hashOrderId, offersBatchId, offersPositionIds,
    tariffOfferName, target, testIds и пр.

    Возвращает dict с полями виджета, либо raise, если offerToken не найден
    (аккаунту этот оффер недоступен).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    url = f'https://plus.yandex.ru/?utm_source={utm}&target={target}'
    try:
        r = requests.get(url, headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': PLUS_UA,
            'referer': 'https://plus.yandex.ru/',
        }, cookies=_web_cookies(acc), timeout=40)
    except requests.RequestException as e:
        raise RuntimeError(f'Плюс: страница офферов: {e}')
    html = r.text
    out = {}
    m = re.search(r'https://payment-widget\.plus\.yandex\.ru/[^"\'\s\\]+', html, re.I)

    def _q(name):
        if not m:
            return ''
        mm = re.search(r'[?&]' + re.escape(name) + r'=([^&"\'\s\\]+)', m.group(0))
        return urllib.parse.unquote(mm.group(1)) if mm else ''

    if m:
        for k in ('authMethod', 'crossSessionId', 'eventSessionId', 'hashOrderId',
                  'lang', 'offerToken', 'offersBatchId', 'offersPositionIds',
                  'silent', 'target', 'tariffOfferName', 'testIds', 'usePlusHost',
                  'widgetServiceName', 'widgetSubServiceName', 'widgetType',
                  'isTarifficator', 'utm_source'):
            out[k] = _q(k)
    if not out.get('offerToken'):
        mm = re.search(r'["\']offerToken["\']\s*:\s*["\']([^"\']+)["\']', html)
        if mm:
            out['offerToken'] = mm.group(1)
    if not out.get('eventSessionId'):
        mm = re.search(r'["\']eventSessionId["\']\s*:\s*["\']([0-9a-f-]+)["\']', html)
        if mm:
            out['eventSessionId'] = mm.group(1)
    if not out.get('crossSessionId'):
        mm = re.search(r'["\']crossSessionId["\']\s*:\s*["\']([0-9a-f-]+)["\']', html)
        if mm:
            out['crossSessionId'] = mm.group(1)
    if not out.get('tariffOfferName'):
        mm = re.search(r'["\']tariffOfferName["\']\s*:\s*["\']([^"\']+)["\']', html)
        if mm:
            out['tariffOfferName'] = mm.group(1)
    if not out.get('offerToken'):
        raise RuntimeError(
            'Плюс: offerToken не найден на plus.yandex.ru (аккаунту этот оффер '
            'недоступен). Ищи в HTML страницы "offerToken"/"payment-widget.plus.yandex.ru".')
    return out


def plus_offers_from_landing(account, url=PLUS_LANDING_PERF):
    """Получить оффер подписки с конкретного лендинга plus.yandex.ru.

    Грузит заданный url (по умолчанию рекламный перф-лендинг) с куками
    аккаунта и вытаскивает из SSR-HTML конфиг виджета оплаты: offerToken,
    eventSessionId, crossSessionId, hashOrderId, batchId, positionId, target,
    tariffOfferName. Подходит для промо-лендингов, которые не отдают оффер
    через /api/v2/offers. Возвращает словарь в формате plus_offers_v2
    (offer_token/target/batch_id/position_id/tariff_offer/event_session_id),
    либо бросает RuntimeError, если для аккаунта этот оффер недоступен.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    referer = url.split('?')[0]
    try:
        r = requests.get(url, headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': PLUS_UA,
            'referer': referer,
        }, cookies=_web_cookies(acc), timeout=40, allow_redirects=True)
    except requests.RequestException as e:
        raise RuntimeError(f'Плюс: лендинг {url}: {e}')
    html = r.text
    out = {}
    m = re.search(r'https://payment-widget\.plus\.yandex\.ru/[^"\'\s\\]+', html, re.I)

    def _q(name):
        if not m:
            return ''
        mm = re.search(r'[?&]' + re.escape(name) + r'=([^&"\'\s\\]+)', m.group(0))
        return urllib.parse.unquote(mm.group(1)) if mm else ''

    if m:
        for k in ('authMethod', 'crossSessionId', 'eventSessionId', 'hashOrderId',
                  'lang', 'offerToken', 'offersBatchId', 'offersPositionIds',
                  'silent', 'target', 'tariffOfferName', 'testIds', 'usePlusHost',
                  'utm_source'):
            out[k] = _q(k)
    if not out.get('offerToken'):
        mm = re.search(r'["\']offerToken["\']\s*:\s*["\']([^"\']+)["\']', html)
        if mm:
            out['offerToken'] = mm.group(1)
    if not out.get('eventSessionId'):
        mm = re.search(r'["\']eventSessionId["\']\s*:\s*["\']([0-9a-f-]+)["\']', html)
        if mm:
            out['eventSessionId'] = mm.group(1)
    if not out.get('offerToken'):
        raise RuntimeError(
            f'Плюс: лендинг {url}: оффер этому аккаунту недоступен '
            '(offerToken не найден в HTML)')
    return {
        'offer_token': out.get('offerToken') or '',
        'target': out.get('target') or PLUS_WIDGET_TARGET,
        'batch_id': out.get('offersBatchId') or '',
        'position_id': out.get('offersPositionIds') or '',
        'tariff_offer': out.get('tariffOfferName') or '',
        'event_session_id': out.get('eventSessionId') or '',
        'cross_session_id': out.get('crossSessionId') or '',
        'hash_order_id': out.get('hashOrderId') or '',
        '_landing': url,
        '_raw': out,
    }


def _intro_period_days(o):
    """Длина trial-периода (INTRO_PLAN) оффера, напр. 'P30D' → 30."""
    to = _dig(o, 'catalogCompositeOffer', 'tariffOffer') or {}
    plans = to.get('plans') or []
    best = 0
    for p in plans:
        if isinstance(p, dict) and 'INTRO' in str(p.get('typename', '')).upper():
            mm = re.search(r'P(\d+)D', str(p.get('period') or ''))
            if mm:
                best = max(best, int(mm.group(1)))
    return best


def _pick_trial_offer(offers):
    """Выбрать trial-оффер с максимальным intro-периодом (30д за 1₽).

    Для чистых аккаунтов /api/v2/offers отдаёт 2+ оффера (пример, uid
    2421294728):
      [0] crazywinback-plus-web — P360D, intro P30D «30 дней за 1₽»;
      [1] crazyintro-plus-web-30 — P30D, intro P14D «14 дней за 1₽».
    Нужен именно вариант с 30 днями за 1₽ (intro-период максимальный),
    иначе — первый.
    """
    if not offers:
        return None
    trials = []
    for o in offers:
        to = _dig(o, 'catalogCompositeOffer', 'tariffOffer') or {}
        plans = to.get('plans') or []
        if any(isinstance(p, dict) and 'INTRO' in str(p.get('typename', '')).upper()
               for p in plans):
            trials.append(o)
    pool = trials or offers
    return max(pool, key=_intro_period_days)


def _plus_landing_test_ids(account, url=PLUS_LANDING_PERF):
    """testIdsArray экспериментов аккаунта из SSR __NEXT_DATA__ лендинга.

    Виджет /api/v2/offers шлёт expTestIds = testIdsArray из SSR-конфига
    лендинга (props.pageProps.experiments.testIdsArray), которые уникальны
    для аккаунта. Статический PLUS_TEST_IDS (из старого перехвата) для части
    аккаунтов даёт 404 «There is no offers configuration for the context» —
    поэтому берём тест-айды из живого лендинга. Возвращает список int либо
    None, если лендинг не отдал testIds.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    try:
        r = requests.get(url, headers={
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'user-agent': PLUS_UA,
            'referer': url.split('?')[0],
        }, cookies=_web_cookies(acc), timeout=40, allow_redirects=True)
    except requests.RequestException:
        return None
    h = r.text
    i = h.find('__NEXT_DATA__" type="application/json" crossorigin="anonymous">')
    if i < 0:
        i = h.find('__NEXT_DATA__')
        j = h.find('>', i)
        if j < 0:
            return None
        i = j
    i = h.find('>', i) + 1
    j = h.find('</script>', i)
    if j < 0:
        return None
    try:
        d = json.loads(h[i:j])
        tids = d['props']['pageProps']['experiments']['testIdsArray']
    except Exception:
        return None
    out = [int(x) for x in tids if str(x).strip().isdigit()]
    return out or None


def plus_offers_v2(account, event_session_id='', page='plus_home',
                   places=None, referer='https://plus.yandex.ru/', test_ids=None):
    """Оффер Плюса через современный backend: api.acquisition-gwe.plus.yandex.ru.

    POST /api/v2/offers?eventSessionId=<uuid> — как лэндинг plus.yandex.ru
    (захват seq 14/24). Возвращает offerToken (подписанный JWT с uid и
    offerNames), target (plus-web-random-trial), analyticData{batchId,
    positionId, placeId} и имя тарифного оффера. Это источник конфигурации
    виджета оплаты (вместо устаревшего парсинга HTML plus.yandex.ru).

    page/places задают страницу и места лендинга: для рекламного
    /perf/plus виджет acquisition шлёт page='perf',
    places=['main_card','secondary_card'] (см. SSR-HTML лендинга), для
    обычного — page='plus_home', places=[].
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    esid = event_session_id or uuid.uuid4().hex
    body = {
        'context': {
            'widgetServiceName': 'landing_plus',
            'page': page,
            'places': places or [],
            'expTestIds': list(test_ids) if test_ids else PLUS_TEST_IDS,
            'expFlags': ['new_pay_widget_plain', 'tarifficator_web_success_screen_sdk',
                         'dwh_logger', 'dwh_metrics', 'tarrificator_sdk',
                         'new_payments_history', 'lk_checkout_widget_on'],
        },
    }
    hdrs = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'origin': 'https://plus.yandex.ru',
        'referer': referer,
        'x-request-id': str(int(time.time() * 1000)) + '-' + uuid.uuid4().hex[:18],
        'x-forwarded-for': '92.124.161.30',
        'x-preferred-language': 'ru',
        'x-requested-with': 'XMLHttpRequest',
        'x-yandex-plus-brand': 'YANDEX',
        'x-yandex-plus-device': 'os=Windows;os_version=10;dpi=96',
        'x-yandex-plus-platform': 'web',
        'x-yandex-plus-sdkversion': '0.10.14',
        'x-yandex-plus-service': 'plus',
        'x-yandex-deviceid': _dev(acc).get('yandex_device_id', ''),
    }
    d = _plus_call(acc, PLUS_ACQ_API, 'POST', '/api/v2/offers',
                   json_body=body, params={'eventSessionId': esid},
                   extra_headers=hdrs)
    offers = d.get('offers') if isinstance(d, dict) else None
    if not isinstance(offers, list) or not offers:
        raise RuntimeError(f'Плюс: /api/v2/offers не вернул офферы: {str(d)[:300]}')
    o = _pick_trial_offer(offers) or offers[0]
    ad = o.get('analyticData') or {}
    co = o.get('catalogCompositeOffer') or {}
    return {
        'offer_token': o.get('offerToken') or '',
        'target': o.get('target') or PLUS_WIDGET_TARGET,
        'batch_id': ad.get('batchId') or '',
        'position_id': ad.get('positionId') or '',
        'place_id': ad.get('placeId') or '',
        'tariff_offer': _dig(co, 'tariffOffer', 'name') or '',
        'event_session_id': esid,
        'position': o.get('position'),
        'offer_texts': o.get('offerTexts') or {},
        '_raw': d,
    }


def _plus_widget_origin(offer_token, tariff_offer, target=PLUS_WIDGET_TARGET,
                        event_session_id='', cross_session_id='', hash_order_id='',
                        batch_id='', position_id=''):
    """Собрать query-строку виджета (input.origin для createInvoice).

    Из URL payment-widget (захват seq 27): те же параметры + поля
    confirmLicenseAgreement/confirmLicenseRegion и offersBatchIdCheck/
    offersPositionIdsCheck, которые видит createInvoice.
    """
    esid = event_session_id or uuid.uuid4().hex
    csid = cross_session_id or uuid.uuid4().hex
    hid = hash_order_id or uuid.uuid4().hex
    tid = urllib.parse.quote(json.dumps([str(t) for t in PLUS_TEST_IDS]))
    q = urllib.parse.urlencode({
        'authMethod': 'default',
        'confirmLicenseAgreement': 'false',
        'confirmLicenseRegion': '225',
        'crossSessionId': csid,
        'eventSessionId': esid,
        'hashOrderId': hid,
        'isTarifficator': 'true',
        'lang': 'ru',
        'offerToken': offer_token,
        'offersBatchId': batch_id,
        'offersBatchIdCheck': batch_id,
        'offersPositionIds': position_id,
        'offersPositionIdsCheck': position_id,
        'ottApiDomain': 'ott.yandex',
        'postMessageVersion': '2',
        'referer': 'widget-plus',
        'silent': 'false',
        'target': target,
        'tariffOfferName': tariff_offer,
        'testIds': tid,
        'theme': 'light',
        'usePlusHost': 'true',
        'utm_source': 'afisha',
        'widgetServiceName': 'landing_plus',
        'widgetSubServiceName': 'web',
        'widgetType': 'plus-my',
    })
    return q, esid, csid, hid


def plus_composite_checkout(account, offer_token='', csrf='', tarif='',
                            target=PLUS_WIDGET_TARGET, event_session_id=''):
    """Инфо чекаута оффера Плюса: api.plus.yandex.ru/graphql?query_name=compositeOfferCheckout.

    Из перехвата payment-widget (seq 33/39): запрос идёт БЕЗ csrf-заголовка;
    variables.input — offerToken + eventSessionId + compositeOffer.tariffOffer
    (имя тарифа) + target (plus-web-random-trial). Возвращает {'ok':True,
    'invoice':…, 'tariff_offer':…, 'trust_service_token':…, 'purchase_token':…,
    '_raw':…}. CSRF для этого вызова не нужен (но безвреден).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not offer_token:
        # без offerToken оффер не определить — такой чекаут невозможен
        return {'ok': False, 'need_offer_token': True,
                'raw': 'Нет offerToken: нужен запрос, который его выдаёт.'}
    esid = event_session_id or uuid.uuid4().hex
    exp = list(PLUS_EXP_FLAGS)
    variables = {
        'input': {
            'offerToken': offer_token,
            'eventSessionId': esid,
            'language': 'RU',
            'target': target,
            'compositeOffer': {
                'offerFor': None,
                'serviceOffers': [],
                'tariffOffer': tarif,
            },
            'storeOffersData': None,
            'storeOffersDataV2': None,
            'checkSilentInvoiceAvailability': None,
            'useTransitions': False,
            'widgetServiceName': 'landing_plus',
            'experimentFlags': exp,
            'checkoutAdditionalOffers': {'passedUpsaleSteps': ['PRESALE']},
            'availablePaymentButtons': None,
            'onetime': None,
        },
        'includeAdditionalOffers': True,
        'includeNewSbp': True,
        'includeBindedSbp': True,
        'includeNewAppleToken': True,
        'includeNewGoogleToken': False,
        'includeNewYaBank': True,
        'includeNewClickWallet': False,
        'includeBindedClickWallet': False,
        'usePaymentGroups': True,
    }
    body = {'query': _COMPSITE_CHECKOUT_DOC,
            'variables': variables,
            'operationName': 'compositeOfferCheckout'}
    params = {'query_name': 'compositeOfferCheckout'}
    d = _plus_call(acc, PLUS_API, 'POST', '/graphql', json_body=body, params=params,
                   csrf=csrf, referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    data = d.get('data') if isinstance(d, dict) else {}
    info = data.get('compositeOfferCheckoutInfo') if isinstance(data, dict) else {}
    inv = None
    if isinstance(info, dict):
        tmp = info.get('invoices')
        if isinstance(tmp, list) and tmp:
            inv = tmp[0]
            price = inv.get('totalPrice') or {}
            inv = {'amount': _dig(price, 'amount') or '',
                   'currency': _dig(price, 'currency') or '',
                   'timestamp': inv.get('timestamp')}
    pm = _dig(info, 'paymentMethods') or {}
    raw_all = [*_plus_token(d)]
    return {'ok': True,
            'invoice': inv,
            'tariff_offer': _dig(info, 'tariffOffer', 'offerName') or '',
            'trust_service_token': _dig(pm, 'trustServiceToken') or '',
            'main_payment_method_id': _dig(pm, 'mainPaymentMethodId') or '',
            'purchase_token': next((t for t in raw_all if t.startswith('payment_')), ''),
            '_raw': d}


_INVOICE_FRAGMENT = (
    'fragment InvoiceFragment on Invoice {\n'
    '  id\n'
    '  form\n'
    '  invoiceStatus\n'
    '  errorCode\n'
    '  paymentMethodId\n'
    '  payment {\n'
    '    id\n'
    '    respCode\n'
    '    respDesc\n'
    '    status\n'
    '    challengeUrl\n'
    '    operationId\n'
    '  }\n'
    '}\n')


def plus_create_invoice(account, offer_token='', tariff_offer='', csrf='',
                        target=PLUS_WIDGET_TARGET, event_session_id='',
                        cross_session_id='', hash_order_id='', batch_id='',
                        position_id=''):
    """Создать инвойс подписки: api.plus.yandex.ru/graphql?query_name=createInvoice.

    Мутация createInvoice(input: CreateInvoiceInput!, eventSessionId) — тело
    целиком из захвата seq 49. input.origin — query-строка виджета оплаты
    (plus.web._plus_widget_origin); CSRF-заголовок x-ya-csrf-token обязателен.
    Возвращает {'ok':True, 'invoice_id':…, 'status':…, '_raw':…}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not offer_token:
        raise RuntimeError('Плюс: createInvoice требует offerToken')
    if not csrf:
        csrf = plus_csrf(acc)
    origin, esid, csid, hid = _plus_widget_origin(
        offer_token, tariff_offer or '', target=target,
        event_session_id=event_session_id, cross_session_id=cross_session_id,
        hash_order_id=hash_order_id, batch_id=batch_id, position_id=position_id)
    dev_payload = json.dumps({
        'payment_completion_action': 'spin',
        'lang': 'ru',
        'submit_button_data': {'text': 'Подключить'},
        'blocks_visibility': {'cardSelector': False},
        'selected_card_id': 'new_card',
        'css-theme': 'light',
    })
    inp = {
        'source': 'landing_plus',
        'target': target,
        'origin': origin,
        'silent': False,
        'returnPath': 'spin',
        'templateTag': 'DESKTOP',
        'paymentMethodId': None,
        'developerPayload': dev_payload,
        'language': 'RU',
        'oneClickRequested': False,
        'points': None,
        'compositeOffer': {'tariffOffer': tariff_offer or '', 'serviceOffers': []},
        'offersBatchId': batch_id,
        'offersPositionId': position_id,
        'useTransitions': False,
        'externalCallerPayload': None,
        'accountCompensationEnable': False,
        'additionalOffers': {'offers': []},
        'offerToken': offer_token,
        'experimentFlags': list(PLUS_EXP_FLAGS),
        'onetime': None,
    }
    q = ('mutation createInvoice($input: CreateInvoiceInput!, $eventSessionId: String) {\n'
         '  invoice {\n'
         '    externalCreate(req: $input, eventSessionId: $eventSessionId) {\n'
         '      ...InvoiceFragment\n'
         '      duplicateInvoice {\n'
         '        ...InvoiceFragment\n'
         '      }\n'
         '    }\n'
         '  }\n'
         '}\n\n' + _INVOICE_FRAGMENT)
    body = {'query': q,
            'variables': {'input': inp, 'eventSessionId': esid},
            'operationName': 'createInvoice'}
    d = _plus_call(acc, PLUS_API, 'POST', '/graphql', json_body=body,
                   params={'query_name': 'createInvoice'}, csrf=csrf,
                   referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    inv = _dig(d, 'data', 'invoice', 'externalCreate') or {}
    return {'ok': True,
            'invoice_id': inv.get('id') or '',
            'status': inv.get('invoiceStatus') or '',
            'error_code': inv.get('errorCode'),
            'duplicate': _dig(d, 'data', 'invoice', 'externalCreate', 'duplicateInvoice'),
            'esid': esid,
            '_raw': d}


def plus_start_invoice(account, invoice_id, csrf=''):
    """Запустить инвойс: api.plus.yandex.ru/graphql?query_name=startInvoice.

    Мутация startInvoice(id) из захвата seq 53 (CSRF-заголовок нужен).
    Возвращает {'ok':True, 'invoice_id':…, 'status':…, '_raw':…}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not csrf:
        csrf = plus_csrf(acc)
    q = ('mutation startInvoice($id: ID!) {\n'
         '  invoice {\n'
         '    externalStart(id: $id) {\n'
         '      ...InvoiceFragment\n'
         '      duplicateInvoice {\n'
         '        ...InvoiceFragment\n'
         '      }\n'
         '    }\n'
         '  }\n'
         '}\n\n' + _INVOICE_FRAGMENT)
    body = {'query': q,
            'variables': {'id': invoice_id},
            'operationName': 'startInvoice'}
    d = _plus_call(acc, PLUS_API, 'POST', '/graphql', json_body=body,
                   params={'query_name': 'startInvoice'}, csrf=csrf,
                   referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    inv = _dig(d, 'data', 'invoice', 'externalStart') or {}
    return {'ok': True,
            'invoice_id': inv.get('id') or invoice_id,
            'status': inv.get('invoiceStatus') or '',
            'error_code': inv.get('errorCode'),
            '_raw': d}


def plus_invoice_status(account, invoice_id='', csrf=''):
    """Статус инвойса: api.plus.yandex.ru/graphql?query_name=invoiceStatus.

    Запрос externalInvoice(id) c InvoiceFragment (захват seq 57-67):
    invoiceStatus + payment{status, operationId, challengeUrl}. CSRF-заголовок
    НЕ нужен. Возвращает {'ok':True, 'status':…, 'payment':…,
    'operation_id':…, 'challenge_url':…, '_raw':…}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not invoice_id:
        raise RuntimeError('Плюс: invoiceStatus требует id инвойса')
    q = ('query invoiceStatus($id: ID!) {\n'
         '  externalInvoice(id: $id) {\n'
         '    ...InvoiceFragment\n'
         '  }\n'
         '}\n\n' + _INVOICE_FRAGMENT)
    body = {'query': q,
            'variables': {'id': invoice_id},
            'operationName': 'invoiceStatus'}
    d = _plus_call(acc, PLUS_API, 'POST', '/graphql', json_body=body,
                   params={'query_name': 'invoiceStatus'},
                   referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    inv = _dig(d, 'data', 'externalInvoice') or {}
    pay = inv.get('payment') or {}
    challenge = pay.get('challengeUrl') or ''
    form = inv.get('form') or ''
    pt = ''
    if not pt and challenge:
        mm = re.search(r'purchase_token=([^&]+)', challenge)
        if mm:
            pt = urllib.parse.unquote(mm.group(1))
    if not pt and form:
        # purchase_token приходит в externalInvoice.form (payment-страница
        # Траста) после WAIT_FOR_NOTIFICATION — захват seq 988
        mm = re.search(r'purchase_token=([^&]+)', form)
        if mm:
            pt = urllib.parse.unquote(mm.group(1))
    return {'ok': True,
            'status': inv.get('invoiceStatus') or '',
            'error_code': inv.get('errorCode'),
            'form': form,
            'payment': pay,
            'payment_status': pay.get('status') or '',
            'operation_id': pay.get('operationId') or '',
            'challenge_url': challenge,
            'purchase_token': pt or (pay.get('purchase_token') or ''),
            '_raw': d}


def plus_wait_operation(account, invoice_id, csrf='', attempts=20, delay=2.0):
    """Дождаться payment.operationId (verification_intent_…) инвойса.

    После startInvoice инвойс уходит в WAIT_FOR_NOTIFICATION /
    wait_payment_method, и только затем Траст знает operation_id — его нужен
    для create_form_url. Возвращает dict из plus_invoice_status.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not csrf:
        csrf = plus_csrf(acc)
    last = None
    for _ in range(attempts):
        last = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
        if last.get('operation_id'):
            return last
        st = last.get('status') or ''
        if st in ('SUCCESS', 'DONE', 'PAID', 'ERROR', 'CANCELED', 'CLOSED'):
            return last
        time.sleep(delay)
    return last


def plus_wait_purchase_token(account, invoice_id, csrf='', attempts=20, delay=2.0):
    """Дождаться purchase_token=payment_<hex> в externalInvoice.form.

    После startInvoice инвойс проходит SCHEDULED → WAIT_FOR_NOTIFICATION, и
    только тогда в response invoiceStatus появляется form — payment-страница
    Траста с purchase_token (захват: seq 928→988). Возвращает dict из
    plus_invoice_status (с полем 'purchase_token').
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not csrf:
        csrf = plus_csrf(acc)
    last = None
    for _ in range(attempts):
        last = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
        pt = last.get('purchase_token') or ''
        if pt.startswith('payment_'):
            return last
        st = last.get('status') or ''
        if st in ('SUCCESS', 'DONE', 'PAID', 'ERROR', 'CANCELED', 'CLOSED', 'FAILED'):
            return last
        time.sleep(delay)
    return last


def plus_payment_form_url(account, service_token='', operation_id='', theme='light'):
    """Форма оплаты Траста для инвойса: POST trust.yandex.ru/web/create_form_url.

    Тело из захвата seq 63 (layout=dh-only — только карта diehard):
    {anonymously:true, integration_profile_id:'yandex_default', flow:'card',
    operation_id:<operationId>, theme:'light', lang:'ru', layout:'dh-only',
    method:'tokenize'}, service_token — в query. Возвращает {form_url,…}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not service_token:
        raise RuntimeError('Плюс: create_form_url требует trustServiceToken из чекаута')
    if not operation_id:
        raise RuntimeError('Плюс: create_form_url требует operation_id (ждём invoiceStatus)')
    body = {
        'anonymously': True,
        'integration_profile_id': TRUST_INTEGRATION_PROFILE_RU,
        'flow': TRUST_BIND_FLOW,
        'operation_id': operation_id,
        'theme': theme or 'light',
        'lang': 'ru',
        'layout': 'dh-only',
        'method': 'tokenize',
    }
    d = _plus_call(acc, TRUST_HOST, 'POST', '/web/create_form_url',
                   json_body=body, params={'service_token': service_token},
                   referer=CARD_WIDGET_ORIGIN + '/',
                   extra_headers=_plus_widget_hdrs())
    form_url = d.get('form_url') or ''
    return {'form_url': form_url, 'service_token': service_token,
            'operation_id': operation_id, '_raw': d}


SMS_STATUSES = ('auth_required', 'three_ds_required', '3ds', 'awaiting_otp',
                'otp_required', 'otp_pending', 'sms_required',
                'sd_cvv_required', 'cvv_required')


def plus_3ds_challenge(acc, purchase_token, csrf=''):
    """Открыть trust open_3ds и получить challenge_url (web/challenge?external_id=…).

    Возвращает {'challenge_url':…, 'external_id':…, 'open_url':…}. Если платёж
    уже истёк/завершён — challenge_url может не содержать external_id.
    """
    acc = get_eda_account(acc) if isinstance(acc, str) else acc
    if not purchase_token:
        raise RuntimeError('Плюс: 3DS требует purchase_token')
    url = TRUST_HOST + '/web/open_3ds?purchase_token=' + urllib.parse.quote(purchase_token)
    hdrs = _plus_hdrs(acc, csrf, CARD_WIDGET_ORIGIN + '/')
    try:
        r = requests.get(url, headers=hdrs, cookies=_web_cookies(acc),
                         allow_redirects=True, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Плюс: 3DS open (сеть): {e}')
    final = r.url or ''
    external_id = ''
    mm = re.search(r'[?&]external_id=([^&\s]+)', final)
    if mm:
        external_id = mm.group(1)
    return {'challenge_url': final, 'external_id': external_id,
            'open_url': url, '_status': r.status_code,
            '_page': (r.text or '')[:400]}


def plus_3ds_info(acc, external_id, csrf=''):
    """Статус 3DS-челленджа: get_info → auth_status + acs_redirect_url и т.п."""
    acc = get_eda_account(acc) if isinstance(acc, str) else acc
    if not external_id:
        return {}
    d = _plus_call(acc, TRUST_HOST, 'GET',
                   '/threedsprovider/front/v1/get_info',
                   params={'external_id': external_id},
                   referer=(TRUST_HOST + '/web/challenge?external_id='
                            + urllib.parse.quote(external_id)),
                   extra_headers={'accept': 'application/json'})
    return d if isinstance(d, dict) else {}


def plus_3ds_auth_status(acc, external_id, csrf=''):
    """auth_status челленджа: in_progress/success/failed ('' если нет external_id)."""
    return str(plus_3ds_info(acc, external_id, csrf=csrf).get('auth_status') or '')


def _plus_3ds_done(acc, purchase_token, invoice_id, csrf, activate, check):
    """Финал после успешного 3DS: invoiceStatus + активация changeStatus ALLOW."""
    ag = {}
    if activate:
        try:
            ag = plus_agreement(acc, status='ALLOW', csrf=csrf)
        except RuntimeError as e:
            ag = {'error': str(e)}
    inv = {}
    if invoice_id:
        try:
            inv = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
        except RuntimeError:
            inv = {}
    return {'ok': True, 'stage': 'done', 'status': inv.get('status') or 'SUCCESS',
            'purchase_token': purchase_token, 'invoice_id': invoice_id,
            '_check': check, '_invoice_status': inv, '_agreement': ag}


def plus_3ds_wait(acc, purchase_token, invoice_id='', csrf='', timeout=600,
                  poll=2.0, activate=True):
    """Ждать завершения 3DS (check_payment → success) и активировать подписку.

    Поллит trust /web/check_payment (и invoiceStatus, если задан invoice_id)
    каждые poll сек до timeout. При success — активация changeStatus ALLOW.
    Возвращает dict-контракт: {'ok':True,'stage':'done',…} либо
    {'ok':False,'stage':'timeout'|'failed',…}.
    """
    acc = get_eda_account(acc) if isinstance(acc, str) else acc
    if not csrf:
        csrf = plus_csrf(acc)
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        check = {}
        try:
            check = plus_check_payment(acc, purchase_token)
        except RuntimeError as e:
            check = {'error': str(e)}
        st = str(check.get('status') or check.get('tr_status') or '')
        last['_check'] = check
        if st.lower() in ('success', 'paid', 'done', 'completed', 'finished'):
            return _plus_3ds_done(acc, purchase_token, invoice_id, csrf,
                                  activate, check)
        if invoice_id:
            try:
                inv = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
            except RuntimeError:
                inv = {}
            last['_invoice_status'] = inv
            ist = str(inv.get('status') or '')
            if ist in ('SUCCESS', 'DONE', 'PAID'):
                return _plus_3ds_done(acc, purchase_token, invoice_id, csrf,
                                      activate, check)
            if ist in ('ERROR', 'CANCELED', 'CLOSED', 'FAILED'):
                return {'ok': False, 'stage': 'failed',
                        'error': f'Плюс: платёж после 3DS {ist}: '
                                 f"{inv.get('error_code')}",
                        'purchase_token': purchase_token,
                        'invoice_id': invoice_id,
                        '_invoice_status': inv, '_check': check}
        time.sleep(poll)
    return {'ok': False, 'stage': 'timeout',
            'error': f'Плюс: 3DS не завершён за {timeout} с',
            'purchase_token': purchase_token, 'invoice_id': invoice_id, **last}


def _plus_finish_payment(acc, purchase_token, card, sms_code='', csrf='',
                         invoice_id='', _checkout=None, _invoice=None,
                         _start=None, _status=None, trigger_res=None):
    """Оплатить инвойс по purchase_token: diehard-флоу без 3DS.

    trust update_payment (bind_card=true) → diehard bin_info →
    diehard start_payment_json (карта открытым текстом) → при SMS повторный
    start_payment_json с sms_code → poll invoiceStatus до SUCCESS →
    changeStatus ALLOW (активация). Возвращает dict-контракт plus_subscribe.
    """
    parsed = plus_parse_card(card) if not isinstance(card, dict) else card
    # 1) подготовка привязки (trust update_payment)
    try:
        up = plus_update_payment(acc, purchase_token, parsed)
    except RuntimeError as e:
        return {'ok': False, 'error': str(e), 'purchase_token': purchase_token,
                'invoice_id': invoice_id}
    # 2) bin_info (diehard) — префикс карты
    bin_ = {}
    try:
        num = str(parsed.get('number', ''))
        d = _plus_call(acc, PLUS_DIEHARD, 'POST', '/web/bin_info',
                       json_body={'params': {'prefix': num[:8]}},
                       referer=CARD_FORM_ORIGIN + '/',
                       extra_headers={'accept': 'application/json',
                                      'origin': CARD_FORM_ORIGIN,
                                      'x-request-id': uuid.uuid4().hex[:16]})
        bin_ = d if isinstance(d, dict) else {'_raw': d}
    except Exception as e:
        bin_ = {'error': str(e)}
    # 3) запуск платежа картой
    try:
        st = plus_start_payment(acc, purchase_token, card=parsed,
                                sms_code=sms_code)
    except RuntimeError as e:
        return {'ok': False, 'error': str(e), 'purchase_token': purchase_token,
                'invoice_id': invoice_id, '_up': up, '_bin': bin_,
                '_trigger': trigger_res}
    raw = st.get('_raw') or {}
    status = st.get('status') or _dig(raw, 'result') or _dig(raw, 'status') or ''
    if sms_code and status in ('otp_incorrect', 'incorrect_otp', 'invalid_code',
                               'wrong_code', 'invalid_otp'):
        return {'ok': False, 'stage': 'sms',
                'error': 'Неверный SMS-код, повтори',
                'purchase_token': purchase_token,
                'invoice_id': invoice_id,
                'card': parsed, 'status': status,
                '_start': st, '_up': up, '_bin': bin_,
                '_trigger': trigger_res}
    if not sms_code and (status in SMS_STATUSES
                         or _dig(raw, 'threeDs') or _dig(raw, '3ds')
                         or _dig(raw, 'auth3ds') or _dig(raw, 'auth_3ds')):
        three_ds = bool(_dig(raw, 'threeDs') or _dig(raw, '3ds')
                        or _dig(raw, 'auth3ds') or _dig(raw, 'auth_3ds'))
        if three_ds:
            return {'ok': False,
                    'error': 'Плюс: требуется 3DS-челлендж (банк). Автопроход '
                             'недоступен — нужен ввод карты в форме Траста.',
                    'purchase_token': purchase_token,
                    'invoice_id': invoice_id,
                    'card': parsed, 'status': status,
                    '_start': st, '_up': up, '_bin': bin_,
                    '_trigger': trigger_res}
        return {'ok': True, 'stage': 'sms',
                'message': 'Требуется SMS-код от банка',
                'purchase_token': purchase_token,
                'invoice_id': invoice_id,
                'card': parsed, 'status': status,
                '_start': st, '_up': up, '_bin': bin_,
                '_trigger': trigger_res}
    # 4) ожидание результата (check_payment + invoiceStatus)
    check = None
    inv = None
    try:
        for _ in range(3):
            check = plus_check_payment(acc, purchase_token)
            stc = (check.get('status') or check.get('tr_status') or '')
            if stc and stc.lower() not in ('pending', 'in_progress', 'processing'):
                break
            time.sleep(2.0)
    except RuntimeError as e:
        check = {'error': str(e)}
    ok_st = ('success', 'paid', 'done', 'completed', 'finished')
    three_ds_wait = ''
    if invoice_id:
        for _ in range(20):
            try:
                inv = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
            except RuntimeError:
                inv = {}
            ist = str(inv.get('status') or '')
            if ist in ('SUCCESS', 'DONE', 'PAID'):
                break
            if '3DS' in ist.upper() or ist in ('THREE_D', 'AUTH_REQUIRED'):
                three_ds_wait = ist
                break
            if ist in ('ERROR', 'CANCELED', 'CLOSED', 'FAILED'):
                break
            time.sleep(3.0)
        if three_ds_wait:
            ch = {}
            try:
                ch = plus_3ds_challenge(acc, purchase_token, csrf=csrf)
            except Exception as e:
                ch = {'error': str(e)}
            return {'ok': True, 'stage': '3ds',
                    'error': f'Плюс: банк требует 3DS-челлендж '
                             f'({three_ds_wait}). Откройте страницу банка '
                             f'и введите SMS-код.',
                    'purchase_token': purchase_token, 'invoice_id': invoice_id,
                    'challenge_url': ch.get('challenge_url')
                                     or (inv or {}).get('form') or '',
                    'external_id': ch.get('external_id') or '',
                    'card': parsed, '_up': up, '_bin': bin_, '_start': st,
                    '_check': check, '_invoice_status': inv, '_challenge': ch,
                    '_trigger': trigger_res}
        if inv and inv.get('status') in ('ERROR', 'CANCELED', 'CLOSED', 'FAILED'):
            return {'ok': False,
                    'error': f"Плюс: платёж не прошёл (invoiceStatus "
                             f"{inv.get('status')}: {inv.get('error_code')})",
                    'purchase_token': purchase_token, 'invoice_id': invoice_id,
                    'card': parsed, '_up': up, '_bin': bin_, '_start': st,
                    '_check': check, '_invoice_status': inv,
                    '_trigger': trigger_res}
    istatus = str((inv or {}).get('status') or '')
    cstatus = str((check or {}).get('status') or '') \
        + str((check or {}).get('tr_status') or '')
    ok = istatus in ('SUCCESS', 'DONE', 'PAID') \
        or (istatus == '' and any(s in cstatus.lower() for s in ok_st))
    if not ok:
        return {'ok': False, 'stage': 'unknown',
                'error': 'Плюс: не удалось подтвердить оплату',
                'purchase_token': purchase_token, 'invoice_id': invoice_id,
                'card': parsed, '_up': up, '_bin': bin_, '_start': st,
                '_check': check, '_invoice_status': inv, '_trigger': trigger_res}
    # 5) активация: changeVoluntaryAgreementStatus ALLOW (захват seq 1040)
    ag = {}
    try:
        ag = plus_agreement(acc, status='ALLOW', csrf=csrf)
    except RuntimeError as e:
        ag = {'error': str(e)}
    return {'ok': True, 'stage': 'done', 'status': istatus or 'SUCCESS',
            'purchase_token': purchase_token, 'invoice_id': invoice_id,
            'card': parsed, '_up': up, '_bin': bin_, '_start': st,
            '_check': check, '_invoice_status': inv, '_agreement': ag,
            '_checkout': _checkout, '_invoice': _invoice, '_start_inv': _start,
            '_status_poll': _status, '_trigger': trigger_res}


def plus_get_offer(account, event_session_id='', landing=''):
    """Получить оффер Плюса для аккаунта, пробуя источники по очереди.

    Порядок (пользователь: "Если вдруг один не доступен — пробовать другой"):
      1. конкретный лендинг (plus_offers_from_landing), если задан landing;
      2. рекламный лендинг PLUS_LANDING_PERF (perf/plus);
      3. обычный лендинг PLUS_LANDING_DEFAULT;
      4. /api/v2/offers с контекстом рекламной страницы perf
         (page='perf', places=['main_card','secondary_card']) — как шлёт
         acquisition-виджет лендинга /perf/plus;
      5. устаревший SSR-парсер plus.yandex.ru (plus_offers);
      6. современный backend /api/v2/offers (plus_offers_v2, page plus_home).
    Первый источник, который вернул offerToken, побеждает. Если ни один не
    смог — RuntimeError со сводкой ошибок. Возвращает dict формата
    plus_offers_v2 (+ ключ '_source' — какой источник сработал).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    _acc_name = acc.get('name', '?')
    sid = (acc.get('session_id') or '').strip()
    _uid = sid.split('|')[1].split('.')[0] if '|' in sid else '?'
    print(f'[plus_get_offer] аккаунт={_acc_name} uid={_uid} yandexuid={acc.get("yandexuid","")} cookies={list(_web_cookies(acc).keys())}')
    attempts = []
    candidates = []
    if landing:
        candidates.append(('landing', landing))
    candidates += [
        ('perf', PLUS_LANDING_PERF),
        ('default', PLUS_LANDING_DEFAULT),
        ('v2_perf', None),
        ('ssr', None),
        ('v2', None),
    ]
    for kind, url in candidates:
        try:
            print(f'[plus_get_offer] пробую {kind}...')
            if kind in ('landing', 'perf', 'default'):
                of = plus_offers_from_landing(acc, url)
                of['_source'] = kind + ':' + url.split('?')[0]
            elif kind == 'v2_perf':
                # testIds из SSR лендинга (уникальны для аккаунта) — как шлёт
                # браузер; со статическим списком часть аккаунтов даёт 404
                tids = _plus_landing_test_ids(acc, PLUS_LANDING_PERF)
                of = plus_offers_v2(acc, event_session_id=event_session_id,
                                    page='perf', places=['main_card', 'secondary_card'],
                                    referer=PLUS_LANDING_PERF.split('?')[0] + '/',
                                    test_ids=tids)
                of['_source'] = 'v2_perf:/api/v2/offers (page=perf' + \
                    (f', testIds={len(tids)}' if tids else ', статич. testIds') + ')'
                of['_test_ids'] = tids
            elif kind == 'ssr':
                of = plus_offers(acc, target='plus-web', utm='afisha')
                of['_source'] = 'ssr:plus.yandex.ru'
                # нормализация ssr-вывода в формат plus_offers_v2
                of = {
                    'offer_token': of.get('offerToken') or '',
                    'target': of.get('target') or PLUS_WIDGET_TARGET,
                    'batch_id': of.get('offersBatchId') or '',
                    'position_id': of.get('offersPositionIds') or '',
                    'tariff_offer': of.get('tariffOfferName') or '',
                    'event_session_id': of.get('eventSessionId') or '',
                    'cross_session_id': of.get('crossSessionId') or '',
                    'hash_order_id': of.get('hashOrderId') or '',
                    '_source': 'ssr:plus.yandex.ru',
                    '_raw': of,
                }
            else:
                of = plus_offers_v2(acc, event_session_id=event_session_id)
                of['_source'] = 'v2:/api/v2/offers'
            if of and of.get('offer_token'):
                print(f'[plus_get_offer] {kind}: ОК token={str(of.get("offer_token",""))[:40]}...')
                return of
            attempts.append(f'{kind}: оффер пуст')
            print(f'[plus_get_offer] {kind}: оффер пуст')
        except RuntimeError as e:
            attempts.append(f'{kind}: {e}')
            print(f'[plus_get_offer] {kind}: ERR {e}')
    _err = 'Плюс: ни один оффер не доступен. Пробовал: ' + '; '.join(attempts)
    print(f'[plus_get_offer] ВСЕ ИСТОЧНИКИ ПРОВАЛЕНЫ: {_err}')
    raise RuntimeError(_err)


def plus_subscribe(account, card, sms_code='', purchase_token='',
                   kroken_uuid='', promo_id='', save=False,
                   offer_token='', event_session_id='', tariff_offer='',
                   invoice_id='', cross_session_id='', hash_order_id='',
                   batch_id='', position_id='', target='',
                   wait_status=False):
    """Подключить «Яндекс Плюс» на аккаунте картой.

    Рабочий флоу из перехвата без 3DS (capture.jsonl, сессия от 16.08):
      offers → csrf → compositeOfferCheckout → createInvoice → startInvoice →
      invoiceStatus до externalInvoice.form (purchase_token=payment_<hex>) →
      trust update_payment (bind_card=true) →
      diehard bin_info (префикс) → diehard start_payment_json (карта открытым
      текстом) → trust check_payment → invoiceStatus SUCCESS →
      changeStatus (changeVoluntaryAgreementStatus ALLOW) — активация.

    purchase_token и invoice_id можно передать вручную (повторный вызов после
    'sms' — с sms_code).

    Возвращает dict:
      {'ok': True, 'stage': 'sms', 'purchase_token':…, 'invoice_id':…} — нужен
      SMS-код (повторный вызов с sms_code);
      {'ok': True, 'stage': 'done', …} — подключение выполнено;
      {'ok': False, 'error': …} — ошибка.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    try:
        # 0) колбек акции Едадила «подтверждение участия» — ОБЯЗАТЕЛЕН перед
        #    подключением подписки на КАЖДОМ аккаунте (trigger-proxy.edadeal.ru).
        #    При повторном вызове (уже есть invoice/purchase_token) не шлём.
        trigger_res = None
        if not (invoice_id or purchase_token):
            trigger_res = edadeal_trigger(acc, promo_id=promo_id,
                                          kroken_uuid=kroken_uuid)
            kroken_uuid = trigger_res.get('kroken_uuid', kroken_uuid)
        csrf = plus_csrf(acc)
        # 1) если инвойс уже создан — идём сразу к оплате/проверке
        if invoice_id or purchase_token:
            if purchase_token and not invoice_id:
                return _plus_finish_payment(acc, purchase_token, card,
                                            sms_code=sms_code, csrf=csrf,
                                            trigger_res=trigger_res)
            inv = plus_invoice_status(acc, invoice_id=invoice_id, csrf=csrf)
            pt = purchase_token or inv.get('purchase_token') or ''
            st = inv.get('status') or ''
            if st in ('SUCCESS', 'DONE', 'PAID'):
                return {'ok': True, 'stage': 'done', 'status': st,
                        'invoice_id': invoice_id, 'invoice': inv,
                        '_trigger': trigger_res}
            if st in ('ERROR', 'CANCELED', 'CLOSED', 'FAILED'):
                return {'ok': False, 'error': f'Плюс: инвойс {st}',
                        'invoice_id': invoice_id, 'invoice': inv,
                        '_trigger': trigger_res}
            if pt:
                return _plus_finish_payment(acc, pt, card, sms_code=sms_code,
                                            csrf=csrf, invoice_id=invoice_id,
                                            trigger_res=trigger_res)
            return {'ok': True, 'stage': 'pending', 'status': st,
                    'invoice_id': invoice_id, 'invoice': inv,
                    '_trigger': trigger_res}
        # 2) оффер + чекаут + инвойс
        of = {}
        if offer_token:
            of = {'offerToken': offer_token,
                  'target': target or PLUS_WIDGET_TARGET,
                  'tariffOfferName': tariff_offer,
                  'batchId': batch_id, 'positionId': position_id,
                  'eventSessionId': event_session_id}
        try:
            if not of.get('offerToken'):
                ofv = plus_get_offer(acc, event_session_id=event_session_id)
                of = {'offerToken': ofv['offer_token'],
                      'target': ofv['target'] or PLUS_WIDGET_TARGET,
                      'tariffOfferName': ofv['tariff_offer'],
                      'batchId': ofv['batch_id'],
                      'positionId': ofv['position_id'],
                      'eventSessionId': ofv['event_session_id'],
                      '_source': ofv.get('_source') or ''}
                cross_session_id = cross_session_id or ofv.get('cross_session_id') or ''
                hash_order_id = hash_order_id or ofv.get('hash_order_id') or ''
            co = plus_composite_checkout(
                acc, offer_token=of.get('offerToken') or '',
                tarif=of.get('tariffOfferName') or '',
                target=of.get('target') or PLUS_WIDGET_TARGET,
                event_session_id=of.get('eventSessionId') or '')
        except RuntimeError as e:
            return {'ok': False,
                    'error': f'Плюс: не удалось получить оффер/чекаут: {e}',
                    '_offers': of}
        if not isinstance(co, dict) or co.get('ok') is not True:
            return {'ok': False,
                    'error': 'Плюс: чекаут не удался: '
                             + str((co or {}).get('raw') or co or {}),
                    '_offers': of, '_checkout': co, '_trigger': trigger_res}
        tarif = of.get('tariffOfferName') or co.get('tariff_offer') or ''
        esid = of.get('eventSessionId') or ''
        ci = plus_create_invoice(
            acc, offer_token=of.get('offerToken') or '', tariff_offer=tarif,
            csrf=csrf, target=of.get('target') or PLUS_WIDGET_TARGET,
            event_session_id=esid, cross_session_id=cross_session_id,
            hash_order_id=hash_order_id, batch_id=of.get('batchId') or batch_id,
            position_id=of.get('positionId') or position_id)
        inv_id = ci.get('invoice_id') or ''
        if not inv_id:
            return {'ok': False,
                    'error': 'Плюс: createInvoice не вернул id: ' + str(ci)[:300],
                    '_checkout': co, '_invoice': ci, '_trigger': trigger_res}
        # 3) старт и ожидание purchase_token в externalInvoice.form
        si = plus_start_invoice(acc, inv_id, csrf=csrf)
        print(f'[plus_subscribe] start_invoice: status={si.get("status")} invoice_id={si.get("invoice_id")}')
        st = plus_wait_purchase_token(acc, inv_id, csrf=csrf, attempts=15, delay=2.0)
        pt = st.get('purchase_token') or ''
        print(f'[plus_subscribe] wait_purchase_token: status={st.get("status")} pt={pt[:30]} form={str(st.get("form",""))[:100]}')
        if not pt.startswith('payment_'):
            return {'ok': False,
                    'error': 'Плюс: инвойс не дал purchase_token в form '
                             f'(status {st.get("status")}): {str(st.get("_raw"))[:300]}',
                    'invoice_id': inv_id, '_checkout': co, '_invoice': ci,
                    '_start': si, '_status': st, '_trigger': trigger_res}
        return _plus_finish_payment(acc, pt, card, sms_code=sms_code,
                                    csrf=csrf, invoice_id=inv_id,
                                    _checkout=co, _invoice=ci, _start=si,
                                    _status=st, trigger_res=trigger_res)
    except RuntimeError as e:
        return {'ok': False, 'error': str(e)}


# ---------- Суперапп-флоу (мобильный WebView, tc.eats.yandex.ru) ----------
#
#  Полное оформление заказа «как в Я.Го/VWebView»: те же хосты, заголовки
#  и тела, что в flows_eda_mumu.mitm (x-platform: superapp_taxi_web,
#  x-year-superapp-version: 1, Session_id cookie). В отличие от desktop_web,
#  этот канал консистентен для карт/промокодов (акции «Бесплатная доставка»
#  и т.п. не «умирают» между cart/promocode и созданием заказа).

def _go_hdrs(acc, lat=None, lon=None):
    """Заголовки суперапп-запроса (копия из перехвата flows_eda_mumu.mitm)."""
    lat = lat if lat is not None else float(acc.get('lat', DEFAULT_LAT))
    lon = lon if lon is not None else float(acc.get('lon', DEFAULT_LON))
    d = _dev(acc)
    ref = 'https://tc.eats.yandex.ru/4.0/eda-superapp/checkout'
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://tc.eats.yandex.ru',
        'referer': ref,
        'x-retpath-y': ref,
        'user-agent': _go_ua(acc),
        'x-platform': 'superapp_taxi_web',
        'x-superapp-version': '1',
        'x-app-version': d['app_version'],
        'x-appmetrica-deviceid': d['appmetrica_deviceid'],
        'x-appmetrica-uuid': d['appmetrica_uuid'],
        'x-client-session': uuid.uuid4().hex[:23],
        'x-device-id': d['device_id'],
        'x-yandex-deviceid': d['yandex_device_id'],
        'x-requested-with': 'ru.yandex.taxi',
        'x-ya-coordinates': f'latitude={lat},longitude={lon}',
        'x-yandex-uid': str(acc.get('yandexuid', '')),
        'x-yataxi-userid': '1f2a6fcef4814723845622276de8c876',
        'x-yataxi-user': '',
    }


def _go_call(acc, method, path, json_body=None, params=None, timeout=25):
    """Запрос к суперапп-бэкенду (tc.eats.yandex.ru/4.0/eda-superapp)."""
    ck = _web_cookies(acc)
    url = GO_EATS_HOST + path
    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}
    try:
        r = requests.request(method, url, headers=_go_hdrs(acc), cookies=ck,
                             json=json_body, params=params, timeout=timeout,
                             proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Еда (суперапп): сеть ({method} {path}): {e}')
    if r.status_code in (401, 403):
        raise RuntimeError(f'Я.Еда (суперапп): авторизация отклонена ({r.status_code}): Session_id невалиден')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Еда (суперапп): HTTP {r.status_code} на {method} {path}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def _addr_superapp(addr):
    """Перевести адрес веб-флоу в формат супераппа: {base_info, details}.

    Элементы details всегда четыре (office/entrance/doorcode/floor) — как
    в захвате; отсутствующие поля — пустые строки. Комментарий уходит в
    base_info.comment.
    """
    a = addr or {}
    loc = a.get('location') or {}
    if isinstance(loc, dict):
        lat = loc.get('latitude') or DEFAULT_LAT
        lon = loc.get('longitude') or DEFAULT_LON
    else:
        lat, lon = DEFAULT_LAT, DEFAULT_LON
    base = {
        'type': {'id': 0},
        'location': [lon, lat],
        'country': a.get('country') or 'Россия',
        'city': a.get('city') or 'Омск',
        'street': a.get('street') or '',
        'house': a.get('house') or '',
        'full_text': a.get('full_text') or '',
        'short_text': a.get('short_text') or '',
        'uri': a.get('uri') or '',
        'comment': a.get('comment') or '',
    }
    if a.get('areas'):
        base['areas'] = a['areas']
    if a.get('districts'):
        base['districts'] = a['districts']
    details = [
        {'type': 'office', 'text': (a.get('office') or a.get('flat') or '')},
        {'type': 'entrance', 'text': (a.get('entrance') or '')},
        {'type': 'doorcode', 'text': (a.get('doorcode') or a.get('intercom') or '')},
        {'type': 'floor', 'text': (a.get('floor') or '')},
    ]
    return {'base_info': base, 'details': details}


def go_checkout(account, slug, address, lat=None, lon=None,
                payment_id='sbp_qr', payment_type='sbp'):
    """Оформление супераппом: POST /api/v2/cart/go-checkout.

    Адрес конвертируется в base_info/details (как WebView Го). Ответ —
    offers + paymentTypeConfig (тот же формат, что парсит web_offer).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    if isinstance(payment_id, dict):
        payment_id = payment_id.get('id') or 'sbp_qr'
        payment_type = payment_type or payment_id.get('type') or 'sbp'
    if isinstance(payment_type, dict):
        payment_type = payment_type.get('type') or 'sbp'
    body = {
        'address': _addr_superapp(address),
        'place_slug': slug,
        'payment': {'recently_link_cards': (payment_id == 'add_new_card')},
    }
    return _go_call(acc, 'POST', '/api/v2/cart/go-checkout', body,
                    params={'longitude': lon, 'latitude': lat})


def go_apply_promocode(account, slug, code, offer_identity='', lat=None, lon=None,
                       receiving_type='delivery'):
    """Применить промокод супераппом: POST /api/v2/cart/promocode.

    Параметры и тело — как в захвате (params: placeSlug/soft_multi/
    shippingType/offer_identity, body {code}).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {
        'placeSlug': slug,
        'soft_multi': 'true',
        'shippingType': 'delivery',
        'receiving_type': receiving_type,
        'is_delivery_without_address': 'false',
    }
    if offer_identity:
        params['offer_identity'] = offer_identity
    return _go_call(acc, 'POST', '/api/v2/cart/promocode',
                    {'code': code}, params=params)


def go_create_order(account, slug, address, offer_identity, payment_info, phone='',
                    code=None, request_id=None, cart_id=None,
                    extended_options=None, recently_link_cards=False,
                    plus_subscription_toggle_state=False, spend_plus=None):
    """Создать заказ супераппом: POST /api/v1/orders.

    Тело — копия из flows_eda_mumu.mitm (260815-5424038 / 260815-6472614):
    address base_info/details, extended_options с tips_chosen_offer,
    payment_information {type, costForCustomer, id, currency},
    request_id = cart_id.offer_identity.
    spend_plus — списать баллы Я.Плюс (cashback_participation, amount).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not request_id and cart_id:
        request_id = f'{cart_id}.{offer_identity}'
    cfc = payment_info.get('costForCustomer') or {}
    if isinstance(cfc, dict):
        currency = cfc.get('currency') or ''
        cfc = cfc.get('value') or cfc.get('amount') or ''
    else:
        currency = payment_info.get('currency') or ''
    try:
        cfc_str = f'{float(cfc):.2f}'
    except (TypeError, ValueError):
        cfc_str = str(cfc)
    if extended_options is None:
        extended_options = [
            {'type': 'delivery_options', 'leave_at_the_door': False},
            {'type': 'tips_chosen_offer', 'tips_type': 'zero', 'save_selected_tip': False},
        ]
    body = {
        'payment_method_id': WEB_PAYMENT_METHOD_EATS,
        'phone': phone,
        'change_on': 0,
        'persons_quantity': 0,
        'payment_information': {
            'type': payment_info.get('type') or 'sbp',
            'costForCustomer': cfc_str,
            'id': payment_info.get('id') or 'sbp_qr',
            'currency': currency or 'RUB',
        },
        'extended_options': _with_spend_plus(extended_options, spend_plus),
        'payment': {'recently_link_cards': recently_link_cards},
        'place_slug': slug,
        'address': _addr_superapp(address),
        'plus_subscription_toggle_state': plus_subscription_toggle_state,
        'request_id': request_id or '',
    }
    if code:
        body['code'] = code
    return _go_call(acc, 'POST', '/api/v1/orders', body)


def go_order_tracking(account, order_id):
    """Статус оплаты/QR супераппом: POST eats-payments order/tracking."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _go_call(acc, 'POST', '/eats/v1/eats-payments/v1/order/tracking',
                    {'order_id': order_id})


def go_sbp_qr(account, order_id, attempts=15, delay=1.5):
    """QR для СБП супераппом: поллит order/tracking до purchase_token.

    Возвращает {order_id, payment, qr_url, purchase_token, service_token}
    (Trust get_payment для контента QR — как web_sbp_qr).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    ck = _web_cookies(acc)
    purchase_token = service_token = ''
    tracking = None
    for _ in range(attempts):
        tracking = go_order_tracking(acc, order_id)
        pay = (tracking or {}).get('payment')
        if pay is None:
            pay = ((tracking or {}).get('order') or {}).get('payment') or {}
        payload = pay.get('payload') or {}
        purchase_token = payload.get('purchase_token') or ''
        service_token = payload.get('service_token') or ''
        if purchase_token:
            break
        time.sleep(delay)
    order = (tracking or {}).get('order') or {}
    out = {
        'order_id': (order.get('order') or {}).get('order_id') or order_id,
        'title': order.get('title'),
        'description': order.get('description'),
        'payment': pay if tracking else {},
        'purchase_token': purchase_token,
        'service_token': service_token,
    }
    if purchase_token:
        try:
            r = requests.get(
                'https://trust.yandex.ru/web/get_payment',
                headers={
                    'user-agent': _go_ua(acc),
                    'accept': '*/*',
                    'referer': 'https://trust.yandex.ru/web/payment?template_tag=desktop%2Fform',
                },
                cookies=ck,
                params={'purchase_token': purchase_token},
                timeout=20,
            )
            if r.status_code == 200:
                data = r.json()
                out['qr_url'] = data.get('processing_payment_form_url') or ''
                out['amount'] = data.get('amount')
                out['currency'] = data.get('currency')
                out['trust_status'] = data.get('status')
        except (requests.RequestException, ValueError) as e:
            out['trust_error'] = str(e)
    return out


def go_promo_apply_checkout(account, slug, code, address, lat=None, lon=None,
                            payment_id='sbp_qr', payment_type='sbp',
                            offer_identity=''):
    """Применить промокод (go_apply_promocode) и пересчитать корзину go_checkout.

    Аналог promo_apply_checkout, но целиком на суперапп-канале: промокод
    оседает в корзине и виден при создании заказа (акции «Бесплатная
    доставка» и т.п. не «протухают» к моменту /api/v1/orders).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    res = go_apply_promocode(acc, slug, code, offer_identity=offer_identity,
                             lat=lat, lon=lon)
    out = {'result': res}
    if not (isinstance(res, dict) and res.get('status') == 'error'):
        try:
            d = go_checkout(acc, slug, address, lat=lat, lon=lon,
                            payment_id=payment_id, payment_type=payment_type)
            offer, pp = web_offer(d, payment_id, payment_type)
            if not offer or not pp:
                avail = [a for a in web_available_payments(d)
                         if a.get('type') != 'add_new_card']
                if avail:
                    first = avail[0]
                    offer, pp = web_offer(d, first.get('id') or first.get('type'),
                                          first.get('type'))
            payment = None
            if offer and pp:
                cfc = pp.get('costForCustomer') or {}
                if isinstance(cfc, dict):
                    cfc = cfc.get('value') or ''
                request_id = offer.get('requestId') or ''
                payment = {
                    'id': pp.get('id'), 'type': pp.get('type'),
                    'title': pp.get('title'),
                    'costForCustomer': cfc,
                    'serviceFee': pp.get('serviceFee'),
                    'offer_identity': offer.get('offer_identity'),
                    'requestId': request_id,
                    'cart_id': request_id.split('.')[0] if '.' in request_id else '',
                }
            out.update({'checkout': d, 'payment': payment,
                        'available': web_available_payments(d)})
        except Exception:
            pass
    return out


def order_status(account, order_id):
    """Статус заказа / трекинг."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', f'/api/v1/orders/{order_id}', None, None)


def active_orders(account):
    """Активные заказы / трекинг."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', '/api/v2/orders/tracking', None, None)


def order_count(account, lat=None, lon=None, max_pages=30):
    """Количество заказов в Я.Еде (eats/v1/orders-info/v1/orders).

    Перебирает историю заказов по пагинации (cursor), считает всего.
    Требует Bearer-токен аккаунта.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    if not _extract_bearer(acc):
        raise RuntimeError('нет Bearer-токена (история заказов недоступна)')
    total = 0
    cursor = None
    for _ in range(max_pages):
        params = {'cursor': cursor} if cursor else None
        d = _eda_call(acc, 'POST', '/eats/v1/orders-info/v1/orders',
                      lat, lon, params=params, json_body={})
        if not isinstance(d, dict):
            break
        total += len(d.get('orders') or [])
        pag = d.get('pagination_settings') or {}
        if not pag.get('has_more'):
            break
        cursor = pag.get('cursor')
        if not cursor:
            break
    return total


def cancel_order(account, order_id):
    """Отмена заказа. Требует досъёмки."""
    raise NotImplementedError(
        'отмена заказа Я.Еды: нужен досъём из приложения')


# ---------- promo codes ----------

def _find_promo_values(obj, out):
    """Рекурсивно собрать промокоды из полей app_link/url вида promocode?value=XXX."""
    if isinstance(obj, dict):
        for v in obj.values():
            _find_promo_values(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _find_promo_values(v, out)
    elif isinstance(obj, str):
        for m in re.finditer(r'promocode\?value=([A-Z0-9_\-]+)', obj, re.IGNORECASE):
            out.append(m.group(1).upper())
        # «...по коду CHICK» — маленькие баннеры-информеры внутри ресторанов
        for m in re.finditer(r'по коду ([A-Z0-9_\-]{2,})', obj, re.IGNORECASE):
            out.append(m.group(1).upper())


def _places_from_layout(d):
    """Слаги ресторанов/магазинов из главного layout."""
    slugs = []
    if not isinstance(d, dict):
        return slugs
    data = d.get('data') or {}
    for key in ('places_v2_lists', 'places_v2_medium_carousels', 'mini_places_carousel'):
        for blk in data.get(key) or []:
            for p in (blk.get('payload') or {}).get('places') or []:
                slug = p.get('slug') or ''
                if slug:
                    slugs.append(slug)
    return slugs


def _go_ua(acc):
    """User-Agent для superapp-запросов, уникальный под device-профиль."""
    d = _dev(acc)
    return (
        f'Mozilla/5.0 (Linux; Android {d["os_version"]}; {d["model"]} '
        f'Build/{d["android_build"]}; wv) AppleWebKit/537.36 '
        f'(KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Safari/537.36 '
        f'yandex-taxi/{d["taxi_version"]} Android/{d["os_version"]} '
        f'({d["manufacturer"]}; {d["model"]}) Superapp/Eats '
        f'promoMode/restricted EatsKit/{d["eatskit_version"]} mode/fullscreen'
    )


def _go_cookies(acc):
    """Куки для вкладки «Еда» в Go: webviewuserid + Session_id + yandexuid."""
    wid = _dev(acc)['device_id']
    ck = {'webviewuserid': wid, 'webviewuserid_eats': wid}
    sid = (acc.get('session_id') or '').strip() or (acc.get('cookies') or {}).get('Session_id', '').strip()
    if sid:
        ck['Session_id'] = sid
    yuid = (acc.get('yandexuid') or '').strip()
    if yuid:
        ck['yandexuid'] = yuid
    return ck


def go_food_layout(acc, lat=None, lon=None):
    """Лайаут вкладки «Еда» в Яндекс Go (layout-constructor).

    Содержит informers_v2 — промо-баннеры («...по коду XXX»), которые
    видит пользователь в Go. Работает по Session_id аккаунта.
    """
    sid = (acc.get('session_id') or '').strip() or (acc.get('cookies') or {}).get('Session_id', '').strip()
    if not sid:
        raise RuntimeError('у аккаунта нет Session_id (нужен для вкладки «Еда» в Go)')
    lat, lon = _coords(acc, lat, lon)
    url = GO_EATS_HOST + '/eats/v1/layout-constructor/v1/layout'
    hdrs = {
        'user-agent': _go_ua(acc),
        'content-type': 'application/json;charset=UTF-8',
        'accept': 'application/json, text/plain, */*',
        'origin': GO_EATS_HOST,
        'referer': (GO_EATS_HOST + '/?externalEntrypoint=hub_button_eats&mode=fullscreen'
                    '&superappIsOpen=true&themeVariantKey=light'),
        'x-requested-with': 'ru.yandex.taxi',
        'x-device-id': _dev(acc)['device_id'],
    }
    body = {'location': {'latitude': lat, 'longitude': lon}}
    try:
        r = requests.post(url, headers=hdrs, json=body, cookies=_go_cookies(acc), timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Яндекс Go (Еда): сеть: {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Яндекс Go (Еда): HTTP {r.status_code}: {r.text[:200]}')
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f'Яндекс Go (Еда): ответ не JSON: {r.text[:200]}')


def _go_layout_codes(d):
    """Промокоды из всего лайаута вкладки «Еда» в Go.

    Ловит все формы промо: deeplink eda.yandex://promocode?value=XXX
    в url/app_link любого баннера (madv_hero_banners, banners_carousel),
    informers_v2 (menu_informers) и коды activation_code (view.code.value).
    """
    codes = []

    def walk(o):
        if isinstance(o, dict):
            if o.get('type') == 'activation_code':
                cv = (o.get('code') or {}).get('value')
                if cv:
                    codes.append(str(cv).upper())
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            for m in re.finditer(r'promocode\?value=([A-Z0-9_\-]+)', o, re.I):
                codes.append(m.group(1).upper())

    walk(d)
    return codes


def _go_informer_codes(d):
    """Промокоды из informers_v2 лайаута вкладки «Еда» в Go.

    Баннер-информер: payload.action.value.payload.deeplink
    (eda.yandex://promocode?value=XXX) и payload.action.view.code.value.
    """
    codes = []
    if not isinstance(d, dict):
        return codes
    for blk in (d.get('data') or {}).get('informers_v2') or []:
        for inf in blk.get('informers') or []:
            act = (inf.get('payload') or {}).get('action') or {}
            val = act.get('value') or {}
            dl = ((val.get('payload') or {}).get('deeplink')) or ''
            m = re.search(r'promocode\?value=([A-Z0-9_\-]+)', dl, re.I)
            if m:
                codes.append(m.group(1).upper())
            view = act.get('view') or {}
            cv = ((view.get('code') or {}).get('value')) or ''
            if cv:
                codes.append(cv.upper())
    return codes


def _promo_items(acc, lat, lon, progress=None, max_restaurants=1):
    """Промокоды аккаунта: баннеры главного экрана, личный список,
    маленькие баннеры внутри ресторанов (menu informers).

    progress — callback(msg, frac) для отчёта о ходе (frac 0..1).
    max_restaurants — сколько ресторанов с главного экрана обойти
    (в Go во вкладке «Еда» промокоды висят и на баннере, и в ресторанах).
    """
    res = {'codes': [], 'error': None, 'restaurants_scanned': 0}
    layout_data = None
    try:
        if progress:
            progress('Загружаю главный экран (баннеры)', 0.0)
        layout_data = layout(acc, lat=lat, lon=lon)
        vals = []
        _find_promo_values(layout_data, vals)
        res['codes'] = list(set(vals))
    except Exception as e:
        res['error'] = str(e)
    try:
        if progress:
            progress('Личный список промокодов', 0.1)
        d = _eda_call(acc, 'GET', '/api/v1/user/promocodes', lat, lon)
        codes = d.get('promocodes') or [] if isinstance(d, dict) else []
        for c in codes:
            if isinstance(c, dict):
                v = c.get('value') or c.get('promocode') or ''
            elif isinstance(c, str):
                v = c
            else:
                v = ''
            if v:
                res['codes'].append(v)
    except Exception as e:
        if res['error']:
            res['error'] += '; ' + str(e)
        else:
            res['error'] = str(e)
    # вкладка «Еда» в Яндекс Go: промо-баннеры (informers_v2) по Session_id
    sid = (acc.get('session_id') or '').strip() or (acc.get('cookies') or {}).get('Session_id', '').strip()
    if sid:
        try:
            if progress:
                progress('Вкладка «Еда» в Go (баннеры)', 0.12)
            go = go_food_layout(acc, lat=lat, lon=lon)
            vals = _go_layout_codes(go)
            res['codes'] += vals
        except Exception as e:
            if res['error']:
                res['error'] += '; ' + str(e)
            else:
                res['error'] = str(e)
    # маленькие баннеры («по коду XXX») внутри ресторанов с главного экрана
    slugs = _places_from_layout(layout_data)
    n = min(len(slugs), max_restaurants)
    for i, slug in enumerate(slugs[:n]):
        try:
            if progress:
                progress(f'Ресторан {i + 1}/{n}: {slug}', 0.15 + 0.85 * i / max(n, 1))
            m = restaurant_menu(acc, slug, lat=lat, lon=lon)
            vals = []
            _find_promo_values(m, vals)
            res['codes'] += vals
            res['restaurants_scanned'] += 1
        except Exception:
            continue
    # уникальный набор промокодов на аккаунте
    res['codes'] = sorted({c.upper() for c in res['codes'] if c})
    if progress:
        progress('Готово', 1.0)
    return res


def find_promocodes(account, lat=None, lon=None, progress=None, max_restaurants=1):
    """Найти промокоды на аккаунте Я.Еды.

    Собирает: баннеры главного экрана, личный список промокодов и
    промо-информеры внутри ресторанов (как вкладка «Еда» в Яндекс Go).

    Возвращает dict: {codes: [уникальные промокоды аккаунта],
    error: str|None, restaurants_scanned: int}.
    progress — callback(msg, frac).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _promo_items(acc, lat, lon, progress, max_restaurants)


# ============================================================
#  Свои Плюсы: ежедневные подарки (sp.yandex.ru/daily).
#
#  Авторизация — cookie Session_id (+ yandexuid), без капчи.
#  Layout приходит из GraphQL egw.sp.plet.yandex.ru (operation
#  pageableSectionGroups — только POST, тело строго из whitelist).
#  Детали и получение подарка — REST egw.daily.plus.yandex.ru.
# ============================================================

# Полная операция GraphQL pageableSectionGroups (должна совпадать с whitelist).
SP_LAYOUT_QUERY = '''\n    query pageableSectionGroups($targeting: TargetingInput!, $attributes: AdditionalAttributesInput, $weightType: SHORTCUT_WEIGHT_TYPE!, $isSDK: Boolean!, $isAllWeightType: Boolean = false) {\n  pageableLayout(\n    input: {targetingWithPagination: {targeting: $targeting, attributes: $attributes}, weightType: $weightType}\n  ) {\n    baseBackgroundColor\n    id\n    name\n    style\n    sectionGroups {\n      sections {\n        id\n        name\n        type\n        hasHeavyMetaShortcuts @skip(if: $isAllWeightType)\n        hasHeavyShortcuts @skip(if: $isAllWeightType)\n        hasMoreShortcuts\n        metaShortcuts {\n          ...BaseShortcut\n        }\n        popupScrollingIsEnabled\n        shortcuts {\n          ...BaseShortcut\n        }\n        shouldHaveViewStatus\n        additionalData\n      }\n    }\n  }\n}\n    \n    fragment BaseShortcut on Shortcut {\n  __typename\n  id\n  type\n  title\n  subtitle\n  actions {\n    ...BaseAction\n  }\n  background {\n    __typename\n    color\n    imageUrl\n    mobileImageUrl\n    lottieUrl\n    lottiePlayType\n    mobileLottieUrl\n    mobileLottiePlayType\n  }\n  textStyle {\n    __typename\n    color\n  }\n  iconUrl\n  iconLottieUrl\n  iconLottiePlayType\n  commonOverlays {\n    ...Overlays\n  }\n  popups @include(if: $isSDK) {\n    id\n  }\n  popups @skip(if: $isSDK) {\n    ...BasePopup\n  }\n  name\n  serviceName\n  subscriptionProductsTarget\n  additionalData\n  hasBeenRead\n  completed\n}\n    \n\n    fragment BaseAction on Action {\n  __typename\n  actionType\n  customSubtype\n  afishaSettings {\n    ...AfishaAction\n  }\n  applicationLink\n  deeplink\n  url\n  inApp\n  subscriptionButtonType\n  subscriptionPaymentMethod\n  subscriptionProductFeatures\n  subscriptionWidgetType\n  text\n  backgroundColor\n  textColor\n  useModalWindow\n  useSmartWebView\n  offerId\n  silent\n  acquisitionPlatformSubscriptionProperties {\n    ...AcquisitionPlatform\n  }\n  modalWindow {\n    ...ModalWindowPopup\n  }\n}\n    \n\n    fragment AfishaAction on AfishaSettings {\n  clientKey\n  dealerId\n  dealerType\n  regionId\n  urlQueryParams\n}\n    \n\n    fragment AcquisitionPlatform on AcquisitionPlatformSubscriptionProperties {\n  page\n  places\n  restrictions\n}\n    \n\n    fragment ModalWindowPopup on ModalWindowActionProperties {\n  popupId\n  height\n  sizeUnit\n}\n    \n\n    fragment Overlays on Overlay {\n  __typename\n  shape\n  text\n  textColor\n  imageUrl\n  imageTag\n  lottieUrl\n  lottiePlayType\n  background {\n    color\n    imageUrl\n    imageTag\n  }\n  attributedText {\n    items {\n      ...ImageProperties\n      ...StyledTextProperties\n      ...TextIconProperties\n      ...TextProperties\n    }\n  }\n}\n    \n\n    fragment ImageProperties on ImageProperties {\n  __typename\n  color\n  metaColor\n  width\n  imageTag\n  name\n}\n    \n\n    fragment StyledTextProperties on StyledTextProperties {\n  __typename\n  id\n  isBold\n  isItalic\n  text\n  textColor {\n    rawValue\n  }\n}\n    \n\n    fragment TextIconProperties on TextIconProperties {\n  __typename\n  id\n  url\n  fallbackText\n}\n    \n\n    fragment TextProperties on TextProperties {\n  __typename\n  color\n  text\n  name\n}\n    \n\n    fragment BasePopup on Popup {\n  id\n  name\n  background {\n    color\n    imageTag\n    imageUrl\n  }\n  buttons {\n    action {\n      ...BaseAction\n    }\n    backgroundColor\n    text\n    textColor\n    subscriptionProductTarget\n  }\n  commonOverlays {\n    ...Overlays\n  }\n  disclaimer\n  iconUrl\n  legal {\n    action {\n      ...BaseAction\n    }\n    text\n  }\n  subtitle\n  textColor\n  title\n  additionalData\n}\n    \n'''

SP_LAYOUT_VARIABLES = {
    'targeting': {
        'appMetricaUUID': None,
        'sdkVersion': None,
        'appVersion': None,
        'consumer': None,
        'consumerType': 'SP_PROMO_CODES',
        'place': 'main',
        'device': 'DESKTOP',
        'flags': [],
        'geoId': None,
        'loyaltyInfo': None,
        'message': None,
        'platform': 'WEB_DESKTOP',
        'plus': None,
        'featureNames': None,
        'segment': None,
        'service': 'promocodes',
        'target': None,
        'language': 'ru',
        'layoutId': None,
        'location': {'geoId': None, 'coordinates': None, 'geoPinPosition': None},
        'testIds': [],
        'theme': 'LIGHT',
        'restrictionMode': 'AUTO',
        'isNativePaymentAvailable': False,
        'inappCountryCode': None,
        'subscriptionResumed': None,
    },
    'weightType': 'ALL',
    'attributes': {'communicationId': None, 'movieId': None},
    'isSDK': False,
    'isAllWeightType': True,
}

SP_UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
         '(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36')


def sp_clean(text):
    """Развернуть HTML-сущности (&nbsp;, &laquo;…) и убрать лишние пробелы."""
    if not text:
        return ''
    return re.sub(r'\s+', ' ', html.unescape(str(text))).strip()


def sp_session_id(acc):
    """Сырой Session_id для API «Свои Плюсы»."""
    return (acc.get('session_id') or '').strip() or (acc.get('cookies') or {}).get('Session_id', '')

def sp_headers(acc):
    """Браузерные заголовки для egw-API «Свои Плюсы» (с кукой Session_id)."""
    h = {
        'Accept': 'application/json, text/plain, */*',
        'Origin': 'https://sp.yandex.ru',
        'Referer': 'https://sp.yandex.ru/',
        'User-Agent': SP_UA,
        'X-Forwarded-For': '92.124.160.8',
        'X-Requested-With': 'XMLHttpRequest',
    }
    sid = sp_session_id(acc)
    cookie = f'Session_id={sid}'
    yuid = (acc.get('yandexuid') or (acc.get('cookies') or {}).get('yandexuid') or '').strip()
    if yuid:
        cookie += f'; yandexuid={yuid}'
    h['Cookie'] = cookie
    return h


def sp_daily_layout(acc):
    """Layout страницы daily: список подарков (reward_id + статус).

    Возвращает список dict'ов: {reward_id, title, subtitle, status}.
    """
    sid = sp_session_id(acc)
    if not sid:
        raise RuntimeError('у аккаунта нет Session_id (нужен для sp.yandex.ru/daily)')
    h = sp_headers(acc)
    h['Content-Type'] = 'application/json'
    url = SP_GRAPHQL_URL + '?query_name=web%3FpageableSectionGroups'
    body = {
        'query': SP_LAYOUT_QUERY,
        'variables': SP_LAYOUT_VARIABLES,
        'operationName': 'pageableSectionGroups',
    }
    try:
        r = requests.post(url, headers=h, json=body, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Свои Плюсы: сеть (layout): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Свои Плюсы: HTTP {r.status_code} (layout): {r.text[:300]}')
    try:
        d = r.json()
    except Exception:
        raise RuntimeError(f'Свои Плюсы: ответ layout не JSON: {r.text[:200]}')
    data = (d or {}).get('data') or {}
    layout = data.get('pageableLayout') or {}
    rewards = []
    for sg in layout.get('sectionGroups') or []:
        for s in sg.get('sections') or []:
            if s.get('type') != 'HOME_DAILY_BIG_REWARDS':
                continue
            for sh in s.get('shortcuts') or []:
                rid = None
                for p in sh.get('popups') or []:
                    if p.get('id'):
                        rid = p['id']
                        break
                if not rid:
                    m = re.search(r'id=([MPE0-9\-_]+)', json.dumps(sh.get('actions') or []))
                    if m:
                        rid = m.group(1)
                if not rid:
                    continue
                status = None
                for ov in sh.get('commonOverlays') or []:
                    for it in (ov.get('attributedText') or {}).get('items') or []:
                        if it.get('name') == 'status':
                            status = it.get('text')
                rewards.append({
                    'reward_id': rid,
                    'title': sp_clean(sh.get('title')),
                    'subtitle': sp_clean(sh.get('subtitle')),
                    'status': status,
                })
    return rewards


def sp_reward_detail(acc, reward_id):
    """Детали подарка: displayStatus, presentOptions (варианты), expiresAt."""
    url = SP_DAILY_BASE + '/plusometer/v2/view/reward/detail'
    params = {'reward_id': reward_id, 'ext_source': 'PLUSOMETER', 'theme': 'LIGHT'}
    try:
        r = requests.get(url, headers=sp_headers(acc), params=params, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Свои Плюсы: сеть (detail): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Свои Плюсы: HTTP {r.status_code} (detail): {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f'Свои Плюсы: ответ detail не JSON: {r.text[:200]}')


def sp_claim_reward(acc, reward_id, chosen_reward_id):
    """Активировать подарок: выбираем вариант presentOption -> промокод.

    Возвращает тело ответа (displayStatus=ACTIVATED, promocode, expiresAt).
    """
    url = (SP_DAILY_BASE + f'/plusometer/v2/view/reward/detail/{reward_id}/claim'
           + '?chosenRewardId=' + urllib.parse.quote(chosen_reward_id) + '&theme=LIGHT')
    try:
        r = requests.post(url, headers=sp_headers(acc), data=b'', timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Свои Плюсы: сеть (claim): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Свои Плюсы: HTTP {r.status_code} (claim): {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f'Свои Плюсы: ответ claim не JSON: {r.text[:200]}')


def sp_present_options(detail):
    """Список вариантов подарка из detail (id + сервис + название)."""
    out = []
    for o in (detail or {}).get('presentOptions') or []:
        if not isinstance(o, dict):
            continue
        svc = (o.get('service') or {}) if isinstance(o.get('service'), dict) else {}
        # название варианта — в разных полях у разных сервисов
        title = (o.get('title') or o.get('subtitle') or o.get('popupTitle')
                 or o.get('description') or '')
        out.append({
            'id': o.get('id'),
            'type': o.get('type'),
            'service_id': svc.get('serviceId'),
            'service_name': sp_clean(svc.get('serviceName') or svc.get('servicePrettyName')),
            'title': sp_clean(title),
        })
    return out


def collect_sp_daily(account, claim=False, progress=None):
    """Собрать ежедневные подарки «Свои Плюсы» на аккаунте.

    Возвращает dict: {rewards: [{reward_id, title, status, options,
    chosen, promocode, expires_at, error}], error: str|None}.
    progress — callback(msg, frac 0..1).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not acc:
        raise RuntimeError(f'аккаунт "{account}" не найден')
    out = {'rewards': [], 'error': None}
    try:
        if progress:
            progress('Загружаю layout', 0.0)
        rewards = sp_daily_layout(acc)
        total = max(len(rewards), 1)
        for i, rw in enumerate(rewards):
            rid = rw['reward_id']
            if progress:
                progress(f'Детали {rid} ({i + 1}/{total})', 0.05 + 0.55 * i / total)
            try:
                detail = sp_reward_detail(acc, rid)
            except Exception as e:
                out['rewards'].append({'reward_id': rid, 'title': rw.get('title'),
                                       'status': rw.get('status'), 'error': str(e)})
                continue
            entry = {
                'reward_id': rid,
                'title': sp_clean((detail or {}).get('popupTitle')) or rw.get('title'),
                'status': (detail or {}).get('displayStatus') or rw.get('status'),
                'options': sp_present_options(detail),
                'promocode': (detail or {}).get('promocode'),
                'expires_at': (detail or {}).get('expiresAt'),
                'error': None,
            }
            # для неактивированного подарка (REACHED) layout даёт заголовок карточки
            # «Выбирайте, что забирать» — вместо него показываем первый вариант
            opts = entry['options']
            if entry['status'] == 'REACHED' and opts:
                first = opts[0]
                opt_title = first.get('service_name') or first.get('title') or ''
                if opt_title:
                    entry['title'] = opt_title
            # забираем только Перекрёсток (perekrestok), если он доступен
            perek = next((o for o in opts
                          if 'perekrestok' in str(o.get('service_id') or '')
                          or 'perekrestok' in str(o.get('service_name') or '').lower()
                          or 'perekrestok' in str(o.get('title') or '').lower()), None)
            if claim and entry['status'] == 'REACHED' and perek:
                if progress:
                    progress(f'Активация {rid}: {perek.get("id")}', 0.65 + 0.3 * i / total)
                try:
                    cl = sp_claim_reward(acc, rid, perek['id'])
                    entry['chosen'] = perek.get('id')
                    entry['status'] = cl.get('displayStatus') or entry['status']
                    entry['promocode'] = cl.get('promocode')
                    entry['expires_at'] = cl.get('expiresAt')
                    if cl.get('popupTitle'):
                        entry['title'] = cl.get('popupTitle')
                except Exception as e:
                    entry['error'] = str(e)
            elif claim and entry['status'] == 'REACHED' and opts and not perek:
                entry['status'] = 'SKIPPED'
                entry['error'] = 'Перекрёсток недоступен — подарок не забран'
            out['rewards'].append(entry)
    except Exception as e:
        out['error'] = str(e)
    if progress:
        progress('Готово', 1.0)
    return out


# ---------- хранение полученных промокодов («Свои Плюсы») ----------

def load_sp_gifts():
    try:
        with open(SP_GIFTS_FILE, encoding='utf-8') as f:
            return json.load(f).get('gifts', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_sp_gifts(items):
    with open(SP_GIFTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'gifts': items}, f, ensure_ascii=False, indent=2)


def record_sp_gift(acc, reward):
    """Записать полученный промокод (или статус) подарка в sp_gifts.json."""
    items = load_sp_gifts()
    entry = {
        'account': acc.get('name', ''),
        'reward_id': reward.get('reward_id'),
        'title': reward.get('title'),
        'chosen': reward.get('chosen'),
        'status': reward.get('status'),
        'promocode': reward.get('promocode'),
        'expires_at': reward.get('expires_at'),
        'error': reward.get('error'),
        'collected_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    items.append(entry)
    save_sp_gifts(items)


# ---------- «Свои Плюсы»: Колесо Фортуны (sp.yandex.ru/wheel) ----------

def _js_unescape(s):
    """Распаковать JS-строку (экраны \\", \\\\, \\uXXXX) в обычный текст."""
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == '\\' and i + 1 < n:
            nxt = s[i + 1]
            if nxt == '"':
                out.append('"'); i += 2; continue
            if nxt == '\\':
                out.append('\\'); i += 2; continue
            if nxt == '/':
                out.append('/'); i += 2; continue
            if nxt == 'n':
                out.append('\n'); i += 2; continue
            if nxt == 't':
                out.append('\t'); i += 2; continue
            if nxt == 'r':
                out.append('\r'); i += 2; continue
            if nxt == 'b':
                out.append('\b'); i += 2; continue
            if nxt == 'f':
                out.append('\f'); i += 2; continue
            if nxt == 'u' and i + 5 < n:
                try:
                    out.append(chr(int(s[i + 2:i + 6], 16))); i += 6; continue
                except ValueError:
                    pass
            out.append(c)
        else:
            out.append(c)
        i += 1
    return ''.join(out)


def _rsc_object(text, start):
    """Вернуть текст JSON-объекта от открывающей '{' до парной '}'."""
    depth = 0
    i = start
    in_str = False
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == '\\':
                i += 2; continue
            if ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    break
        i += 1
    return text[start:i + 1]


def _rsc_value(text, key):
    """Достать значение ключа key из распакованного RSC-текста страницы."""
    k = '"' + key + '":'
    p = text.find(k)
    if p < 0:
        return None
    s = text[p + len(k):].lstrip()
    if not s:
        return None
    if s[0] == '{':
        return json.loads(_rsc_object(s, 0))
    if s[0] == '[':
        end = s.find(']')
        return json.loads(s[:end + 1])
    if s[0] == '"':
        end = s.find('"', 1)
        return json.loads(s[:end + 1])
    end = 0
    while end < len(s) and s[end] not in ',}]':
        end += 1
    return json.loads(s[:end])


def wheel_page_state(acc):
    """Скачать страницу колеса и разобрать RSC: signups, wheels, categoryMap.

    Возвращает dict {signups, wheels, categoryMap}.
    """
    sid = sp_session_id(acc)
    if not sid:
        raise RuntimeError('у аккаунта нет Session_id (нужен для sp.yandex.ru/wheel)')
    h = sp_headers(acc)
    h['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    try:
        r = requests.get(SP_WHEEL_PAGE, headers=h, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Колесо Фортуны: сеть: {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Колесо Фортуны: HTTP {r.status_code}: {r.text[:300]}')
    body = r.text
    unesc = None
    for m in re.finditer(r'self\.__next_f\.push\(\[1,"', body):
        p = m.end()
        end = body.find('"])', p)
        u = _js_unescape(body[p:end])
        if 'globalSelector' in u:
            unesc = u
            break
    if unesc is None:
        raise RuntimeError('Колесо Фортуны: не нашёл данные globalSelector на странице')
    return {
        'signups': _rsc_value(unesc, 'globalSelector').get('signups') or [],
        'wheels': _rsc_value(unesc, 'wheels') or {},
        'categoryMap': _rsc_value(unesc, 'categoryMap') or {},
    }


def wheel_signup(state):
    """Взять актуальный signup Колеса Фортуны (самый свежий период)."""
    sups = [s for s in (state.get('signups') or []) if s.get('offerType') == 'WheelOfFortune']
    if not sups:
        return None
    sups.sort(key=lambda s: s.get('endDate') or '', reverse=True)
    return sups[0]


def wheel_spin_category(su):
    """Категория для спина: статус New у группы fortuna.

    Если статусов нет/другие — берём первую категорию группы fortuna,
    которая ещё не Selected.
    """
    for g in (su or {}).get('groups') or []:
        cats = g.get('categories') or []
        if not cats:
            continue
        for c in cats:
            if c.get('status') == 'New':
                return c
        for c in cats:
            if c.get('status') != 'Selected':
                return c
    return None


def wheel_selected_category(su):
    """Уже выбранная (выигранная) категория: статус Selected."""
    for g in (su or {}).get('groups') or []:
        for c in g.get('categories') or []:
            if c.get('status') == 'Selected':
                return c
    return None


def _session_uid_web(acc):
    """Получить passport uid по Session_id через веб-паспорт (без mobileproxy).

    passport.yandex.ru/am/profile отдаёт HTML с uid владельца сессии
    (var uid = N / data-uid="N"). Не использует mobileproxy, поэтому
    работает и с датацентровых IP (Railway), где обмен может быть
    заблокирован.
    """
    sid = sp_session_id(acc)
    if not sid:
        return ''
    h = sp_headers(acc)
    h['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    h['Accept-Language'] = 'ru'
    try:
        r = requests.get('https://passport.yandex.ru/am/profile', headers=h, timeout=20)
    except requests.RequestException:
        return ''
    m = re.search(r'data-uid="(\d+)"', r.text) or re.search(r'var uid = (\d+)', r.text)
    return m.group(1) if m else ''


def _session_uid(acc):
    """Верный passport uid из Session_id (обмен на OAuth, иначе веб-паспорт)."""
    sid = sp_session_id(acc)
    if not sid:
        return ''
    try:
        _, uid = exchange_sessionid(sid)
        uid = (uid or '').strip()
        if uid:
            return uid
    except Exception:
        pass
    return _session_uid_web(acc)


def spin_wheel(acc, signup_id, category_id):
    """Крутануть колесо: POST /api/v1/offers/signup.

    passport_id — это uid владельца Session_id. Если сохранённый yandexuid
    пустой или не совпадает с сессией (HTTP 400 mismatch), берём uid из
    самой Session_id и повторяем.

    Возвращает тело ответа (например {"data":{"show_super_screen":false}}).
    """
    uid = (acc.get('yandexuid') or '').strip()
    if not uid:
        uid = _session_uid(acc)
        if uid:
            acc['yandexuid'] = uid
            try:
                accs = load_eda_accounts()
                for a in accs:
                    if a.get('name') == acc.get('name'):
                        a['yandexuid'] = uid
                        break
                save_eda_accounts(accs)
            except Exception:
                pass
    if not uid:
        raise RuntimeError('Колесо Фортуны: нет yandexuid (passport uid) для спина')
    h = sp_headers(acc)
    h['Content-Type'] = 'application/json'
    h['Accept'] = 'application/json, text/plain, */*'
    h['Accept-Language'] = 'ru_RU'
    body = {'id': signup_id, 'categories': [{'id': category_id}], 'passport_id': int(uid)}
    try:
        r = requests.post(SP_WHEEL_API + '/v1/offers/signup', headers=h, json=body, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Колесо Фортуны: сеть (спин): {e}')
    if r.status_code == 400 and 'match request user' in r.text:
        new_uid = _session_uid(acc)
        if new_uid and new_uid != uid:
            body['passport_id'] = int(new_uid)
            try:
                r = requests.post(SP_WHEEL_API + '/v1/offers/signup', headers=h, json=body, timeout=25)
            except requests.RequestException as e:
                raise RuntimeError(f'Колесо Фортуны: сеть (спин, повтор): {e}')
    if r.status_code >= 400:
        raise RuntimeError(f'Колесо Фортуны: HTTP {r.status_code} (спин): {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        raise RuntimeError(f'Колесо Фортуны: ответ спина не JSON: {r.text[:200]}')


def wheel_prize(state, su):
    """Приз из categoryMap по выбранной категории."""
    cat = wheel_selected_category(su)
    if not cat:
        return None
    key = cat.get('categoryKey') or ''
    entry = (state.get('categoryMap') or {}).get(key) or {}
    return {
        'category_key': key,
        'title': sp_clean(entry.get('widgetTitle')) or sp_clean(entry.get('successTitle')),
        'cashback': sp_clean(entry.get('cashbackText')),
        'description': sp_clean(entry.get('widgetDescription')) or sp_clean(entry.get('successDescription')),
        'icon': entry.get('icon'),
        'expires_at': su.get('endDate'),
    }


def collect_sp_wheel(account, spin=False, progress=None):
    """Проверить/крутануть Колесо Фортуны на аккаунте.

    spin=False — только состояние и текущий приз.
    spin=True — потратить попытку (если signup NEW) и вернуть выигрыш.

    Возвращает dict {results: [{account, spun, status, prize, error}], error}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not acc:
        raise RuntimeError(f'аккаунт "{account}" не найден')
    out = {'results': [], 'error': None}

    def _res(**kw):
        return {'account': acc.get('name'), 'spun': False, 'status': '',
                'endDate': None, 'prize': None, 'error': None, **kw}

    try:
        if progress:
            progress('Загружаю колесо', 0.1)
        state = wheel_page_state(acc)
        su = wheel_signup(state)
        if su is None:
            out['results'].append(_res(status='нет колеса',
                                       error='signup WheelOfFortune не найден'))
            return out
        if su.get('endDate') and su['endDate'][:10] < time.strftime('%Y-%m-%d'):
            out['results'].append(_res(status='период закончился', endDate=su.get('endDate')))
            return out
        new_cat = wheel_spin_category(su) if su.get('status') == 'NEW' else None
        if new_cat is None and su.get('status') == 'NEW':
            out['results'].append(_res(status='нет категории для спина', endDate=su.get('endDate'),
                                       error='категория для спина не найдена'))
            return out
        if new_cat and spin:
            if progress:
                progress('Кручу колесо', 0.6)
            try:
                resp = spin_wheel(acc, su['id'], new_cat['id'])
                if progress:
                    progress('Узнаю приз', 0.85)
                try:
                    state = wheel_page_state(acc)
                    su = wheel_signup(state) or su
                except Exception as e:
                    out['results'].append(_res(spun=True, status='спин сделан',
                                               endDate=su.get('endDate'),
                                               error=f'приз не определился: {e}'))
                    return out
            except Exception as e:
                out['results'].append(_res(spun=True, status='ошибка спина',
                                           endDate=su.get('endDate'), error=str(e)))
                return out
        prize = wheel_prize(state, su)
        result = _res(spun=bool(new_cat and spin), status=su.get('status'),
                      endDate=su.get('endDate'), prize=prize)
        if new_cat and not spin:
            result['status'] = 'можно крутить'
        elif prize is None and not new_cat:
            result['status'] = 'уже кручено'
        out['results'].append(result)
    except Exception as e:
        out['error'] = str(e)
    if progress:
        progress('Готово', 1.0)
    return out


# ---------- хранение результатов колеса ----------

def load_sp_wheel():
    try:
        with open(SP_WHEEL_FILE, encoding='utf-8') as f:
            return json.load(f).get('wheels', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_sp_wheel(items):
    with open(SP_WHEEL_FILE, 'w', encoding='utf-8') as f:
        json.dump({'wheels': items}, f, ensure_ascii=False, indent=2)


def record_sp_wheel(acc, result):
    """Записать результат прокрутки колеса в sp_wheel.json."""
    items = load_sp_wheel()
    prize = result.get('prize') or {}
    entry = {
        'account': acc.get('name', ''),
        'spun': bool(result.get('spun')),
        'status': result.get('status'),
        'endDate': result.get('endDate'),
        'prize_title': prize.get('title'),
        'cashback': prize.get('cashback'),
        'description': prize.get('description'),
        'error': result.get('error'),
        'spinned_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    items.append(entry)
    save_sp_wheel(items)
