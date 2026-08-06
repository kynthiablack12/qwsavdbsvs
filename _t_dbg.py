import sys
from mitmproxy import io, http

inf = r"D:\gfe\flows_pay.mitm"
want = ['getOrderParametersFront', 'paymentByCard', 'finish3dsMethodFront', 'sessionIdWeb', '/v2/payment-methods']
reader = io.FlowReader(open(inf, "rb"))
for fl in reader.stream():
    if not isinstance(fl, http.HTTPFlow) or not fl.request:
        continue
    host = (fl.request.pretty_host or "").lower()
    p = fl.request.path
    if host not in ("payecom.ru", "platiecom.ru", "middle-api.magnit.ru"):
        continue
    if not any(w in p for w in want):
        continue
    print("=" * 90)
    print(f"{fl.request.method} {host}{p[:120]}")
    print("--- REQ ---")
    if fl.request.content:
        print((fl.request.get_text(strict=False) or '')[:4000])
    if fl.response:
        print(f"--- RESP {fl.response.status_code} (ct={fl.response.headers.get('content-type','')[:40]}) ---")
        b = fl.response.get_text(strict=False)
        print((b or '')[:4000])
    print()
