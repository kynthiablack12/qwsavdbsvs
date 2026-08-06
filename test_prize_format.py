import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import core

accs = core.load_accounts()
acc = [a for a in accs if a.get('name') == 'aleksey'][0]
at = core.refresh_magnit_token(acc)
rs = core.get_game_token(acc, at)
login = core.login_game(rs)
h = core.game_headers(login['token'], login['external_id'])
prof = core.s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=20).json()
print('attempts:', prof.get('attempts'), 'level:', prof.get('last_finished_map_level'))
if prof.get('attempts', {}).get('total_count', 0) > 0:
    game = core.start_game(h, prof.get('last_finished_map_level', 0) + 1)
    print('game id:', game['id'])
    fin = core.finish_game(h, game['id'])
    print(json.dumps(fin, ensure_ascii=False, indent=1))
else:
    print('no attempts to test with')
