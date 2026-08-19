import sys, os, json, uuid, time, re, random, threading, urllib.parse, html, contextlib, base64
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
        return {'has_wow': False, 'error': 'no session_id', 'session_id': ''}

    has_wow = check_wow_offers(session_id)
    return {
        'has_wow': has_wow,
        'session_id': session_id[:24] + '...',
        'checked_at': time.time(),
    }


def scan_all_accounts_wow_offers(accs=None, workers=5, progress=None):
    """Сканировать аккаунты на наличие акций параллельно.

    accs — список dict-аккаунтов {name, session_id}. По умолчанию — все
    аккаунты из market_accounts.json.
    workers — число параллельных потоков (по умолчанию 5).
    progress — колбэк (msg, frac) для лога/прогресса.
    Возвращает dict {name: {has_wow: bool, ...}}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if accs is None:
        accs = load_market_accounts()
    if not accs:
        return {}

    if progress:
        progress(f'Найдено аккаунтов для проверки: {len(accs)}', None)

    def _check(acc):
        name = acc.get('name', 'unknown')
        try:
            r = scan_account_wow_offers(acc)
            sid = r.get('session_id') or ''
            has = r.get('has_wow')
            if has:
                msg = f'{name}: акция ЕСТЬ (sid {sid})'
            elif r.get('error'):
                msg = f'{name}: ошибка: {r.get("error")}'
            else:
                msg = f'{name}: акции нет (sid {sid})'
            if progress:
                progress(msg, None)
            return name, r
        except Exception as e:
            if progress:
                progress(f'{name}: ошибка {e}', None)
            return name, {'has_wow': False, 'error': str(e)}

    results = {}
    done = 0
    total = len(accs)
    with ThreadPoolExecutor(max_workers=min(workers, len(accs))) as pool:
        futures = {pool.submit(_check, acc): acc for acc in accs}
        for f in as_completed(futures):
            name, result = f.result()
            results[name] = result
            done += 1
            if progress:
                progress(f'Проверено {done}/{total}', done / total)

    return results


# ---------- UGC reviews (авто-отзывы) ----------

# Базовый URL UGC-эндпоинтов (получен из браузера, см. market_review_flow.md)
UGC_MARKET_FRONT = (
    'https://market.yandex.ru/api/web/'
    'market.front.marketFront.MarketFront'
)

MY_TASKS_PATH = '/my/tasks'


def _parse_tasks_page(text):
    """Извлечь sk (CSRF) и задания на отзыв из HTML страницы /my/tasks.

    Возвращает (sk, tasks), где tasks — список dict
    {'context': base64, 'data': {раскодированный JSON}, 'title': str}.
    """
    sk = None
    m = re.search(r'"sk":"(u[0-9a-f]{32})"', text)
    if m:
        sk = m.group(1)

    tasks = []
    b64pat = re.compile(r'[A-Za-z0-9+/]{60,}={0,2}')
    for mm in b64pat.finditer(text):
        s = mm.group(0)
        try:
            d = json.loads(base64.b64decode(s))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        if not ('orderId' in d and 'agitationId' in d and 'modelId' in d):
            continue
        tasks.append({'context': s, 'data': d})

    # Уникализация по agitationId
    seen = set()
    uniq = []
    for t in tasks:
        key = t['data'].get('agitationId') or t['context']
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return sk, uniq


def get_review_tasks(session_id, timeout=30):
    """Получить задания на отзыв (UGC-контексты) для аккаунта.

    session_id — строка Session_id (начинается с "3:...").
    Возвращает dict {'sk': str, 'tasks': [...], 'error': str|None}.
    """
    if not session_id:
        return {'sk': None, 'tasks': [], 'error': 'no session_id'}

    if session_id.startswith('Session_id='):
        session_id = session_id[len('Session_id='):]

    hdrs = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/151.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ru-RU,ru;q=0.9',
        'Cookie': f'Session_id={session_id}',
    }

    try:
        r = requests.get(MARKET_HOST + MY_TASKS_PATH, headers=hdrs, timeout=timeout)
    except requests.RequestException as e:
        return {'sk': None, 'tasks': [], 'error': f'сеть: {e}'}

    if r.status_code in (401, 403):
        return {'sk': None, 'tasks': [], 'error': 'авторизация отклонена (сессия невалидна)'}
    if r.status_code >= 400:
        return {'sk': None, 'tasks': [], 'error': f'HTTP {r.status_code}'}

    sk, tasks = _parse_tasks_page(r.text)
    return {'sk': sk, 'tasks': tasks, 'error': None}


def _ugc_headers(sk, session_id):
    """Заголовки для UGC-запросов (соответствуют реальным из браузера)."""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/151.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'ru',
        'Content-Type': 'application/json',
        'Origin': 'https://market.yandex.ru',
        'Referer': 'https://market.yandex.ru/my/tasks',
        'sk': sk,
        'x-market-app-version': '2026.08.16.0-desktop.t4520775952',
        'x-market-apphost-target': 'market-pers-master-apphost',
        'x-market-core-service': '<UNKNOWN>',
        'x-market-front-glue': '1787131749000',
        'x-market-page-id': 'market:my-tasks',
        'x-requested-with': 'XMLHttpRequest',
        'x-retpath-y': 'https://market.yandex.ru/my/tasks',
        'Cookie': f'Session_id={session_id}',
    }


def _ugc_call(sk, session_id, method, body, timeout=30):
    """Вызвать UGC-эндпоинт Маркета."""
    url = f'{UGC_MARKET_FRONT}/{method}'
    try:
        r = requests.post(url, headers=_ugc_headers(sk, session_id),
                          json=body, timeout=timeout)
    except requests.RequestException as e:
        return {'_error': f'сеть: {e}'}
    if r.status_code >= 400:
        return {'_error': f'HTTP {r.status_code}: {r.text[:300]}'}
    try:
        return r.json()
    except Exception:
        return {'_status': r.status_code, '_text': r.text[:500]}


def post_review(session_id, sk, context, text, grade=5, anonymity=0,
                factors=None, timeout=30):
    """Отправить отзыв на задание из «Мои задания».

    session_id — Session_id аккаунта.
    sk — CSRF-токен со страницы /my/tasks.
    context — base64-контекст задания (из get_review_tasks).
    text — текст отзыва (pro).
    grade — оценка 1..5.
    anonymity — 0 (публично) или 1 (анонимно).
    factors — dict выбранных факторов (по умолчанию {}).
    Возвращает dict с результатом Save + ThankPage.
    """
    if session_id.startswith('Session_id='):
        session_id = session_id[len('Session_id='):]

    save_body = {
        'path': '/my/tasks',
        'params': {
            'requestType': 'SAVE_REVIEW',
            'context': context,
            'body': {
                'averageGrade': grade,
                'pro': text,
                'anonymity': anonymity,
                'selectedFactors': factors or {},
                'media': [],
            },
        },
    }
    save_res = _ugc_call(sk, session_id, 'apiUgcReviewFormSave', save_body, timeout)

    result = {'save': save_res}

    # Если отзыв сохранён — завершаем флоу (ThankPage)
    review_id = None
    try:
        col = (save_res.get('result') or {}).get('collections') or {}
        for rid, rv in (col.get('review') or {}).items():
            review_id = rid
            break
    except Exception:
        pass
    result['review_id'] = review_id

    if review_id is not None:
        thanks_body = {
            'path': '/my/tasks',
            'params': {'requestType': 'THANKS', 'context': context},
        }
        result['thank'] = _ugc_call(sk, session_id, 'apiUgcThankPage', thanks_body, timeout)

    return result


def review_all_accounts(accs=None, text=None, grade=5, anonymity=0, workers=5,
                        progress=None, dry_run=False):
    """Оставить отзывы на всех аккаунтах.

    accs — список dict {name, session_id}. По умолчанию — все из
    market_accounts.json.
    text — текст отзыва. По умолчанию — нейтральный.
    grade — оценка 1..5.
    anonymity — 0/1.
    workers — число параллельных потоков.
    progress — колбэк (msg, frac).
    dry_run — не отправлять, только показать найденные задания.
    Возвращает dict {name: результат}.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if accs is None:
        accs = load_market_accounts()
    if not accs:
        return {}

    if text is None:
        text = 'Товар соответствует описанию. Доставка быстрая.'

    if progress:
        progress(f'Аккаунтов для отзывов: {len(accs)}', None)

    def _work(acc):
        name = acc.get('name', 'unknown')
        session_id = acc.get('session_id', '')
        if not session_id:
            if progress:
                progress(f'{name}: нет session_id', None)
            return name, {'error': 'no session_id'}

        info = get_review_tasks(session_id)
        if info.get('error'):
            if progress:
                progress(f'{name}: ошибка {info["error"]}', None)
            return name, {'error': info['error']}

        sk = info.get('sk')
        tasks = info.get('tasks') or []
        if not sk or not tasks:
            if progress:
                reason = ('страница загрузилась, но sk не найден'
                          if not sk else 'страница загрузилась, заданий на отзыв не найдено')
                progress(f'{name}: {reason} (sid {session_id[:16]}...)', None)
            return name, {'reviews': [], 'skipped': 'no tasks'}

        if progress:
            progress(f'{name}: заданий на отзыв: {len(tasks)}', None)

        reviews = []
        for t in tasks:
            context = t['context']
            data = t.get('data') or {}
            if dry_run:
                reviews.append({'context': context, 'data': data,
                                'dry_run': True})
                continue
            try:
                res = post_review(session_id, sk, context, text,
                                  grade=grade, anonymity=anonymity)
                rid = res.get('review_id')
                status = f'отзыв #{rid}' if rid else 'не сохранён'
                reviews.append({'context': context, 'data': data,
                                'review_id': rid, 'save': res.get('save'),
                                'thank': res.get('thank')})
                if progress:
                    progress(f'{name}: {status}', None)
            except Exception as e:
                reviews.append({'context': context, 'data': data,
                                'error': str(e)})
                if progress:
                    progress(f'{name}: ошибка отзыва: {e}', None)

        return name, {'reviews': reviews, 'reviewed_count': len(reviews)}

    results = {}
    done = 0
    total = len(accs)
    with ThreadPoolExecutor(max_workers=min(workers, len(accs))) as pool:
        futures = {pool.submit(_work, acc): acc for acc in accs}
        for f in as_completed(futures):
            name, result = f.result()
            results[name] = result
            done += 1
            if progress:
                progress(f'Обработано {done}/{total}', done / total)

    return results
