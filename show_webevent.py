import sys
sys.stdout.reconfigure(encoding='utf-8')
from mitmproxy import io, http
import json

flows = list(io.FlowReader(open(r'D:\gfe\flows.mitm', 'rb')).stream())

def show(path_sub, label):
    print('=' * 20, label)
    for f in flows:
        if isinstance(f, http.HTTPFlow) and f.request and path_sub in f.request.path and f.response and f.response.status_code == 200:
            try:
                t = f.response.get_text()
            except Exception:
                continue
            print('URL:', f.request.url[:100])
            print(t[:2000])
            print('----')
            break

show('scratch-and-webevents', 'scratch-and-webevents')
show('goals/interactive', 'goals/interactive')
