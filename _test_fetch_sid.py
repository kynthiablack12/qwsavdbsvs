"""Test fetch_session_id for all accounts."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
import eda

accs = eda.load_eda_accounts()
for a in accs:
    name = a.get('name', '?')
    sid = (a.get('session_id') or '').strip()
    bearer = eda._extract_bearer(a)
    print(f'\n=== {name} ===')
    print(f'  has session_id: {bool(sid)}')
    print(f'  has bearer: {bool(bearer)}')
    if not sid and bearer:
        ok = eda.fetch_session_id(a)
        print(f'  fetch_session_id: {ok}')
        sid2 = (a.get('session_id') or '').strip()
        print(f'  new session_id: {sid2[:60] if sid2 else "NONE"}')
    elif sid:
        print(f'  already has: {sid[:60]}')
    else:
        print('  SKIP: no bearer')
