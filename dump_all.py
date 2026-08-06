import sys, io as _io, json
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
_out = open(r'D:\gfe\dump_all.txt', 'w', encoding='utf-8')
def print(*a, **k):
    _out.write(' '.join(str(x) for x in a) + '\n')

WANT = ('/v2/cities', '/v1/cities', '/stores-facade', '/v2/carts/lite', '/v1/carts',
        '/v1/checkout', '/v2/goods/search', '/v3/categories', '/v2/orders',
        '/v2/suggestions', '/v2/configs/mainpage')
n = 0
for f in flows:
    if not (isinstance(f, http.HTTPFlow) and f.request and 'middle-api.magnit.ru' in f.request.host):
        continue
    p = f.request.path.split('?')[0]
    if not any(w in p for w in WANT):
        continue
    n += 1
    print('#' * 110)
    print('### %s %s' % (f.request.method, f.request.path[:300]))
    b = f.request.get_text() or ''
    if b.strip():
        try:
            print('-- body:', json.dumps(json.loads(b), ensure_ascii=False)[:1200])
        except Exception:
            print('-- body:', b[:1200])
    if f.response is None:
        print('-- NO RESPONSE')
        continue
    print('-- status:', f.response.status_code)
    t = f.response.get_text() or ''
    if t.strip():
        try:
            print('-- resp:', json.dumps(json.loads(t), ensure_ascii=False)[:1200])
        except Exception:
            print('-- resp:', t[:1200])
    else:
        print('-- resp: <empty>')
print('TOTAL_FLOWS:', n)
