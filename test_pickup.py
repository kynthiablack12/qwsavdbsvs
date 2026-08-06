import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pickup

acc = 'aleksey'

try:
    c = pickup.current_city(acc)
    print('CITY:', json.dumps(c, ensure_ascii=False)[:200])
except Exception as e:
    print('CITY ERR:', e)

try:
    s = pickup.search_stores(acc, query='омск мира')
    print('STORES total:', s['totalCount'])
    for st in s['data'][:5]:
        print('   ', st['code'], st['name'], '|', st['address'], '|', st['hours'])
except Exception as e:
    print('STORES ERR:', e)
