import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import datetime

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

targets = ('/v1/auth/otp', '/v1/auth/otp/check', '/v1/profile/register/magnit-id-code', '/v1/auth/token')
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'id.magnit.ru' == f.request.pretty_host and any(f.request.path == t for t in targets):
        t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
        print('=' * 25)
        print(t, f.request.method, f.request.path, '->', f.response.status_code if f.response else '?')
        for k in ('authorization', 'x-request-sign', 'X-Telemetry'):
            if k in f.request.headers:
                print('  ', k, ':', f.request.headers.get(k)[:80])
        print('  REQ:', f.request.get_text()[:250])
        print('  RESP:', (f.response.get_text() or '')[:350] if f.response else '')
