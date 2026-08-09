import sys, os, json, uuid, time, re, html, base64
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
import requests

# ============================================================
#  Самокат: доставка.
#
#  Авторизация — через веб-сессию samokat.ru (куки NextAuth):
#    GET  https://samokat.ru/api/auth/session  -> токены
#    POST https://samokat.ru/api/auth/refresh  -> продлить accessToken
#
#  Каталог/корзина/оформление — веб-API api-web.samokat.ru
#  (эндпоинты сняты с браузера через DevTools).
# ============================================================

SAMOKAT_ACCOUNTS_FILE = os.path.join(core.DATA_DIR, 'samokat_accounts.json')
SAMOKAT_SESSIONS_FILE = os.path.join(core.DATA_DIR, 'samokat_sessions.json')

SAMOKAT_WEB = 'https://samokat.ru'
AUTH_SESSION_URL = SAMOKAT_WEB + '/api/auth/session'
AUTH_REFRESH_URL = SAMOKAT_WEB + '/api/auth/refresh'

# Веб-API Самоката (эндпоинты сняты с браузера через DevTools).
API_HOST = 'https://api-web.samokat.ru'

# Дефолтная точка: Омск, пр-кт К. Маркса 36/2 (адрес из профиля аккаунта).
DEFAULT_LAT = 54.9804045
DEFAULT_LON = 73.3727487

# Обязательные куки веб-сессии самоката (NextAuth + аналитика).
REQUIRED_COOKIES = [
    'spjs', 'spid', 'spsc', 'DEVICE_ID_KEY',
    '__Host-next-auth.csrf-token',
    '__Secure-next-auth.callback-url',
    '__Secure-next-auth.session-token',
    '_sv',
    '_sas.539b23c941af8edbc30d9fc12c0eb1103cb65530fc07505659f86348677c076d',
    'sberid_auto_login_progress', 'viewport_width',
    'sberid_auto_error_pause', 'adtech_uid',
    'top100_id', 't3_sid_7726639',
]

# Дефолтные заголовки веб-запроса (рабочие, взяты из проверенного curl).
WEB_HEADERS = {
    'Accept': '*/*',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Connection': 'keep-alive',
}

# Заголовки веб-API api-web.samokat.ru (из дампа браузера).
# deviceid = кука spid; x-creeper уникален на каждый запрос — берём из аккаунта.
APP = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
    'x-application-platform': 'web',
    'sec-ch-ua': '"Not/A)Brand";v="8", "Chromium";v="151", "Google Chrome";v="151"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'cross-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
}


# ---------- разбор кук ----------

def _parse_cookies(raw):
    """Разобрать строку 'k=v; k2=v2' или JSON-объект кук в dict."""
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


def _cookie_header(cookies):
    """Собрать заголовок Cookie из dict."""
    return '; '.join(f'{k}={v}' for k, v in cookies.items() if v)


def _pick_cookies(cookies):
    """Оставить только нужные куки для API."""
    return {k: v for k, v in cookies.items() if k in REQUIRED_COOKIES and v}


# ---------- работа с токенами (веб-сессия) ----------

def get_tokens(cookies):
    """Получить свежие токены с веба: GET /api/auth/session.

    Возвращает dict: accessToken, refreshToken, sessionToken,
    accessTokenExpires (ms), expires (ISO), user.
    Кидает RuntimeError при ошибке/401.
    """
    hdrs = dict(WEB_HEADERS)
    hdrs['Cookie'] = _cookie_header(cookies)
    try:
        r = requests.get(AUTH_SESSION_URL, headers=hdrs, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Самокат: сеть (auth/session): {e}')
    if r.status_code == 401:
        raise RuntimeError('Самокат: куки истекли или невалидны (401), перезайдите на samokat.ru')
    if r.status_code >= 400:
        raise RuntimeError(f'Самокат: auth/session HTTP {r.status_code}: {r.text[:300]}')
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f'Самокат: ответ auth/session не JSON: {r.text[:200]}')
    if not data.get('accessToken'):
        raise RuntimeError('Самокат: в ответе auth/session нет accessToken (сессия не вошла)')
    return data


