import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'token/refresh' in f.request.path and f.response:
        print('URL:', f.request.url)
        print('METHOD:', f.request.method)
        print('--- REQUEST HEADERS ---')
        for k, v in f.request.headers.items():
            print(' ', k, ':', v)
        print('--- REQUEST BODY ---')
        print(f.request.get_text())
        print('--- RESPONSE STATUS ---')
        print(f.response.status_code)
        print('--- RESPONSE BODY ---')
        print(f.response.get_text()[:1500])
