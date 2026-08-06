import sys, io as _io
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
_out = open(r'D:\gfe\headers_dump.txt', 'w', encoding='utf-8')
def print(*a, **k):
    _out.write(' '.join(str(x) for x in a) + '\n')

WANT = ('/v1/checkout', '/v2/carts/lite', '/v2/goods/search', '/v3/categories',
        '/stores-facade', '/v1/carts', '/v2/orders')
seen = set()
for f in flows:
    if not (isinstance(f, http.HTTPFlow) and f.request and 'middle-api.magnit.ru' in f.request.host):
        continue
    p = f.request.path.split('?')[0]
    if not any(w in p for w in WANT):
        continue
    key = (f.request.method, p[:120])
    if key in seen:
        continue
    seen.add(key)
    print('###', f.request.method, f.request.path[:130])
    for k, v in f.request.headers.items():
        print('   ', k, ':', v[:90])
