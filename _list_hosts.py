import sys, collections
from mitmproxy import io, http

inf = r"D:\gfe\flows.mitm"
hosts = collections.Counter()
sample = {}
reader = io.FlowReader(open(inf, "rb"))
for fl in reader.stream():
    if not isinstance(fl, http.HTTPFlow) or not fl.request:
        continue
    host = (fl.request.pretty_host or "").lower()
    hosts[host] += 1
    if host not in sample:
        sample[host] = f"{fl.request.method} {fl.request.path}"[:160]
for h, n in hosts.most_common(120):
    print(f"{n:6d}  {h:45s} {sample[h]}")
