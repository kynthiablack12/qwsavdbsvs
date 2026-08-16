import sys, os, json, uuid, time, re, html, base64, threading, queue
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core

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

def _norm_samokat_phone(phone):
    """Привести номер к виду +7XXXXXXXXXX (требование confirmation/code)."""
    p = re.sub(r'\D', '', phone or '')
    if p.startswith('8'):
        p = '7' + p[1:]
    if not p.startswith('7'):
        p = '7' + p
    return '+' + p


def get_tokens(cookies):
    """Получить свежие токены с веба: GET /api/auth/session.

    Возвращает dict: accessToken, refreshToken, sessionToken,
    accessTokenExpires (ms), expires (ISO), user.
    Кидает RuntimeError при ошибке/401.
    """
    # через браузерный мост — curl_cffi режется антиботом (403)
    return _browser_session_tokens(cookies)


def refresh_tokens(refresh_token, cookies):
    """Продлить токены: POST /api/auth/refresh.

    Возвращает тот же dict токенов. Кидает RuntimeError при ошибке.
    """
    res = _browser_api(cookies, AUTH_REFRESH_URL, method='POST',
                       body={'refreshToken': refresh_token})
    status = res.get('status') or 0
    text = res.get('body') or ''
    if status == 401:
        raise RuntimeError('Самокат: refresh-токен истёк или невалиден (401)')
    if status >= 400:
        raise RuntimeError(f'Самокат: auth/refresh HTTP {status}: {text[:300]}')
    try:
        data = json.loads(text) if text else {}
    except Exception:
        raise RuntimeError(f'Самокат: ответ auth/refresh не JSON: {text[:200]}')
    if not data.get('accessToken'):
        raise RuntimeError('Самокат: в ответе auth/refresh нет accessToken')
    return data


def is_token_expired(access_token_expires):
    """True, если accessToken уже протух (с запасом 60 сек)."""
    try:
        return int(access_token_expires) / 1000 - time.time() < 60
    except Exception:
        return True


# ---------- вход по номеру + SMS-коду ----------
#
# Flow (снят с веба api-web.samokat.ru):
#   1. GET  /api/auth/session          -> accessToken (анонимный, если не вошёл)
#   2. POST /confirmation/code         -> {phoneNumber}  -> отправляет SMS
#   3. GET  /api/auth/csrf             -> csrfToken
#   4. POST /api/auth/callback/smsCode -> phone, code, anonymousAccessToken, csrfToken
#   5. GET  /api/auth/session          -> уже вошёл: accessToken/refreshToken
#
# Между шагами держим "запрос кода" в памяти: {phone -> {name, token}}.

_PENDING_CODES = {}


def request_sms_code(phone):
    """Отправить SMS-код: POST api-web.samokat.ru/confirmation/code.

    Токен не нужен — только номер в формате +7XXXXXXXXXX.
    Возвращает {'ok': True, 'retry_timeout': n}.
    """
    phone = _norm_samokat_phone(phone)
    if len(phone) < 12:
        raise RuntimeError('введите корректный номер телефона')
    h = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        'content-type': 'application/json',
    }
    res = _browser_api({}, API_HOST + '/confirmation/code', method='POST',
                       headers=h, body={'phoneNumber': phone})
    status = res.get('status') or 0
    text = res.get('body') or ''
    if status == 403:
        raise RuntimeError('Самокат: антибот (403) — по IP временный лимит, подождите несколько минут или запустите с другого IP')
    if status >= 400:
        raise RuntimeError(f'Самокат: confirmation/code HTTP {status}: {text[:300]}')
    try:
        j = json.loads(text)
    except Exception:
        j = {}
    _PENDING_CODES[phone] = {'sent_at': time.time()}
    return {'ok': True, 'retry_timeout': j.get('retryTimeout', 120)}


_BROWSER_FETCH_JS = """
async (a) => {
  const [url, method, headers, body, form] = a;
  const opts = {method: method || 'GET', credentials: 'include', headers: headers || {}};
  if (form) {
    opts.headers['content-type'] = 'application/x-www-form-urlencoded';
    opts.body = new URLSearchParams(form).toString();
  } else if (body) {
    opts.headers['content-type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const r = await fetch(url, opts);
  const t = await r.text();
  return {status: r.status, ct: r.headers.get('content-type') || '', body: t};
}
"""


