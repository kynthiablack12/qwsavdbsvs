import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import datetime

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

print('=== promokod.magnit.ru / webevent hosts ===')
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request:
        h = f.request.pretty_host
        if 'promokod' in h or 'webevent' in h or 'game' in h.lower() and 'magnit' in h:
            t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
            st = f.response.status_code if f.response else '?'
            print(t, f.request.method, h, f.request.path[:90], '->', st)

print()
print('=== playlist endpoint (tenant) ===')
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and '/playlist' in f.request.path and f.response and f.response.status_code == 200:
        print('URL:', f.request.url[:100])
        try:
            print((f.response.get_text() or '')[:1500])
        except Exception as e:
            print('err', e)
        print('----')
