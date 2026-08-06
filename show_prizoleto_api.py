import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import datetime

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

def safe(f):
    try:
        return f.get_text() or ''
    except Exception:
        return ''

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'magnit-prizoleto.ru' == f.request.pretty_host and f.request.path.startswith('/api/'):
        t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
        st = f.response.status_code if f.response else '?'
        print('=' * 30)
        print(t, f.request.method, f.request.url[:110], '->', st)
        print('--- REQUEST BODY ---')
        print(safe(f.request)[:800])
        print('--- REQUEST COOKIES ---')
        for k, v in f.request.cookies.items():
            print('  ', k, '=', v)
        print('--- REQUEST AUTH HEADERS ---')
        for k in ('authorization', 'x-token', 'token', 'x-auth', 'cookie'):
            if k in f.request.headers:
                print('  ', k, ':', f.request.headers.get(k)[:200])
        print('--- RESPONSE BODY ---')
        print(safe(f.response)[:1500])
