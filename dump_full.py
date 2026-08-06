import sys, io as _io, json
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
_out = open(r'D:\gfe\full_payloads.txt', 'w', encoding='utf-8')
def print(*a, **k):
    _out.write(' '.join(str(x) for x in a) + '\n')

def show(f, label):
    if not f or f.response is None:
        return
    t = f.response.get_text() or ''
    if not t.strip():
        return
    try:
        j = json.loads(t)
        print('=' * 100)
        print('### %s  [%s %s]' % (label, f.request.method, f.request.path[:120]))
        print(json.dumps(j, ensure_ascii=False, indent=1)[:20000])
    except Exception:
        pass

last = {}
for f in flows:
    if not (isinstance(f, http.HTTPFlow) and f.request and 'middle-api.magnit.ru' in f.request.host):
        continue
    p = f.request.path.split('?')[0]
    if p in ('/v1/checkout/preview', '/v2/orders/info'):
        last[p] = f
    elif p.startswith('/v1/checkout/') and not p.endswith('/order') and f.request.method == 'GET':
        last['checkout_single'] = f
    elif p == '/v2/goods/search':
        last['goods_cat'] = f
    elif p == '/v3/categories/store/558713':
        last['cats'] = f

show(last.get('goods_cat'), 'GOODS SEARCH (category)')
show(last.get('cats'), 'CATEGORIES')
show(last.get('checkout_single'), 'CHECKOUT SINGLE (GET /v1/checkout/{id})')
show(last.get('/v1/checkout/preview'), 'CHECKOUT PREVIEW')
show(last.get('/v2/orders/info'), 'ORDER INFO')
