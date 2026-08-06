import sys, json, urllib.request, time
sys.stdout.reconfigure(encoding='utf-8')

tok = '986d0be8071548e287c992e5d992cad394465145'

def call(method, p, body=None, timeout=30):
    t0 = time.time()
    req = urllib.request.Request('http://127.0.0.1:5001' + p, method=method,
                                 data=json.dumps(body).encode('utf-8') if body is not None else None,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = r.read().decode('utf-8')
        print('%.1fs' % (time.time()-t0), p[:110], '->', len(d), 'bytes')
        return json.loads(d)
    except Exception as e:
        print('%.1fs' % (time.time()-t0), p[:110], '-> ERR', str(e)[:160])
        return None

city = call('GET', '/api/pickup/%s/city' % tok)
if city:
    print('city:', json.dumps(city['city'], ensure_ascii=False)[:200])
    fias = city['city'].get('cityFiasId')
    stores = call('GET', '/api/pickup/%s/stores?city_fias_id=%s' % (tok, fias))
    if stores:
        st = stores['stores'].get('data') or []
        print('stores count:', len(st))
        if st:
            print('  first:', st[0]['code'], st[0]['name'])
            call('GET', '/api/pickup/%s/categories?store_code=%s' % (tok, st[0]['code']))
cart = call('GET', '/api/pickup/%s/cart' % tok)
if cart:
    c = cart['cart']['carts'][0]
    print('cart items:', [(i['goodId'], i['qnty']) for i in c.get('items', [])])
