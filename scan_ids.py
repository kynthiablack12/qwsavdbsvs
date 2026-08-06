import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import re

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
seen = set()
for f in flows:
    if not isinstance(f, http.HTTPFlow) or not f.request:
        continue
    def safe_text(m):
        try:
            return m.get_text() or ''
        except Exception:
            return ''
    pairs = [(safe_text(f.request), 'REQ')]
    if f.response:
        pairs.append((safe_text(f.response), 'RESP'))
    for text, kind in pairs:
        for m in re.findall(r'magnitIdCode["\s:]+([0-9a-fA-F-]{36})', text):
            key = (kind, m, f.request.url)
            if key not in seen:
                seen.add(key)
                print(kind, m, f.request.method, f.request.url[:90])
        for m in re.findall(r'refreshToken["\s:]+([0-9a-fA-F-]{36})', text):
            key = ('RT', m, f.request.url)
            if key not in seen:
                seen.add(key)
                print('RT ', m, f.request.method, f.request.url[:90])
print('---')
print('total unique', len(seen))
