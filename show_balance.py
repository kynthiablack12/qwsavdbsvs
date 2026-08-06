import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.response and f.response.status_code == 200:
        if '/v2/user/balance' in f.request.path:
            print('=== BALANCE:', f.request.url[:120])
            print(f.response.get_text()[:2000])
        if '/promoter-v2/v1/offers' in f.request.path:
            print('=== OFFERS:', f.request.url[:120])
            t = f.response.get_text()
            print(t[:3000])
