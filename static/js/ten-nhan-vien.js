/* Hiện TÊN nhân viên thay cho mã (anh Quang 25/09/2026: "nv26006 cụ thể là ai?").
   Nhiều API chỉ trả username/mã NV (created_by, nguoi_duyet…), rải trên 42 màn + modal + panel.
   Lớp này đổi mọi mã NV được in ra màn hình thành họ tên, rê chuột vào vẫn thấy mã (title).
   Quy tắc an toàn:
   - Chỉ đổi mã CÓ trong danh bạ (/api/nhan-vien/ten) — mã lạ giữ nguyên.
   - Không đụng mã đơn hàng kiểu NV26023-26-00064 (mã NV đứng liền "-số").
   - Mã nằm trong câu dài mà cùng dòng/thẻ đã có tên người đó rồi (vd dòng phụ "NV26004 · Giám Đốc"
     dưới tên) thì bỏ qua để khỏi in tên 2 lần.
   - Không đụng ô nhập, script, style, vùng có [data-giu-ma]. */
(function () {
  if (window.__tenNvReady) return;
  window.__tenNvReady = true;

  var API = '/api/nhan-vien/ten';
  var KHOA = 'ten-nv:v1';
  var TTL_MS = 10 * 60 * 1000;
  var RE_MA = /(^|[^\w-])((?:nv|NV)\d{5}(?:_\d+)?)(?![\w-])/g;
  var BO_QUA = 'SCRIPT,STYLE,TEXTAREA,INPUT,CODE,PRE';
  var KHUNG_DONG = 'tr, li, dd, dt, article, .kd-kpi, .kd-panel__head, .kd-lines > *, .kd-rank > *';

  var banDo = null;
  var choXuLy = [];
  var henGio = 0;

  function napBanDo() {
    try {
      var c = JSON.parse(sessionStorage.getItem(KHOA) || 'null');
      if (c && Date.now() - c.t < TTL_MS) return Promise.resolve(c.d);
    } catch (e) {}
    return fetch(API, { credentials: 'include' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d) { try { sessionStorage.setItem(KHOA, JSON.stringify({ t: Date.now(), d: d })); } catch (e) {} }
        return d;
      })
      .catch(function () { return null; });
  }

  function boQua(el) {
    for (var x = el; x && x !== document.body; x = x.parentElement) {
      if (BO_QUA.indexOf(x.tagName) >= 0 || x.isContentEditable || x.hasAttribute('data-giu-ma')) return true;
    }
    return false;
  }

  function doiNut(nut) {
    var t = nut.nodeValue;
    if (!t || t.length > 400 || !/nv\d{5}/i.test(t)) return;
    var cha = nut.parentElement;
    if (!cha || boQua(cha)) return;
    var chiMotMa = /^\s*(?:nv|NV)\d{5}(?:_\d+)?\s*$/.test(t);
    var khung = chiMotMa ? null : cha.closest(KHUNG_DONG);
    var daDoi = [];
    var moi = t.replace(RE_MA, function (m, truoc, ma) {
      var ten = banDo[ma.toLowerCase()];
      if (!ten) return m;
      if (khung && khung.textContent.indexOf(ten) >= 0) return m;
      daDoi.push(ma);
      return truoc + ten;
    });
    if (!daDoi.length) return;
    nut.nodeValue = moi;
    if (!cha.title) cha.title = daDoi.join(', ');
  }

  function quet(goc) {
    if (goc.nodeType === 3) { doiNut(goc); return; }
    if (goc.nodeType !== 1 || !/nv\d{5}/i.test(goc.textContent || '')) return;
    var w = document.createTreeWalker(goc, NodeFilter.SHOW_TEXT);
    var ds = [];
    for (var n = w.nextNode(); n; n = w.nextNode()) ds.push(n);
    ds.forEach(doiNut);
  }

  function xuLyHang() {
    henGio = 0;
    var ds = choXuLy; choXuLy = [];
    ds.forEach(function (n) { if (n.isConnected) quet(n); });
  }

  function batDau(d) {
    if (!d) return;
    banDo = d;
    quet(document.body);
    new MutationObserver(function (bienDoi) {
      bienDoi.forEach(function (b) {
        if (b.type === 'characterData') choXuLy.push(b.target);
        else b.addedNodes.forEach(function (n) { choXuLy.push(n); });
      });
      if (!henGio) henGio = requestAnimationFrame(xuLyHang);
    }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  function khoiDong() { napBanDo().then(batDau); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', khoiDong);
  else khoiDong();
})();
