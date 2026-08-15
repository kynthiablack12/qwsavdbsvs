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
GO_EATS_UA = ('Mozilla/5.0 (Linux; Android 15; SM-A235F Build/V417IR; wv) AppleWebKit/537.36 '
              '(KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Safari/537.36 '
              'yandex-taxi/5.89.1.128364 Android/15 (Samsung; SM-A235F) Superapp/Eats '
              'promoMode/restricted EatsKit/29.3.0 mode/fullscreen')
GO_DEVICE_ID = 'z14561cd16b144d695f05886b6ff21e2'  # webviewuserid из захвата Go

# Дефолтная точка: Омск, проспект Мира, 33 (координаты из дампа).
DEFAULT_LAT = 55.02878527315827
DEFAULT_LON = 73.27583823706175

# Пул реальных моделей для device-профилей (антифрод: разные устройства).
# Каждая пара модель/версия ОС реалистична (версия не ниже той, с которой
# модель вышла) — несоответствия типа S22 на Android 9 палят эмулятор.
DEVICE_MODELS = [
    {'model': 'SM-S906N', 'brand': 'samsung', 'manufacturer': 'samsung', 'os_version': '13'},
    {'model': 'SM-A235F', 'brand': 'samsung', 'manufacturer': 'samsung', 'os_version': '13'},
    {'model': 'SM-A515F', 'brand': 'samsung', 'manufacturer': 'samsung', 'os_version': '10'},
    {'model': 'SM-G991B', 'brand': 'samsung', 'manufacturer': 'samsung', 'os_version': '11'},
    {'model': 'SM-S911B', 'brand': 'samsung', 'manufacturer': 'samsung', 'os_version': '14'},
    {'model': '23127PN0CC', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '14'},
    {'model': '2210132G', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '12'},
    {'model': '2201117TG', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '12'},
    {'model': '2107119DC', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '11'},
    {'model': 'M2004J19C', 'brand': 'xiaomi', 'manufacturer': 'Xiaomi', 'os_version': '10'},
    {'model': 'Pixel 7', 'brand': 'google', 'manufacturer': 'Google', 'os_version': '13'},
    {'model': 'Pixel 6a', 'brand': 'google', 'manufacturer': 'Google', 'os_version': '12'},
    {'model': 'Pixel 4a', 'brand': 'google', 'manufacturer': 'Google', 'os_version': '10'},
    {'model': 'RMX3363', 'brand': 'realme', 'manufacturer': 'realme', 'os_version': '12'},
    {'model': 'RMX1921', 'brand': 'realme', 'manufacturer': 'realme', 'os_version': '9'},
    {'model': 'LRA-NX9', 'brand': 'honor', 'manufacturer': 'HONOR', 'os_version': '12'},
]


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
        'model': m['model'],
        'brand': m['brand'],
        'manufacturer': m['manufacturer'],
        'os_version': m['os_version'],
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
        'model': p.get('model') or APP['x-device-model'],
        'brand': p.get('brand') or APP['x-device-brand'],
        'manufacturer': p.get('manufacturer') or APP['x-device-manufacturer'],
        'os_version': p.get('os_version') or APP['x-os-version'],
    }

