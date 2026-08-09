import sys, os, json, threading, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core
import pickup
import eda
import samokat
from flask import Flask, jsonify, request, render_template, Response, session, redirect, url_for
import time

app = Flask(__name__)

# Админка закрывается паролем из env ADMIN_PASSWORD.
# Если переменная не задана (локальная разработка) — админка открыта.
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', '')
app.secret_key = hashlib.sha256((ADMIN_PASSWORD or 'local-dev').encode()).hexdigest()


@app.before_request
def guard():
    """Пользователь (pickup-клиент /p/... и купоны /c/...) не имеет доступа
    к админке. Админ-роуты защищены паролем, если ADMIN_PASSWORD задан."""
    if not ADMIN_PASSWORD:
        return None
    p = request.path
    if (p.startswith('/static') or p.startswith('/p/') or
            p.startswith('/api/pickup/') or p.startswith('/c/') or p == '/login' or
            (p.startswith('/api/coupons/shares/') and p.endswith('/data'))):
        return None
    if session.get('admin'):
        return None
    if p.startswith('/api/'):
        return jsonify({'error': 'Требуется вход в админку'}), 401
    return redirect(url_for('login_page'))


@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if not ADMIN_PASSWORD:
        return redirect(url_for('index'))
    if request.method == 'POST':
        if request.form.get('password', '') == ADMIN_PASSWORD:
            session['admin'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='Неверный пароль')
    return render_template('login.html', error=None)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))


@app.after_request
def no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp

# per-account live logs
LOGS = {}
LOCK = threading.Lock()


def get_logs(name):
    with LOCK:
        return LOGS.setdefault(name, [])


def push_log(name, line):
    with LOCK:
        LOGS.setdefault(name, []).append({'t': time.strftime('%H:%M:%S'), 'line': line})


def run_in_thread(name):
    def log(line):
        push_log(name, line)
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        push_log(name, f'ERROR: account "{name}" not found')
        return
    try:
        core.play_account(acc, log)
    except Exception as e:
        push_log(name, f'ERROR: {e}')
    push_log(name, '--- finished ---')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/accounts')
def api_accounts():
    accs = core.load_accounts()
    running = core.runs.running()
    result = []
    for a in accs:
        result.append({
            'name': a.get('name'),
            'event_id': a.get('event_id'),
            'device_id': a.get('device_id', '')[:8] + '...',
            'running': a.get('name') in running,
            'last_updated': None,
        })
    return jsonify(result)