def _browser_fetch_page(page, url, method='GET', headers=None, body=None, form=None):
    """fetch через реальный JS из уже загруженной страницы (same-origin requests:
    /api/auth/* на samokat.ru). Выполняет антибот-скрипты страницы, которые ставят
    куки — это нужно для анонимного входа по SMS, где context.request не годится.
    Для cross-origin api-web.samokat.ru использовать НЕЛЬЗЯ (CORS) — там context.request.
    """
    return page.evaluate(_BROWSER_FETCH_JS, [url, method, headers, body, form])


def _browser_fetch(ctx, url, method='GET', headers=None, body=None, form=None):
    """Настоящий браузерный HTTP из контекста (context.request).
    Обходит CORS (fetch из JS-страницы к api-web.samokat.ru блокировался).
    Куки антибота/сессии берутся из контекста автоматически.
    """
    opts = {'headers': headers or {}, 'timeout': 45000}
    if form:
        opts['data'] = {k: v for k, v in form.items()}
    elif body is not None:
        opts['data'] = json.dumps(body)
        opts['headers'].setdefault('content-type', 'application/json')
    req = ctx.request
    try:
        r = getattr(req, method.lower())(url, **opts)
    except Exception as e:
        return {'status': 0, 'ct': '', 'body': '', 'error': repr(e)}
    return {'status': r.status, 'ct': r.headers.get('content-type', ''),
            'body': r.text()}


# ---------- браузерный API-мост (обходит антибот ServicePipe) ----------
#
# curl_cffi-запросы к samokat.ru / api-web.samokat.ru с этого IP режутся
# антиботом (403), поэтому весь API ходит через реальный Chromium: одна
# страница на аккаунт с его куками, запросы через page.evaluate(fetch).
# Перед каждым вызовом берём свежий accessToken из /api/auth/session
# (куки __Secure-next-auth.session-token валидны до 2027) — это заодно
# решает 5-минутное истечение accessToken без ручного refresh.
#
# Playwright sync API живёт в одном потоке — все запросы гоняются через
# фоновый воркер-поток с очередью, чтобы не конфликтовать с потоками webapp.

_BROWSER_Q = None
_BROWSER_LOCK = threading.Lock()


def _ensure_browser_worker():
    global _BROWSER_Q
    with _BROWSER_LOCK:
        if _BROWSER_Q is None:
            _BROWSER_Q = queue.Queue()
            t = threading.Thread(target=_browser_worker_main, daemon=True, name='samokat-browser')
            t.start()
    return _BROWSER_Q


def _browser_worker_main():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        contexts = {}   # cookies-hash -> (context, page)
        while True:
            task = _BROWSER_Q.get()
            if task is None:
                break
            ck_hash, cookies, method, url, headers, body, form, result_q = task
            try:
                ctx, page = contexts.get(ck_hash) or (None, None)
                if ctx is None:
                    ctx = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
                        locale='ru-RU',
                    )
                    if cookies:
                        ctx.add_cookies(_playwright_cookies(cookies))
                    page = ctx.new_page()
                    contexts[ck_hash] = (ctx, page)
                res = _browser_fetch_resilient(ctx, page, url, method, headers, body, form)
                result_q.put((ck_hash, res))
            except Exception as e:
                result_q.put((ck_hash, {'error': repr(e)}))


def _is_antibot_html(body):
    """Антибот-стена ServicePipe: HTML без JSON, часто содержит servicepipe.tech или noscript-redirect."""
    b = (body or '')
    return ('<' in b) and ('json' not in (b[:60]).lower()) and ('servicepipe' in b.lower() or b.lstrip().startswith('<!DOCTYPE html>') or b.lstrip().startswith('<html'))


def _browser_fetch_resilient(ctx, page, url, method, headers, body, form, attempts=5):
    """Запрос с антибот-ритраями: грузим samokat.ru (ставит куки антибота),
    затем context.request; при HTML-стене/403 reload'им и повторяем.
    """
    last = {'status': 0, 'ct': '', 'body': ''}
    for i in range(attempts):
        try:
            page.goto(SAMOKAT_WEB + '/', timeout=45000, wait_until='domcontentloaded')
        except Exception:
            pass
        page.wait_for_timeout(3000)
        res = _browser_fetch(ctx, url, method, headers, body, form)
        last = res
        if res.get('error') or (res.get('status') and res.get('status') != 403 and not _is_antibot_html(res.get('body'))):
            return res
        # 403/стена — reload и ещё попытка
        page.wait_for_timeout(2000)
    return last


