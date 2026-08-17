"""Автоматическая регистрация Яндекс-аккаунтов (каркас).

Админ нажимает «Регистрация» в админке → задача встаёт в очередь → воркер
поднимает mitmdump-захват и открывает браузер на passport.preregister →
когда регистрация пройдена (вручную или будущим автоматом), из захвата
извлекается Session_id → аккаунт добавляется в админку Я.Еды через
eda.add_eda_account. Автозаполнение формы + API почты — заглушки под развитие.
"""

import json
import os
import queue
import subprocess
import threading
import time
import uuid

import eda

MITM_PORT = 8095
MITM_ADDON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'yandex_capture_addon.py')
CAPTURE_JSONL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'yandex_capture.jsonl')
FLOWS_MITM = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          'flows_yandex.mitm')
WORKDIR = os.path.dirname(os.path.abspath(__file__))

PREREGISTER_URL = ('https://passport.yandex.ru/auth/preregister?origin=plus'
                   '&retpath=https%3A%2F%2Fplus.yandex.ru%2F'
                   '%3Futm_source%3Dafisha%26target%3Dplus-web&utm_source=afisha')

SESSION_TTL = 600          # сколько ждём Session_id в захвате, сек
TRACE_BRANCH_DELAY = 2     # задержка чтения захвата

_LOCK = threading.Lock()
_QUEUE = queue.Queue()
_TASKS = {}        # task_id -> dict(state, name, progress, error, account, ...)
_WORKER = False


def start(name='', count=1):
    """Поставить задачи авторегистрации в очередь. Возвращает (task_ids)."""
    ids = []
    with _LOCK:
        for _ in range(max(1, int(count))):
            task_id = uuid.uuid4().hex[:12]
            _TASKS[task_id] = {
                'state': 'queued', 'name': (name or '').strip(),
                'created_at': time.time(), 'updated_at': time.time(),
                'progress': 'в очереди', 'error': None, 'account': None,
            }
            _QUEUE.put(task_id)
            ids.append(task_id)
    _ensure_worker()
    return ids


def _ensure_worker():
    global _WORKER
    with _LOCK:
        if _WORKER:
            return
        _WORKER = True
    threading.Thread(target=_worker, daemon=True, name='eda-reg').start()


def _worker():
    while True:
        try:
            task_id = _QUEUE.get(timeout=1)
        except queue.Empty:
            continue
        try:
            _process(task_id)
        except Exception as e:
            _set(task_id, 'failed', error=repr(e))


def _process(task_id):
    with _LOCK:
        t = _TASKS[task_id]
    name = t.get('name') or f'reg-{task_id[:6]}'
    _set(task_id, 'launching', 'старт mitmdump…')

    mitm = None
    launcher = None
    try:
        # 1) свежий захват для задачи (файл обнуляем — ловим только новую регистрацию)
        with open(CAPTURE_JSONL, 'w', encoding='utf-8') as f:
            f.write('')
        mitm = subprocess.Popen(
            ['mitmdump', '-s', MITM_ADDON, '--listen-port', str(MITM_PORT),
             '-w', FLOWS_MITM, '--set', 'console_eventlog_verbosity=warn'],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            cwd=WORKDIR,
        )
        time.sleep(4)
        if mitm.poll() is not None:
            raise RuntimeError('mitmdump не запустился')

        # 2) браузер с захватом — открывается у оператора (или автомата)
        _set(task_id, 'browser_open', 'браузер открыт — проходите регистрацию')
        launcher = subprocess.Popen(
            [sys.executable, '-c', _launcher_code()],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=WORKDIR,
        )

        # 3) читаем захват до появления Session_id
        _set(task_id, 'waiting_capture', 'ждём Session_id…')
        sid, uid = _wait_session_id(allowed=launcher)
        if not sid:
            raise RuntimeError('Session_id не появился в захвате (превышен лимит ожидания)')
        _set(task_id, 'finalizing', 'Session_id получен — добавляем аккаунт…')
        accs = eda.add_eda_account(name, '', session_id=sid, yandexuid=uid or '')
        added = next((a for a in accs if a.get('name') == name), None)
        _set(task_id, 'done', f'аккаунт {name} добавлен', account=name)
        if added:
            t2 = _TASKS.get(task_id)
            t2['account_uid'] = added.get('yandexuid', '')
    except subprocess.TimeoutExpired:
        _set(task_id, 'failed', error='таймаут задачи')
    except Exception as e:
        _set(task_id, 'failed', error=str(e))
    finally:
        for p in (launcher, mitm):
            try:
                if p is not None and p.poll() is None:
                    p.kill()
            except Exception:
                pass