@app.route('/api/accounts/<name>/status')
def api_account_status(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        at = core.refresh_magnit_token(acc)
        games = {}
        # Призолето
        try:
            rs = core.get_game_token(acc, at, event_id='wX8CoYBu0OQzsA6DBwqlU')
            login = core.login_game(rs)
            h = core.game_headers(login['token'], login['external_id'])
            prof = core.s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=20).json()
            ind = prof.get('indicators') or {}
            base = prof.get('attempts', {}).get('total_count') or 0
            tasks = core.get_tasks_prizoleto(h)
            ready = [t for t in tasks if t.get('ready_for_activation')]
            pend_sum = sum(int((r.get('amount') or 0)) for t in ready for r in (t.get('rewards') or []) if r.get('type') == 'attempts')
            games['wX8CoYBu0OQzsA6DBwqlU'] = {
                'game': 'Призолето',
                'attempts': base + pend_sum,
                'base_attempts': base,
                'pending_attempts': pend_sum,
                'last_level': prof.get('last_finished_map_level'),
                'daily_reward_ready': bool(ind.get('has_ready_daily_login_reward')),
                'everyday_task_ready': bool(ind.get('has_ready_everyday_login_task')),
                'has_tasks': bool(ind.get('has_ready_tasks')),
            }
        except Exception as e:
            games['wX8CoYBu0OQzsA6DBwqlU'] = {'game': 'Призолето', 'error': str(e)[:120]}
        # Монстро-планетяне
        try:
            rs = core.get_game_token(acc, at, event_id='At99RuZXsCpnFRhpmEZCK')
            data = core.auth_game_monstro(rs)
            user = data.get('user', {})
            pending = data.get('pending_rewards') or []
            base = user.get('attempts_count') or 0
            pend_sum = sum((t.get('attempts') or 0) for t in pending)
            games['At99RuZXsCpnFRhpmEZCK'] = {
                'game': 'Монстро-планетяне',
                'attempts': base + pend_sum,
                'base_attempts': base,
                'pending_attempts': pend_sum,
                'last_level': None,
                'daily_reward_ready': bool(pending),
                'pending_tasks': len(pending),
                'chances': user.get('chances_count'),
            }
        except Exception as e:
            games['At99RuZXsCpnFRhpmEZCK'] = {'game': 'Монстро-планетяне', 'error': str(e)[:120]}
        return jsonify({
            'name': name,
            'games': games,
            'active_event_id': acc.get('event_id'),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<name>/extras')
def api_account_extras(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        at = core.refresh_magnit_token(acc)
        return jsonify({
            'name': name,
            'balance': core.get_balance(acc, at),
            'offers': core.get_offers(acc, at),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<name>/coupons')
def api_account_coupons(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        cs = pickup.coupons(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    out = []
    for c in cs:
        it = (c.get('items') or [{}])[0]
        out.append({
            'id': c.get('favoriteId'),
            'title': c.get('title') or '',
            'subtitle': c.get('subtitle') or '',
            'code': (it or {}).get('couponCode') or c.get('favoriteId') or '',
            'display_type': c.get('displayType'),
            'discount_value': (it or {}).get('discountValue'),
            'discount_type': (it or {}).get('discountType'),
            'expiration_date': c.get('expirationDate'),
            'image': c.get('smallImageUrl') or c.get('largeImageUrl') or c.get('promoImageUrl') or '',
        })
    return jsonify({'ok': True, 'coupons': out})


@app.route('/api/accounts/<name>/play', methods=['POST'])
def api_play(name):
    started, err = core.runs.start(name)
    if err:
        return jsonify({'error': err}), 409
    push_log(name, '--- started ---')
    threading.Thread(target=run_in_thread, args=(name,), daemon=True).start()
    return jsonify({'ok': True})


@app.route('/api/accounts/play-all', methods=['POST'])
def api_play_all():
    """Запустить автоплей одновременно на всех аккаунтах."""
    accs = core.load_accounts()
    if not accs:
        return jsonify({'error': 'нет аккаунтов'}), 400
    results = []
    for a in accs:
        name = a.get('name')
        started, err = core.runs.start(name)
        if err:
            results.append({'name': name, 'status': 'already_running'})
            continue
        push_log(name, '--- started (all) ---')
        threading.Thread(target=run_in_thread, args=(name,), daemon=True).start()
        results.append({'name': name, 'status': 'started'})
    return jsonify({'ok': True, 'results': results})


@app.route('/api/accounts/<name>/rewards/claim', methods=['POST'])
def api_claim_daily(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    lines = []
    log = lambda l: lines.append(l)
    try:
        at = core.refresh_magnit_token(acc)
        results = {}
        # Призолето — ежедневный бонус за вход и готовые задачи
        try:
            rs = core.get_game_token(acc, at, event_id='wX8CoYBu0OQzsA6DBwqlU')
            login = core.login_game(rs)
            h = core.game_headers(login['token'], login['external_id'])
            got = core.claim_prizoleto_daily(h, log)
            results['wX8CoYBu0OQzsA6DBwqlU'] = {'game': 'Призолето', 'attempts_got': got}
        except Exception as e:
            results['wX8CoYBu0OQzsA6DBwqlU'] = {'game': 'Призолето', 'error': str(e)[:120]}
        # Монстро — pending rewards (ежедневный бонус и задачи)
        try:
            rs = core.get_game_token(acc, at, event_id='At99RuZXsCpnFRhpmEZCK')
            data = core.auth_game_monstro(rs)
            h = core.mh_headers(data['token'])
            got = 0
            for task in (data.get('pending_rewards') or []):
                tid = task.get('task_id')
                if not tid:
                    continue
                rew = core.claim_daily_reward_monstro(h, [tid])
                g = (rew.get('reward') or {}).get('attempts', 0)
                got += g
                log(f'   task {tid} reward: +{g} attempts')
            results['At99RuZXsCpnFRhpmEZCK'] = {'game': 'Монстро-планетяне', 'attempts_got': got}
        except Exception as e:
            results['At99RuZXsCpnFRhpmEZCK'] = {'game': 'Монстро-планетяне', 'error': str(e)[:120]}
        return jsonify({'ok': True, 'results': results, 'log': lines})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<name>/game', methods=['POST'])
def api_account_set_game(name):
    d = request.get_json(force=True, silent=True) or {}
    event_id = str(d.get('event_id', '')).strip()
    if event_id not in core.GAME_EVENTS.values():
        return jsonify({'error': 'unknown event_id'}), 400
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    acc['event_id'] = event_id
    core.save_accounts(accs)
    return jsonify({'ok': True, 'event_id': event_id})


@app.route('/api/accounts/<name>/logs')
def api_logs(name):
    logs = get_logs(name)
    return Response('\n'.join(f'[{x["t"]}] {x["line"]}' for x in logs), mimetype='text/plain')


@app.route('/api/accounts/<name>/logs/stream')
def api_logs_stream(name):
    def gen():
        last = 0
        while True:
            logs = get_logs(name)
            if len(logs) > last:
                for x in logs[last:]:
                    yield f'[{x["t"]}] {x["line"]}\n'
                last = len(logs)
            time.sleep(0.5)
    return Response(gen(), mimetype='text/event-stream')


@app.route('/api/accounts/from-token', methods=['POST'])
def api_account_from_token():
    d = request.get_json(force=True)
    name = str(d.get('name', '')).strip()
    token = str(d.get('refresh_token', '')).strip()
    event_id = str(d.get('event_id', '')).strip() or 'wX8CoYBu0OQzsA6DBwqlU'
    if not name or not token:
        return jsonify({'error': 'name and refresh_token required'}), 400
    try:
        core.add_account_by_token(name, token, event_id=event_id)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'name': name})


@app.route('/api/register/start', methods=['POST'])
def api_register_start():
    d = request.get_json(force=True)
    phone = core.norm_phone(str(d.get('phone', '')).strip())
    name = str(d.get('name', '')).strip() or None
    first_name = str(d.get('first_name', '')).strip() or None
    birth_date = str(d.get('birth_date', '')).strip() or None
    event_id = str(d.get('event_id', '')).strip() or 'wX8CoYBu0OQzsA6DBwqlU'
    if not phone:
        return jsonify({'error': 'phone required'}), 400
    try:
        reg = core.add_account(phone, name, first_name, birth_date, event_id=event_id)
        core.store_pending(reg)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'name': reg['name']})


@app.route('/api/register/confirm', methods=['POST'])
def api_register_confirm():
    d = request.get_json(force=True)
    name = str(d.get('name', '')).strip()
    phone = core.norm_phone(str(d.get('phone', '')).strip()) if d.get('phone') else None
    code = str(d.get('code', '')).strip()
    if (not name and not phone) or not code:
        return jsonify({'error': 'phone/name and code required'}), 400
    reg = core.get_pending(name or phone)
    if not reg:
        return jsonify({'error': 'pending registration state not found, restart registration'}), 400
    try:
        core.confirm_account(reg, code)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'name': reg['name']})


@app.route('/api/accounts/<name>/coupons/sync', methods=['POST'])
def api_coupons_sync(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        added = core.sync_coupons(acc, lambda line: push_log(name, line))
        return jsonify({'ok': True, 'added': added})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<name>/rewards/sync', methods=['POST'])
def api_rewards_sync(name):
    accs = core.load_accounts()
    acc = next((a for a in accs if a.get('name') == name), None)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        added = core.sync_game_rewards(acc, lambda line: push_log(name, line))
        return jsonify({'ok': True, 'added': added})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/accounts/<name>', methods=['DELETE'])
def api_delete(name):
    accs = core.load_accounts()
    accs = [a for a in accs if a.get('name') != name]
    core.save_accounts(accs)
    return jsonify({'ok': True})


# ---------- Яндекс Еда: cookie-аккаунты ----------

@app.route('/api/eda/accounts')
def api_eda_accounts():
    return jsonify([{'name': a.get('name'),
                     'added': a.get('added'),
                     'has_token': bool(eda._extract_bearer(a)),
                     'has_sid': bool(eda.sp_session_id(a)),
                     'uid': a.get('yandexuid', ''),
                     'profile_name': a.get('profile_name', ''),
                     'plus_balance': a.get('plus_balance'),
                     'plus_status': a.get('plus_status', '')}
                    for a in eda.load_eda_accounts()])


@app.route('/api/eda/accounts', methods=['POST'])
def api_eda_accounts_add():
    data = request.get_json(silent=True) or {}
    try:
        eda.add_eda_account(data.get('name', ''), data.get('cookies', ''),
                            token=data.get('token', ''), yandexuid=data.get('yandexuid', ''),
                            session_id=data.get('session_id', ''))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@app.route('/api/eda/accounts/<name>', methods=['DELETE'])
def api_eda_accounts_delete(name):
    eda.delete_eda_account(name)


@app.route('/api/eda/accounts/<name>/refresh', methods=['POST'])
def api_eda_accounts_refresh(name):
    try:
        res = eda.refresh_eda_account(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, **res})


# Промо-задачи: {task_id: {state, progress, message, result}}
PROMO_TASKS = {}
_PROMO_LOCK = threading.Lock()


@app.route('/api/eda/promos', methods=['POST'])
def api_eda_promos():
    """Чекер промокодов: по всем аккаунтам Я.Еды (в фоне, с прогрессом)."""
    data = request.get_json(silent=True) or {}
    names = data.get('names') or None
    task_id = hashlib.md5(os.urandom(16)).hexdigest()[:12]
    with _PROMO_LOCK:
        PROMO_TASKS[task_id] = {'state': 'running', 'progress': 0, 'message': 'Запуск…', 'result': None}

    def _run():
        try:
            accounts = eda.load_eda_accounts()
            if names:
                accounts = [a for a in accounts if a.get('name') in names]
            result = []
            total = max(len(accounts), 1)
            for idx, a in enumerate(accounts):
                acc_progress = {'frac': 0.0, 'msg': ''}

                def _cb(msg, frac, _idx=idx, _a=a, _acc_progress=acc_progress):
                    _acc_progress['frac'] = frac
                    _acc_progress['msg'] = msg
                    pct = int(((_idx + frac) / total) * 100)
                    with _PROMO_LOCK:
                        t = PROMO_TASKS[task_id]
                        t['progress'] = pct
                        t['message'] = f'{_a.get("name")}: {msg}'

                try:
                    r = eda.find_promocodes(a, progress=_cb)
                except Exception as e:
                    r = {'codes': [], 'error': str(e)}
                result.append({'name': a.get('name'), **r})
            with _PROMO_LOCK:
                PROMO_TASKS[task_id]['state'] = 'done'
                PROMO_TASKS[task_id]['progress'] = 100
                PROMO_TASKS[task_id]['message'] = 'Готово'
                PROMO_TASKS[task_id]['result'] = result
        except Exception as e:
            with _PROMO_LOCK:
                PROMO_TASKS[task_id]['state'] = 'error'
                PROMO_TASKS[task_id]['message'] = str(e)
                PROMO_TASKS[task_id]['result'] = None

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'task_id': task_id})