def refresh_tokens(refresh_token, cookies):
    """Продлить токены: POST /api/auth/refresh.

    Возвращает тот же dict токенов. Кидает RuntimeError при ошибке.
    """
    hdrs = dict(WEB_HEADERS)
    hdrs['Cookie'] = _cookie_header(cookies)
    hdrs['Content-Type'] = 'application/json'
    try:
        r = requests.post(AUTH_REFRESH_URL, headers=hdrs,
                          json={'refreshToken': refresh_token}, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f'Самокат: сеть (auth/refresh): {e}')
    if r.status_code == 401:
        raise RuntimeError('Самокат: refresh-токен истёк или невалиден (401)')
    if r.status_code >= 400:
        raise RuntimeError(f'Самокат: auth/refresh HTTP {r.status_code}: {r.text[:300]}')
    try:
        data = r.json()
    except Exception:
        raise RuntimeError(f'Самокат: ответ auth/refresh не JSON: {r.text[:200]}')
    if not data.get('accessToken'):
        raise RuntimeError('Самокат: в ответе auth/refresh нет accessToken')
    return data


def is_token_expired(access_token_expires):
    """True, если accessToken уже протух (с запасом 60 сек)."""
    try:
        return int(access_token_expires) / 1000 - time.time() < 60
    except Exception:
        return True


# ---------- аккаунты ----------

def load_samokat_accounts():
    try:
        with open(SAMOKAT_ACCOUNTS_FILE, encoding='utf-8') as f:
            return json.load(f).get('accounts', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_samokat_accounts(accs):
    with open(SAMOKAT_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'accounts': accs}, f, ensure_ascii=False, indent=2)


def get_samokat_account(name):
    return next((a for a in load_samokat_accounts() if a.get('name') == name), None)


def _jwt_payload(token):
    """Раскодировать payload JWT без проверки подписи."""
    try:
        _, payload, _ = token.split('.')
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def add_samokat_account(name, cookies_raw):
    """Добавить аккаунт Самоката по кукам веб-сессии.

    Сразу проверяет куки запросом auth/session и сохраняет токены.
    """
    name = (name or '').strip()
    cookies = _parse_cookies(cookies_raw)
    if not any(k in cookies for k in ('__Secure-next-auth.session-token',)):
        raise RuntimeError('не найдена кука __Secure-next-auth.session-token — возьмите все куки из браузера (samokat.ru)')
    data = get_tokens(cookies)          # проверим, что куки рабочие
    jwt = _jwt_payload(data.get('accessToken', ''))
    acc = {
        'name': name,
        'cookies': _pick_cookies(cookies),
        'refresh_token': data.get('refreshToken', ''),
        'access_token': data.get('accessToken', ''),
        'session_token': data.get('sessionToken', ''),
        'access_token_expires': data.get('accessTokenExpires', 0),
        'expires': data.get('expires', ''),
        'user': data.get('user', {}),
        'user_id': str(jwt.get('sub') or (data.get('user') or {}).get('userId') or ''),
        'device_id': str(jwt.get('device_id') or ''),
        'added': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    accs = load_samokat_accounts()
    if any(a.get('name') == name for a in accs):
        raise RuntimeError(f'аккаунт "{name}" уже существует')
    accs.append(acc)
    save_samokat_accounts(accs)
    return accs


def delete_samokat_account(name):
    accs = load_samokat_accounts()
    accs = [a for a in accs if a.get('name') != name]
    save_samokat_accounts(accs)


def refresh_samokat_account(name):
    """Продлить accessToken аккаунта и сохранить свежие токены."""
    accs = load_samokat_accounts()
    for a in accs:
        if a.get('name') == name:
            data = refresh_tokens(a.get('refresh_token'), a.get('cookies') or {})
            a['access_token'] = data.get('accessToken', a.get('access_token'))
            a['refresh_token'] = data.get('refreshToken', a.get('refresh_token', ''))
            a['session_token'] = data.get('sessionToken', a.get('session_token', ''))
            a['access_token_expires'] = data.get('accessTokenExpires', a.get('access_token_expires', 0))
            a['expires'] = data.get('expires', a.get('expires', ''))
            if data.get('user'):
                a['user'] = data['user']
            jwt = _jwt_payload(a.get('access_token', ''))
            if jwt.get('sub'):
                a['user_id'] = str(jwt.get('sub'))
            if jwt.get('device_id'):
                a['device_id'] = str(jwt.get('device_id'))
            save_samokat_accounts(accs)
            return a
    raise RuntimeError(f'аккаунт "{name}" не найден')


def ensure_access_token(acc):
    """Вернуть живой accessToken аккаунта, при необходимости продлевая."""
    if is_token_expired(acc.get('access_token_expires')):
        acc = refresh_samokat_account(acc.get('name'))
    return acc.get('access_token')


# ---------- сессии доступа ----------

def load_samokat_sessions():
    try:
        with open(SAMOKAT_SESSIONS_FILE, encoding='utf-8') as f:
            return json.load(f).get('sessions', {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_samokat_sessions(sess):
    with open(SAMOKAT_SESSIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'sessions': sess}, f, ensure_ascii=False, indent=2)


def create_samokat_session(name, account, hours=24):
    """Сессия доступа для стороннего человека: ссылка /s/<token>.

    Даёт доступ к каталогу/корзине/оформлению на аккаунте Самоката.
    """
    name = (name or '').strip()
    account = (account or '').strip()
    if not name or not account:
        raise RuntimeError('имя и аккаунт обязательны')
    if not get_samokat_account(account):
        raise RuntimeError(f'аккаунт "{account}" не найден')
    token = uuid.uuid4().hex + uuid.uuid4().hex[:8]
    sess = load_samokat_sessions()
    sess[token] = {
        'name': name,
        'account': account,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + int(hours) * 3600)),
        'last_seen': None,
        'active': True,
    }
    save_samokat_sessions(sess)
    return token


