import sys, json
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

# full detail of the barcode coupon
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and f.request.method == 'POST' and f.request.path == '/v3/user/coupons' and f.response and f.response.status_code == 200:
        try:
            d = json.loads(f.response.get_text())
        except Exception:
            continue
        print('COUPON DETAIL (barcode):', json.dumps(d, ensure_ascii=False, indent=1))
        print('===')
        break

# the coupons list entries for game category wX8CoYBu0OQzsA6DBwqlU
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and '/coupons/list' in f.request.path and f.response and f.response.status_code == 200:
        try:
            d = json.loads(f.response.get_text())
        except Exception:
            continue
        for c in d.get('coupons', []):
            if c.get('category') == 'wX8CoYBu0OQzsA6DBwqlU':
                print('GAME COUPON in list:', json.dumps(c, ensure_ascii=False, indent=1))
                print('---')

# look at game reward responses for is_barcode
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'rewards' in f.request.path and f.response and f.response.status_code == 200:
        t = f.response.get_text()
        if 'barcode' in t or 'current' in t:
            print('REWARDS RESP url:', f.request.url)
            print(t[:1500])
            print('---')