def _wait_session_id(allowed, known_size=None):
    """Читать захват, пока не появится Session_id (или allowed-процесс умрёт)."""
    deadline = time.time() + SESSION_TTL
    size = known_size or 0
    while time.time() < deadline:
        if allowed is not None and allowed.poll() is not None:
            # браузер закрыт без результата — всё равно дополлим последние строки
            pass
        try:
            with open(CAPTURE_JSONL, 'r', encoding='utf-8') as f:
                f.seek(size)
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    for key in ('set_cookies', 'cookies'):
                        d = e.get(key) or {}
                        sid = d.get('Session_id')
                        if sid:
                            return sid, (d.get('yandexuid') or '')
                size = f.tell()
        except FileNotFoundError:
            pass
        time.sleep(TRACE_BRANCH_DELAY)
    return None, None


def _launcher_code():
    return (
        'import sys\n'
        f'from playwright.sync_api import sync_playwright\n'
        f'START_URL = {PREREGISTER_URL!r}\n'
        'with sync_playwright() as p:\n'
        '    browser = p.chromium.launch(headless=False,\n'
        '        proxy={"server": "http://127.0.0.1:%d"},\n'
        '        args=["--ignore-certificate-errors", "--disable-blink-features=AutomationControlled"],\n'
        '        slow_mo=50)\n'
        '    ctx = browser.new_context(locale="ru-RU", viewport={"width": 1360, "height": 900})\n'
        '    page = ctx.new_page()\n'
        '    page.goto(START_URL, timeout=60000, wait_until="domcontentloaded")\n'
        '    print("READY", page.url, flush=True)\n'
        '    while True:\n'
        '        page.wait_for_timeout(3000)\n'
        '        cks = {c["name"]: c["value"] for c in ctx.cookies()}\n'
        '        if cks.get("Session_id"):\n'
        '            print("SESSION_ID", cks["Session_id"], flush=True)\n'
        '            break\n'
        '    browser.close()\n'
    ) % MITM_PORT


def status(task_id=None):
    """Статус одной задачи или всех."""
    with _LOCK:
        if task_id is not None:
            t = _TASKS.get(task_id)
            if not t:
                return {'ok': False, 'error': 'задача не найдена'}
            return {'ok': True, **t}
        tasks = {k: dict(v) for k, v in _TASKS.items()}
    return {'ok': True, 'tasks': tasks}


def cancel(task_id):
    with _LOCK:
        t = _TASKS.get(task_id)
        if t is None:
            return {'ok': False, 'error': 'задача не найдена'}
        if t['state'] in ('done', 'failed'):
            return {'ok': True, 'state': t['state']}
        t['state'] = 'cancelled'
        t['progress'] = 'отменена'
        t['updated_at'] = time.time()
    return {'ok': True, 'state': 'cancelled'}


def _set(task_id, state, progress=None, error=None, account=None, **kw):
    with _LOCK:
        t = _TASKS.get(task_id)
        if t is None:
            return
        t['state'] = state
        t['updated_at'] = time.time()
        if progress is not None:
            t['progress'] = progress
        if error is not None:
            t['error'] = error
        if account is not None:
            t['account'] = account
        t.update(kw)


# ---------- будущий автомат (заглушки) ----------

def _fill_form(page, email):
    """Заполнить форму регистрации passport.preregister.

    ЗАГЛУШКА: точные селекторы будут доработаны после реверсинжиниринга чучу-
    passport-формы. Сейчас открытый браузер наполняется оператором вручную.
    """
    # TODO: выбрать «по почте», ввести email/пароль/подтверждение, submit
    raise NotImplementedError('автозаполнение формы регистрации — ещё не реализовано')


def _enter_email_code(page, code):
    """Ввести код подтверждения почты (когда появится API почты).

    ЗАГЛУШКА: сбор почты пока вне scope.
    """
    raise NotImplementedError('API почты — потом')