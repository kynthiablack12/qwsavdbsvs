import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'coupons' in f.request.path and f.response and f.response.status_code == 200:
        try:
            t = f.response.get_text()
        except Exception:
            continue
        print('URL:', f.request.url[:130])
        print('REQ auth:', f.request.headers.get('authorization', '')[:50])
        print((t or '')[:2500])
        print('=' * 60)
