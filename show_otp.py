import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'id.magnit.ru' == f.request.pretty_host and f.request.path == '/v1/auth/otp':
        print('STATUS:', f.response.status_code if f.response else '?')
        print('--- HEADERS ---')
        for k, v in f.request.headers.items():
            print(' ', k, ':', v)
        print('--- BODY ---')
        print(repr(f.request.get_text()))
        print('--- RESP ---')
        print((f.response.get_text() or '')[:500] if f.response else '')
        print('======')