def _cookies_hash(cookies):
    import hashlib
    key = ';'.join(f'{k}={v}' for k, v in sorted((cookies or {}).items()))
    return hashlib.sha1(key.encode('utf-8', 'replace')).hexdigest()


def _playwright_cookies(cookies):
    """Привести куки аккаунта к формату playwright.

    __Host-* куки обязаны быть host-only и Secure; __Secure-* — Secure.
    host-only куки (domain без точки) не ходят на api-web.samokat.ru,
    но __Host-* в любом случае на поддомены не отправляются.
    """
    out = []
    for k, v in (cookies or {}).items():
        if not v:
            continue
        c = {'name': k, 'value': str(v), 'path': '/'}
        if k.startswith('__Host-'):
            c['domain'] = 'samokat.ru'
            c['secure'] = True
        else:
            c['domain'] = '.samokat.ru'
            if k.startswith('__Secure-'):
                c['secure'] = True
        out.append(c)
    return out


def _browser_api(cookies, url, method='GET', headers=None, body=None, form=None, timeout=45):
    """Выполнить запрос через браузерный мост. Возвращает {status, ct, body}."""
    q = _ensure_browser_worker()
    ck_hash = _cookies_hash(cookies)
    result_q = queue.Queue(maxsize=1)
    q.put((ck_hash, cookies, method, url, headers, body, form, result_q))
    try:
        _, res = result_q.get(timeout=timeout)
    except queue.Empty:
        raise RuntimeError(f'Самокат: таймаут браузерного запроса {url[:80]}')
    if isinstance(res, dict) and res.get('error'):
        raise RuntimeError(f'Самокат: браузерный запрос {url[:80]}: {res["error"]}')
    return res


def _browser_api_json(cookies, url, method='GET', headers=None, body=None, form=None):
    """Браузерный запрос, ответ разбирается как JSON. Кидает RuntimeError."""
    res = _browser_api(cookies, url, method=method, headers=headers, body=body, form=form)
    status = res.get('status') or 0
    text = res.get('body') or ''
    if status == 401:
        raise RuntimeError('Самокат: 401 — сессия истекла, перевойдите на samokat.ru')
    if status >= 400:
        raise RuntimeError(f'Самокат: HTTP {status}: {text[:300]}')
    try:
        return json.loads(text) if text else {}
    except Exception:
        return {}


def _browser_session_tokens(cookies):
    """Свежие токены через браузер: GET /api/auth/session."""
    d = _browser_api_json(cookies, AUTH_SESSION_URL, method='GET')
    if not d.get('accessToken'):
        raise RuntimeError('Самокат: браузер не отдал accessToken из /api/auth/session')
    return d


def _browser_login_session(phone, code):
    """Весь вход в реальном браузере (обходит ServicePipe):
    session -> csrf -> callback/smsCode -> session.

    Возвращает (tokens_dict, cookies_list).
    """
    from playwright.sync_api import sync_playwright
    phone = _norm_samokat_phone(phone)
    code = (code or '').strip()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        try:
            ctx = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
                locale='ru-RU',
            )
            page = ctx.new_page()
            page.goto(SAMOKAT_WEB + '/', timeout=60000, wait_until='domcontentloaded')
            data = {}
            for _ in range(5):
                page.wait_for_timeout(5000)
                # same-origin /api/auth/session — идёт ЖС-фетчем со страницы, чтобы
                # антибот-скрипты успели поставить куки (иначе context.request -> 403)
                res = _browser_fetch_page(page, AUTH_SESSION_URL)
                if res['status'] == 200 and 'json' in res['ct']:
                    try:
                        data = json.loads(res['body']) or {}
                    except Exception:
                        data = {}
                    if data.get('accessToken'):
                        break
                page.reload()
                page.wait_for_timeout(3000)
            token = data.get('accessToken', '')
            if not token:
                raise RuntimeError('Самокат: не получен анонимный accessToken (антибот). Повторите через несколько минут.')
            csrf = ''
            for _ in range(3):
                res = _browser_fetch_page(page, SAMOKAT_WEB + '/api/auth/csrf')
                try:
                    csrf = (json.loads(res['body']) or {}).get('csrfToken', '')
                except Exception:
                    csrf = ''
                if csrf:
                    break
                page.reload()
                page.wait_for_timeout(3000)
            if not csrf:
                raise RuntimeError('Самокат: не получен csrfToken (антибот)')
            cb = _browser_fetch_page(page, SAMOKAT_WEB + '/api/auth/callback/smsCode', 'POST',
                                     form={'redirect': 'false', 'callbackUrl': '/',
                                           'phone': phone, 'code': code,
                                           'anonymousAccessToken': token,
                                           'csrfToken': csrf, 'json': 'true'})
            res = _browser_fetch_page(page, AUTH_SESSION_URL)
            try:
                data = json.loads(res['body']) or {}
            except Exception:
                data = {}
            if not data.get('accessToken'):
                raise RuntimeError(f'Самокат: вход не прошёл (callback={cb["status"]}). Проверьте код или повторите позже.')
            return data, ctx.cookies()
        finally:
            browser.close()


