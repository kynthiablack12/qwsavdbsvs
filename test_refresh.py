import json, urllib.request, urllib.error

BASE = "https://id.magnit.ru/v1/auth/token"
REFRESH = "3343705e-41cb-4df3-997b-81a5c4c3ce1f"

def post(payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE, data=data, method="POST",
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "x-app-version": "8.114.0",
            "x-device-id": "fe53fb8c-79eb-3f35-876b-5beadded889b",
            "x-device-platform": "Android",
            "x-platform-version": "28",
            "user-agent": "Dalvik/2.1.0 (Linux; U; Android 9; SM-S906N Build/PQ3A.190605.09261140)",
            "x-device-tag": "8AA04F8C-3C01-4F11-A0E5-35221DD407CF_L!3E5CB4F7-61A8-4628-8A63-F8CE3E6A7222",
            "Accept": "application/json",
        })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()[:500].decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:500].decode(errors="replace")
    except Exception as e:
        return "ERR", str(e)

tests = [
    ("refreshToken only", {"aud": "loyalty-mobile", "refreshToken": REFRESH}),
    ("refreshToken only, no aud", {"refreshToken": REFRESH}),
    ("grant_type refresh", {"grant_type": "refresh_token", "refresh_token": REFRESH}),
    ("type=refresh", {"type": "refresh", "refreshToken": REFRESH}),
    ("aud refresh grant", {"aud": "loyalty-mobile", "grant_type": "refresh_token", "refresh_token": REFRESH}),
]
for name, payload in tests:
    print(name, "->", post(payload))
