import requests, sys, json, argparse, os
sys.stdout.reconfigure(encoding='utf-8')

CONFIG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.json')

s = requests.Session()


def dev_headers(acc):
    return {
        'x-device-id': acc['device_id'],
        'x-device-tag': acc['device_tag'],
        'x-app-version': '8.114.0',
        'x-platform-version': '28',
        'x-device-platform': 'Android',
        'User-Agent': 'okhttp/5.1.0',
    }


def refresh_magnit_token(acc):
    r = s.post('https://id.magnit.ru/v1/auth/token/refresh',
               headers={**dev_headers(acc), 'Content-Type': 'application/json; charset=UTF-8'},
               data=json.dumps({'aud': 'loyalty-mobile', 'refreshToken': acc['refresh_token']}), timeout=15)
    r.raise_for_status()
    return r.json()['accessToken']


def get_game_token(acc, magnit_token):
    r = s.get(f'https://middle-api.magnit.ru/v1/promo-games/{acc["event_id"]}/mobile',
              headers={**dev_headers(acc), 'Authorization': 'bearer ' + magnit_token}, timeout=15)
    r.raise_for_status()
    return r.json()['url'].split('token=')[1]


def login_game(rs256_token):
    r = s.post('https://magnit-prizoleto.ru/api/v1/auth/login',
               headers={'Content-Type': 'application/json', 'User-Agent': 'okhttp/5.1.0'},
               data=json.dumps({'token': rs256_token}), timeout=15)
    r.raise_for_status()
    return r.json()


def game_headers(hs256_token, external_id):
    return {
        'Authorization': 'Bearer ' + hs256_token,
        'Cookie': f'External={external_id}; token_{external_id}={hs256_token}',
        'User-Agent': 'Mozilla/5.0 (Linux; Android 9) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36',
    }


def start_game(h, level=1):
    r = s.post('https://magnit-prizoleto.ru/api/v1/game', headers=h,
               data=json.dumps({'level': level}), timeout=15)
    r.raise_for_status()
    return r.json()


def finish_game(h, game_id, turns=1, victory=True, duration='00:00:05'):
    body = {"duration": duration, "turns_count": turns,
            "lines_used": 0, "multipliers_used": 0, "blasts_used": 0,
            "is_victory": victory, "lose_reason": 1}
    r = s.put(f'https://magnit-prizoleto.ru/api/v1/game/{game_id}:finish',
              headers={**h, 'Content-Type': 'application/json'},
              data=json.dumps(body), timeout=15)
    r.raise_for_status()
    return r.json()


def pick_reward(h, reward_id):
    r = s.put(f'https://magnit-prizoleto.ru/api/v1/game/rewards/{reward_id}:choice',
              headers=h, data='', timeout=15)
    return r.status_code


def play_one(acc, max_games=None):
    name = acc.get('name', '?')
    print(f'=== Account: {name} ===')
    at = refresh_magnit_token(acc)
    print('1. magnit token OK')
    rs = get_game_token(acc, at)
    login = login_game(rs)
    gt = login['token']
    ext = login['external_id']
    h = game_headers(gt, ext)

    prof = s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=15).json()
    attempts = prof.get('attempts', {}).get('total_count', 0)
    print('   attempts:', attempts)

    level = prof.get('last_finished_map_level', 0) + 1
    games = 0
    while attempts > 0 and (max_games is None or games < max_games):
        try:
            game = start_game(h, level)
        except Exception as e:
            print('   start game error:', e)
            break
        gid = game['id']
        ld = json.loads(game['level_data'])
        target = ld.get('targetScore')
        rows, cols = ld['grid']['rows'], ld['grid']['cols']
        print(f'   game {gid}: board {cols}x{rows} target {target}, boosters {game.get("boosters")}')

        fin = finish_game(h, gid, turns=1, victory=True)
        print('   finish ->', fin.get('attempt_type'))
        for p in fin.get('rewards_preview', {}).get('current', []):
            st = pick_reward(h, p['id'])
            print('   reward', p['id'], p.get('info', {}).get('name', '')[:40], '->', st)
            if fin.get('attempt_type') == 'conditional':
                level += 1
        attempts -= 1
        games += 1

    prof2 = s.get('https://magnit-prizoleto.ru/api/v1/profile', headers=h, timeout=15).json()
    print('   remaining attempts:', prof2.get('attempts', {}).get('total_count'),
          '| last level:', prof2.get('last_finished_map_level'))
    return games


def main():
    ap = argparse.ArgumentParser(description='Magnit Prizoleto autoplay')
    ap.add_argument('--account', help='name from accounts.json (default: all)')
    ap.add_argument('--games', type=int, help='max games per account')
    args = ap.parse_args()

    with open(CONFIG, encoding='utf-8') as f:
        cfg = json.load(f)
    accs = cfg['accounts']
    if args.account:
        accs = [a for a in accs if a.get('name') == args.account]
        if not accs:
            print(f'account "{args.account}" not found')
            sys.exit(1)

    total = 0
    for acc in accs:
        total += play_one(acc, max_games=args.games)
    print('Done. total games played:', total)


if __name__ == '__main__':
    main()