def get_samokat_session(token):
    if not token:
        return None
    s = load_samokat_sessions().get(token)
    if not s or not s.get('active'):
        return None
    if s.get('expires_at') and s['expires_at'] < time.strftime('%Y-%m-%d %H:%M:%S'):
        return None
    return s


def touch_samokat_session(token):
    sess = load_samokat_sessions()
    if token in sess:
        sess[token]['last_seen'] = time.strftime('%Y-%m-%d %H:%M:%S')
        save_samokat_sessions(sess)


def revoke_samokat_session(token):
    sess = load_samokat_sessions()
    if token in sess:
        sess[token]['active'] = False
        save_samokat_sessions(sess)
        return True
    return False


# ---------- API-клиент (api-web.samokat.ru) ----------

def _api_headers(acc):
    """Заголовки запроса к api-web.samokat.ru (по образцу дампа браузера).

    deviceid = кука spid; Origin/Referer — samokat.ru; все куки шлём целиком.
    """
    h = dict(APP)
    h['authorization'] = 'Bearer ' + ensure_access_token(acc)
    ck = acc.get('cookies') or {}
    h['deviceid'] = ck.get('spid') or acc.get('device_id') or ''
    h['origin'] = SAMOKAT_WEB
    h['referer'] = SAMOKAT_WEB + '/'
    if ck:
        h['Cookie'] = _cookie_header(ck)
    creeper = acc.get('x_creeper')
    if creeper:
        h['x-creeper'] = creeper
    return h