@app.route('/api/eda/promos/<task_id>', methods=['GET'])
def api_eda_promos_status(task_id):
    with _PROMO_LOCK:
        t = PROMO_TASKS.get(task_id)
    if not t:
        return jsonify({'error': 'task not found'}), 404
    return jsonify({'state': t['state'], 'progress': t['progress'],
                    'message': t['message'], 'result': t['result']})


# Задачи сбора «Свои Плюсы» (ежедневные подарки).
SP_TASKS = {}
_SP_LOCK = threading.Lock()


@app.route('/api/sp/daily', methods=['POST'])
def api_sp_daily():
    """Собрать ежедневные подарки «Свои Плюсы» по аккаунтам с Session_id."""
    data = request.get_json(silent=True) or {}
    names = data.get('names') or None
    claim = bool(data.get('claim', False))
    task_id = hashlib.md5(os.urandom(16)).hexdigest()[:12]
    with _SP_LOCK:
        SP_TASKS[task_id] = {'state': 'running', 'progress': 0, 'message': 'Запуск…', 'result': None}

    def _run():
        try:
            accounts = eda.load_eda_accounts()
            if names:
                accounts = [a for a in accounts if a.get('name') in names]
            accounts = [a for a in accounts if eda.sp_session_id(a)]
            result = []
            total = max(len(accounts), 1)
            for idx, a in enumerate(accounts):
                acc_progress = {'frac': 0.0, 'msg': ''}

                def _cb(msg, frac, _idx=idx, _a=a, _acc_progress=acc_progress):
                    _acc_progress['frac'] = frac
                    _acc_progress['msg'] = msg
                    pct = int(((_idx + frac) / total) * 100)
                    with _SP_LOCK:
                        t = SP_TASKS[task_id]
                        t['progress'] = pct
                        t['message'] = f'{_a.get("name")}: {msg}'

                try:
                    r = eda.collect_sp_daily(a, claim=claim, progress=_cb)
                except Exception as e:
                    r = {'rewards': [], 'error': str(e)}
                if claim:
                    for rw in r.get('rewards') or []:
                        if rw.get('promocode') or rw.get('error') or rw.get('status'):
                            eda.record_sp_gift(a, rw)
                result.append({'name': a.get('name'), **r})
            with _SP_LOCK:
                SP_TASKS[task_id]['state'] = 'done'
                SP_TASKS[task_id]['progress'] = 100
                SP_TASKS[task_id]['message'] = 'Готово'
                SP_TASKS[task_id]['result'] = result
        except Exception as e:
            with _SP_LOCK:
                SP_TASKS[task_id]['state'] = 'error'
                SP_TASKS[task_id]['message'] = str(e)
                SP_TASKS[task_id]['result'] = None

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({'task_id': task_id})


