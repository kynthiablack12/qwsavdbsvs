import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import base64, json

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

vals = set()
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request:
        v = f.request.headers.get('X-Telemetry', '')
        if v:
            vals.add(v)

for v in list(vals)[:3]:
    print('LEN', len(v))
    pad = v + '=' * (-len(v) % 4)
    raw = base64.urlsafe_b64decode(pad.encode())
    print('decoded bytes:', len(raw))
    print('hex head:', raw[:32].hex())
    print('ascii head:', raw[:64])
    print()

# try to see if it splits into signature(64)+payload
for v in list(vals)[:1]:
    pad = v + '=' * (-len(v) % 4)
    raw = base64.urlsafe_b64decode(pad.encode())
    print('last 64 bytes ascii:', raw[-64:])
    print('payload attempt JSON:', raw[-128:])
