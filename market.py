import sys, os, json, uuid, time, re, random, threading, urllib.parse, html, contextlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
import requests

# ============================================================
#  Яндекс Маркет: поиск акций и товаров за 1 рубль.
#
#  Реальные эндпоинты получены из mitm-перехвата flows_market.mitm
#  (приложение ru.beru.android).
#
#  Авторизация: cookie Session_id (из passport).
# ============================================================

MARKET_ACCOUNTS_FILE = os.path.join(core.DATA_DIR, 'market_accounts.json')

MARKET_HOST = 'https://market.yandex.ru'

# URL для акций «Товар за 1 рубль» (Wow Offers)
WOW_OFFERS_PATH = '/page/wow_offers'

# App-параметры для Market (мобильное приложение)
MARKET_APP = {
    'user-agent': 'Mozilla/5.0 (Linux; Android 13; M391Q Build/PPR1.190610.011) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/110.0.5481.154 Mobile Safari/537.36',
    'accept-language': 'ru-RU,ru;q=0.9',
    'accept': 'application/json',
    'content-type': 'application/json',
}


# ---------- account storage ----------

@contextlib.contextmanager
def _store_lock():
    """Межпроцессная блокировка файла хранилища."""
    lock_path = MARKET_ACCOUNTS_FILE + '.lock'
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
        try:
            if os.name == 'nt':
                f.seek(0)
                import msvcrt
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UNLCK)
        except:
            pass
        f.close()


def _market_read():
    """Прочитать хранилище аккаунтов."""
    if os.path.exists(MARKET_ACCOUNTS_FILE):
        with open(MARKET_ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'accounts': []}


def _market_write(store):
    """Записать хранилище аккаунтов."""
    with open(MARKET_ACCOUNTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(store, f, ensure_ascii=False, indent=2)


def load_market_accounts():
    """Загрузить все аккаунты."""
    with _store_lock():
        store = _market_read()
        return list(store.get('accounts', []))


def get_market_account(name):
    """Получить аккаунт по имени."""
    accs = load_market_accounts()
    return next((a for a in accs if a.get('name') == name), None)


def add_market_account(name, session_id=None, bearer=None, phone=None, email=None,
                       lat=None, lon=None, proxy=None):
    """Добавить аккаунт Яндекс Маркета."""
    with _store_lock():
        store = _market_read()
        accs = store.get('accounts', [])

        # Проверяем дубликаты
        if any(a.get('name') == name for a in accs):
            raise RuntimeError(f'аккаунт "{name}" уже существует')

        acc = {
            'name': name,
            'created_at': time.time(),
            'session_id': session_id or '',
            'bearer': bearer or '',
            'phone': phone or '',
            'email': email or '',
            'lat': lat,
            'lon': lon,
            'proxy': proxy or '',
        }

        accs.append(acc)
        store['accounts'] = accs
        _market_write(store)
        return acc


def update_market_account(name, **kwargs):
    """Обновить данные аккаунта."""
    with _store_lock():
        store = _market_read()
        accs = store.get('accounts', [])
        target = next((a for a in accs if a.get('name') == name), None)
        if not target:
            raise RuntimeError(f'аккаунт "{name}" не найден')
        for k, v in kwargs.items():
            if v is not None:
                target[k] = v
        target['updated_at'] = time.time()
        store['accounts'] = accs
        _market_write(store)
        return target


def remove_market_account(name):
    """Удалить аккаунт."""
    with _store_lock():
        store = _market_read()
        accs = store.get('accounts', [])
        store['accounts'] = [a for a in accs if a.get('name') != name]
        _market_write(store)


# ---------- API calls ----------

def _market_call(acc, method, path, json_body=None, params=None, timeout=25):
    """HTTP-запрос к Яндекс Маркету."""
    url = MARKET_HOST + path
    hdrs = {
        'User-Agent': MARKET_APP['user-agent'],
        'Accept': MARKET_APP['accept'],
        'Accept-Language': MARKET_APP['accept-language'],
    }

    # Авторизация через cookie Session_id
    # Session_id может быть в формате "3:..." или "Session_id=3:..."
    session_id = acc.get('session_id', '')
    if session_id:
        # Убираем префикс если есть
        if session_id.startswith('Session_id='):
            session_id = session_id[len('Session_id='):]
        hdrs['Cookie'] = f'Session_id={session_id}'

    # Bearer-токен (если есть) — для дополнительной авторизации
    bearer = acc.get('bearer', '')
    if bearer:
        hdrs['Authorization'] = f'OAuth {bearer}'

    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}

    try:
        r = requests.request(method, url, headers=hdrs, json=json_body,
                             params=params, timeout=timeout, proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Маркет: сеть ({method} {path}): {e}')

    if r.status_code in (401, 403):
        raise RuntimeError(f'Я.Маркет: авторизация отклонена ({r.status_code}): сессия устарела/невалидна')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Маркет: HTTP {r.status_code} на {method} {path}: {r.text[:300]}')

    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:1000]}


