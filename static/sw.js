/**
 * Service Worker — Papasan Báo Giá.
 *
 * NHIỆM VỤ:
 *   1) Cache-first cho static asset (.js .css .woff2 .ttf .svg .png .jpg .webp .ico)
 *      → giảm tải mạng, tăng tốc load lại trang.
 *   2) Nhận push event + notificationclick để mở app (PWA push receiver).
 *
 * NGUYÊN TẮC AN TOÀN:
 *   - CHỈ cache static asset → KHÔNG cache HTML/API (tránh serve data cũ).
 *   - Chỉ xử lý request method GET. Method khác hoặc URL không phải static
 *     → bypass (return undefined) để browser xử lý mặc định.
 *
 * Lifecycle:
 *   - install: skipWaiting để SW mới thay SW cũ ngay
 *   - activate: xoá cache cũ khác CACHE_NAME hiện tại + clients.claim
 *   - fetch:   cache-first cho static asset
 *   - push:    hiện OS notification + setAppBadge(unread)
 *   - notificationclick: focus tab cũ hoặc mở tab mới tại url payload
 */
const CACHE_NAME = 'baogia-static-v1';
const STATIC_ASSET_RE = /\.(?:js|css|woff2|ttf|svg|png|jpg|jpeg|webp|ico)(?:\?.*)?$/i;

self.addEventListener('install', (event) => {
  // Activate ngay không chờ tab cũ đóng
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    // Xoá tất cả cache cũ không cùng CACHE_NAME hiện tại
    const keys = await caches.keys();
    await Promise.all(
      keys.map((k) => (k === CACHE_NAME ? null : caches.delete(k)))
    );
    await self.clients.claim();
  })());
});

self.addEventListener('fetch', (event) => {
  const req = event.request;

  // Chỉ xử lý GET
  if (req.method !== 'GET') return;

  // Chỉ xử lý static asset theo regex extension
  let url;
  try {
    url = new URL(req.url);
  } catch (_) {
    return;
  }
  if (!STATIC_ASSET_RE.test(url.pathname)) return;

  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(req);
    if (cached) return cached;

    try {
      const res = await fetch(req);
      if (res && res.ok) {
        // Clone trước khi cache vì response stream chỉ đọc 1 lần
        cache.put(req, res.clone()).catch(() => {});
      }
      return res;
    } catch (e) {
      // Network lỗi và không có cache → trả về lỗi bình thường
      throw e;
    }
  })());
});

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { title: 'Thông báo', body: event.data ? event.data.text() : '' };
  }

  // === Cuộc gọi đến: thông báo kiểu call (nút Nghe / Từ chối) ===
  if (data.type === 'call') {
    event.waitUntil(self.registration.showNotification(data.title || '📞 Cuộc gọi đến', {
      body: data.body || ((data.from_name || 'Ai đó') + ' đang gọi cho bạn...'),
      icon: '/static/icons/icon-192.png',
      badge: '/static/icons/icon-192.png',
      tag: 'zcall-' + (data.call_id || 'x'),
      renotify: true,
      requireInteraction: true,
      vibrate: [600, 300, 600, 300, 600, 300, 600],
      actions: [
        { action: 'accept', title: '✅ Nghe' },
        { action: 'reject', title: '❌ Từ chối' },
      ],
      data: {
        zcall: true, call_id: data.call_id, from: data.from, from_name: data.from_name,
        media: data.media, room_id: data.room_id, kind: data.kind,
        url: '/?zcall_accept=' + (data.call_id || ''),
      },
    }));
    return;
  }

  const title = data.title || 'Papasan – QLPPS uketoan';
  const body = data.body || '';
  const url = data.url || '/';
  const badge = typeof data.badge === 'number' ? data.badge : null;

  const options = {
    body,
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    tag: data.ref_type && data.ref_id ? `${data.ref_type}:${data.ref_id}` : undefined,
    renotify: true,
    data: { url, ref_type: data.ref_type, ref_id: data.ref_id },
  };

  const work = [self.registration.showNotification(title, options)];

  if (badge !== null && 'setAppBadge' in self.navigator) {
    work.push(self.navigator.setAppBadge(badge).catch(() => {}));
  } else if (badge === 0 && 'clearAppBadge' in self.navigator) {
    work.push(self.navigator.clearAppBadge().catch(() => {}));
  }

  event.waitUntil(Promise.all(work));
});

self.addEventListener('notificationclick', (event) => {
  const nd = event.notification.data || {};
  event.notification.close();

  // === Cuộc gọi: Nghe / Từ chối ngay từ thông báo ===
  if (nd.zcall) {
    if (event.action === 'reject') {
      event.waitUntil(fetch('/api/chat/call/signal', {
        method: 'POST', credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to: nd.from, kind: 'reject', call_id: nd.call_id }),
      }).catch(() => {}));
      return;
    }
    event.waitUntil((async () => {
      const cs = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const c of cs) {
        try {
          if (new URL(c.url).origin === self.location.origin) {
            await c.focus();
            c.postMessage({ type: 'zcall-accept', call_id: nd.call_id });
            return;
          }
        } catch (_) {}
      }
      if (self.clients.openWindow) await self.clients.openWindow('/?zcall_accept=' + (nd.call_id || ''));
    })());
    return;
  }

  const url = nd.url || '/';

  event.waitUntil((async () => {
    const allClients = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true,
    });
    // Tìm tab Báo Giá đang mở → focus + navigate
    for (const c of allClients) {
      try {
        const cUrl = new URL(c.url);
        if (cUrl.origin === self.location.origin) {
          await c.focus();
          if ('navigate' in c) {
            await c.navigate(url);
          }
          return;
        }
      } catch (_) {}
    }
    // Không có tab → mở mới
    if (self.clients.openWindow) {
      await self.clients.openWindow(url);
    }
  })());
});

// Cleanup badge khi SW nhận message từ page (vd: user mark-all-read)
self.addEventListener('message', (event) => {
  const msg = event.data || {};
  if (msg.type === 'set-badge' && 'setAppBadge' in self.navigator) {
    const n = Number(msg.count) || 0;
    if (n > 0) self.navigator.setAppBadge(n).catch(() => {});
    else if ('clearAppBadge' in self.navigator) self.navigator.clearAppBadge().catch(() => {});
  }
});