@app.route('/api/sp/daily/<task_id>', methods=['GET'])
def api_sp_daily_status(task_id):
    with _SP_LOCK:
        t = SP_TASKS.get(task_id)
    if not t:
        return jsonify({'error': 'task not found'}), 404
    return jsonify({'state': t['state'], 'progress': t['progress'],
                    'message': t['message'], 'result': t['result']})


@app.route('/api/sp/gifts', methods=['GET'])
def api_sp_gifts():
    return jsonify(eda.load_sp_gifts())


@app.route('/api/eda/sessions', methods=['GET'])
def api_eda_sessions_list():
    return jsonify(eda.load_eda_sessions())


@app.route('/api/eda/sessions', methods=['POST'])
def api_eda_sessions_create():
    data = request.get_json(silent=True) or {}
    try:
        token = eda.create_eda_session(data.get('name', ''), data.get('account', ''),
                                       int(data.get('hours') or 24))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'token': token,
                    'url': f'/d/{token}'})


@app.route('/api/eda/sessions/<token>', methods=['DELETE'])
def api_eda_sessions_revoke(token):
    eda.revoke_eda_session(token)
    return jsonify({'ok': True})


@app.route('/api/prizes')
def api_prizes():
    account = request.args.get('account')
    prizes = core.list_prizes(account)
    return jsonify(prizes)


@app.route('/api/prizes/stats')
def api_prizes_stats():
    account = request.args.get('account')
    return jsonify(core.prize_stats(account))


# ---------- admin panel (database-style tables) ----------

@app.route('/api/admin/overview')
def api_admin_overview():
    """Сводка для верхней панели: счётчики аккаунтов, призов, купонов, заказов."""
    accs = core.load_accounts()
    prizes = core.prize_stats()
    running = core.runs.running()
    out = {
        'accounts': len(accs),
        'running': len(running),
        'prizes': prizes.get('count', 0),
        'games': prizes.get('games', 0),
    }
    try:
        out['coupons'] = len(core.admin_coupons())
    except Exception:
        out['coupons'] = None
    try:
        import pickup
        out['orders'] = sum(len(pickup.order_history(a.get('name'), limit=50)) for a in accs)
    except Exception:
        out['orders'] = None
    return jsonify(out)


@app.route('/api/admin/accounts')
def api_admin_accounts():
    return jsonify(core.account_rows())


@app.route('/api/admin/purchases')
def api_admin_purchases():
    return jsonify(core.admin_purchases())


@app.route('/api/admin/coupons')
def api_admin_coupons():
    return jsonify(core.admin_coupons())


@app.route('/api/admin/accounts/<name>/coupons')
def api_admin_account_coupons(name):
    accs = core.load_accounts()
    if not any(a.get('name') == name for a in accs):
        return jsonify({'error': 'not found'}), 404
    try:
        import pickup
        cs = pickup.coupons(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    out = []
    for c in cs:
        it = (c.get('items') or [{}])[0]
        out.append({
            'id': c.get('favoriteId'),
            'title': c.get('title') or '',
            'subtitle': c.get('subtitle') or '',
            'code': (it or {}).get('couponCode') or c.get('favoriteId') or '',
            'display_type': c.get('displayType'),
            'discount_value': (it or {}).get('discountValue'),
            'discount_type': (it or {}).get('discountType'),
            'expiration_date': c.get('expirationDate'),
            'image': c.get('smallImageUrl') or c.get('largeImageUrl') or c.get('promoImageUrl') or '',
        })
    return jsonify({'ok': True, 'coupons': out})


# ---------- access sessions (pickup for third parties) ----------

@app.route('/api/sessions', methods=['GET'])
def api_sessions_list():
    return jsonify(core.load_sessions())


@app.route('/api/sessions', methods=['POST'])
def api_sessions_create():
    d = request.get_json(force=True)
    try:
        token = core.create_session(str(d.get('name', '')).strip(),
                                    str(d.get('account', '')).strip(),
                                    int(d.get('hours', 24)))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'token': token,
                    'link': f'http://{request.host}/p/{token}'})