def api_get(acc, path, **params):
    """GET к api-web.samokat.ru, возвращает JSON. Кидает RuntimeError."""
    h = _api_headers(acc)
    try:
        r = core.s.get(API_HOST + path, headers=h, params=params or None, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Самокат: сеть {path}: {e}')
    if r.status_code == 401:
        raise RuntimeError('Самокат: 401 — сессия истекла, обновите токен в админке')
    if r.status_code >= 400:
        raise RuntimeError(f'Самокат: {path} HTTP {r.status_code}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {}


def api_post(acc, path, body=None):
    """POST к api-web.samokat.ru, возвращает JSON. Кидает RuntimeError."""
    h = _api_headers(acc)
    h['content-type'] = 'application/json'
    try:
        r = core.s.post(API_HOST + path, headers=h,
                        data=json.dumps(body or {}), timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Самокат: сеть {path}: {e}')
    if r.status_code == 401:
        raise RuntimeError('Самокат: 401 — сессия истекла, обновите токен в админке')
    if r.status_code >= 400:
        raise RuntimeError(f'Самокат: {path} HTTP {r.status_code}: {r.text[:300]}')
    try:
        return r.json()
    except Exception:
        return {}


# ---------- профиль / витрина ----------

def profile(acc):
    """Профиль пользователя: телефон, имя, выбранный адрес."""
    return api_get(acc, '/users/profile')


def addresses(acc):
    """Список сохранённых адресов пользователя. TODO: снять с веба."""
    raise NotImplementedError('адреса Самоката: ожидается эндпоинт с веба')


def catalog_config(acc):
    """Конфиг каталога: /config/new_samokat_catalog (список витрин)."""
    return api_get(acc, '/config/new_samokat_catalog')


def _find_showcase_id(data, depth=0):
    """Рекурсивно найти id витрины (UUID) в ответе каталога."""
    if depth > 8 or not isinstance(data, (dict, list)):
        return None
    items = data.items() if isinstance(data, dict) else enumerate(data)
    for k, v in items:
        if k in ('id', 'showcase_id', 'showcaseId') and isinstance(v, str) \
                and re.fullmatch(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}', v):
            return v
        r = _find_showcase_id(v, depth + 1)
        if r:
            return r
    return None


def showcase_list(acc):
    """Список витрин: берём из /config/new_samokat_catalog.

    Возвращает [{id, name}] — один активный showcase (как на вебе).
    """
    cfg = catalog_config(acc)
    sid = _find_showcase_id(cfg)
    if not sid:
        raise RuntimeError('Самокат: не удалось найти витрину в /config/new_samokat_catalog')
    return [{'id': sid, 'name': 'Самокат'}]


def categories(acc, showcase_id):
    """Категории товаров витрины: /v2/showcases/{id}/categories/list.

    Возвращает список категорий [{id, name, ...}] — рекурсивно из дерева.
    """
    data = api_get(acc, f'/v2/showcases/{showcase_id}/categories/list')
    tree = data.get('categories', data.get('tree', data))
    out = []

    def walk(node):
        if isinstance(node, dict):
            if 'id' in node and 'name' in node:
                out.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(tree)
    return out


def main_page(acc, showcase_id):
    """Главная витрины: /v2/showcases/{id}/main (блоки/товары)."""
    return api_get(acc, f'/v2/showcases/{showcase_id}/main')


def product(acc, showcase_id, slug):
    """Карточка товара: /v2/showcases/{id}/products/{slug}."""
    return api_get(acc, f'/v2/showcases/{showcase_id}/products/{slug}')


def goods(acc, showcase_id, category_id=None, term=None):
    """Товары витрины: главная /main + при необходимости категория/поиск.

    TODO: точный эндпоинт товаров категории/поиска снимем с веба;
    пока отдаём товары, найденные на главной странице витрины.
    """
    data = main_page(acc, showcase_id)
    items = _collect_goods(data)
    if category_id:
        items = [g for g in items
                 if category_id in ((g.get('category_id') or ''), *([str(c) for c in g.get('category_ids') or []]))]
    if term:
        t = term.lower()
        items = [g for g in items if t in (g.get('name') or '').lower()
                 or t in (g.get('slug') or '').lower()
                 or t in (g.get('keywords') or '')]
    return items


def _collect_goods(data, out=None, depth=0):
    """Собрать товары (dict с 'id' и 'name') из ответа главной витрины."""
    if out is None:
        out = []
    if depth > 10 or not isinstance(data, (dict, list)):
        return out
    items = data.items() if isinstance(data, dict) else enumerate(data)
    for k, v in items:
        if isinstance(v, dict):
            if isinstance(v.get('id'), (str, int)) and isinstance(v.get('name'), str) \
                    and v not in out:
                out.append(v)
            _collect_goods(v, out, depth + 1)
        elif isinstance(v, list):
            _collect_goods(v, out, depth + 1)
    return out


def cart(acc):
    """Текущая корзина. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('корзина Самоката: ожидается эндпоинт с веба')


def add_to_cart(acc, item, qty=1):
    """Добавить товар в корзину. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('корзина Самоката: ожидается эндпоинт с веба')


def set_cart_item(acc, item, qty):
    """Изменить количество товара в корзине. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('корзина Самоката: ожидается эндпоинт с веба')


def checkout_info(acc):
    """Информация для оформления: слоты, оплата. TODO: снимем с веба."""
    raise NotImplementedError('оформление Самоката: ожидается эндпоинт с веба')


def place_order(acc, address_id, slots=None):
    """Оформить заказ. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('оформление Самоката: ожидается эндпоинт с веба')


def orders(acc):
    """Список заказов. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('заказы Самоката: ожидается эндпоинт с веба')


def order_status(acc, order_id):
    """Статус заказа. TODO: эндпоинт снимем с веба."""
    raise NotImplementedError('заказы Самоката: ожидается эндпоинт с веба')
