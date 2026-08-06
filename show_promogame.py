import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

def safe(f):
    try:
        return f.get_text() or ''
    except Exception:
        return ''

for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request:
        if 'promo-games/wX8CoYBu0OQzsA6DBwqlU/mobile' in f.request.path:
            print('======= promo-games flow =======')
            print('REQ URL:', f.request.url)
            for k in ('authorization', 'x-device-id', 'x-device-tag', 'x-app-version'):
                if k in f.request.headers:
                    print('  ', k, ':', f.request.headers.get(k))
            print('REQ BODY:', safe(f.request))
            print('RESP:', f.response.status_code if f.response else '?')
            print(safe(f.response)[:3000])
        if 'magnit-prizoleto.ru' == f.request.pretty_host and f.request.path.startswith('/?token='):
            print('======= game entry flow =======')
            print('REQ URL:', f.request.url[:250])
            print('RESP:', f.response.status_code if f.response else '?')
