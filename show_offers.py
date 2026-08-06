import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.response and f.response.status_code == 200:
        p = f.request.path
        if 'promoter' in p or 'promotion' in p or 'offer' in p or 'balance' in p:
            print('===', f.request.method, p[:120])
            t = f.response.get_text()
            print(t[:2500])
            print()
