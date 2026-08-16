import json
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured_requests.log")
MAX_BODY = 300000
WATCH = ("eda.yandex", "eda.yandex.ru", "tc.eats.yandex.ru", "api.eda.yandex.ru",
         "api.plus.yandex.net", "plus.yandex.ru", "egw.plus.yandex.net",
         "trust.yandex.ru", "pay.yandex.ru", "passport.yandex.ru",
         "yandex.ru", "hri.yandex.net", "mobileproxy.passport.yandex.net",
         "bank-authproxy.prod.yandex-bank.net", "paylater.prod.yandex-bank.net")
# Дополнительные домены JS-бандлов формы tokenize и diehard/CCT (генерация
# pmd-card/psd-cvn дескрипторов). Совпадают по суффиксу — ловят поддомены
# (cct.trust.yandex.ru, hq.cct.yandex.net, mc.yandex.ru и т.п.).
WATCH_CDN = ("yastatic.net", "yandex.net", "diehard.yandex.ru", "mc.yandex.ru",
             "cct.trust.yandex.ru", "hq.cct.yandex.net")
SKIP = ("passport.yandex.ru", "auth.yandex.ru", "oauth.yandex.ru",
        "clck.yandex.ru", "ya.ru", "yandex.ru/set", "yandex.ru/portal")

REQ_HDRS = ("host", "content-type", "accept", "user-agent", "x-request-id",
            "authorization", "x-uid", "x-yandex-login", "x-geoid", "x-lang", "cookie")
RESP_HDRS = ("content-type", "x-request-id", "content-encoding")


def log(msg):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def watch(flow):
    try:
        host = flow.request.pretty_host
        url = flow.request.url
        if any(s in url for s in SKIP):
            return False
        for d in WATCH:
            if host == d:
                return True
        for d in WATCH_CDN:
            if host.endswith(d):
                return True
        return False
    except Exception:
        return False


def request(flow):
    try:
        if not watch(flow):
            return
        r = flow.request
        hdrs = {k: v for k, v in r.headers.items() if k.lower() in REQ_HDRS}
        body = ""
        if r.content:
            body = r.content.decode("utf-8", "replace")[:MAX_BODY]
        log("=== REQUEST %s %s\nHEADERS: %s\nBODY: %s\n" % (
            r.method, r.url, json.dumps(hdrs, ensure_ascii=False), body))
    except Exception as e:
        log("REQ ERR " + str(e))


def response(flow):
    try:
        if not watch(flow):
            return
        r = flow.response
        hdrs = {k: v for k, v in r.headers.items() if k.lower() in RESP_HDRS}
        body = ""
        if r.content:
            body = r.content.decode("utf-8", "replace")[:MAX_BODY]
        log("=== RESPONSE %s for %s\nRESP-HEADERS: %s\nRESP-BODY: %s\n" % (
            r.status_code, flow.request.url, json.dumps(hdrs, ensure_ascii=False), body))
    except Exception as e:
        log("RESP ERR " + str(e))
