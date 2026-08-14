import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import mitmproxy.io as mio

SRC = sys.argv[1] if len(sys.argv) > 1 else r'D:\gfe\flows_eda.mitm'
MAX_BODY = 200000

KEYS = ('/api/v1/orders', '/api/v2/cart', '/cart/', '/go-checkout', '/promocode',
        'eats-payments', 'trust.yandex', '/checkout', '/order/tracking',
        'payment-methods', '/api/v2/order', '/createOrder')


def redact_headers(h):
    out = {}
    for k, v in h.items():
        kl = k.lower()
        if kl == 'authorization':
            out[k] = v[:40] + '…' if v else v
        elif kl == 'cookie':
            out[k] = 'REDACTED'
        else:
            out[k] = v
    return out


def main():
    f = mio.FlowReader(io.BytesIO(open(SRC, 'rb').read()))
    total = 0
    for fl in f.stream():
        total += 1
        try:
            req = fl.request
            path = req.path
        except Exception:
            continue
        if not any(k.lower() in path.lower() for k in KEYS):
            continue
        host = ''
        try:
            host = req.host or ''
        except Exception:
            pass
        print('=' * 100)
        print('REQ', req.method, host, path)
        print('-- headers:')
        for k, v in sorted(redact_headers(req.headers).items()):
            print('   %s: %s' % (k, v[:300]))
        body = req.get_text() if req.content else ''
        if body:
            print('-- body (%d chars):' % len(body))
            print(body[:MAX_BODY])
        try:
            resp = fl.response
            print('-- RESP %s %s' % (getattr(resp, 'status_code', '?'), getattr(resp, 'reason', '')))
            rb = resp.get_text() if resp.content else ''
            if rb:
                print('-- resp body (%d chars):' % len(rb))
                print(rb[:MAX_BODY])
        except Exception as e:
            print('-- no resp:', e)
    print('=' * 100)
    print('TOTAL flows:', total)


if __name__ == '__main__':
    main()
