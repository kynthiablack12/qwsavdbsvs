import json, urllib.request, ssl
from mitmproxy import io, http

# --- pull real headers from a captured middle-api request ---
flows = list(io.FlowReader(open(r"D:\gfe\flows.mitm", "rb")).stream())
tmpl = None
for f in flows:
    if (isinstance(f, http.HTTPFlow) and f.request
            and f.request.pretty_host == "middle-api.magnit.ru"
            and f.request.headers.get("authorization", "").lower().startswith("bearer")
            and "X-Telemetry" in f.request.headers):
        tmpl = f.request
        break
if not tmpl:
    raise SystemExit("no template flow found")

def hdrs(sign_mode):
    h = {
        "authorization": tmpl.headers["authorization"],
        "x-app-version": tmpl.headers["x-app-version"],
        "x-device-id": tmpl.headers["x-device-id"],
        "x-device-platform": tmpl.headers.get("x-device-platform", "Android"),
        "x-platform-version": tmpl.headers.get("x-platform-version", "28"),
        "x-device-tag": tmpl.headers["x-device-tag"],
        "X-Analytics-Session-Id": tmpl.headers.get("X-Analytics-Session-Id", ""),
        "X-Apps-Flyer-Id": tmpl.headers.get("X-Apps-Flyer-Id", ""),
        "X-Telemetry": tmpl.headers.get("X-Telemetry", ""),
        "X-Telemetry-Version": tmpl.headers.get("X-Telemetry-Version", "1"),
        "Content-Type": "application/json",
        "User-Agent": "okhttp/5.1.0",
        "Accept": "application/json",
    }
    if sign_mode == "real":
        h["x-request-sign"] = tmpl.headers.get("x-request-sign", "")
    elif sign_mode == "garbage":
        h["x-request-sign"] = "0" * 128
    # else: no sign header
    return h

def call(method, url, sign_mode, body=None):
    req = urllib.request.Request(url, method=method, headers=hdrs(sign_mode))
    if body is not None:
        req.data = json.dumps(body).encode()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read()[:600].decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:600].decode(errors="replace")
    except Exception as e:
        return "ERR", str(e)

URL_MAIN = "https://middle-api.magnit.ru/v1/goals/main"
URL_CHECKIN = "https://middle-api.magnit.ru/v1/goals/check-in"

print("=== GET /v1/goals/main ===")
for mode in ["real", "none", "garbage"]:
    print(mode, "->", call("GET", URL_MAIN, mode))

print("=== POST /v1/goals/check-in ===")
for mode in ["real", "none", "garbage"]:
    print(mode, "->", call("POST", URL_CHECKIN, mode))