# App-параметры (дефолт — реальная модель Galaxy A23 на Android 13,
# а не эмуляторная S22+Android 9: такие несоответствия палят антифрод).
# x-app-version/user-agent: поднимаем до актуальной версии приложения — мобильный
# эндпоинт cart/promocode гейтит свежие промокоды (500go, FREE500) сообщением
# «Необходимо обновить приложение» по версии в user-agent (порог ~3.80, проверено:
# 3.19.0…3.70 — гейт, 3.80+ — реальный ответ). x-code-version на гейт не влияет.
APP = {
    'x-os-version': '13',
    'x-device-model': 'SM-A235F',
    'x-device-brand': 'samsung',
    'x-device-manufacturer': 'samsung',
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
    if not get_eda_account(account):
        raise RuntimeError(f'аккаунт "{account}" не найден')
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    now = time.time()
    sess = load_eda_sessions()
    sess[token] = {
        'name': name,
        'account': account,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now + hours * 3600)),
        'last_seen': None,
        'active': True,
        # каждая сессия — свежее «устройство» (свои device_id/модель),
        # поэтому таймер 22 мин считаем с момента создания сессии.
        'device': new_device_profile(),
        'device_at': now,
        'promo_ready_at': now + DEVICE_WAIT_SECONDS,
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
    h.update({
        'x-device-id': d['device_id'],
        'x-appmetrica-deviceid': d['appmetrica_deviceid'],
        'x-appmetrica-uuid': d['appmetrica_uuid'],
        'x-device-model': d['model'],
        'x-device-brand': d['brand'],
        'x-device-manufacturer': d['manufacturer'],
        'x-os-version': d['os_version'],
    })
    if d.get('mobile_ifa'):
        h['x-mobile-ifa'] = d['mobile_ifa']
    if d.get('tracker_id'):
        h['x-tracker-id'] = d['tracker_id']
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
    try:
        r = requests.request(method, url, headers=hdrs, json=json_body,
                             params=params, timeout=timeout)
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
        'X-Yandex-Plus-HostAppVersion': APP['x-app-version'],
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
    return {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru',
        'content-type': 'application/json;charset=UTF-8',
        'origin': 'https://eda.yandex.ru',
        'referer': 'https://eda.yandex.ru/checkout',
        'user-agent': WEB_UA,
        'x-app-version': '18.41.3',
        'x-client-session': uuid.uuid4().hex[:32],
        'x-device-id': _dev(acc)['device_id'],
        'x-platform': 'desktop_web',
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
    try:
        r = requests.request(method, url, headers=hdrs, cookies=ck,
                             json=json_body, params=params, timeout=timeout)
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
    """Оформление (веб): go-checkout с выбором СБП.

    Возвращает offers — каждый с offer_identity, requestId
    (= cart_id.offer_identity) и possiblePayment{id,type,costForCustomer}.
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
            'selected_payment_type': {'id': payment_id, 'type': payment_type},
        },
    }
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

    Сначала ищем оффер под запрошенный способ (web_offer). Для СБП, если
    отдельного оффера в go-checkout нет (бывает: СБП есть только в
    paymentTypeConfig, сайт платит единым способом EATS_PAYMENTS), берём
    первый доступный оффер корзины и подставляем способ sbp/sbp_qr.
    costForCustomer у оффера зависит только от варианта доставки, а не от
    способа оплаты (см. probe_checkout_resp.json: у всех payment одной
    группы сумма одинаковая), поэтому его можно переносить как есть.
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
    want_sbp = (payment_id in ('sbp_qr', 'sbp', 'sbp_token')
                or payment_type in ('sbp', 'sbp_token'))
    meta['sbp_in_config'] = any(
        c.get('id') == 'sbp_qr' or c.get('type') in ('sbp', 'sbp_token')
        for c in (d.get('paymentTypeConfig') or []))
    if want_sbp:
        for o in (d.get('offers') or []):
            avail = (o.get('availability') or {}).get('available')
            if avail is False:
                continue
            if not (o.get('requestId') and o.get('offer_identity')):
                continue
            o_pp = o.get('possiblePayment') or {}
            if o_pp.get('type') == 'add_new_card':
                continue
            sbp_pp = {'id': 'sbp_qr', 'type': 'sbp', 'title': 'СБП',
                      'serviceFee': o_pp.get('serviceFee')}
            cfc = o_pp.get('costForCustomer')
            if cfc is not None:
                sbp_pp['costForCustomer'] = cfc
            meta['fallback'] = True
            meta['fallback_offer'] = (o_pp.get('id'), o_pp.get('type'))
            return o, sbp_pp, meta
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
                     plus_subscription_toggle_state=False, user_address_id=None):
    """Создать заказ с оплатой СБП (POST /api/v1/orders, веб-флоу).

    payment_info — possiblePayment из go-checkout (id='sbp_qr',
    type='sbp', costForCustomer.value, currency). request_id по умолчанию
    = cart_id + '.' + offer_identity (как offer.requestId на фронте).
    Ответ: {orderNr, firstOrder, ...} — orderNr используется для tracking.
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
        'extended_options': (extended_options if extended_options is not None else
                             [{'type': 'delivery_options', 'leave_at_the_door': False}]),
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
        payment_id = payment_id.get('id') or 'sbp_qr'
        payment_type = payment_type or payment_id.get('type') or 'sbp'
    if isinstance(payment_type, dict):
        payment_type = payment_type.get('type') or 'sbp'
    body = {
        'address': address,
        'place_slug': slug,
        'payment': {
            'recently_link_cards': False,
            'selected_payment_type': {'id': payment_id, 'type': payment_type},
        },
    }
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


def mob_create_order(account, slug, address, offer_identity, payment_info, phone='',
                     lat=None, lon=None,
                     request_id=None, cart_id=None, extended_options=None,
                     recently_link_cards=False,
                     plus_subscription_toggle_state=False):
    """Создать заказ мобильным каналом: POST /api/v1/orders (без code!).

    code не передаём: промокод уже применён к корзине через cart/promocode,
    передача code заново вызывает перепроверку акции и ошибку 58.
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
        'extended_options': (extended_options if extended_options is not None else
                             [{'type': 'delivery_options', 'leave_at_the_door': False}]),
        'payment': {'recently_link_cards': recently_link_cards},
        'place_slug': slug,
        'address': address,
        'plus_subscription_toggle_state': plus_subscription_toggle_state,
        'request_id': request_id or '',
    }
    return _eda_call(acc, 'POST', '/api/v1/orders', lat, lon, json_body=body)


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
        'user-agent': GO_EATS_UA,
        'x-platform': 'superapp_taxi_web',
        'x-superapp-version': '1',
        'x-app-version': '18.38.2',
        'x-appmetrica-deviceid': d['appmetrica_deviceid'],
        'x-appmetrica-uuid': d['appmetrica_uuid'],
        'x-client-session': uuid.uuid4().hex[:23],
        'x-device-id': d['device_id'],
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
    try:
        r = requests.request(method, url, headers=_go_hdrs(acc), cookies=ck,
                             json=json_body, params=params, timeout=timeout)
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
                    plus_subscription_toggle_state=False):
    """Создать заказ супераппом: POST /api/v1/orders.

    Тело — копия из flows_eda_mumu.mitm (260815-5424038 / 260815-6472614):
    address base_info/details, extended_options с tips_chosen_offer,
    payment_information {type, costForCustomer, id, currency},
    request_id = cart_id.offer_identity.
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
        'extended_options': extended_options,
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
                    'user-agent': GO_EATS_UA,
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
        'user-agent': GO_EATS_UA,
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
