import sys, os, json, uuid, time, re, urllib.parse, html
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

# Дефолтная точка: Омск, проспект Мира, 33 (координаты из дампа).
DEFAULT_LAT = 55.02878527315827
DEFAULT_LON = 73.27583823706175

# App-параметры из перехвата (эмулятор LDPlayer).
APP = {
    'x-os-version': '9',
    'x-device-model': 'SM-S906N',
    'x-device-brand': 'samsung',
    'x-device-manufacturer': 'samsung',
    'x-android-platform-services-type': 'huawei',
    'x-platform': 'android_app',
    'x-app-version': '3.19.0',
    'x-code-version': '249708',
    'x-device-id': 'dab454cb-f8f4-34cc-950c-91759cc19869',
    'x-appmetrica-deviceid': '1c1e4355a8142f9d52e1f218c928d7de',
    'x-appmetrica-uuid': 'c4a9b2f931aa4e78957a0669566685c9',
    'user-agent': 'android (3.19.0)',
    'accept-language': 'ru',
    'content-type': 'application/json',
}


# ---------- account storage (bearer-based) ----------

def load_eda_accounts():
    try:
        with open(EDA_ACCOUNTS_FILE, encoding='utf-8') as f:
            return json.load(f).get('accounts', [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_eda_accounts(accs):
    with open(EDA_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'accounts': accs}, f, ensure_ascii=False, indent=2)


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


def add_eda_account(name, cookies_raw, token=None, yandexuid='', session_id=''):
    """Добавить аккаунт Я.Еды.

    Авторизация Я.Еды — Bearer-токен (OAuth). Его можно передать:
      - напрямую параметром `token`, либо
      - внутри cookie-строки как webviewtoken=..., либо
      - как сам token в поле cookies (если строка не 'k=v'), либо
      - как passport `session_id` (Session_id cookie) — тогда он будет
        обменян на OAuth-токен через mobileproxy passport.
    yandexuid (passport uid) — желателен для x-yandex-uid.
    """
    name = (name or '').strip()
    acc = {'name': name}
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


def get_eda_account(name):
    return next((a for a in load_eda_accounts() if a.get('name') == name), None)


# ---------- delivery access sessions ----------

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
    sess = load_eda_sessions()
    sess[token] = {
        'name': name,
        'account': account,
        'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'expires_at': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() + hours * 3600)),
        'last_seen': None,
        'active': True,
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
    h = dict(APP)
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
        'X-Yandex-DeviceID': APP['x-device-id'],
        'X-Yandex-Plus-Platform': 'Android',
        'X-Yandex-PUID': uid,
        'X-Yandex-Plus-SdkVersion': '52.0.0',
        'X-Yandex-Plus-Service': 'eda',
        'X-Yandex-Plus-Source': 'PlusSdk',
        'X-Yandex-UUID': APP['x-appmetrica-uuid'],
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


def search_restaurants(account, query='', lat=None, lon=None):
    """Поиск ресторанов/каталог (full-text-search)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST', '/eats/v1/full-text-search/v1/search',
                     lat, lon,
                     json_body={'location': {'latitude': lat, 'longitude': lon},
                                'text': query or '',
                                'shipping_type': 'delivery',
                                'selector': ''})


def restaurant_menu(account, slug, lat=None, lon=None, shipping='delivery'):
    """Меню ресторана по slug (категории, товары)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'GET', f'/api/v2/menu/retrieve/{slug}',
                     lat, lon,
                     params={'latitude': lat, 'longitude': lon, 'shippingType': shipping})


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
    """Текущая корзина. slug — ресторан, к которому привязана корзина."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    params = {'latitude': lat, 'longitude': lon,
              'screen': screen, 'shippingType': shipping}
    if slug:
        params['placeSlug'] = slug
    return _eda_call(acc, 'POST', '/eats/v1/cart/v2/full-carts',
                     lat, lon, params=params, json_body={})


def all_carts(account, lat=None, lon=None, shipping='delivery', screen='catalog'):
    """Все корзины (для каталога/списка)."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _eda_call(acc, 'POST', '/eats/v1/cart/v2/multi-carts',
                     lat, lon,
                     params={'latitude': lat, 'longitude': lon,
                             'screen': screen, 'shippingType': shipping},
                     json_body={'need_items_icons': False})


def add_to_cart(account, slug, item_id, qty=1, item_options=None, lat=None, lon=None, shipping='delivery', business='restaurant'):
    """Добавить товар в корзину. business — 'restaurant' или 'shop'."""
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


