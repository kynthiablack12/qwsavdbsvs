import sys, os, json, uuid, time
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
    if not name:
        raise RuntimeError('имя аккаунта обязательно')
    acc = {'name': name}
    ck = _parse_keyvals(cookies_raw)
    # если передан token отдельно — берём его
    if token:
        acc['token'] = token.strip()
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
    # подтянем баллы Я.Плюс
    try:
        pb = plus_balance(acc)
        acc['plus_balance'] = pb.get('balance')
        acc['plus_status'] = pb.get('status')
    except Exception:
        pass
    accs = load_eda_accounts()
    if any(a.get('name') == name for a in accs):
        raise RuntimeError(f'аккаунт "{name}" уже существует')
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
