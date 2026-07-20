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
      background: transparent; border: none; cursor: pointer; padding: 10px 14px;
      line-height: 1; position: relative; color: inherit;
      border-radius: 8px; transition: background .15s;
    }
    .qlpps-bell-btn:hover { background: rgba(255,255,255,.2); }
    .qlpps-bell-btn .qlpps-bell-icon {
      display: inline-block; transition: transform .2s;
      font-size: 32px; line-height: 1;
    }
    .qlpps-bell-btn.has-new .qlpps-bell-icon { animation: qlppsRing .8s ease-in-out 3; }
    .qlpps-bell-btn.has-unread { animation: qlppsPulse 2s ease-in-out infinite; }
    @keyframes qlppsRing {
      0%, 100% { transform: rotate(0deg); }
      20% { transform: rotate(-25deg); }
      40% { transform: rotate(25deg); }
      60% { transform: rotate(-18deg); }
      80% { transform: rotate(18deg); }
    }
    @keyframes qlppsPulse {
      0%, 100% { transform: scale(1); opacity: 1; }
      50% { transform: scale(1.08); opacity: .85; }
    }
    .qlpps-bell-badge {
      position: absolute; top: -2px; right: -2px;
      background: #e53935; color: #fff; font-size: 12px; font-weight: 700;
      min-width: 22px; height: 22px; padding: 0 5px;
      border-radius: 11px; border: 2px solid #fff;
      display: flex; align-items: center; justify-content: center;
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

  // Beep tổng hợp bằng Web Audio (không cần asset file)
  let _audioCtx = null;
  function playBeep() {
    try {
      _audioCtx = _audioCtx || new (window.AudioContext || window.webkitAudioContext)();
      const ctx = _audioCtx;
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.setValueAtTime(660, now + 0.1);
      gain.gain.setValueAtTime(0.001, now);
      gain.gain.exponentialRampToValueAtTime(0.15, now + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.3);
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
            <div class="qlpps-bell-list">
              <div class="qlpps-bell-empty">Chưa có thông báo</div>
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
      s.btn.addEventListener('click', (e) => {
        e.stopPropagation();
        this._toggleDropdown();
      });
      s.mountEl.querySelector('.qlpps-mark-all').addEventListener('click', () => this._markAllRead());
      s.soundBtn.addEventListener('click', () => this._toggleSound());
    },

    _toggleDropdown() {
      const s = this.state;
      if (s.dropdown.classList.contains('open')) {
        this._closeDropdown();
      } else {
        s.dropdown.classList.add('open');
        this._loadList();  // refresh khi mở
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
      s.btn.classList.toggle('has-unread', n > 0);
      if (n > prev) {
        s.btn.classList.add('has-new');
        setTimeout(() => s.btn.classList.remove('has-new'), 1500);
      }
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
