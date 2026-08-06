import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import datetime

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
n = 0
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.request.pretty_host == 'id.magnit.ru':
        t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
        st = f.response.status_code if f.response else '?'
        print(t, f.request.method, f.request.path[:80], '->', st)
        n += 1
print('total id.magnit.ru flows:', n)
