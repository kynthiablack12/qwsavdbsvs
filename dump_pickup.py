import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

import io as _io
flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
_out = open(r'D:\gfe\dump_pickup.txt', 'w', encoding='utf-8')
def print(*a, **k):
    _out.write(' '.join(str(x) for x in a) + '\n')

WANT = ('/v2/cities', '/v1/stores-facade/search', '/v1/stores-facade/store',
        '/v2/goods/search', '/v1/carts', '/v2/carts/lite',
        '/v1/checkout/preview', '/v1/checkout/', '/v3/categories/store',
        '/v2/orders/info', '/v2/suggestions', '/v1/stores-facade/store-type-groups')
seen = set()
for f in flows:
    if not (isinstance(f, http.HTTPFlow) and f.request and 'middle-api.magnit.ru' in f.request.host):
        continue
    p = f.request.path.split('?')[0]
    if not any(w in p for w in WANT):
        continue
    key = (f.request.method, f.request.path.split('&')[0][:130])
    if key in seen:
        continue
    seen.add(key)
    print('=' * 100)
    print('###', f.request.method, f.request.path[:260])
    print('-- headers:')
    for k, v in f.request.headers.items():
        if k.lower() in ('authorization', 'x-device-id', 'x-device-tag', 'content-type'):
            print('    ', k, ':', (v[:60] + '...') if len(v) > 60 else v)
    if f.request.method in ('POST', 'PUT', 'PATCH'):
        b = f.request.get_text() or ''
        print('-- body:', b[:1500])
    print('-- status:', f.response.status_code if f.response else None)
    if f.response:
        t = f.response.get_text() or ''
        print('-- response:', t[:2500])
