/**
 * toast.js — Global toast notification component.
 *
 * Replace alert() bằng UI đẹp hơn. Auto-fade sau 3.5s, click X để dismiss.
 *
 * Usage:
 *   showToast('ok',  'Đã lưu thành công');
 *   showToast('err', 'Lỗi: ' + msg);
 *   showToast('info', 'Đang xử lý...');
 *   showToast('warn', 'Quá nhiều request');
 *
 * Include trong base.html (sau csrf.js):
 *   <script src="{{ url_for('static', filename='js/toast.js') }}"></script>
 */
(function () {
    // Inject CSS once
    const css = `
        .ps-toast-container {
            position: fixed; top: var(--sp-9, 20px); right: var(--sp-9, 20px); z-index: 99999;
            display: flex; flex-direction: column; gap: var(--sp-5, 10px);
            max-width: 380px; pointer-events: none;
        }
        .ps-toast {
            background: var(--bg-card, white); border-radius: var(--r, 8px);
            padding: var(--sp-6, 12px) var(--sp-8, 16px) var(--sp-6, 12px) var(--sp-7, 14px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.15);
            display: flex; align-items: flex-start; gap: var(--sp-5, 10px);
            font-size: var(--fs-body, 13px); line-height: var(--lh-body, 1.5);
            border-left: 4px solid var(--text-3, #5B6A80);
            animation: ps-toast-in 0.25s ease-out;
            pointer-events: auto;
            color: var(--text-1, #101C44);
        }
        /* Màu theo VAI TRÒ từ theme.css. Mọi var() trong file có dự phòng = giá trị
           HIỆN TẠI của token đó trong theme.css (hệ xanh ADR-012, 11/09/2026), phòng
           trang nạp toast.js mà thiếu theme.css. Đổi theme.css thì đổi dự phòng theo. */
        .ps-toast.ok    { border-left-color: var(--success, #15803D); }
        .ps-toast.err   { border-left-color: var(--danger, #B91C1C); }
        .ps-toast.warn  { border-left-color: var(--warning, #B45309); }
        .ps-toast.info  { border-left-color: var(--brand, #2563EB); }
        .ps-toast .icon { font-size: var(--fs-h, 18px); line-height: 1; flex-shrink: 0; }
        .ps-toast.ok    .icon { color: var(--success, #15803D); }
        .ps-toast.err   .icon { color: var(--danger, #B91C1C); }
        .ps-toast.warn  .icon { color: var(--warning, #B45309); }
        .ps-toast.info  .icon { color: var(--brand, #2563EB); }
        .ps-toast .msg  { flex: 1; word-break: break-word; }
        .ps-toast .x    {
            cursor: pointer; opacity: 0.5; padding: var(--sp-1, 2px) var(--sp-3, 6px);
            margin: -4px -6px -4px 0;
            border: none; background: transparent; font-size: var(--fs-title, 15px); line-height: 1;
        }
        .ps-toast .x:hover { opacity: 1; }
        .ps-toast.fade-out { animation: ps-toast-out 0.3s ease-in forwards; }
        @keyframes ps-toast-in {
            from { transform: translateX(20px); opacity: 0; }
            to   { transform: translateX(0);    opacity: 1; }
        }
        @keyframes ps-toast-out {
            from { transform: translateX(0);    opacity: 1; }
            to   { transform: translateX(20px); opacity: 0; }
        }
    `;
    const style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    let container = null;
    function ensureContainer() {
        if (container && document.body.contains(container)) return container;
        container = document.createElement('div');
        container.className = 'ps-toast-container';
        document.body.appendChild(container);
        return container;
    }

    const ICONS = {
        ok:   '✓',
        err:  '✕',
        warn: '⚠',
        info: 'ℹ',
    };

    /**
     * showToast(type, message, durationMs)
     * type: 'ok' | 'err' | 'warn' | 'info'
     */
    window.showToast = function (type, message, durationMs) {
        const t = (type || 'info').toLowerCase();
        const dur = durationMs != null ? durationMs : (t === 'err' ? 5000 : 3500);
        const c = ensureContainer();
        const el = document.createElement('div');
        el.className = 'ps-toast ' + (['ok', 'err', 'warn', 'info'].includes(t) ? t : 'info');
        el.innerHTML = `
            <div class="icon">${ICONS[t] || ICONS.info}</div>
            <div class="msg"></div>
            <button class="x" aria-label="close">×</button>
        `;
        el.querySelector('.msg').textContent = String(message || '');
        const close = () => {
            el.classList.add('fade-out');
            setTimeout(() => el.remove(), 300);
        };
        el.querySelector('.x').onclick = close;
        c.appendChild(el);
        if (dur > 0) setTimeout(close, dur);
        return el;
    };

    /**
     * showToastFromResponse(res, okMsg) — convenience cho fetch response.
     *   const res = await fetch(...).then(r=>r.json());
     *   if (showToastFromResponse(res, 'Đã lưu')) { ... continue ... }
     */
    window.showToastFromResponse = function (res, okMsg) {
        if (res && res.ok) {
            if (okMsg) showToast('ok', okMsg);
            return true;
        }
        showToast('err', (res && res.error) || 'Lỗi không xác định');
        return false;
    };
})();
