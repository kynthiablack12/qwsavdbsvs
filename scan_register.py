import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import datetime, re

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

print('=== register/magnit-id-code responses ===')
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'register/magnit-id-code' in f.request.path and f.response:
        t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
        print(t, f.request.method, f.request.path, '->', f.response.status_code)
        try:
            print('  BODY:', (f.response.get_text() or '')[:600])
        except Exception as e:
            print('  BODY err', e)

print()
print('=== otp/check responses ===')
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'otp/check' in f.request.path and f.response:
        t = datetime.datetime.fromtimestamp(f.request.timestamp_start).strftime('%H:%M:%S')
        print(t, '->', f.response.status_code)
        try:
            print('  BODY:', (f.response.get_text() or '')[:600])
        except Exception as e:
            print('  BODY err', e)

print()
print('=== X-Telemetry uniqueness ===')
vals = set()
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request:
        v = f.request.headers.get('X-Telemetry', '')
        if v:
            vals.add(v)
print('unique X-Telemetry values:', len(vals))
for v in vals:
    print('  len', len(v), 'start', v[:40])
