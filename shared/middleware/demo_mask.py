"""Demo-mask middleware — LÀM MỜ số liệu kinh doanh cho tài khoản demo.

Anh Quang 2026-08-27: tài khoản `demo` (quyền CEO) để trình chiếu 7 app Papasan.
KHÔNG tạo số giả — chỉ **làm mờ (blur)** các con số tiền + biểu đồ trên màn hình
để lớp học không đọc được số thật; chữ/tên/thao tác giữ nguyên.

Cơ chế: ASGI middleware — CHỈ khi user là demo VÀ response là text/html thì chèn
1 đoạn <script> làm mờ (blur) trước </body>. Không đụng JSON/logic → không vỡ app.
Script blur các phần tử chứa: số tiền (tỷ/tr/nghìn/k/đ, số nhóm 1.234.567), số "N đơn",
và các biểu đồ (canvas/svg). Non-demo pass-through hoàn toàn.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

DEMO_USERNAMES = {"demo"}

# ── JS làm mờ (inline, chèn vào mọi trang HTML của demo) ──
_BLUR_JS = r"""
<style>
.__demomask{filter:blur(7px)!important;-webkit-filter:blur(7px)!important;
 user-select:none!important;pointer-events:none!important;transition:none!important}
.__demomask *{filter:none!important}
</style>
<script>
(function(){
  if(window.__demoMaskOn)return; window.__demoMaskOn=true;
  // Số tiền: 9.4 tỷ | 116.2 tr | 162.5k | 663.640.164đ | số nhóm >=7 chữ số | "N đơn"
  // Đơn vị tiền non-ASCII (tỷ/đ) KHÔNG dùng \b (JS \b không khớp ký tự Việt) →
  // dùng lookahead "không phải chữ cái" thay cho \b.
  var MONEY=/(\d{1,3}(?:[.,]\d{3}){1,}|\d+(?:[.,]\d+)?)\s*(tri[ệe]u|ngh[ìi]n|t[ỷy]|tr|k|đ|₫|vnd)(?![a-zA-Z])/i;
  var GROUP=/\d{1,3}(?:[.,]\d{3}){2,}/;                 // 663.640.164
  var DON=/\d+(?:[.,]\d+)?\s*(đơn|khách|kh|h[ợo]p đồng|lead)(?![a-zA-Z])/i;
  var DATE=/^\s*\d{1,2}[\/\-]\d{1,2}([\/\-]\d{2,4})?\s*$/;
  var PHONE=/^\s*0\d{8,10}\s*$/;
  function hit(t){ if(!t)return false; if(DATE.test(t)||PHONE.test(t))return false;
    return MONEY.test(t)||GROUP.test(t)||DON.test(t); }
  var SKIP={SCRIPT:1,STYLE:1,INPUT:1,TEXTAREA:1,SELECT:1,OPTION:1};
  // HIỆU NĂNG: chỉ quét phần MỚI thêm (incremental) + đánh dấu đã xử lý,
  // KHÔNG quét lại toàn trang liên tục (bản cũ quét mỗi 1.2s gây treo trình duyệt).
  function blurText(root){
    try{
      if(root.nodeType===1 && root.__dmDone) return;
      var w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,null);
      var hits=[],n,cnt=0;
      while((n=w.nextNode()) && cnt++<4000){
        var p=n.parentNode; if(!p||SKIP[p.tagName])continue;
        if(p.classList&&p.classList.contains('__demomask'))continue;
        if(hit(n.nodeValue)) hits.push(p);
      }
      hits.forEach(function(el){ el.classList.add('__demomask'); });
      if(root.nodeType===1) root.__dmDone=1;
    }catch(e){}
  }
  function blurCharts(root){
    try{
      if(!root.querySelectorAll) return;
      var els=root.querySelectorAll('canvas, svg.recharts-surface, .recharts-wrapper, [class*="chart"] canvas, .chartjs-render-monitor');
      for(var i=0;i<els.length;i++){ if(!els[i].classList.contains('__demomask')) els[i].classList.add('__demomask'); }
    }catch(e){}
  }
  function scan(root){ if(!root)return; blurText(root); blurCharts(root); }
  function full(){ try{ if(document.body){ document.body.__dmDone=0; scan(document.body); } }catch(e){} }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',full); else full();
  // Quan sát phần tử MỚI, gộp nhóm (debounce 400ms) — chỉ xử lý node vừa thêm.
  var pending=[], timer=null;
  function flush(){
    timer=null;
    var list=pending; pending=[];
    for(var i=0;i<list.length && i<200;i++) scan(list[i]);
  }
  try{
    new MutationObserver(function(muts){
      for(var i=0;i<muts.length;i++){
        var add=muts[i].addedNodes;
        for(var j=0;j<add.length;j++){
          var nd=add[j];
          if(nd.nodeType===1){ nd.__dmDone=0; pending.push(nd); }
          else if(nd.nodeType===3 && nd.parentNode){ nd.parentNode.__dmDone=0; pending.push(nd.parentNode); }
        }
      }
      if(pending.length && !timer) timer=setTimeout(flush,400);
    }).observe(document.documentElement,{childList:true,subtree:true});
  }catch(e){}
  // Lưới an toàn: quét lại toàn trang RẤT THƯA (20 giây) phòng nội dung đổi kiểu khác.
  setInterval(full, 20000);
})();
</script>
"""

_BLUR_BYTES = _BLUR_JS.encode("utf-8")


def _is_demo_scope(scope) -> bool:
    try:
        from shared.auth.jwt import decode_token
    except Exception:
        return False
    tok = None
    for k, v in scope.get("headers", []):
        if k == b"cookie":
            for part in v.decode("latin-1").split(";"):
                part = part.strip()
                if part.startswith("access_token="):
                    tok = part[len("access_token="):]
                    break
        elif k == b"authorization":
            val = v.decode("latin-1")
            if val.lower().startswith("bearer "):
                tok = val[7:]
    if not tok:
        return False
    try:
        p = decode_token(tok)
        return (getattr(p, "username", "") or "").lower() in DEMO_USERNAMES
    except Exception:
        return False


def _header_val(headers, name: bytes) -> bytes:
    for k, v in headers:
        if k.lower() == name:
            return v
    return b""


def _inject(html: bytes) -> bytes:
    """Chèn blur script trước </body> (hoặc cuối nếu không có)."""
    low = html.lower()
    i = low.rfind(b"</body>")
    if i == -1:
        return html + _BLUR_BYTES
    return html[:i] + _BLUR_BYTES + html[i:]


class DemoMaskMiddleware:
    """Pure-ASGI — gắn NGOÀI CÙNG (add_middleware sau cùng)."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _is_demo_scope(scope):
            return await self.app(scope, receive, send)

        state = {"html": False, "start": None, "buf": bytearray()}

        async def _send(message):
            t = message.get("type")
            if t == "http.response.start":
                ct = _header_val(message.get("headers", []), b"content-type").lower()
                # chỉ đụng HTML; bỏ qua JSON/SSE/file/stream
                if b"text/html" in ct:
                    state["html"] = True
                    state["start"] = message
                    return
                await send(message)
            elif t == "http.response.body":
                if not state["html"]:
                    await send(message)
                    return
                state["buf"].extend(message.get("body", b"") or b"")
                if message.get("more_body"):
                    return
                out = _inject(bytes(state["buf"]))
                start = state["start"]
                new_headers = [(k, v) for k, v in start.get("headers", [])
                               if k.lower() != b"content-length"]
                new_headers.append((b"content-length", str(len(out)).encode()))
                await send({**start, "headers": new_headers})
                await send({"type": "http.response.body", "body": out, "more_body": False})
            else:
                await send(message)

        await self.app(scope, receive, _send)


def install_demo_masking(app) -> None:
    """Gắn blur cho demo NGOÀI CÙNG — GỌI Ở CUỐI main.py mỗi app."""
    app.add_middleware(DemoMaskMiddleware)