def confirm_sms_code(phone, code):
    """Шаги 3-5: подтвердить код в браузере.

    Возвращает (tokens_dict, cookies_list) для сохранения аккаунта.
    """
    phone = _norm_samokat_phone(phone)
    code = (code or '').strip()
    if not phone or not code:
        raise RuntimeError('номер и код обязательны')
    if not _PENDING_CODES.get(phone):
        raise RuntimeError('сначала отправьте код на этот номер')
    data, cookies = _browser_login_session(phone, code)
    _PENDING_CODES.pop(phone, None)
    return data, cookies


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


def add_samokat_account_by_tokens(name, data, cookies=None):
    """Создать аккаунт из токенов, полученных после ввода SMS-кода.

    data — ответ GET /api/auth/session после успешного входа;
    cookies — браузерные куки сессии (опционально, для refresh).
    """
    name = (name or '').strip()
    if not name:
        raise RuntimeError('имя аккаунта обязательно')
    jwt = _jwt_payload(data.get('accessToken', ''))
    acc = {
        'name': name,
        'cookies': _pick_cookies({c.get('name'): c.get('value', '') for c in (cookies or [])}),
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
    """Живой accessToken аккаунта через браузерный GET /auth/session.

    Не используем /auth/refresh: он на том же IP режется антиботом (403).
    Куки __Secure-next-auth.session-token валидны до 2027, поэтому каждого
    вызова хватает: session возвращает свежий accessToken (живёт ~5 мин).
    """
    cookies = acc.get('cookies') or {}
    if not cookies:
        raise RuntimeError('у аккаунта нет кук — перевойдите на samokat.ru')
    data = get_tokens(cookies)
    return data.get('accessToken')


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

def _api_headers(acc, with_token=True):
    """Заголовки запроса к api-web.samokat.ru (по образцу дампа браузера).

    deviceid = кука spid; Origin/Referer — samokat.ru; все куки шлём целиком.
    При with_token=False не добавляет authorization (для анонимных вызовов).
    """
    h = dict(APP)
    if with_token:
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


def _api_url(path, **params):
    url = API_HOST + path
    if params:
        from urllib.parse import urlencode
        url += ('&' if '?' in url else '?') + urlencode(params)
    return url


def api_get(acc, path, **params):
    """GET к api-web.samokat.ru через браузер, возвращает JSON. RuntimeError."""
    h = _api_headers(acc)
    res = _browser_api(acc.get('cookies') or {},
                       _api_url(path, **params), method='GET', headers=h)
    status = res.get('status') or 0
    text = res.get('body') or ''
    if status == 401:
        raise RuntimeError('Самокат: 401 — сессия истекла, перевойдите в аккаунт')
    if status >= 400:
        raise RuntimeError(f'Самокат: {path} HTTP {status}: {text[:300]}')
    try:
        return json.loads(text) if text else {}
    except Exception:
        return {}


def api_post(acc, path, body=None):
    """POST к api-web.samokat.ru через браузер, возвращает JSON. RuntimeError."""
    h = _api_headers(acc)
    h['content-type'] = 'application/json'
    res = _browser_api(acc.get('cookies') or {},
                       _api_url(path), method='POST', headers=h,
                       body=body or {})
    status = res.get('status') or 0
    text = res.get('body') or ''
    if status == 401:
        raise RuntimeError('Самокат: 401 — сессия истекла, перевойдите в аккаунт')
    if status >= 400:
        raise RuntimeError(f'Самокат: {path} HTTP {status}: {text[:300]}')
    try:
        return json.loads(text) if text else {}
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
