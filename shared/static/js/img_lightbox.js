/**
 * Global Image Lightbox — dùng chung 8 app V2.
 *
 * Tự intercept click trên:
 *   - <a href="...{jpg|jpeg|png|webp|gif|bmp|avif}..."> (không phân biệt query string)
 *   - <a data-lightbox="...">
 *   - <img data-lightbox="..."> hoặc bất kỳ img nằm trong <a> image-link
 *
 * Hiển thị overlay full-screen với:
 *   - Ảnh fit tối đa 92vw × 88vh
 *   - Nút ✕ đóng
 *   - Nút "Mở tab mới" fallback (cho ảnh quá lớn / cần download)
 *   - Click backdrop / ESC → đóng
 *
 * Idempotent: load nhiều lần không trùng listener.
 * Skip: nếu href có data-no-lightbox / target="_self" / là PDF (giữ tab mới).
 */
(function () {
  if (window.__QlppsImgLightbox) return;
  window.__QlppsImgLightbox = true;

  const IMG_EXT_RE = /\.(jpe?g|png|webp|gif|bmp|avif|svg)(\?.*)?$/i;

  function isImageUrl(href) {
    if (!href) return false;
    const clean = String(href).split('#')[0];
    return IMG_EXT_RE.test(clean);
  }

  function findLightboxTarget(ev) {
    let el = ev.target;
    // Climb tối đa 5 cấp tìm <a> hoặc element có data-lightbox
    for (let i = 0; i < 5 && el && el !== document.body; i++) {
      if (el.dataset && el.dataset.noLightbox === 'true') return null;
      if (el.dataset && el.dataset.lightbox) {
        return { url: el.dataset.lightbox, anchor: el.tagName === 'A' ? el : null };
      }
      if (el.tagName === 'A') {
        const href = el.getAttribute('href') || '';
        if (href && isImageUrl(href)) return { url: href, anchor: el };
        return null; // có <a> nhưng không phải ảnh → không capture
      }
      el = el.parentElement;
    }
    return null;
  }

  let overlayEl = null;
  let prevFocus = null;

  function ensureOverlay() {
    if (overlayEl) return overlayEl;
    overlayEl = document.createElement('div');
    overlayEl.id = 'qlpps-img-lightbox';
    overlayEl.style.cssText = [
      'position:fixed', 'inset:0', 'background:rgba(0,0,0,.86)',
      'z-index:99999', 'display:none', 'align-items:center', 'justify-content:center',
      'flex-direction:column', 'gap:14px', 'padding:24px',
    ].join(';');
    overlayEl.innerHTML = `
      <button type="button" data-act="close" aria-label="Đóng"
        style="position:absolute;top:14px;right:18px;background:rgba(0,0,0,.4);border:none;color:#fff;
        font-size:26px;line-height:1;width:38px;height:38px;border-radius:50%;cursor:pointer">✕</button>
      <img alt="" style="max-width:92vw;max-height:88vh;object-fit:contain;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.6)">
      <div style="display:flex;gap:10px;align-items:center">
        <a data-act="open" target="_blank" rel="noopener" style="background:rgba(255,255,255,.15);color:#fff;
          border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:6px 14px;font-size:13px;
          text-decoration:none;cursor:pointer">↗ Mở tab mới</a>
        <button type="button" data-act="close" style="background:rgba(255,255,255,.15);color:#fff;
          border:1px solid rgba(255,255,255,.3);border-radius:6px;padding:6px 14px;font-size:13px;cursor:pointer">Đóng (ESC)</button>
      </div>`;
    overlayEl.addEventListener('click', (e) => {
      const act = e.target.dataset && e.target.dataset.act;
      if (act === 'close' || e.target === overlayEl) close();
    });
    document.body.appendChild(overlayEl);
    return overlayEl;
  }

  function open(url) {
    const o = ensureOverlay();
    const img = o.querySelector('img');
    const openBtn = o.querySelector('a[data-act="open"]');
    img.src = url;
    openBtn.href = url;
    o.style.display = 'flex';
    prevFocus = document.activeElement;
    o.querySelector('button[data-act="close"]').focus();
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!overlayEl) return;
    overlayEl.style.display = 'none';
    const img = overlayEl.querySelector('img');
    if (img) img.src = '';
    document.body.style.overflow = '';
    if (prevFocus && prevFocus.focus) try { prevFocus.focus(); } catch (_) {}
  }

  document.addEventListener('click', (ev) => {
    // Bỏ qua nếu user giữ Cmd/Ctrl/Shift (mở tab mới ý đồ)
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    if (ev.button !== 0) return;
    const t = findLightboxTarget(ev);
    if (!t) return;
    ev.preventDefault();
    ev.stopPropagation();
    open(t.url);
  }, true);

  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape' && overlayEl && overlayEl.style.display !== 'none') close();
  });

  // Override window.open: nếu mở 1 URL ảnh (vd `onclick="window.open(url,'_blank')"`
  // pattern phổ biến trong marketing / baogia) → redirect sang lightbox thay vì tab mới.
  // Non-image URL (PDF, link thường) vẫn dùng window.open gốc.
  const _origOpen = window.open;
  window.open = function (url, target, features) {
    if (typeof url === 'string' && isImageUrl(url)) {
      open(url);
      // Trả về object stub để code caller không crash khi check ret.focus() / ret.closed
      return { focus: () => {}, close: () => {}, closed: false };
    }
    return _origOpen.apply(this, arguments);
  };

  // Direct click trên <img> với cursor pointer hoặc có inline onclick — fallback
  // cho trường hợp app render `<img onclick=...>` mà window.open override miss
  // (vd handler dùng location.assign hay tạo <a download>).
  document.addEventListener('click', (ev) => {
    if (ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    if (ev.button !== 0) return;
    const el = ev.target;
    if (!el || el.tagName !== 'IMG') return;
    if (el.dataset && el.dataset.noLightbox === 'true') return;
    const src = el.getAttribute('src') || '';
    if (!isImageUrl(src)) return;
    // Chỉ intercept nếu img có vẻ clickable (style cursor:pointer hoặc onclick)
    const style = window.getComputedStyle(el);
    const looksClickable = style.cursor === 'pointer' || el.hasAttribute('onclick');
    if (!looksClickable) return;
    // Nếu img nằm trong <a> đã được handler đầu tiên capture rồi → skip ở đây
    if (el.closest('a[href]')) return;
    ev.preventDefault();
    ev.stopImmediatePropagation();
    open(src);
  }, true);
})();
