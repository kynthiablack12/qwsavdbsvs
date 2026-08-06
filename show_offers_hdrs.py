import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.request.path.startswith('/promoter-v2/v1/main'):
        print('=== MAIN REQUEST')
        for k, v in f.request.headers.items():
            if k.lower() in ('authorization', 'x-device-id', 'x-device-tag', 'x-sa-token', 'x-cfids', 'x-app-version', 'x-platform-version', 'x-device-platform'):
                print('  ', k, ':', v[:120])
        print('  URL:', f.request.url)
        break

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.request.path.startswith('/v2/user/balance'):
        print('=== BALANCE REQUEST')
        for k, v in f.request.headers.items():
            if k.lower() in ('authorization', 'x-device-id', 'x-device-tag', 'x-sa-token', 'x-cfids'):
                print('  ', k, ':', v[:120])
        print('  URL:', f.request.url)
        break