def _web_call(acc, method, path, json_body=None, params=None, timeout=25):
    """HTTP-запрос к веб-интерфейсу Яндекс Маркета."""
    url = MARKET_HOST + path
    hdrs = {
        'User-Agent': MARKET_APP['user-agent'],
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': MARKET_APP['accept-language'],
    }

    session_id = acc.get('session_id', '')
    if session_id:
        hdrs['Cookie'] = f'Session_id={session_id}'

    proxies = None
    proxy_url = (acc.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}

    try:
        r = requests.request(method, url, headers=hdrs, json=json_body,
                             params=params, timeout=timeout, proxies=proxies)
    except requests.RequestException as e:
        raise RuntimeError(f'Я.Маркет (web): сеть ({method} {path}): {e}')

    if r.status_code in (401, 403):
        raise RuntimeError(f'Я.Маркет (web): авторизация отклонена ({r.status_code})')
    if r.status_code >= 400:
        raise RuntimeError(f'Я.Маркет (web): HTTP {r.status_code} на {method} {path}: {r.text[:300]}')

    return r.text


# ---------- Wow Offers (Акции «Товар за 1 рубль») ----------

def get_wow_offers(acc, page_id=None):
    """Получить список акций «Wow Offers» (товары за 1 рубль).

    page_id — идентификатор страницы акции (из URL).
    Если не указан — загружает основную страницу акций.
    """
    if page_id:
        path = f'/page/wow_offers/{page_id}'
    else:
        path = '/page/wow_offers'

    try:
        data = _market_call(acc, 'GET', path)
        return data
    except Exception as e:
        # Пробуем через веб
        html_text = _web_call(acc, 'GET', path)
        return {'_html': html_text[:5000], '_error': str(e)}


def search_wow_items(acc, query=None, category=None, price_max=1.0):
    """Поиск акционных товаров (за 1 рубль).

    query — поисковый запрос.
    category — категория товара.
    price_max — максимальная цена (по умолчанию 1 рубль).
    """
    params = {}
    if query:
        params['text'] = query
    if category:
        params['category'] = category
    params['price-max'] = price_max
    params['onstock'] = 1
    params['local-offers-first'] = 0

    path = '/search'
    try:
        data = _market_call(acc, 'GET', path, params=params)
        return data
    except Exception as e:
        return {'_error': str(e)}


def get_promo_landing(acc):
    """Получить лендинг промо-акций."""
    path = '/promos'
    try:
        data = _market_call(acc, 'GET', path)
        return data
    except Exception as e:
        return {'_error': str(e)}


def check_wow_availability(acc, sku_id):
    """Проверить доступность акционного товара по SKU."""
    path = f'/product/{sku_id}'
    try:
        data = _market_call(acc, 'GET', path)
        return data
    except Exception as e:
        return {'_error': str(e)}


