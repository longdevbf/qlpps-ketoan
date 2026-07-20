/**
 * QLPPS Mandatory Push Notification Request — Anh Quang 2026-06-13
 *
 * Bắt buộc NV bật thông báo trên cả desktop + mobile. Mỗi lần load page:
 *   - Notification.permission === 'granted' + đã subscribe → silent.
 *   - 'granted' chưa subscribe → tự subscribe (không hiện popup).
 *   - 'default' (chưa hỏi) → POPUP MANDATORY, không có nút Đóng.
 *   - 'denied' (đã từ chối) → POPUP hướng dẫn vào Settings bật lại.
 *
 * Yêu cầu:
 *   - Browser hỗ trợ Service Worker + PushManager (Safari iOS 16.4+, Chrome,
 *     Firefox, Edge tất cả OK).
 *   - Server có endpoint /api/notifications/push/vapid-public-key
 *     và /api/notifications/push/subscribe (đã có sẵn shared.notifications_router).
 *
 * Cách dùng (trong base.html hoặc index.html):
 *   <script src="/static/push_request_popup.js?v=1"
 *           data-app="baogia"
 *           data-api-base="/api/notifications"></script>
 */
(function () {
  'use strict';

  // ── 0. Skip nếu trang login / 403 / không có cookie auth ──
  const _path = location.pathname || '';
  if (_path.startsWith('/login') || _path.startsWith('/logout') ||
      _path.startsWith('/403') || _path.startsWith('/static/') ||
      _path === '/favicon.ico') {
    return;
  }

  // ── 1. Cấu hình từ data-attributes ──
  const scriptEl = document.currentScript ||
    document.querySelector('script[src*="push_request_popup.js"]');
  const APP_NAME = (scriptEl && scriptEl.getAttribute('data-app')) || 'qlpps';
  const API_BASE = (scriptEl && scriptEl.getAttribute('data-api-base')) || '/api/notifications';

  // ── 2. Check support ──
  if (!('Notification' in window) || !('serviceWorker' in navigator) || !('PushManager' in window)) {
    console.warn('[PushPopup] Browser không hỗ trợ Push Notification');
    return;
  }

  // ── 2.5. Daily limit — NV chỉ thấy popup 1-2 lần/ngày, ấn X hoặc qua
  //     page khác là không hiện lại nữa (tránh spam). 2026-06-17.
  const _STATE_KEY = '_qlpps_push_popup_v1';
  const _MAX_PER_DAY = 2;

  function _today() {
    return new Date().toISOString().slice(0, 10);  // YYYY-MM-DD
  }

  function _getState() {
    try {
      const raw = localStorage.getItem(_STATE_KEY);
      const s = raw ? JSON.parse(raw) : null;
      if (!s || s.date !== _today()) {
        return { date: _today(), shown: 0, dismissed: false };
      }
      return s;
    } catch (e) {
      return { date: _today(), shown: 0, dismissed: false };
    }
  }

  function _saveState(s) {
    try { localStorage.setItem(_STATE_KEY, JSON.stringify(s)); } catch (e) {}
  }

  function _shouldShowPopup() {
    const s = _getState();
    if (s.dismissed) return false;
    if (s.shown >= _MAX_PER_DAY) return false;
    return true;
  }

  function _markShown() {
    const s = _getState();
    s.shown = (s.shown || 0) + 1;
    _saveState(s);
  }

  function _markDismissed() {
    const s = _getState();
    s.dismissed = true;
    _saveState(s);
  }

  // ── 3. Đợi page load + DOM ready ──
  function ready(fn) {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  }

  ready(async function () {
    // Đợi 1.5s sau khi DOM ready để không che trang load đầu
    await new Promise(r => setTimeout(r, 1500));

    // Auto-register Service Worker /static/sw.js nếu chưa có (đảm bảo
    // push event được handle để show notification + setAppBadge).
    try {
      const existing = await navigator.serviceWorker.getRegistration('/');
      if (!existing) {
        await navigator.serviceWorker.register('/static/sw.js', { scope: '/' });
      }
    } catch (e) {
      console.warn('[PushPopup] SW register fail:', e);
    }

    const perm = Notification.permission;
    if (perm === 'granted') {
      // Tự subscribe nếu chưa
      try { await _subscribeIfNeeded(); } catch (e) { /* silent */ }
      return;
    }

    // 'default' hoặc 'denied' → check daily limit trước khi show
    if (!_shouldShowPopup()) return;
    _markShown();
    _showPopup(perm);
  });

  /**
   * Đăng ký subscription nếu chưa có. Gọi sau khi permission='granted'.
   */
  async function _subscribeIfNeeded() {
    const reg = await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (sub) {
      // Send lại cho server (idempotent — đảm bảo server biết)
      await _sendSubToServer(sub);
      return;
    }
    // Chưa có sub → subscribe mới
    const r = await fetch(API_BASE + '/push/vapid-public-key', { credentials: 'same-origin' });
    if (!r.ok) throw new Error('VAPID key fetch fail');
    const { publicKey } = await r.json();
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: _urlBase64ToUint8Array(publicKey),
    });
    await _sendSubToServer(sub);
  }

  async function _sendSubToServer(sub) {
    const json = sub.toJSON();
    await fetch(API_BASE + '/push/subscribe', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        endpoint: sub.endpoint,
        p256dh: json.keys && json.keys.p256dh,
        auth: json.keys && json.keys.auth,
        user_agent: navigator.userAgent,
        source_app: APP_NAME,
      }),
    });
  }

  function _urlBase64ToUint8Array(b64) {
    const padding = '='.repeat((4 - b64.length % 4) % 4);
    const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  }

  /**
   * Hiện popup mandatory. permState: 'default' | 'denied'.
   */
  function _showPopup(permState) {
    // Tránh duplicate (sau khi user click rồi popup re-render)
    if (document.getElementById('qlpps-push-popup-overlay')) return;

    const isDenied = permState === 'denied';
    const title = isDenied
      ? '⚠ Bạn đã từ chối thông báo'
      : '🔔 Vui lòng bật thông báo';
    const body = isDenied
      ? `Trình duyệt đã chặn thông báo từ QLPPS. Bạn cần mở Cài đặt của
         trình duyệt để cho phép lại.<br><br>
         <b>iPhone Safari:</b> Cài đặt → Safari → Trang web → Thông báo<br>
         <b>Android Chrome:</b> Cài đặt → Trang web → Thông báo<br>
         <b>Máy tính:</b> Click biểu tượng 🔒 cạnh URL → Thông báo → Cho phép`
      : `Để nhận tin nhắn, đơn mới, lịch trực, duyệt chi… ngay tức thì,
         bạn cần bật thông báo. Đây là <b>yêu cầu bắt buộc</b> với mọi
         nhân viên QLPPS để không bỏ lỡ thông tin quan trọng.`;
    const btnLabel = isDenied ? 'Tôi đã bật trong Cài đặt' : 'Bật thông báo ngay';

    const overlay = document.createElement('div');
    overlay.id = 'qlpps-push-popup-overlay';
    overlay.innerHTML = `
      <style>
        #qlpps-push-popup-overlay{
          position:fixed; inset:0; background:rgba(15,23,42,.72);
          z-index:2147483640; display:flex; align-items:center;
          justify-content:center; padding:16px;
          font-family:'Inter','Segoe UI',system-ui,-apple-system,sans-serif;
          animation:_qpfade .25s ease;
        }
        @keyframes _qpfade{from{opacity:0}to{opacity:1}}
        @keyframes _qpup{from{transform:translateY(20px) scale(.95);opacity:0}
                          to{transform:translateY(0) scale(1);opacity:1}}
        .qp-box{
          background:#fff; border-radius:18px; max-width:440px; width:100%;
          box-shadow:0 25px 60px rgba(0,0,0,.4);
          animation:_qpup .3s cubic-bezier(.16,1,.3,1);
          overflow:hidden;
        }
        .qp-head{
          background:linear-gradient(135deg,#2563eb,#06b6d4);
          color:#fff; padding:24px 24px 18px; text-align:center;
        }
        .qp-icon{
          font-size:48px; line-height:1; margin-bottom:6px;
          display:inline-block; animation:_qpring 1.2s ease-in-out infinite;
        }
        @keyframes _qpring{
          0%,100%{transform:rotate(0)}
          15%{transform:rotate(-12deg)}
          30%{transform:rotate(10deg)}
          45%{transform:rotate(-8deg)}
          60%{transform:rotate(5deg)}
        }
        .qp-title{font-size:18px; font-weight:800; letter-spacing:.2px}
        .qp-body{padding:20px 24px 16px; color:#334155;
                 font-size:14px; line-height:1.55}
        .qp-body b{color:#0f172a}
        .qp-body br{line-height:1.8}
        .qp-foot{padding:8px 24px 22px; display:flex; flex-direction:column; gap:10px}
        .qp-btn{
          width:100%; padding:13px 18px; border:none; border-radius:10px;
          font-size:15px; font-weight:700; cursor:pointer;
          transition:transform .12s, box-shadow .15s;
          background:linear-gradient(135deg,#2563eb,#06b6d4); color:#fff;
          box-shadow:0 4px 14px rgba(37,99,235,.35);
        }
        .qp-btn:hover{transform:translateY(-1px); box-shadow:0 6px 18px rgba(37,99,235,.45)}
        .qp-btn:active{transform:translateY(0)}
        .qp-btn[disabled]{opacity:.6; cursor:wait}
        .qp-help{
          font-size:11.5px; color:#64748b; text-align:center;
          padding-top:6px;
        }
        @media (max-width:480px){
          .qp-box{border-radius:14px; max-width:96vw}
          .qp-head{padding:20px 18px 14px}
          .qp-icon{font-size:40px}
          .qp-title{font-size:16px}
          .qp-body{font-size:13px; padding:16px 18px 12px}
          .qp-foot{padding:6px 18px 18px}
          .qp-btn{padding:12px 16px; font-size:14px}
        }
      </style>
      <div class="qp-box" role="dialog" aria-modal="true" aria-labelledby="qp-title">
        <div class="qp-head" style="position:relative">
          ${isDenied ? '<button type="button" id="qp-btn-close" aria-label="Đóng" title="Đóng" style="position:absolute;top:10px;right:12px;width:30px;height:30px;border:none;border-radius:50%;background:rgba(255,255,255,.2);color:#fff;font-size:18px;font-weight:700;cursor:pointer;display:flex;align-items:center;justify-content:center;line-height:1;transition:background .15s" onmouseover="this.style.background=\'rgba(255,255,255,.35)\'" onmouseout="this.style.background=\'rgba(255,255,255,.2)\'">×</button>' : ''}
          <div class="qp-icon">🔔</div>
          <div class="qp-title" id="qp-title">${title}</div>
        </div>
        <div class="qp-body">${body}</div>
        <div class="qp-foot">
          <button type="button" class="qp-btn" id="qp-btn-enable">${btnLabel}</button>
          <div class="qp-help">QLPPS Papasan · Yêu cầu bắt buộc với tất cả nhân viên</div>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    // X close button — chỉ có ở trạng thái denied (user đã chối, có thể tắt
    // popup nhắc nhở để dùng app tiếp; lần load sau popup vẫn hiện lại).
    const btnClose = overlay.querySelector('#qp-btn-close');
    if (btnClose) {
      btnClose.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        _closePopup();
      });
    }

    const btn = overlay.querySelector('#qp-btn-enable');
    btn.addEventListener('click', async function () {
      btn.disabled = true; btn.textContent = 'Đang xử lý…';
      try {
        if (isDenied) {
          // User đã vào Settings bật lại → re-check permission
          // Lưu ý: Notification.permission là live, chỉ re-read là đủ
          const newPerm = Notification.permission;
          if (newPerm === 'granted') {
            await _subscribeIfNeeded();
            _closePopup();
            return;
          }
          if (newPerm === 'denied') {
            btn.textContent = '⚠ Vẫn chưa bật — kiểm tra Cài đặt';
            setTimeout(() => {
              btn.disabled = false;
              btn.textContent = 'Tôi đã bật trong Cài đặt';
            }, 2000);
            return;
          }
          // Permission về 'default' → request bình thường
        }
        // 'default' → request permission
        const perm = await Notification.requestPermission();
        if (perm === 'granted') {
          await _subscribeIfNeeded();
          _closePopup();
        } else if (perm === 'denied') {
          // Re-render popup với hướng dẫn
          _closePopup();
          _showPopup('denied');
        } else {
          // 'default' → user click ngoài popup permission → giữ popup ở lại
          btn.disabled = false;
          btn.textContent = 'Bật thông báo ngay';
        }
      } catch (e) {
        console.warn('[PushPopup] Enable fail:', e);
        btn.disabled = false;
        btn.textContent = 'Thử lại';
      }
    });
  }

  function _closePopup() {
    const el = document.getElementById('qlpps-push-popup-overlay');
    if (el) el.remove();
    // User chủ động đóng (X close) hoặc subscribe thành công → mark dismissed
    // → không hiện lại trong ngày, dù còn quota.
    _markDismissed();
  }
})();
