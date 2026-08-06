import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pickup

acc = 'aleksey'
code = '558713'

g = pickup.goods(acc, code, category_id=116168)
items = [{'good_id': it['id'], 'qnty': 1, 'catalog_price': it['price']} for it in g['items'][:2]]
print('adding', items)

cart = pickup.add_to_cart(acc, code, items)
cart_id = cart.get('id')
print('CART ID:', cart_id, 'count:', cart.get('totalGoodsCount'), 'price:', cart.get('totalFinalPrice'))

info = pickup.checkout_info(acc, cart_id, code)
avail = info['orderTimeslot']['available']
print('TIMESLOTS:', len(avail), 'first:', avail[0]['interval'])
sl = avail[0]['interval']
print('PAYMENT:', [(p['id'], p['title']) for p in info['paymentMethods']['available']])
print('CUSTOMER:', info['customer'])
print('SUMMARY:', info['summary']['totalFinalPrice'], info['summary']['itemsCount'])

print('placing order for', sl)
res = pickup.place_order(acc, cart_id, code, sl['from'], sl['to'],
                         customer={'email': info['customer']['email'], 'phone': info['customer']['phone']})
print('ORDER:', json.dumps(res, ensure_ascii=False))

num = res.get('orderNumber')
if num:
    oi = pickup.order_info(acc, num)
    print('ORDER INFO:', oi.get('orderNumber'), oi.get('pvzCode'), oi.get('formattedTotalPrice'), oi.get('status'))
    for it in (oi.get('items') or [])[:3]:
        print('   -', it.get('formattedQuantity'), it.get('name', '')[:40], it.get('formattedPricePosition'))
