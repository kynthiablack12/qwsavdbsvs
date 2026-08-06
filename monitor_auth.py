import time
from mitmproxy import io, http

seen = set()
while True:
    try:
        flows = list(io.FlowReader(open(r"D:\gfe\flows.mitm", "rb")).stream())
    except Exception as e:
        print("read err", e); time.sleep(5); continue
    for f in flows:
        if isinstance(f, http.HTTPFlow) and f.request:
            key = (f.request.method, f.request.pretty_host + f.request.path)
            if key[1].startswith("id.magnit.ru/v1/auth/") and key not in seen:
                seen.add(key)
                print("AUTH FLOW:", key[0], key[1])
                for k, v in f.request.headers.items():
                    print("   ", k, "=", v)
                if f.request.content:
                    print("   BODY:", f.request.get_text()[:800])
                if f.response:
                    print("   STATUS:", f.response.status_code)
                    if f.response.content:
                        print("   RESP:", f.response.get_text()[:800])
    time.sleep(4)
