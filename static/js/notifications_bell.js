/**
 * Notification Bell — module dùng chung 3 app (baogia/marketing/muahang).
 *
 * Cách dùng (đặt vào base template, sau khi DOM ready):
 *
 *   <div id="qlpps-bell-mount"></div>
 *   <script src="/static/shared/notifications_bell.js"></script>
 *   <script>
 *     QlppsBell.mount({
 *       mountId: 'qlpps-bell-mount',
 *       apiBase: '/api/notifications',
 *       enableSound: false,    // user toggle on
 *       pollMs: 30000,         // fallback polling khi SSE down
 *     });
 *   </script>
 *
 * Tính năng:
 * - Bell icon + badge số unread
 * - Dropdown 10 noti gần nhất + nút "đánh dấu đã đọc tất cả"
 * - SSE realtime push, fallback polling 30s
 * - Sound toggle (off mặc định, lưu localStorage)
 * - Severity color coding (info/warning/critical)
 * - Click noti → mark-read + open URL
 */
(function () {
  'use strict';

  const STYLE = `
    .qlpps-bell-wrap { position: relative; display: inline-flex; align-items: center; }
    .qlpps-bell-btn {
      background: transparent; border: none; cursor: pointer; padding: 6px 8px;
      font-size: 18px; line-height: 1; position: relative; color: inherit;
      border-radius: 6px; transition: background .15s;
    }
    .qlpps-bell-btn:hover { background: rgba(255,255,255,.12); }
    .qlpps-bell-btn .qlpps-bell-icon { display: inline-block; transition: transform .2s; }
    .qlpps-bell-btn.has-new .qlpps-bell-icon { animation: qlppsRing .6s ease-in-out 2; }
    @keyframes qlppsRing {
      0%, 100% { transform: rotate(0deg); }
      20% { transform: rotate(-15deg); }
      40% { transform: rotate(15deg); }
      60% { transform: rotate(-10deg); }
      80% { transform: rotate(10deg); }
    }
    .qlpps-bell-badge {
      position: absolute; top: 0; right: 0;
      background: #e53935; color: #fff; font-size: 10px; font-weight: 700;
      min-width: 16px; height: 16px; padding: 0 4px;
      border-radius: 8px; display: flex; align-items: center; justify-content: center;
      line-height: 1; box-shadow: 0 1px 3px rgba(0,0,0,.3);
    }
    .qlpps-bell-badge[data-count="0"] { display: none; }
    .qlpps-bell-dropdown {
      position: absolute; top: calc(100% + 6px); right: 0;
      width: 360px; max-height: 480px;
      background: #fff; color: #333;
      border: 1px solid #e0e0e0; border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0,0,0,.18);
      display: none; z-index: 9999;
      flex-direction: column;
    }
    .qlpps-bell-dropdown.open { display: flex; }
    .qlpps-bell-head {
      padding: 10px 14px; border-bottom: 1px solid #eee;
      display: flex; align-items: center; justify-content: space-between;
      font-weight: 600; font-size: 13px;
    }
    .qlpps-bell-actions { display: flex; gap: 8px; }
    .qlpps-bell-actions button {
      background: transparent; border: none; cursor: pointer;
      font-size: 12px; color: #1976d2; padding: 2px 4px;
    }
    .qlpps-bell-actions button:hover { text-decoration: underline; }
    .qlpps-bell-list { overflow-y: auto; max-height: 400px; }
    .qlpps-bell-item {
      padding: 10px 14px; border-bottom: 1px solid #f0f0f0;
      cursor: pointer; transition: background .12s;
      display: flex; gap: 10px; align-items: flex-start;
    }
    .qlpps-bell-item:hover { background: #f5f9ff; }
    .qlpps-bell-item.unseen { background: #f0f7ff; }
    .qlpps-bell-item.severity-warning { border-left: 3px solid #f57c00; }
    .qlpps-bell-item.severity-critical { border-left: 3px solid #d32f2f; }
    .qlpps-bell-icon-wrap {
      flex: 0 0 28px; height: 28px; border-radius: 50%;
      background: #e3f2fd; color: #1976d2;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px;
    }
    .qlpps-bell-item.severity-warning .qlpps-bell-icon-wrap { background: #fff3e0; color: #f57c00; }
    .qlpps-bell-item.severity-critical .qlpps-bell-icon-wrap { background: #ffebee; color: #d32f2f; }
    .qlpps-bell-content { flex: 1; min-width: 0; }
    .qlpps-bell-title {
      font-size: 13px; font-weight: 600; color: #222;
      margin-bottom: 2px; line-height: 1.3;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .qlpps-bell-msg {
      font-size: 12px; color: #666; line-height: 1.3;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }
    .qlpps-bell-time { font-size: 11px; color: #999; margin-top: 3px; }
    .qlpps-bell-empty {
      padding: 30px 14px; text-align: center; color: #aaa; font-size: 13px;
    }
    .qlpps-bell-foot {
      padding: 8px 14px; border-top: 1px solid #eee;
      display: flex; justify-content: space-between; align-items: center;
      font-size: 12px; color: #666;
    }
    .qlpps-sound-toggle {
      background: transparent; border: 1px solid #ddd; border-radius: 4px;
      padding: 3px 8px; cursor: pointer; font-size: 11px;
    }
    .qlpps-sound-toggle.on { color: #1976d2; border-color: #1976d2; }
    .qlpps-push-cta {
      display: none; margin: 8px 14px 4px; padding: 10px 12px;
      background: #fff8e1; border: 1px solid #ffd54f; border-radius: 6px;
      font-size: 12px; color: #5d4037; line-height: 1.4;
    }
    .qlpps-push-cta.show { display: block; }
    .qlpps-push-cta b { color: #b85c00; }
    .qlpps-push-cta button {
      margin-top: 6px; background: #1976d2; color: #fff; border: none;
      border-radius: 4px; padding: 5px 10px; font-size: 12px; font-weight: 600;
      cursor: pointer;
    }
    .qlpps-push-cta button:hover { background: #1565c0; }
    .qlpps-push-cta .qlpps-push-dismiss {
      background: transparent; color: #999; margin-left: 6px;
    }
    .qlpps-push-status {
      display: flex; align-items: center; gap: 6px; font-size: 11px;
      padding: 5px 14px; border-top: 1px solid #eee; color: #888; flex-wrap: wrap;
    }
    .qlpps-push-status.on  { color: #2e7d32; }
    .qlpps-push-status.off { color: #b71c1c; }
    .qlpps-push-status button {
      font-size: 11px; padding: 2px 8px; border: 1px solid #1976d2; border-radius: 4px;
      background: #e3f2fd; color: #1565c0; cursor: pointer; font-weight: 600;
    }
    .qlpps-push-status button:hover { background: #1976d2; color: #fff; }
  `;

  const ICON_MAP = {
    'lead:new': '👤',
    'lead:status': '🔄',
    'lead:chuyen_kd': '➡️',
    'lead:comment': '💬',
    'quote:new': '📝',
    'quote:duyet': '✅',
    'quote:comment': '💬',
    'order:new': '📦',
    'order:status': '🔄',
    'supplier:new': '🏭',
  };

  function relTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return 'vừa xong';
    if (diff < 3600) return `${Math.floor(diff / 60)}p trước`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h trước`;
    if (diff < 604800) return `${Math.floor(diff / 86400)}d trước`;
    return d.toLocaleDateString('vi-VN');
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Beep tổng hợp bằng Web Audio — TO ĐÙNG (marketing override, KHÔNG động shared)
  // Loud + 3 lần ping liên tiếp + master gain ~6x (limiter giữ không clip)
  let _audioCtx = null;
  function _playOnePing(ctx, startAt, baseFreq, sweepFreq, masterGain) {
    const osc1 = ctx.createOscillator();           // sine — body
    const osc2 = ctx.createOscillator();           // square — "bite" cho to hơn
    const gain = ctx.createGain();
    osc1.type = 'sine';
    osc2.type = 'square';
    osc1.frequency.setValueAtTime(baseFreq, startAt);
    osc1.frequency.setValueAtTime(sweepFreq, startAt + 0.1);
    osc2.frequency.setValueAtTime(baseFreq, startAt);
    osc2.frequency.setValueAtTime(sweepFreq, startAt + 0.1);
    gain.gain.setValueAtTime(0.001, startAt);
    gain.gain.exponentialRampToValueAtTime(1.0, startAt + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.001, startAt + 0.35);
    osc1.connect(gain);
    osc2.connect(gain);
    gain.connect(masterGain);
    osc1.start(startAt);
    osc2.start(startAt);
    osc1.stop(startAt + 0.4);
    osc2.stop(startAt + 0.4);
  }
  function playBeep() {
    try {
      _audioCtx = _audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const ctx = _audioCtx;
      if (ctx.state === 'suspended') { try { ctx.resume(); } catch (_) {} }
      const now = ctx.currentTime;
      // Master chain: gain (boost) → compressor (chống vỡ tiếng) → destination
      const master = ctx.createGain();
      master.gain.value = 6.0;                       // boost ~6x
      const comp = ctx.createDynamicsCompressor();
      comp.threshold.value = -10;
      comp.knee.value = 20;
      comp.ratio.value = 12;
      comp.attack.value = 0.003;
      comp.release.value = 0.25;
      master.connect(comp).connect(ctx.destination);
      // 3 ping liên tiếp — "to đùng"
      _playOnePing(ctx, now,        880, 660, master);
      _playOnePing(ctx, now + 0.20, 988, 740, master);
      _playOnePing(ctx, now + 0.42, 1175, 880, master);
    } catch (e) { /* ignore */ }
  }


  const QlppsBell = {
    state: {
      apiBase: '/api/notifications',
      mountEl: null,
      btn: null, badge: null, dropdown: null, list: null, soundBtn: null,
      items: [],
      unreadCount: 0,
      sseSource: null,
      pollTimer: null,
      pollMs: 30000,
      soundOn: false,
    },

    mount(opts) {
      const s = this.state;
      s.apiBase = (opts && opts.apiBase) || '/api/notifications';
      s.pollMs = (opts && opts.pollMs) || 30000;
      s.appName = (opts && opts.appName) || 'baogia';
      s.soundOn = localStorage.getItem('qlpps_bell_sound') === '1';
      s.mountEl = document.getElementById((opts && opts.mountId) || 'qlpps-bell-mount');
      if (!s.mountEl) {
        console.warn('[QlppsBell] mount element not found');
        return;
      }
      this._injectStyle();
      this._renderShell();
      this._loadInitial();
      this._connectSSE();
      this._initPush();
      // Polling fallback (vẫn chạy phòng SSE drop)
      s.pollTimer = setInterval(() => this._refreshCount(), s.pollMs);
      // Click outside → close dropdown
      document.addEventListener('click', (e) => {
        if (!s.mountEl.contains(e.target)) this._closeDropdown();
      });
    },

    _injectStyle() {
      if (document.getElementById('qlpps-bell-style')) return;
      const st = document.createElement('style');
      st.id = 'qlpps-bell-style';
      st.textContent = STYLE;
      document.head.appendChild(st);
    },

    _renderShell() {
      const s = this.state;
      s.mountEl.innerHTML = `
        <div class="qlpps-bell-wrap">
          <button type="button" class="qlpps-bell-btn" title="Thông báo">
            <span class="qlpps-bell-icon">🔔</span>
            <span class="qlpps-bell-badge" data-count="0">0</span>
          </button>
          <div class="qlpps-bell-dropdown">
            <div class="qlpps-bell-head">
              <span>🔔 Thông báo</span>
              <div class="qlpps-bell-actions">
                <button type="button" class="qlpps-mark-all">Đọc hết</button>
              </div>
            </div>
            <div class="qlpps-push-cta">
              <b>Bật thông báo trên thiết bị này</b><br>
              Để nhận tin nhắn ngay cả khi tắt trình duyệt + thấy số trên icon app.
              <div>
                <button type="button" class="qlpps-push-enable">Bật thông báo</button>
                <button type="button" class="qlpps-push-dismiss">Để sau</button>
              </div>
            </div>
            <div class="qlpps-bell-list">
              <div class="qlpps-bell-empty">Chưa có thông báo</div>
            </div>
            <div class="qlpps-push-status" id="qlpps-push-status-row">
              <span class="qlpps-push-status-text">⏳ Đang kiểm tra...</span>
            </div>
            <div class="qlpps-bell-foot">
              <span class="qlpps-foot-status">—</span>
              <button type="button" class="qlpps-sound-toggle ${s.soundOn ? 'on' : ''}">
                ${s.soundOn ? '🔔 Âm thanh ON' : '🔕 Âm thanh OFF'}
              </button>
            </div>
          </div>
        </div>
      `;
      s.btn = s.mountEl.querySelector('.qlpps-bell-btn');
      s.badge = s.mountEl.querySelector('.qlpps-bell-badge');
      s.dropdown = s.mountEl.querySelector('.qlpps-bell-dropdown');
      s.list = s.mountEl.querySelector('.qlpps-bell-list');
      s.soundBtn = s.mountEl.querySelector('.qlpps-sound-toggle');
      s.pushCta = s.mountEl.querySelector('.qlpps-push-cta');
      s.pushStatusRow = s.mountEl.querySelector('#qlpps-push-status-row');
      s.btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleDropdown();
      });
      s.mountEl.querySelector('.qlpps-mark-all').addEventListener('click', () => this._markAllRead());
      s.soundBtn.addEventListener('click', () => this._toggleSound());
      s.mountEl.querySelector('.qlpps-push-enable').addEventListener('click', () => this._enablePush());
      s.mountEl.querySelector('.qlpps-push-dismiss').addEventListener('click', () => {
        localStorage.setItem('qlpps_push_dismissed_at', String(Date.now()));
        s.pushCta.classList.remove('show');
      });
    },

    _toggleDropdown() {
      const s = this.state;
      if (s.dropdown.classList.contains('open')) {
        this._closeDropdown();
      } else {
        s.dropdown.classList.add('open');
        this._loadList();       // refresh khi mở
        this._updatePushStatusRow();  // luôn cập nhật trạng thái push
      }
    },
    _closeDropdown() { this.state.dropdown.classList.remove('open'); },

    _toggleSound() {
      const s = this.state;
      s.soundOn = !s.soundOn;
      localStorage.setItem('qlpps_bell_sound', s.soundOn ? '1' : '0');
      s.soundBtn.classList.toggle('on', s.soundOn);
      s.soundBtn.textContent = s.soundOn ? '🔔 Âm thanh ON' : '🔕 Âm thanh OFF';
      if (s.soundOn) playBeep();  // demo
    },

    async _loadInitial() {
      await Promise.all([this._refreshCount(), this._loadList()]);
    },

    async _refreshCount() {
      try {
        const r = await fetch(this.state.apiBase + '/count-unread', { credentials: 'same-origin' });
        if (!r.ok) return;
        const d = await r.json();
        this._setUnread(d.count || 0);
      } catch (e) { /* fail-soft */ }
    },

    async _loadList() {
      const s = this.state;
      try {
        const r = await fetch(s.apiBase + '?all=true&limit=20', { credentials: 'same-origin' });
        if (!r.ok) return;
        const items = await r.json();
        s.items = Array.isArray(items) ? items : [];
        this._renderList();
      } catch (e) { /* fail-soft */ }
    },

    _renderList() {
      const s = this.state;
      if (!s.items.length) {
        s.list.innerHTML = '<div class="qlpps-bell-empty">Chưa có thông báo</div>';
        return;
      }
      s.list.innerHTML = s.items.map(n => {
        const icon = ICON_MAP[n.event_type] || '🔔';
        const sevClass = n.severity && n.severity !== 'info' ? ` severity-${esc(n.severity)}` : '';
        const unseenClass = n.seen ? '' : ' unseen';
        return `
          <div class="qlpps-bell-item${unseenClass}${sevClass}" data-id="${n.id}" data-url="${esc(n.url || '')}">
            <div class="qlpps-bell-icon-wrap">${icon}</div>
            <div class="qlpps-bell-content">
              <div class="qlpps-bell-title">${esc(n.title)}</div>
              <div class="qlpps-bell-msg">${esc(n.message || '')}</div>
              <div class="qlpps-bell-time">${esc(relTime(n.created_at))} · ${esc(n.source_app || '')}</div>
            </div>
          </div>
        `;
      }).join('');
      s.list.querySelectorAll('.qlpps-bell-item').forEach(el => {
        el.addEventListener('click', () => this._onItemClick(el));
      });
    },

    async _onItemClick(el) {
      const id = el.dataset.id;
      const url = el.dataset.url;
      // Mark read silent
      if (el.classList.contains('unseen')) {
        try {
          await fetch(this.state.apiBase + '/' + id + '/mark-read', {
            method: 'POST', credentials: 'same-origin',
          });
          el.classList.remove('unseen');
          this._setUnread(Math.max(0, this.state.unreadCount - 1));
        } catch (e) { /* ignore */ }
      }
      if (url) window.location.href = url;
    },

    async _markAllRead() {
      try {
        const r = await fetch(this.state.apiBase + '/mark-all-read', {
          method: 'POST', credentials: 'same-origin',
        });
        if (r.ok) {
          this._setUnread(0);
          this.state.items.forEach(n => { n.seen = true; });
          this._renderList();
        }
      } catch (e) { /* ignore */ }
    },

    _setUnread(n) {
      const s = this.state;
      const prev = s.unreadCount;
      s.unreadCount = n;
      s.badge.textContent = n > 99 ? '99+' : String(n);
      s.badge.dataset.count = String(n);
      if (n > prev) {
        s.btn.classList.add('has-new');
        setTimeout(() => s.btn.classList.remove('has-new'), 1500);
      }
      // Đồng bộ badge số trên icon home screen (PWA installed apps)
      try {
        if (n > 0 && 'setAppBadge' in navigator) {
          navigator.setAppBadge(n).catch(() => {});
        } else if (n === 0 && 'clearAppBadge' in navigator) {
          navigator.clearAppBadge().catch(() => {});
        }
      } catch (_) { /* ignore */ }
    },

    // ── Web Push (OS-level notification + badge) ──────────────────────────
    async _initPush() {
      const s = this.state;
      // Browser hỗ trợ?
      if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
        return;  // iOS <16.4, hoặc browser cũ
      }
      // Đã từ chối permission → không hiện CTA (user phải mở Settings)
      if (Notification.permission === 'denied') return;

      try {
        const reg = await navigator.serviceWorker.ready;
        const existing = await reg.pushManager.getSubscription();

        if (Notification.permission === 'granted' && existing) {
          // Đã ok — không cần CTA. Đẩy lên server lại để cập nhật last_seen.
          this._sendSubscription(existing);
          return;
        }
        if (Notification.permission === 'granted' && !existing) {
          // Đã cho phép nhưng chưa subscribe (vd: user bấm "Đừng hỏi nữa" trước đó)
          await this._subscribeAndSend(reg);
          return;
        }
        // Permission default → hiện CTA, trừ khi user mới dismiss <1 ngày
        const dismissedAt = parseInt(localStorage.getItem('qlpps_push_dismissed_at') || '0', 10);
        if (Date.now() - dismissedAt < 1 * 86400000) return;
        s.pushCta.classList.add('show');
      } catch (e) {
        console.warn('[QlppsBell] push init fail', e);
      }
    },

    // Cập nhật dòng trạng thái push ở footer bell — luôn gọi khi mở dropdown
    async _updatePushStatusRow() {
      const s = this.state;
      if (!s.pushStatusRow) return;
      const row = s.pushStatusRow;

      const noPushSupport = !('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window);
      if (noPushSupport) {
        row.innerHTML = '<span class="qlpps-push-status-text">📵 Trình duyệt không hỗ trợ push</span>';
        return;
      }

      if (Notification.permission === 'denied') {
        row.className = 'qlpps-push-status off';
        row.innerHTML = `<span class="qlpps-push-status-text">🚫 Thông báo bị chặn</span>
          <span style="color:#888;font-size:10px">Vào cài đặt trình duyệt để bật lại</span>`;
        return;
      }

      try {
        const reg = await navigator.serviceWorker.ready;
        const sub = await reg.pushManager.getSubscription();
        if (sub) {
          row.className = 'qlpps-push-status on';
          row.innerHTML = `<span class="qlpps-push-status-text">✅ Thông báo đang bật trên máy này</span>`;
        } else {
          row.className = 'qlpps-push-status off';
          row.innerHTML = `<span class="qlpps-push-status-text">📵 Chưa bật thông báo trên máy này</span>
            <button type="button" class="qlpps-push-enable-footer">Bật ngay</button>`;
          row.querySelector('.qlpps-push-enable-footer').addEventListener('click', async () => {
            await this._enablePush();
            await this._updatePushStatusRow();
          });
        }
      } catch (e) {
        row.innerHTML = '<span class="qlpps-push-status-text">⚠ Không kiểm tra được</span>';
      }
    },

    async _enablePush() {
      const s = this.state;
      if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
      try {
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') {
          s.pushCta.classList.remove('show');
          return;
        }
        const reg = await navigator.serviceWorker.ready;
        await this._subscribeAndSend(reg);
        s.pushCta.classList.remove('show');
      } catch (e) {
        console.warn('[QlppsBell] enable push fail', e);
      }
    },

    async _subscribeAndSend(reg) {
      const r = await fetch(this.state.apiBase + '/push/vapid-public-key', { credentials: 'same-origin' });
      if (!r.ok) throw new Error('vapid key fetch failed');
      const { publicKey } = await r.json();
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: this._urlBase64ToUint8Array(publicKey),
      });
      await this._sendSubscription(sub);
    },

    async _sendSubscription(sub) {
      const json = sub.toJSON();
      const body = {
        endpoint: sub.endpoint,
        p256dh: json.keys && json.keys.p256dh,
        auth: json.keys && json.keys.auth,
        user_agent: navigator.userAgent,
        source_app: this.state.appName,
      };
      try {
        await fetch(this.state.apiBase + '/push/subscribe', {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
      } catch (e) { /* fail-soft */ }
    },

    _urlBase64ToUint8Array(b64) {
      const padding = '='.repeat((4 - b64.length % 4) % 4);
      const base64 = (b64 + padding).replace(/-/g, '+').replace(/_/g, '/');
      const raw = atob(base64);
      const out = new Uint8Array(raw.length);
      for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
      return out;
    },

    _connectSSE() {
      const s = this.state;
      try {
        const url = s.apiBase + '/sse';
        const es = new EventSource(url, { withCredentials: true });
        s.sseSource = es;
        es.addEventListener('notification', (e) => {
          let data = {};
          try { data = JSON.parse(e.data); } catch (_) {}
          // Tăng unread + chèn vào đầu list (best-effort)
          this._setUnread(s.unreadCount + 1);
          // Ring animation
          s.btn.classList.add('has-new');
          setTimeout(() => s.btn.classList.remove('has-new'), 1500);
          if (s.soundOn) playBeep();
          // Refresh list nếu dropdown đang mở
          if (s.dropdown.classList.contains('open')) this._loadList();
        });
        es.onerror = () => {
          // EventSource auto-reconnect; vẫn dựa vào polling fallback
        };
      } catch (e) {
        console.warn('[QlppsBell] SSE init failed, polling only', e);
      }
    },
  };

  window.QlppsBell = QlppsBell;
})();
