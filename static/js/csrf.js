/**
 * csrf.js — Wrap window.fetch:
 *   1. Tự động thêm X-Requested-With header (chống CSRF cho /api/*)
 *   2. Bắt 401 (JWT session hết hạn) → toast + redirect /logout (clear cookie)
 *
 * Include trên mọi page: <script src="/static/js/csrf.js"></script>
 * Đặt TRƯỚC mọi script khác dùng fetch.
 */
(function () {
    const _origFetch = window.fetch;
    window.__sessionExpired = false;

    function _doLogout() {
        if (window.__sessionExpired) return;
        window.__sessionExpired = true;
        try {
            if (typeof window.showToast === 'function') {
                window.showToast('⏰ Phiên đăng nhập đã hết — đang đăng xuất…', 'err');
            } else if (typeof window.toast === 'function') {
                window.toast('⏰ Phiên đăng nhập đã hết — đang đăng xuất…', 'error');
            } else {
                console.warn('Phiên đăng nhập đã hết hạn — redirect /logout');
            }
        } catch (e) { /* ignore */ }
        setTimeout(function () { window.location.href = '/logout'; }, 900);
    }

    window.fetch = function (input, init) {
        init = init || {};

        // 1. Thêm header X-Requested-With nếu chưa có (CSRF protection)
        let h;
        if (init.headers instanceof Headers) {
            h = init.headers;
            if (!h.has('X-Requested-With')) h.set('X-Requested-With', 'XMLHttpRequest');
        } else {
            h = init.headers ? Object.assign({}, init.headers) : {};
            const hasHeader = Object.keys(h).some(function (k) { return k.toLowerCase() === 'x-requested-with'; });
            if (!hasHeader) h['X-Requested-With'] = 'XMLHttpRequest';
        }
        init.headers = h;

        // 2. Đảm bảo gửi cookie session
        if (init.credentials === undefined) init.credentials = 'same-origin';

        return _origFetch.call(this, input, init).then(function (res) {
            // 3. Bắt 401 (token expired / missing) → logout flow
            if (res.status === 401) {
                // Bỏ qua /login, /logout, /auth/login để tránh redirect loop
                const url = typeof input === 'string' ? input : (input && input.url) || '';
                if (!/\/(login|logout|auth\/login)/.test(url)) {
                    _doLogout();
                }
            }
            return res;
        });
    };
})();