@app.route('/api/sessions/<token>', methods=['DELETE'])
def api_sessions_revoke(token):
    return jsonify({'ok': True, 'revoked': core.revoke_session(token)})


@app.route('/api/coupons/shares', methods=['GET'])
def api_coupon_shares_list():
    shares = core.list_coupon_shares()
    by_account = {}
    for token, s in shares.items():
        by_account.setdefault(s.get('account'), []).append((token, s))
    out = []
    for account, items in by_account.items():
        titles = {}
        try:
            for c in pickup.coupons(account):
                titles[c.get('favoriteId')] = c.get('title') or ''
                for it in (c.get('items') or []):
                    if it.get('couponCode'):
                        titles.setdefault(it['couponCode'], c.get('title') or '')
        except Exception:
            pass
        for token, s in items:
            out.append({
                'token': token,
                'name': s.get('name') or '',
                'account': s.get('account'),
                'coupon_id': s.get('coupon_id'),
                'title': titles.get(s.get('coupon_id')) or '',
                'created_at': s.get('created_at'),
                'expires_at': s.get('expires_at'),
                'active': s.get('active'),
                'link': f'http://{request.host}/c/{token}',
            })
    out.sort(key=lambda x: (x.get('expires_at') or ''), reverse=True)
    return jsonify(out)


@app.route('/api/coupons/shares', methods=['POST'])
def api_coupon_shares_create():
    d = request.get_json(force=True)
    try:
        token = core.create_coupon_share(str(d.get('account', '')).strip(),
                                         str(d.get('coupon_id', '')).strip(),
                                         int(d.get('hours', 24)),
                                         str(d.get('name', '')).strip())
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'token': token,
                    'link': f'http://{request.host}/c/{token}'})


@app.route('/api/coupons/shares/<token>', methods=['DELETE'])
def api_coupon_shares_revoke(token):
    return jsonify({'ok': True, 'revoked': core.revoke_coupon_share(token)})


@app.route('/api/coupons/shares/<token>/data')
def api_coupon_share_data(token):
    s = core.get_coupon_share(token)
    if not s:
        return jsonify({'error': 'Ссылка недействительна или истекла'}), 404
    try:
        coupon = pickup.coupon_by_id(s['account'], s['coupon_id'])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    if not coupon:
        return jsonify({'error': 'Купон не найден на аккаунте'}), 404
    return jsonify({'ok': True, 'share': s, 'coupon': coupon})


@app.route('/c/<token>')
def coupon_page(token):
    s = core.get_coupon_share(token)
    if not s:
        return render_template('coupon.html', invalid=True, token=token), 404
    return render_template('coupon.html', invalid=False, token=token)


@app.route('/api/sessions/detailed')
def api_sessions_detailed():
    """Админ-панель: активные сессии с данными пользователя
    (баланс, купоны, промокоды, активные заказы, история покупок)."""
    sess = core.load_sessions()
    out = []
    for token, s in sess.items():
        if not s.get('active'):
            continue
        item = {
            'token': token,
            'name': s.get('name'),
            'account': s.get('account'),
            'created_at': s.get('created_at'),
            'expires_at': s.get('expires_at'),
            'last_seen': s.get('last_seen'),
            'link': f'http://{request.host}/p/{token}',
        }
        try:
            item['orders_active'] = pickup.active_orders(s['account'])
        except Exception as e:
            item['orders_active'] = None
            item['orders_active_err'] = str(e)
        try:
            item['orders_history'] = pickup.order_history(s['account'])
        except Exception as e:
            item['orders_history'] = None
            item['orders_history_err'] = str(e)
        try:
            item['balance'] = pickup.user_balance(s['account'])
        except Exception as e:
            item['balance'] = {'ok': False, 'error': str(e)}
        try:
            item['promos'] = pickup.express_promos(s['account'])
        except Exception as e:
            item['promos'] = None
            item['promos_err'] = str(e)
        try:
            item['coupons'] = pickup.coupons(s['account'])
        except Exception as e:
            item['coupons'] = None
            item['coupons_err'] = str(e)
        out.append(item)
    return jsonify(out)


def pickup_session(token):
    """Возвращает session dict либо бросает RuntimeError."""
    s = core.get_session(token)
    if not s:
        raise RuntimeError('сессия не найдена, истекла или отозвана')
    core.touch_session(token)
    return s


@app.route('/p/<token>')
def client_page(token):
    if not core.get_session(token):
        return render_template('client.html', invalid=True), 403
    return render_template('client.html', invalid=False)