def get_wow_offers_from_url(acc, url):
    """Получить акции из полного URL.

    Пример URL:
    https://market.yandex.ru/page/wow_offers?3:1787060731...
    """
    # Извлекаем path и query из URL
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    query = parsed.query

    # Преобразуем query string в dict
    params = {}
    if query:
        for param in query.split('&'):
            if '=' in param:
                key, value = param.split('=', 1)
                params[key] = value
            else:
                # Для параметров без значения (как в URL акций)
                params[param] = ''

    try:
        # Пробуем через API
        data = _market_call(acc, 'GET', path, params=params)
        return data
    except Exception as e:
        # Пробуем через веб-запрос
        try:
            html_text = _web_call(acc, 'GET', path, params=params)
            # Парсим HTML и ищем данные
            return {'_html': html_text[:10000], '_source': 'web'}
        except Exception as e2:
            return {'_error': str(e), '_web_error': str(e2)}


# ---------- Wow Offers check (streaming) ----------

_ONE_RUBLE_RE = re.compile(
    rb'data-zone-name="oneRuble(Task|Banner|Header)"'
)

def check_wow_offers(session_id, timeout=30):
    """Проверить, есть ли на аккаунте акция «Товар за 1 рубль».

    Скачивает HTML страницы /page/wow_offers потоково (чанками ~64КБ),
    останавливается как только находит виджет oneRubleTask / oneRubleBanner /
    oneRubleHeader (виджет рендерится только когда акция доступна).

    session_id — строка Session_id (начинается с "3:...")
    Возвращает True если акция есть, False если нет, None при ошибке.
    """
    if not session_id:
        return None

    url = MARKET_HOST + WOW_OFFERS_PATH
    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/151.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Accept-Encoding': 'gzip, deflate',
    }
    if session_id.startswith('Session_id='):
        session_id = session_id[len('Session_id='):]
    hdrs['Cookie'] = f'Session_id={session_id}'

    proxies = None
    proxy_url = (MARKET_APP.get('proxy') or '').strip()
    if proxy_url:
        proxies = {'http': proxy_url, 'https': proxy_url}

    try:
        r = requests.get(url, headers=hdrs, timeout=timeout,
                         proxies=proxies, stream=True)
    except requests.RequestException as e:
        return None

    if r.status_code in (401, 403):
        r.close()
        return None
    if r.status_code >= 400:
        r.close()
        return False

    found = False
    buf = b''
    try:
        for chunk in r.iter_content(chunk_size=65536):
            if not chunk:
                continue
            buf += chunk
            if _ONE_RUBLE_RE.search(buf):
                found = True
                break
            if len(buf) > 4_000_000:
                break
    finally:
        r.close()

    return found


# ---------- Scan accounts for wow offers ----------

def scan_account_wow_offers(acc):
    """Сканировать аккаунт на наличие акций «Wow Offers».

    acc — dict с session_id/bearer (из eda_accounts.json).
    Возвращает результат проверки.
    """
    session_id = acc.get('session_id', '')
    if not session_id:
        return {'has_wow': False, 'error': 'no session_id'}

    has_wow = check_wow_offers(session_id)
    return {
        'has_wow': has_wow,
        'session_id': session_id[:20] + '...',
        'checked_at': time.time(),
    }


def scan_all_accounts_wow_offers(accs=None, workers=5):
    """Сканировать аккаунты на наличие акций параллельно.

    accs — список dict-аккаунтов {name, session_id}. По умолчанию — все
    аккаунты из market_accounts.json.
    workers — число параллельных потоков (по умолчанию 5).
    Возвращает dict {name: {has_wow: bool, ...}}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if accs is None:
        accs = load_market_accounts()
    if not accs:
        return {}

    def _check(acc):
        name = acc.get('name', 'unknown')
        try:
            return name, scan_account_wow_offers(acc)
        except Exception as e:
            return name, {'has_wow': False, 'error': str(e)}

    results = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(accs))) as pool:
        futures = {pool.submit(_check, acc): acc for acc in accs}
        for f in as_completed(futures):
            name, result = f.result()
            results[name] = result

    return results
