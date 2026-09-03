import sys, urllib.request
sys.path.insert(0,"/app"); sys.stdout.reconfigure(encoding="utf-8")
from shared.auth.jwt import create_access_token
tok,_=create_access_token(5,"ceopps","ceo",[])
port=sys.argv[1]
req=urllib.request.Request(f"http://localhost:{port}/",headers={"Authorization":f"Bearer {tok}","Cookie":f"access_token={tok}"})
try:
    html=urllib.request.urlopen(req,timeout=25).read().decode("utf-8","replace")
    print("  render_widget=", ("--z-blue" in html), "jinja_error=", ("TemplateNotFound" in html or "Traceback" in html), "len=",len(html))
except Exception as e:
    b=""
    try: b=e.read().decode("utf-8","replace")[:300]
    except Exception: pass
    print("  ERR", type(e).__name__, e, "::", b)