@app.route('/api/pickup/<token>/info')
def api_pickup_info(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    return jsonify({'name': s['name'], 'account': s['account'],
                    'expires_at': s['expires_at']})


@app.route('/api/pickup/<token>/city')
def api_pickup_city(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'city': pickup.current_city(s['account'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/cities')
def api_pickup_cities(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'cities': pickup.search_cities(
            s['account'], query=request.args.get('query', ''))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/cart')
def api_pickup_cart(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        cart = pickup.cart(s['account'])
        for c in cart.get('carts', []):
            pickup.enrich_cart(s['account'], c)
        return jsonify({'ok': True, 'cart': cart})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/stores')
def api_pickup_stores(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'stores': pickup.search_stores(
            s['account'],
            query=request.args.get('query', ''),
            city_fias_id=request.args.get('city_fias_id'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/store')
def api_pickup_store(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'store': pickup.store_detail(
            s['account'], request.args.get('store_code'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/categories')
def api_pickup_categories(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'categories': pickup.categories(
            s['account'], request.args.get('store_code'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/catalog')
def api_pickup_catalog(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        cat = request.args.get('category_id')
        cids = request.args.get('category_ids')
        cids = [c for c in (cids or '').split(',') if c.isdigit()]
        return jsonify({'ok': True, 'catalog': pickup.goods(
            s['account'], request.args.get('store_code'),
            category_id=int(cat) if cat and cat.isdigit() else None,
            category_ids=cids or None,
            term=request.args.get('term') or None,
            offset=int(request.args.get('offset', 0)),
            sort_type=request.args.get('sort', 'popularity'),
            sort_order=request.args.get('order', 'desc'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/cart', methods=['POST'])
def api_pickup_cart_add(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        d = request.get_json(force=True)
        c = pickup.add_to_cart(s['account'], d.get('store_code'), d.get('items', []))
        if c.get('id'):
            pickup.enrich_cart(s['account'], c)
        return jsonify({'ok': True, 'cart': c})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/cart/item', methods=['DELETE'])
def api_pickup_cart_item_delete(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        d = request.get_json(force=True)
        c = pickup.remove_from_cart(s['account'], d.get('store_code'),
                                    d.get('good_id'), d.get('catalog_price'),
                                    qnty=d.get('qnty', 0), weight_step=d.get('weight_step'))
        if c.get('id'):
            pickup.enrich_cart(s['account'], c)
        return jsonify({'ok': True, 'cart': c})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/checkout')
def api_pickup_checkout(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'checkout': pickup.checkout_info(
            s['account'], request.args.get('cart_id'), request.args.get('store_code'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/promos')
def api_pickup_promos(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'promocodes': pickup.promo_codes(s['account'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/checkout/promo', methods=['POST'])
def api_pickup_checkout_promo(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        d = request.get_json(force=True)
        return jsonify({'ok': True, 'result': pickup.check_promo(
            s['account'], d.get('cart_id'), d.get('store_code'), d.get('promo_code'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/payment/methods')
def api_pickup_payment_methods(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'methods': pickup.payment_methods(s['account'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/payment/bind', methods=['POST'])
def api_pickup_payment_bind(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'bind': pickup.bind_card(s['account'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/order', methods=['POST'])
def api_pickup_order(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        d = request.get_json(force=True)
        return jsonify({'ok': True, 'order': pickup.place_order(
            s['account'],
            d.get('cart_id'),
            d.get('store_code'),
            d.get('from'),
            d.get('to'),
            customer=d.get('customer'),
            payment=d.get('payment', 'StoreOffline'),
            replacement=d.get('replacement', 'REPLACE_GOODS'),
            promo_code=d.get('promo_code'))})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/order/<number>')
def api_pickup_order_info(token, number):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'order': pickup.order_info(s['account'], number)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/orders/active')
def api_pickup_active_orders(token):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'orders': pickup.active_orders(s['account'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/pickup/<token>/order/<number>/cancel', methods=['POST'])
def api_pickup_cancel_order(token, number):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        reason = (request.get_json(silent=True) or {}).get('reason', 'another_reason')
        pickup.cancel_order(s['account'], number, reason)
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/p/<token>/order/<number>')
def api_pickup_order_page(token, number):
    try:
        s = pickup_session(token)
    except RuntimeError as e:
        return render_template('client.html', invalid=True), 403
    try:
        order = pickup.order_info(s['account'], number)
        status = order.get('status', {})
        status_code = status.get('code', 'UNKNOWN')
        status_text = status.get('text', '')
        status_name = status.get('name', '')
        shop = order.get('shop', {})
        di = order.get('deliveryTimeInterval', {})
        items = order.get('items', [])
        summary = order.get('summary', {})
        header = summary.get('header', {})
        spending = summary.get('spending', [])
        discount = 0
        for sp in spending:
            for child in sp.get('children', []):
                if child.get('isSaving'):
                    discount += child.get('value', 0)
        old_total = order.get('oldTotalPrice', header.get('value', 0))
        total = order.get('totalPrice', header.get('value', 0))
        discount_total = order.get('discountTotalPrice', discount)
        pay = order.get('payment', {})
        pay_type = pay.get('type', {}) if pay else {}
        pay_method = pay_type.get('text', 'На кассе')
        pay_badge = pay_type.get('system', 'cash')
        if pay_badge == 'cash':
            pay_badge = '💵'
        elif pay_badge == 'card':
            pay_badge = '💳'
        else:
            pay_badge = '💳'
        if status_code in ('NEW', 'ASSEMBLING', 'ON_ASSEMBLE'):
            stage_state = 'active'
        elif status_code in ('READY', 'WAITING', 'DELIVERED', 'PICKED_UP'):
            stage_state = 'done'
        else:
            stage_state = 'pending'
        stages = [
            {'state': 'done', 'dot': '✓', 'title': 'Принят', 'time': 'Оформлен', 'desc': 'Заказ подтверждён магазином'},
            {'state': 'done' if status_code not in ('NEW','ASSEMBLING','ON_ASSEMBLE') else stage_state, 'dot': '📦', 'title': 'Сборка', 'time': status_name, 'desc': status_text, 'progress': 75 if status_code in ('NEW','ASSEMBLING','ON_ASSEMBLE') else None},
            {'state': 'active' if status_code in ('READY','WAITING') else 'done' if status_code in ('DELIVERED','PICKED_UP') else 'pending', 'dot': '✓', 'title': 'Готов к выдаче', 'time': status_name if status_code in ('READY','WAITING') else 'Ожидается', 'desc': status_text if status_code in ('READY','WAITING') else 'Заказ будет готов в указанном слоте'},
            {'state': 'pending', 'dot': '🤝', 'title': 'Выдан', 'time': 'Ожидается', 'desc': 'Покажите код при получении'},
        ]
        from datetime import datetime
        created_at = ''
        try:
            created_at = datetime.fromisoformat(order.get('createdAt', '')).strftime('%d %b %Y, %H:%M')
        except Exception:
            created_at = order.get('createdAt', '')
        return render_template('order.html',
            order=order,
            order_id=order.get('orderId', number),
            created_at=created_at,
            status_badge='✅ Оплачен' if pay else '⏳ Ожидает',
            status_code=status_code,
            status_text=status_text,
            stages=stages,
            shop_name=shop.get('format', 'Магнит'),
            shop_address=order.get('formattedAddress', ''),
            shop_distance='1.2 км',
            shop_hours='09:00–22:00',
            slot_time=di.get('from', '')[11:16] + ' – ' + (di.get('to', '')[11:16] if di.get('to') else ''),
            slot_date=datetime.fromisoformat(di.get('from', '')[:10]).strftime('%d %B %Y') if di.get('from') else '',
            items_count=len(items),
            items=items,
            formatted_old_total=order.get('formattedOldTotalPrice', ''),
            formatted_discount=order.get('formattedDiscountTotalPrice', ''),
            formatted_total=order.get('formattedTotalPrice', ''),
            discount_total=discount_total,
            pay_method_badge=pay_badge,
            pay_method_label=pay_method,
            pay_status='Оплачено' if pay else 'Ожидает оплаты',
            barcode=order.get('delivery', {}).get('orderBarcode', order.get('delivery', {}).get('pvzCode', '')),
            can_cancel=(order.get('availableActions', {}) or {}).get('canCancelOrder', False),
            token=token,
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- Яндекс Еда: клиент доставки ----------

@app.route('/d/<token>')
def eda_client_page(token):
    s = eda.get_eda_session(token)
    if not s:
        return render_template('eda.html', invalid=True), 403
    return render_template('eda.html', token=token, invalid=False)


def eda_session(token):
    s = eda.get_eda_session(token)
    if not s:
        raise RuntimeError('сессия не найдена, истекла или отозвана')
    eda.touch_eda_session(token)
    return s


@app.route('/api/eda/<token>/info')
def api_eda_info(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    return jsonify({'name': s['name'], 'account': s['account'],
                    'expires_at': s['expires_at']})


@app.route('/api/eda/<token>/profile')
def api_eda_profile(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'profile': eda.profile(s['account'])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/restaurants')
def api_eda_restaurants(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        q = request.args.get('query', '')
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        return jsonify({'ok': True, 'restaurants': eda.search_restaurants(
            s['account'], query=q, lat=lat, lon=lon)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/restaurants/<rid>')
def api_eda_menu(token, rid):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        return jsonify({'ok': True, 'menu': eda.restaurant_menu(
            s['account'], rid, lat=lat, lon=lon)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/layout')
def api_eda_layout(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        slug = request.args.get('slug')
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        view = {'type': 'collection', 'slug': slug} if slug else None
        return jsonify({'ok': True, 'layout': eda.layout(
            s['account'], view=view, lat=lat, lon=lon)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/shop/<slug>/categories')
def api_eda_shop_categories(token, slug):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'categories': eda.shop_categories(
            s['account'], slug)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/shop/<slug>/goods', methods=['POST'])
def api_eda_shop_goods(token, slug):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'goods': eda.shop_goods(
            s['account'], slug, data.get('uids') or [])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/shop/<slug>/category/<uid>')
def api_eda_shop_category(token, slug, uid):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'category': eda.shop_category(
            s['account'], slug, uid)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/shop/<slug>/info')
def api_eda_shop_info(token, slug):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'info': eda.shop_info(s['account'], slug)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/shop/<slug>/search')
def api_eda_shop_search(token, slug):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        q = request.args.get('query', '')
        return jsonify({'ok': True, 'search': eda.shop_search(
            s['account'], slug, q)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/cart')
def api_eda_cart(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        lat = request.args.get('lat', type=float)
        lon = request.args.get('lon', type=float)
        slug = request.args.get('place_slug')
        return jsonify({'ok': True, 'cart': eda.cart(
            s['account'], slug=slug, lat=lat, lon=lon)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/cart', methods=['POST'])
def api_eda_cart_add(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'cart': eda.add_to_cart(
            s['account'],
            data.get('place_slug') or data.get('restaurant_id'),
            data.get('item') or data.get('item_id'),
            qty=int(data.get('qty') or 1),
            item_options=data.get('item_options'),
            lat=data.get('lat'), lon=data.get('lon'),
            business=data.get('business', 'restaurant'))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/addresses')
def api_eda_addresses(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'addresses': eda.addresses(s['account'])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/checkout', methods=['GET', 'POST'])
def api_eda_checkout(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'checkout': eda.checkout(
            s['account'],
            data.get('place_slug'),
            data.get('address', {}),
            lat=data.get('lat'), lon=data.get('lon'))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/payment/methods')
def api_eda_payment_methods(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'methods': eda.payment_methods(s['account'])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/order', methods=['POST'])
def api_eda_order_create(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    data = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'order': eda.create_order(
            s['account'], data.get('address_id'), data.get('payment_id'),
            data.get('items') or [])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/orders/active')
def api_eda_orders_active(token):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'orders': eda.active_orders(s['account'])})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/order/<oid>')
def api_eda_order_info(token, oid):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        return jsonify({'ok': True, 'order': eda.order_status(s['account'], oid)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/eda/<token>/order/<oid>/cancel', methods=['POST'])
def api_eda_order_cancel(token, oid):
    try:
        s = eda_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    try:
        eda.cancel_order(s['account'], oid)
        return jsonify({'ok': True})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------- Самокат: аккаунты и сессии ----------

@app.route('/api/samokat/accounts')
def api_samokat_accounts():
    return jsonify([{'name': a.get('name'),
                     'added': a.get('added'),
                     'user': a.get('user') or {},
                     'token_ok': bool(a.get('access_token')),
                     'expires': a.get('expires', ''),
                     'access_expires': a.get('access_token_expires', 0),
                     'session_token': bool(a.get('session_token'))}
                    for a in samokat.load_samokat_accounts()])


@app.route('/api/samokat/accounts', methods=['POST'])
def api_samokat_accounts_add():
    data = request.get_json(silent=True) or {}
    try:
        samokat.add_samokat_account(data.get('name', ''), data.get('cookies', ''))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True})


@app.route('/api/samokat/accounts/<name>', methods=['DELETE'])
def api_samokat_accounts_delete(name):
    samokat.delete_samokat_account(name)
    return jsonify({'ok': True})


@app.route('/api/samokat/accounts/<name>/refresh', methods=['POST'])
def api_samokat_accounts_refresh(name):
    try:
        acc = samokat.refresh_samokat_account(name)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'expires': acc.get('expires'),
                    'access_expires': acc.get('access_token_expires')})


@app.route('/api/samokat/accounts/<name>/profile')
def api_samokat_profile(name):
    acc = samokat.get_samokat_account(name)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        return jsonify({'ok': True, 'profile': samokat.profile(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/accounts/<name>/addresses')
def api_samokat_addresses(name):
    acc = samokat.get_samokat_account(name)
    if not acc:
        return jsonify({'error': 'not found'}), 404
    try:
        return jsonify({'ok': True, 'addresses': samokat.addresses(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/sessions')
def api_samokat_sessions_list():
    return jsonify(samokat.load_samokat_sessions())


@app.route('/api/samokat/sessions', methods=['POST'])
def api_samokat_sessions_create():
    data = request.get_json(silent=True) or {}
    try:
        token = samokat.create_samokat_session(data.get('name', ''),
                                               data.get('account', ''),
                                               int(data.get('hours', 24)))
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({'ok': True, 'token': token,
                    'link': f'http://{request.host}/s/{token}'})


@app.route('/api/samokat/sessions/<token>', methods=['DELETE'])
def api_samokat_sessions_revoke(token):
    samokat.revoke_samokat_session(token)
    return jsonify({'ok': True})


def samokat_session(token):
    """Возвращает сессию Самоката либо бросает RuntimeError."""
    s = samokat.get_samokat_session(token)
    if not s:
        raise RuntimeError('сессия не найдена, истекла или отозвана')
    samokat.touch_samokat_session(token)
    return s


@app.route('/s/<token>')
def samokat_client_page(token):
    if not samokat.get_samokat_session(token):
        return render_template('samokat.html', token=token, invalid=True), 403
    return render_template('samokat.html', token=token, invalid=False)


@app.route('/api/samokat/<token>/info')
def api_samokat_info(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    return jsonify({'name': s['name'], 'account': s['account'],
                    'expires_at': s['expires_at']})


@app.route('/api/samokat/<token>/profile')
def api_samokat_client_profile(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'profile': samokat.profile(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/addresses')
def api_samokat_client_addresses(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'addresses': samokat.addresses(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/showcases')
def api_samokat_showcases(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'showcases': samokat.showcase_list(acc)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/categories')
def api_samokat_categories(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'categories': samokat.categories(
            acc, request.args.get('showcase_id'))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/catalog')
def api_samokat_catalog(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'goods': samokat.goods(
            acc, request.args.get('showcase_id'),
            category_id=request.args.get('category_id'),
            term=request.args.get('term'))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/cart')
def api_samokat_cart(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'cart': samokat.cart(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/cart/item', methods=['POST'])
def api_samokat_cart_item(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'cart': samokat.set_cart_item(
            acc, d.get('item'), int(d.get('qty', 1)))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/checkout')
def api_samokat_checkout(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'checkout': samokat.checkout_info(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/order', methods=['POST'])
def api_samokat_order(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    d = request.get_json(silent=True) or {}
    try:
        return jsonify({'ok': True, 'order': samokat.place_order(
            acc, d.get('address_id'), slots=d.get('slots'))})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/samokat/<token>/orders')
def api_samokat_orders(token):
    try:
        s = samokat_session(token)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 403
    acc = samokat.get_samokat_account(s['account'])
    try:
        return jsonify({'ok': True, 'orders': samokat.orders(acc)})
    except NotImplementedError as e:
        return jsonify({'error': str(e)}), 501
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '5001'))
    print(f' * Web UI: http://0.0.0.0:{port}')
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
