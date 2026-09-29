/* Chuyển trang mượt cho app nhiều trang (MPA) — không phải viết lại 42 màn thành SPA.
   1. Speculation Rules: rê chuột vào link /ketoan/* ~200ms là trình duyệt tải sẵn NGẦM cả trang
      (kể cả JS gọi API) → bấm vào hiện gần như tức thì. Chrome/Edge 121+; trình duyệt khác bỏ qua.
   2. Giữ vị trí cuộn của sidebar giữa các lần chuyển trang (trước đây mỗi lần bấm sidebar nhảy về đầu).
   3. Bấm link sidebar: tô đậm mục ngay lập tức, không chờ trang mới.
   Hiệu ứng mờ chuyển trang (@view-transition) khai báo ở CSS trong _header.html. */
(function () {
  if (window.__dieuHuongReady) return;
  window.__dieuHuongReady = true;

  var KHOA_CUON = 'ab-sb-cuon';

  function themLuatTaiSan() {
    if (!(HTMLScriptElement.supports && HTMLScriptElement.supports('speculationrules'))) return;
    var s = document.createElement('script');
    s.type = 'speculationrules';
    s.textContent = JSON.stringify({
      prerender: [{
        source: 'document',
        where: { and: [
          { href_matches: '/ketoan/*' },
          { not: { selector_matches: '[data-no-prerender], [target=_blank], [download]' } }
        ] },
        eagerness: 'moderate'
      }]
    });
    document.head.appendChild(s);
  }

  function napViTriCuon() {
    var nav = document.querySelector('.ab-sb-nav');
    if (!nav) return;
    try {
      var y = sessionStorage.getItem(KHOA_CUON);
      if (y !== null) nav.scrollTop = +y;
    } catch (e) { /* storage bị chặn — bỏ qua */ }
    // Trang được prerender: lúc hiển thị thật mới đọc vị trí cuộn mới nhất.
    if (document.prerendering) {
      document.addEventListener('prerenderingchange', function () {
        try { var y2 = sessionStorage.getItem(KHOA_CUON); if (y2 !== null) nav.scrollTop = +y2; } catch (e) {}
      }, { once: true });
    }
  }

  function luuViTriCuon() {
    var nav = document.querySelector('.ab-sb-nav');
    if (!nav) return;
    try { sessionStorage.setItem(KHOA_CUON, String(nav.scrollTop)); } catch (e) {}
  }

  function danhDauNgay(e) {
    var a = e.target.closest && e.target.closest('.ab-sb a[href]');
    if (!a || e.ctrlKey || e.metaKey || e.shiftKey || e.button) return;
    luuViTriCuon();
    document.querySelectorAll('.ab-sb a.active').forEach(function (x) { x.classList.remove('active'); });
    a.classList.add('active');
  }

  themLuatTaiSan();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', napViTriCuon);
  else napViTriCuon();
  document.addEventListener('click', danhDauNgay, true);
  window.addEventListener('pagehide', luuViTriCuon);
})();
