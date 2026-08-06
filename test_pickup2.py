import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pickup

acc = 'aleksey'
code = '558713'

try:
    cats = pickup.categories(acc, code)
    print('CATS:', len(cats))
    for c in cats[:8]:
        print('   ', c['id'], c['path'])
except Exception as e:
    print('CATS ERR:', e)

try:
    g = pickup.goods(acc, code, category_id=116168)
    print('GOODS cat116168:', g['total_count'], 'items:', len(g['items']))
    for it in g['items'][:4]:
        print('   ', it['id'], it['price'], '|', it['name'][:50], '|', it['image'][:60] if it['image'] else None)
except Exception as e:
    print('GOODS ERR:', e)

try:
    g2 = pickup.goods(acc, code, term='молоко')
    print('GOODS term "молоко":', g2['total_count'], 'items:', len(g2['items']))
    for it in g2['items'][:4]:
        print('   ', it['id'], it['price'], '|', it['name'][:50])
except Exception as e:
    print('GOODS TERM ERR:', e)
