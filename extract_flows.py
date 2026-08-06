import sys
from mitmproxy import io, http

targets = ["magnit.ru", "tander", "magnit"]
inf = sys.argv[1] if len(sys.argv) > 1 else r"D:\gfe\flows.mitm"
outf = r"D:\gfe\extracted.txt"

results = []
reader = io.FlowReader(open(inf, "rb"))
for fl in reader.stream():
    if not isinstance(fl, http.HTTPFlow):
        continue
    if not fl.request:
        continue
    host = (fl.request.pretty_host or "").lower()
    if not any(t in host for t in targets):
        continue
    # skip static assets / images / fonts
    path = fl.request.path.lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".css", ".woff", ".woff2", ".mp4", ".js")):
        continue

    lines = []
    lines.append("=" * 80)
    lines.append(f"{fl.request.method} {fl.request.scheme}://{host}{fl.request.path}")
    lines.append("--- REQUEST HEADERS ---")
    for k, v in fl.request.headers.items():
        lines.append(f"{k}: {v}")
    if fl.request.content:
        ct = fl.request.headers.get("content-type", "")
        body = fl.request.get_text(strict=False)
        lines.append("--- REQUEST BODY ---")
        lines.append(body[:6000] if body else repr(fl.request.content[:6000]))
    lines.append("--- RESPONSE STATUS ---")
    if fl.response:
        lines.append(f"{fl.response.status_code}")
        lines.append("--- RESPONSE HEADERS ---")
        for k, v in fl.response.headers.items():
            if k.lower() in ("content-type", "set-cookie", "location", "x-request-id"):
                lines.append(f"{k}: {v}")
        rbody = fl.response.get_text(strict=False) if fl.response.content else ""
        lines.append("--- RESPONSE BODY ---")
        lines.append((rbody[:8000] if rbody else repr(fl.response.content[:8000])))
    lines.append("")
    results.append("\n".join(lines))

with open(outf, "w", encoding="utf-8") as f:
    f.write("\n".join(results))

print(f"Extracted {len(results)} flows to {outf}")
