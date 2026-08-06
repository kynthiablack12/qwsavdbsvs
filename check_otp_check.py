import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')

DEV_H = {
    'x-device-id': 'fe53fb8c-79eb-3f35-876b-5beadded889b',
    'x-device-tag': '8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222',
    'x-app-version': '8.114.0',
    'x-platform-version': '28',
    'x-device-platform': 'Android',
    'User-Agent': 'Dalvik/2.1.0 (Linux; U; Android 9; SM-S906N Build/PQ3A.190605.09261140)',
    'Content-Type': 'application/json; charset=UTF-8',
}

# смотрим формат otp/check из перехвата
import io as mio
from mitmproxy import io as mitmio
flows = list(mitmio.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())
for f in flows:
    if isinstance(f, requests.models.Response):
        pass
from mitmproxy import http
for f in flows:
    if isinstance(f, http.HTTPFlow) and f.request and 'otp/check' in f.request.path:
        print('otp/check REQ:', f.request.get_text())
        print('otp/check RESP:', (f.response.get_text() or '')[:400])
        break