def order_status(account, order_id):
    """Статус заказа / трекинг."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', f'/api/v1/orders/{order_id}', None, None)


def active_orders(account):
    """Активные заказы / трекинг."""
    acc = get_eda_account(account) if isinstance(account, str) else account
    return _eda_call(acc, 'GET', '/api/v2/orders/tracking', None, None)


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


def _promo_items(acc, lat, lon, progress=None):
    """Промокоды аккаунта: баннеры главного экрана, личный список,
    маленькие баннеры внутри ресторанов (menu informers).

    progress — callback(msg, frac) для отчёта о ходе (frac 0..1).
    """
    res = {'codes': [], 'error': None}
    layout_data = None
    try:
        if progress:
            progress('Загружаю главный экран', 0.0)
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
    # маленький баннер внутри первого ресторана с главного экрана
    slugs = _places_from_layout(layout_data)
    n = min(len(slugs), 1)
    for i, slug in enumerate(slugs[:n]):
        try:
            if progress:
                progress(f'Ресторан {i + 1}/{n}: {slug}', 0.15 + 0.85 * i / n)
            m = restaurant_menu(acc, slug, lat=lat, lon=lon)
            vals = []
            _find_promo_values(m, vals)
            res['codes'] += vals
        except Exception:
            continue
    # уникальный набор промокодов на аккаунте
    res['codes'] = sorted({c.upper() for c in res['codes'] if c})
    if progress:
        progress('Готово', 1.0)
    return res


def find_promocodes(account, lat=None, lon=None, progress=None):
    """Найти промокоды на аккаунте Я.Еды.

    Возвращает dict: {codes: [уникальные промокоды аккаунта],
    error: str|None}. progress — callback(msg, frac).
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    lat, lon = _coords(acc, lat, lon)
    return _promo_items(acc, lat, lon, progress)


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
    """Взять signup Колеса Фортуны из состояния страницы."""
    for su in state.get('signups') or []:
        if su.get('offerType') == 'WheelOfFortune':
            return su
    return None


def wheel_spin_category(su):
    """Категория для спина: статус New у группы fortuna."""
    for g in (su or {}).get('groups') or []:
        for c in g.get('categories') or []:
            if c.get('status') == 'New':
                return c
    return None


def wheel_selected_category(su):
    """Уже выбранная (выигранная) категория: статус Selected."""
    for g in (su or {}).get('groups') or []:
        for c in g.get('categories') or []:
            if c.get('status') == 'Selected':
                return c
    return None


def spin_wheel(acc, signup_id, category_id):
    """Крутануть колесо: POST /api/v1/offers/signup.

    Возвращает тело ответа (например {"data":{"show_super_screen":false}}).
    """
    uid = int(acc.get('yandexuid') or 0)
    h = sp_headers(acc)
    h['Content-Type'] = 'application/json'
    h['Accept'] = 'application/json, text/plain, */*'
    h['Accept-Language'] = 'ru_RU'
    body = {'id': signup_id, 'categories': [{'id': category_id}], 'passport_id': uid}
    try:
        r = requests.post(SP_WHEEL_API + '/v1/offers/signup', headers=h, json=body, timeout=25)
    except requests.RequestException as e:
        raise RuntimeError(f'Колесо Фортуны: сеть (спин): {e}')
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
    spin=True — потратить попытку (если категория New) и вернуть выигрыш.

    Возвращает dict {results: [{account, spun, status, prize, error}], error}.
    """
    acc = get_eda_account(account) if isinstance(account, str) else account
    if not acc:
        raise RuntimeError(f'аккаунт "{account}" не найден')
    out = {'results': [], 'error': None}
    try:
        if progress:
            progress('Загружаю колесо', 0.1)
        state = wheel_page_state(acc)
        su = wheel_signup(state)
        if su is None:
            out['results'].append({'account': acc.get('name'), 'spun': False,
                                   'status': 'нет колеса', 'error': 'signup WheelOfFortune не найден'})
            return out
        if su.get('endDate') and su['endDate'][:10] < time.strftime('%Y-%m-%d'):
            out['results'].append({'account': acc.get('name'), 'spun': False,
                                   'status': 'период закончился', 'endDate': su.get('endDate')})
            return out
        new_cat = wheel_spin_category(su)
        if new_cat and spin:
            if progress:
                progress('Кручу колесо', 0.6)
            try:
                resp = spin_wheel(acc, su['id'], new_cat['id'])
                if progress:
                    progress('Узнаю приз', 0.85)
                state = wheel_page_state(acc)
                su = wheel_signup(state)
            except Exception as e:
                out['results'].append({'account': acc.get('name'), 'spun': True,
                                       'status': 'ошибка спина', 'error': str(e)})
                return out
        prize = wheel_prize(state, su)
        result = {
            'account': acc.get('name'),
            'spun': bool(new_cat and spin),
            'status': su.get('status'),
            'endDate': su.get('endDate'),
            'prize': prize,
            'error': None,
        }
        if prize is None and not new_cat:
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
