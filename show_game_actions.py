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
    if isinstance(f, http.HTTPFlow) and f.request and f.request.pretty_host == 'magnit-prizoleto.ru':
        p = f.request.path
        if any(k in p for k in ('finish', 'choice', 'reward', 'activate', 'take', 'collect', 'claim', 'daily')):
            t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
            st = f.response.status_code if f.response else '?'
            print('=' * 30)
            print(t, f.request.method, f.request.url[:110], '->', st)
            print('REQ:', safe(f.request)[:400])
            print('RESP:', safe(f.response)[:800])
