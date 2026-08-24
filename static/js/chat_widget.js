(function(){
'use strict';

// ============================================================
// ZALO V2 CHAT WIDGET — INIT JS (Skeleton)
// Other agents append after END_SKELETON_JS marker.
// ============================================================

// ---------- Global state ----------
window._zV2 = window._zV2 || {
  open: false,
  currentTab: 'tin-nhan',
  currentRoomId: null,
  rooms: [],
  messages: {},
  users: [],
  online: new Set(),
  typing: {},
  sse: null,
  oldestMsgId: {},
  scrollLocked: {},
  replyTo: null,
  editingMsgId: null,
  infoPanelOpen: false,
  _roomsLoaded: false,
  _usersLoaded: false
};

// ---------- Shortcuts ----------
var $ = function(id){ return document.getElementById(id); };
var $$ = function(sel, root){ return (root || document).querySelectorAll(sel); };

// ---------- Element refs (cached after DOMContentLoaded) ----------
var $panel, $fab, $fabBadge;
var $rail, $railTin, $railDanhba, $railSettings, $railBadgeTin;
var $colMiddle, $midHeader, $midAvatar, $midName, $btnNewGroup;
var $searchBox, $tabsFilter, $convList, $contactsList, $emptyList;
var $colMain, $emptyMain;
var $mainHeader, $mainAvatar, $mainTitle, $mainMeta, $mainBackBtn;
var $btnCall, $btnVideo, $btnInfo;
var $messagesScroll, $messagesInner;
var $typing, $scrollBottomBtn, $scrollBadge;
var $replyStrip, $replyTo, $replyText, $replyCloseBtn;
var $composeWrap, $composeInput, $composeSendWrap, $thumbsBtn, $sendBtn;
var $btnEmoji, $btnSticker, $btnImage, $btnFile, $btnMic;
var $infoPanel, $infoHeader, $infoTitle, $infoCloseBtn, $infoTabs;
var $panelCloseBtn;

function zV2_cacheRefs(){
  $panel             = $('_chat_panel');
  $fab               = $('_chat_fab');
  $fabBadge          = $('_chat_fab_badge');

  $rail              = $('zV2_rail');
  $railTin           = $('zV2_rail_btn_tin');
  $railDanhba        = $('zV2_rail_btn_danhba');
  $railSettings      = $('zV2_rail_btn_settings');
  $railBadgeTin      = $('zV2_rail_badge_tin');

  $colMiddle         = $('zV2_col_middle');
  $midHeader         = $('zV2_mid_header');
  $midAvatar         = $('zV2_mid_header_avatar');
  $midName           = $('zV2_mid_header_name');
  $btnNewGroup       = $('zV2_btn_new_group');

  $searchBox         = $('zV2_search_box');
  $tabsFilter        = $('zV2_tabs_filter');
  $convList          = $('zV2_conv_list');
  $contactsList      = $('zV2_contacts_list');
  $emptyList         = $('zV2_empty_list');

  $colMain           = $('zV2_col_main');
  $emptyMain         = $('zV2_empty_main');

  $mainHeader        = $('zV2_main_header');
  $mainAvatar        = $('zV2_main_avatar');
  $mainTitle         = $('zV2_main_title');
  $mainMeta          = $('zV2_main_meta');
  $mainBackBtn       = $('zV2_main_back_btn');

  $btnCall           = $('zV2_btn_call');
  $btnVideo          = $('zV2_btn_video');
  $btnInfo           = $('zV2_btn_info');

  $messagesScroll    = $('zV2_messages_scroll');
  $messagesInner     = $('zV2_messages_inner');

  $typing            = $('zV2_typing_indicator');
  $scrollBottomBtn   = $('zV2_scroll_bottom_btn');
  $scrollBadge       = $('zV2_scroll_badge');

  $replyStrip        = $('zV2_reply_strip');
  $replyTo           = $('zV2_reply_to');
  $replyText         = $('zV2_reply_text');
  $replyCloseBtn     = $('zV2_reply_close_btn');

  $composeWrap       = $('zV2_compose_wrap');
  $composeInput      = $('zV2_compose_input');
  $composeSendWrap   = $('zV2_compose_send_wrap');
  $thumbsBtn         = $('zV2_thumbs_btn');
  $sendBtn           = $('zV2_send_btn');

  $btnEmoji          = $('zV2_btn_emoji');
  $btnSticker        = $('zV2_btn_sticker');
  $btnImage          = $('zV2_btn_image');
  $btnFile           = $('zV2_btn_file');
  $btnMic            = $('zV2_btn_mic');

  $infoPanel         = $('zV2_info_panel');
  $infoHeader        = $('zV2_info_header');
  $infoTitle         = $('zV2_info_title');
  $infoCloseBtn      = $('zV2_info_close_btn');
  $infoTabs          = $('zV2_info_tabs');

  $panelCloseBtn     = $('zV2_panel_close_btn');

  // expose for other agents (no risk of TDZ)
  window._zV2._refs = {
    panel: $panel, fab: $fab,
    rail: $rail, railTin: $railTin, railDanhba: $railDanhba,
    convList: $convList, contactsList: $contactsList,
    mainHeader: $mainHeader, messagesScroll: $messagesScroll,
    messagesInner: $messagesInner, typing: $typing,
    scrollBottomBtn: $scrollBottomBtn, replyStrip: $replyStrip,
    composeInput: $composeInput, thumbsBtn: $thumbsBtn,
    sendBtn: $sendBtn, infoPanel: $infoPanel,
    emptyMain: $emptyMain, composeWrap: $composeWrap
  };
}

// ---------- Stub functions (other agents override via window.zV2_*) ----------
window.zV2_loadRooms      = window.zV2_loadRooms      || function(){};
window.zV2_renderRooms    = window.zV2_renderRooms    || function(){};
window.zV2_loadUsers      = window.zV2_loadUsers      || function(){};
window.zV2_renderContacts = window.zV2_renderContacts || function(){};
window.zV2_openRoom       = window.zV2_openRoom       || function(){};
window.zV2_loadMessages   = window.zV2_loadMessages   || function(){};
window.zV2_renderMessages = window.zV2_renderMessages || function(){};
window.zV2_buildBubble    = window.zV2_buildBubble    || function(){};
window.zV2_sendMessage    = window.zV2_sendMessage    || function(){};
window.zV2_handleSSE      = window.zV2_handleSSE      || function(){};
window.zV2_openInfoPanel  = window.zV2_openInfoPanel  || function(){
  if (!$infoPanel) return;
  $infoPanel.classList.add('open');
  window._zV2.infoPanelOpen = true;
  if ($btnInfo) $btnInfo.classList.add('active');
};
window.zV2_closeInfoPanel = window.zV2_closeInfoPanel || function(){
  if (!$infoPanel) return;
  $infoPanel.classList.remove('open');
  window._zV2.infoPanelOpen = false;
  if ($btnInfo) $btnInfo.classList.remove('active');
};
window.zV2_toggleInfoPanel = window.zV2_toggleInfoPanel || function(){
  if (window._zV2.infoPanelOpen) window.zV2_closeInfoPanel();
  else window.zV2_openInfoPanel();
};
window.zV2_setReplyTo     = window.zV2_setReplyTo     || function(){};
window.zV2_clearReplyTo   = window.zV2_clearReplyTo   || function(){
  if (!$replyStrip) return;
  $replyStrip.classList.remove('visible');
  window._zV2.replyTo = null;
};
window.zV2_focusInput     = window.zV2_focusInput     || function(){
  if ($composeInput) try { $composeInput.focus(); } catch(_){}
};
window.zV2_scrollToBottom = window.zV2_scrollToBottom || function(){
  if ($messagesScroll) $messagesScroll.scrollTop = $messagesScroll.scrollHeight;
};
window.zV2_showTyping     = window.zV2_showTyping     || function(){};
window.zV2_hideTyping     = window.zV2_hideTyping     || function(){};
window.zV2_updateUnreadBadges = function(){
  var total = 0;
  var rooms = (window._zV2 && _zV2.rooms) || [];
  var hidden = (typeof window.zV2_hiddenRooms === 'function') ? window.zV2_hiddenRooms() : new Set();
  for (var i = 0; i < rooms.length; i++) {
    var r = rooms[i];
    if (hidden.has(r.id)) continue;
    total += (r.unread_count || 0);
  }
  var fab = document.getElementById('_chat_fab');
  var badge = document.getElementById('_chat_fab_badge');
  if (badge) badge.textContent = total > 99 ? '99+' : String(total);
  if (fab) {
    if (total > 0) fab.classList.add('has-unread');
    else fab.classList.remove('has-unread');
  }
  // Đổi title document để mọi tab biết có tin
  if (total > 0) {
    if (!document.title.startsWith('(' + total + ')')) {
      document.title = '(' + (total > 99 ? '99+' : total) + ') ' + (window._zV2_origTitle || document.title);
    }
  } else if (window._zV2_origTitle) {
    document.title = window._zV2_origTitle;
  }
};
// Lưu title gốc lần đầu chạy
if (typeof window._zV2_origTitle === 'undefined') {
  window._zV2_origTitle = (document.title || '').replace(/^\(\d+\+?\)\s*/, '');
}
// Notification + sound khi có tin mới (chỉ kích khi widget closed hoặc khác room)
window.zV2_notifyNewMessage = function(msg, room){
  try {
    // 1) Sound beep (Web Audio API, không cần file)
    if (!window._zV2_audioCtx) {
      try { window._zV2_audioCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch(_){}
    }
    var ctx = window._zV2_audioCtx;
    if (ctx && ctx.state === 'suspended') ctx.resume();
    if (ctx) {
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(660, ctx.currentTime + 0.12);
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
      osc.connect(gain); gain.connect(ctx.destination);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.25);
    }
  } catch(_){}
  // 2) Browser notification (nếu permission granted)
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'granted' && !document.hasFocus()) {
      var senderName = msg.sender_name || msg.sender_username || 'Ai đó';
      var roomName = (room && (room.display_name || room.name)) || '';
      var bodyText = (msg.msg_type === 'card') ? window.zV2_cardPreview(msg)
        : (msg.content || (msg.msg_type === 'image' ? 'Đã gửi ảnh' : (msg.msg_type === 'file' ? 'Đã gửi file' : '')));
      var n = new Notification(senderName + (roomName && roomName !== senderName ? ' • ' + roomName : ''), {
        body: bodyText,
        icon: '/static/papasan_icon_1024.png',
        tag: 'chat-' + (msg.room_id || ''),
      });
      n.onclick = function(){ window.focus(); if (typeof zV2_open === 'function') zV2_open(); if (room && typeof zV2_openRoom === 'function') zV2_openRoom(room.id); n.close(); };
    }
  } catch(_){}
};
// Xin permission notification 1 lần khi user open chat lần đầu
window.zV2_askNotificationPermission = function(){
  try {
    if (typeof Notification !== 'undefined' && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  } catch(_){}
};

// Alias để các call site dùng renderConvList vẫn work — DEBOUNCED để gộp nhiều SSE event
var _zV2_renderConvTimer = null;
window.zV2_renderConvList = function(){
  // Luôn update badge ngay (cheap)
  window.zV2_updateUnreadBadges();
  // Debounce render heavy DOM 50ms (gộp nhiều SSE event trong vài chục ms)
  if (_zV2_renderConvTimer) return;
  _zV2_renderConvTimer = requestAnimationFrame(function(){
    _zV2_renderConvTimer = null;
    if (typeof window.zV2_renderRooms === 'function') {
      var q = (document.getElementById('zV2_search_box') || {}).value || '';
      window.zV2_renderRooms(q);
    }
  });
};
window.zV2_initSSE        = window.zV2_initSSE        || function(){};
window.zV2_closeSSE       = window.zV2_closeSSE       || function(){};
window.zV2_openSettings   = window.zV2_openSettings   || function(){};

// ---------- Tab switching ----------
function zV2_switchTab(name){
  window._zV2.currentTab = name;

  // Rail btn active state
  if ($railTin)      $railTin.classList.toggle('active',      name === 'tin-nhan');
  if ($railDanhba)   $railDanhba.classList.toggle('active',   name === 'danh-ba');

  if (name === 'tin-nhan'){
    if ($convList)     $convList.style.display     = 'block';
    if ($contactsList) $contactsList.style.display = 'none';
    if ($tabsFilter)   $tabsFilter.style.display   = '';
    if ($searchBox)    $searchBox.placeholder      = 'Tìm cuộc trò chuyện...';
  } else if (name === 'danh-ba'){
    if ($convList)     $convList.style.display     = 'none';
    if ($contactsList) $contactsList.style.display = 'block';
    if ($tabsFilter)   $tabsFilter.style.display   = 'none';
    if ($searchBox)    $searchBox.placeholder      = 'Tìm liên hệ...';

    try { window.zV2_loadUsers && window.zV2_loadUsers(); } catch(e){ console.warn('[zV2] loadUsers fail', e); }
  }
}
window.zV2_switchTab = zV2_switchTab;

// ---------- Open / close panel ----------
function zV2_open(){
  if (!$panel) zV2_cacheRefs();
  if (!$panel) return;
  window._zV2.open = true;
  $panel.classList.add('open');
  if (!window._zV2._roomsLoaded){
    try { window.zV2_loadRooms(); } catch(e){ console.warn('[zV2] loadRooms stub', e); }
  }
  try { window.zV2_initSSE(); } catch(_){}
  // Force poll presence ngay khi mở widget → đỡ stale
  try { window.zV2_handlePresenceUpdate && window.zV2_handlePresenceUpdate(); } catch(_){}
  // Xin quyền browser notification khi user lần đầu open chat
  try { window.zV2_askNotificationPermission && window.zV2_askNotificationPermission(); } catch(_){}
}
function zV2_close(){
  if (!$panel) return;
  window._zV2.open = false;
  $panel.classList.remove('open');
  // Reset mobile state
  $panel.classList.remove('show-main');
  // KHÔNG đóng SSE khi user đóng widget — vẫn cần nhận tin để bump FAB badge
  // try { window.zV2_closeSSE && window.zV2_closeSSE(); } catch(_){}
}
function zV2_toggle(){
  if (window._zV2.open) zV2_close();
  else zV2_open();
}
window.zV2_open   = zV2_open;
window.zV2_close  = zV2_close;
window.zV2_toggle = zV2_toggle;

// ---------- Bấm ra ngoài thì tự đóng ----------
// Cẩn thận: widget gắn 13 lớp phủ THẲNG VÀO <body> (lightbox ảnh, menu chuột
// phải, popup emoji, modal chuyển tiếp, toast, màn gọi…) nên chúng nằm NGOÀI
// #_chat_panel. Nếu chỉ kiểm tra "ngoài panel" thì mở ảnh lên là chat tự tắt.
// Mọi thứ widget sinh ra đều mang tiền tố zV2_ hoặc zcall_ — dựa vào đó để chừa.
document.addEventListener('pointerdown', function (e) {
  if (!window._zV2 || !window._zV2.open) return;
  var t = e.target;
  if (!t || !t.closest) return;
  if (t.closest('#_chat_panel')) return;   // bấm trong panel
  if (t.closest('#_chat_fab'))   return;   // để nút FAB tự bật/tắt, tránh đóng rồi mở lại
  if (t.closest('[id^="zV2_"], [class*="zV2_"], [id^="zcall"], [class*="zcall"]')) return;
  zV2_close();
}, true);   // pha capture: chạy trước khi lớp phủ kịp gỡ chính nó khỏi DOM

// Esc cũng đóng — bàn phím phải làm được việc mà chuột làm được
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape' || !window._zV2 || !window._zV2.open) return;
  // Chừa khi đang có lớp phủ con mở: Esc phải đóng lớp trong cùng trước
  if (document.querySelector('#zV2_lightbox_overlay, .zV2_modal_overlay, #zcall_overlay.show')) return;
  zV2_close();
});

// ---------- Composer input/send toggle ----------
function zV2_onComposeInput(){
  if (!$composeInput || !$composeSendWrap) return;
  var v = $composeInput.value || '';
  if (v.trim().length > 0) $composeSendWrap.classList.add('has-text');
  else                     $composeSendWrap.classList.remove('has-text');

  // Auto-resize textarea
  $composeInput.style.height = 'auto';
  var h = Math.min($composeInput.scrollHeight, 140);
  $composeInput.style.height = h + 'px';
}

function zV2_onComposeKeydown(e){
  // Enter = send, Shift+Enter = newline
  if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.isComposing && e.keyCode !== 229){
    e.preventDefault();
    try { window.zV2_sendMessage && window.zV2_sendMessage(); } catch(err){ console.warn(err); }
  }
}

// ---------- Scroll bottom button visibility ----------
function zV2_onMessagesScroll(){
  if (!$messagesScroll || !$scrollBottomBtn) return;
  var atBottom = ($messagesScroll.scrollHeight - $messagesScroll.scrollTop - $messagesScroll.clientHeight) < 80;
  var farUp    = ($messagesScroll.scrollHeight - $messagesScroll.scrollTop - $messagesScroll.clientHeight) > 300;
  if (farUp) $scrollBottomBtn.classList.add('visible');
  if (atBottom) $scrollBottomBtn.classList.remove('visible');

  var rid = window._zV2.currentRoomId;
  if (rid){
    window._zV2.scrollLocked[rid] = !atBottom;
  }
}

// ---------- Info-panel tabs ----------
function zV2_onInfoTabClick(e){
  var btn = e.target.closest('.zV2_info_tab_btn');
  if (!btn || !$infoTabs) return;
  var tab = btn.getAttribute('data-info-tab');
  if (!tab) return;
  // toggle button
  var btns = $infoTabs.querySelectorAll('.zV2_info_tab_btn');
  for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
  btn.classList.add('active');
  // toggle panel
  var panels = document.querySelectorAll('#zV2_info_body .zV2_info_tab_panel');
  for (var j = 0; j < panels.length; j++){
    panels[j].classList.toggle('active', panels[j].getAttribute('data-info-panel') === tab);
  }
}

// ---------- Filter tabs (Tất cả / Chưa đọc) ----------
function zV2_onFilterClick(e){
  var btn = e.target.closest('.zV2_tab_filter_btn');
  if (!btn) return;
  var siblings = $tabsFilter.querySelectorAll('.zV2_tab_filter_btn');
  for (var i = 0; i < siblings.length; i++) siblings[i].classList.remove('active');
  btn.classList.add('active');
  var f = btn.getAttribute('data-filter') || 'all';
  window._zV2.currentFilter = f;
  try { window.zV2_renderRooms && window.zV2_renderRooms(); } catch(_){}
}

// ---------- Mobile back ----------
function zV2_mobileBack(){
  if ($panel) $panel.classList.remove('show-main');
}

// ---------- FAB kéo thả được ----------
// Nút chat đặt đâu là việc của người dùng, không phải của CSS. Ba điều đáng chú ý:
//  1. Nhớ vị trí theo TỈ LỆ (0..1) trong vùng kéo được, KHÔNG theo px — thu nhỏ
//     cửa sổ thì nút vẫn nằm đúng góc tương đối thay vì trôi ra ngoài màn hình.
//  2. Phân biệt "bấm" với "kéo" bằng ngưỡng 5px; đi quá ngưỡng thì nuốt luôn cú
//     click sinh ra sau đó, nếu không thả tay ra là chat tự mở.
//  3. Có đường đi bằng bàn phím (mũi tên khi nút đang focus) — WCAG 2.5.7 đòi mọi
//     thao tác kéo phải có cách làm khác không cần kéo.
function zV2_initFabDrag(){
  var fab = $fab;
  if (!fab || fab._zV2DragBound) return;
  fab._zV2DragBound = true;

  var KEY  = 'zV2_fab_pos';   // localStorage: {rx, ry}
  var EDGE = 8;               // chừa mép màn hình
  var STEP = 12;              // bước dịch mỗi lần bấm phím mũi tên
  var drag = null;            // {dx, dy, x0, y0} khi đang giữ chuột/ngón tay
  var moved = false;          // đã vượt ngưỡng kéo chưa
  var suppressClick = false;  // nuốt đúng một cú click sau khi kéo xong
  var pos = null;             // {x, y} hiện tại — nguồn sự thật, tránh đọc lại rect
  var ratio = null;           // {rx, ry} để tính lại khi đổi cỡ cửa sổ

  // offsetWidth/Height chứ không phải rect: rect đã nhân transform của :hover
  function limits(){
    return {
      maxX: Math.max(0, window.innerWidth  - fab.offsetWidth  - EDGE * 2),
      maxY: Math.max(0, window.innerHeight - fab.offsetHeight - EDGE * 2)
    };
  }
  function here(){
    if (pos) return pos;
    var r = fab.getBoundingClientRect();
    return { x: r.left, y: r.top };
  }
  // commit = true khi kết thúc một thao tác → mới ghi nhớ vị trí
  function place(x, y, commit){
    var lim = limits();
    x = Math.min(Math.max(x, EDGE), EDGE + lim.maxX);
    y = Math.min(Math.max(y, EDGE), EDGE + lim.maxY);
    pos = { x: x, y: y };
    fab.style.setProperty('--zfab-x', Math.round(x) + 'px');
    fab.style.setProperty('--zfab-y', Math.round(y) + 'px');
    fab.classList.add('zV2_fab_moved');
    if (!commit) return;
    ratio = {
      rx: lim.maxX ? (x - EDGE) / lim.maxX : 0,
      ry: lim.maxY ? (y - EDGE) / lim.maxY : 0
    };
    // Chế độ riêng tư chặn localStorage → chỉ mất trí nhớ giữa các lần tải trang,
    // nút vẫn kéo được bình thường. Fail-soft đúng như phần còn lại của widget.
    try { localStorage.setItem(KEY, JSON.stringify(ratio)); } catch(_){}
  }
  function applyRatio(){
    if (!ratio) return;
    var lim = limits();
    place(EDGE + ratio.rx * lim.maxX, EDGE + ratio.ry * lim.maxY, false);
  }

  // ── Kéo bằng chuột / ngón tay ──
  fab.addEventListener('pointerdown', function(e){
    if (e.button) return;                       // chỉ chuột trái, chạm, bút
    var r = fab.getBoundingClientRect();
    drag = { dx: e.clientX - r.left, dy: e.clientY - r.top, x0: e.clientX, y0: e.clientY };
    moved = false;
    // Bắt con trỏ để vẫn nhận pointermove khi kéo nhanh ra ngoài nút
    try { fab.setPointerCapture(e.pointerId); } catch(_){}
  });
  fab.addEventListener('pointermove', function(e){
    if (!drag) return;
    if (!moved){
      if (Math.abs(e.clientX - drag.x0) + Math.abs(e.clientY - drag.y0) < 5) return;
      moved = true;
      fab.classList.add('zV2_fab_dragging');
    }
    e.preventDefault();
    place(e.clientX - drag.dx, e.clientY - drag.dy, false);
  });
  function zV2_fabDragEnd(e){
    if (!drag) return;
    try { fab.releasePointerCapture(e.pointerId); } catch(_){}
    drag = null;
    fab.classList.remove('zV2_fab_dragging');
    if (moved){
      var p = here();
      place(p.x, p.y, true);
      suppressClick = true;
      // Click bắn ra ngay sau pointerup (đồng bộ), nên timeout 0 chạy sau nó.
      // Cần reset để lần `fab.click()` bằng code sau đó không bị nuốt oan
      // (lich_lam_viec.html gọi kiểu đó để mở chat).
      setTimeout(function(){ suppressClick = false; }, 0);
    }
    moved = false;
  }
  fab.addEventListener('pointerup', zV2_fabDragEnd);
  fab.addEventListener('pointercancel', zV2_fabDragEnd);

  // Nuốt click ở pha capture của document: listener trên chính nút sẽ chạy SAU
  // zV2_open (cùng target thì thứ tự là thứ tự đăng ký), chặn không kịp.
  document.addEventListener('click', function(e){
    if (!suppressClick) return;
    if (!e.target || !e.target.closest || !e.target.closest('#_chat_fab')) return;
    e.preventDefault();
    e.stopPropagation();
  }, true);

  // ── Kéo bằng bàn phím: Tab tới nút rồi bấm mũi tên (Shift = bước dài) ──
  fab.addEventListener('keydown', function(e){
    var dx = 0, dy = 0;
    if      (e.key === 'ArrowLeft')  dx = -1;
    else if (e.key === 'ArrowRight') dx =  1;
    else if (e.key === 'ArrowUp')    dy = -1;
    else if (e.key === 'ArrowDown')  dy =  1;
    else return;
    e.preventDefault();                          // đừng để mũi tên cuộn trang
    var step = e.shiftKey ? STEP * 4 : STEP;
    var p = here();
    place(p.x + dx * step, p.y + dy * step, true);
  });

  // ── Khôi phục vị trí đã nhớ + bám theo khi đổi cỡ cửa sổ ──
  try {
    var saved = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (saved && typeof saved.rx === 'number' && typeof saved.ry === 'number'){
      ratio = saved;
      applyRatio();
    }
  } catch(_){}
  window.addEventListener('resize', applyRatio);

  // Trả nút về góc dưới-phải mặc định
  window.zV2_resetFabPos = function(){
    ratio = null; pos = null;
    fab.classList.remove('zV2_fab_moved');
    fab.style.removeProperty('--zfab-x');
    fab.style.removeProperty('--zfab-y');
    try { localStorage.removeItem(KEY); } catch(_){}
  };
}

// ---------- Bind events ----------
function zV2_bind(){
  // FAB — kéo thả bind TRƯỚC click để bộ nuốt click kịp chặn zV2_open
  zV2_initFabDrag();
  if ($fab) $fab.addEventListener('click', zV2_open);

  // Panel close
  if ($panelCloseBtn) $panelCloseBtn.addEventListener('click', zV2_close);

  // Rail tabs
  if ($railTin)      $railTin.addEventListener('click',      function(){ zV2_switchTab('tin-nhan'); });
  if ($railDanhba)   $railDanhba.addEventListener('click',   function(){ zV2_switchTab('danh-ba'); });
  if ($railSettings) $railSettings.addEventListener('click', function(){ try{ window.zV2_openSettings(); }catch(_){} });

  // Filter tabs
  if ($tabsFilter) $tabsFilter.addEventListener('click', zV2_onFilterClick);

  // Search box (other agents may attach handler too)
  if ($searchBox){
    $searchBox.addEventListener('input', function(e){
      window._zV2.searchQuery = (e.target.value || '').trim().toLowerCase();
      try {
        if (window._zV2.currentTab === 'tin-nhan') window.zV2_renderRooms && window.zV2_renderRooms();
        else                                       window.zV2_renderContacts && window.zV2_renderContacts();
      } catch(_){}
    });
  }

  // Main header actions — ℹ️ mở dropdown menu (ghim/ẩn/xoá)
  // Bind ở CAPTURE phase trên document để chắc chắn bắt click trước mọi handler khác
  document.addEventListener('click', function(ev){
    var btn = ev.target && ev.target.closest && ev.target.closest('#zV2_btn_info');
    if (!btn) return;
    ev.preventDefault();
    ev.stopPropagation();
    console.log('[zV2] btn_info clicked → openInfoMenu');
    if (typeof window.zV2_openInfoMenu === 'function') {
      window.zV2_openInfoMenu(btn);
    } else {
      alert('Lỗi: chức năng thông tin chưa load. F5 lại.');
    }
  }, true); /* capture: true */
  if ($mainBackBtn) $mainBackBtn.addEventListener('click', zV2_mobileBack);

  // Info panel
  if ($infoCloseBtn) $infoCloseBtn.addEventListener('click', function(){ window.zV2_closeInfoPanel(); });
  if ($infoTabs) $infoTabs.addEventListener('click', zV2_onInfoTabClick);

  // Composer — KHÔNG bind ở đây, zV2_composeBind() (msg.js) handle với guard _zV2Bound

  // Reply strip close
  if ($replyCloseBtn) $replyCloseBtn.addEventListener('click', function(){ window.zV2_clearReplyTo(); });

  // Scroll bottom btn
  if ($scrollBottomBtn) $scrollBottomBtn.addEventListener('click', function(){
    window.zV2_scrollToBottom();
    $scrollBottomBtn.classList.remove('visible', 'has-unread');
  });

  // Messages scroll listener
  if ($messagesScroll) $messagesScroll.addEventListener('scroll', zV2_onMessagesScroll);

  // ESC closes info panel first, then panel itself
  document.addEventListener('keydown', function(e){
    if (e.key !== 'Escape') return;
    if (!window._zV2.open) return;
    if (window._zV2.infoPanelOpen){
      window.zV2_closeInfoPanel();
      return;
    }
    zV2_close();
  });

  // Click outside panel = no-op (chat is modal-ish but persistent)
}

// ---------- Responsive breakpoint helper ----------
function zV2_applyBreakpoint(){
  if (!$panel) return;
  var w = window.innerWidth;
  $panel.classList.toggle('zV2-mobile', w < 600);
  $panel.classList.toggle('zV2-tablet', w >= 600 && w < 1024);
  $panel.classList.toggle('zV2-desktop', w >= 1024);
}

// ---------- Public surface: enter/exit room visual ----------
window.zV2_showChatSurface = window.zV2_showChatSurface || function(){
  if ($emptyMain)     $emptyMain.style.display     = 'none';
  if ($mainHeader)    $mainHeader.style.display    = '';
  if ($messagesScroll)$messagesScroll.style.display= '';
  if ($composeWrap)   $composeWrap.style.display   = '';
  if ($panel)         $panel.classList.add('show-main');
};
window.zV2_hideChatSurface = window.zV2_hideChatSurface || function(){
  if ($emptyMain)     $emptyMain.style.display     = '';
  if ($mainHeader)    $mainHeader.style.display    = 'none';
  if ($messagesScroll)$messagesScroll.style.display= 'none';
  if ($composeWrap)   $composeWrap.style.display   = 'none';
  if ($panel)         $panel.classList.remove('show-main');
};

// ---------- Apply current user to middle col header ----------
function zV2_applyCurrentUser(){
  var me = (typeof zV2_getCurrentUser === 'function')
    ? zV2_getCurrentUser()
    : { username: window.currentUsername || '', name: window.currentUserDisplayName || '' };
  zV2_renderMidHeaderAvatar(me);
  // Fetch /api/chat/me để lấy avatar_data thật (avatar nhân viên trong HCNS)
  fetch('/api/chat/me', { credentials: 'same-origin' })
    .then(function(r){ return r.ok ? r.json() : null; })
    .then(function(data){
      if (!data) return;
      var fullUser = {
        username: data.username,
        name: data.ho_ten || data.username,
        avatar_data: data.avatar_data,
        phong_ban: data.phong_ban,
        chuc_vu: data.chuc_vu,
      };
      if (window._zV2) _zV2.currentUser = fullUser;
      zV2_renderMidHeaderAvatar(fullUser);
    })
    .catch(function(){ /* silent */ });
}
function zV2_renderMidHeaderAvatar(me){
  var avEl = document.getElementById('zV2_mid_header_avatar');
  var nmEl = document.getElementById('zV2_mid_header_name');
  if (nmEl && me.name) nmEl.textContent = me.name;
  if (!avEl) return;
  if (me.avatar_data) {
    avEl.innerHTML = '<img src="' + me.avatar_data + '" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" />';
    avEl.style.background = 'transparent';
  } else if (me.name) {
    var ch = (me.name.charAt(0) || '?').toUpperCase();
    avEl.textContent = ch;
    var palette = ['#0B63CE','#1F6F72','#2E7D4F','#6B4E7D','#B02A18','#3D5A80','#A02C5A','#4A4A82'];
    var hash = 0;
    for (var i = 0; i < me.name.length; i++) hash = (hash * 31 + me.name.charCodeAt(i)) >>> 0;
    avEl.style.background = palette[hash % palette.length];
    avEl.style.color = '#fff';
  }
}
// Format relative time cho last_seen (giờ/ngày trước)
function zV2_formatLastSeen(unixSec){
  if (!unixSec) return 'Chưa từng truy cập';
  var nowSec = Math.floor(Date.now() / 1000);
  var diff = nowSec - unixSec;
  if (diff < 60) return 'Vừa truy cập';
  if (diff < 3600) return 'Hoạt động ' + Math.floor(diff/60) + ' phút trước';
  if (diff < 86400) return 'Hoạt động ' + Math.floor(diff/3600) + ' giờ trước';
  var days = Math.floor(diff/86400);
  if (days < 30) return 'Hoạt động ' + days + ' ngày trước';
  return 'Hoạt động lâu rồi';
}
// Lookup presence entry cho 1 username (online + last_seen_at)
function zV2_getPresence(username){
  if (!username) return null;
  var p = (window._zV2 && _zV2.presenceMap) || {};
  return p[username] || null;
}
// Wire call/video header buttons → placeholder modal (real WebRTC ngoài scope)
function zV2_wireHeaderActions(){
  var btnCall  = document.getElementById('zV2_btn_call');
  var btnVideo = document.getElementById('zV2_btn_video');
  var btnInfo  = document.getElementById('zV2_btn_info');
  if (btnCall && !btnCall._zV2Bound) {
    btnCall._zV2Bound = true;
    btnCall.addEventListener('click', function(){ zV2_openCallModal('voice'); });
  }
  if (btnVideo && !btnVideo._zV2Bound) {
    btnVideo._zV2Bound = true;
    btnVideo.addEventListener('click', function(){ zV2_openCallModal('video'); });
  }
  // btnInfo đã được skeleton zV2_bind() wire vào toggleInfoPanel — không bind đôi
}
// Tạo nhiệm vụ từ tin nhắn
window.zV2_openTaskModal = async function(msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  if (!(window._zV2 && window._zV2.users && window._zV2.users.length)) { try { await window.zV2_loadUsers(); } catch(e){} }
  var existing = document.getElementById('zV2_task_modal');
  if (existing) existing.remove();
  var users = ((window._zV2 && window._zV2.users) || []).filter(function(u){ return u.username !== ((window._zV2.currentUser && window._zV2.currentUser.username) || ''); });
  var ov = document.createElement('div');
  ov.id = 'zV2_task_modal';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(51,33,15,.42);z-index:2147483040;display:flex;align-items:center;justify-content:center;padding:16px;';
  ov.innerHTML =
    '<div style="background:#fff;border-radius:14px;padding:24px;width:420px;max-width:90vw;box-shadow:0 12px 40px rgba(0,0,0,.2);">' +
    '<div style="font-size:17px;font-weight:600;color:#0068FF;margin-bottom:14px;">Tạo nhiệm vụ từ tin nhắn</div>' +
    '<div style="background:var(--z-hover);border-radius:8px;padding:10px 12px;margin-bottom:14px;font-size:14px;color:var(--z-text);max-height:80px;overflow:hidden;">' +
      zV2_escapeHtml(zV2_truncate(msg.content || msg.file_name || '[Đính kèm]', 160)) +
    '</div>' +
    '<label style="display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;">Tiêu đề nhiệm vụ</label>' +
    '<input id="zV2_task_title" type="text" value="' + zV2_escapeHtml(zV2_truncate(msg.content || '', 80)) + '" style="width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;margin-bottom:12px;outline:none;box-sizing:border-box;" />' +
    '<label style="display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;">Mô tả chi tiết</label>' +
    '<textarea id="zV2_task_desc" rows="2" placeholder="Nội dung công việc cần làm…" style="width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;margin-bottom:12px;outline:none;box-sizing:border-box;resize:vertical;font-family:inherit;line-height:1.5;"></textarea>' +
    '<label style="display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;">Giao cho</label>' +
    '<select id="zV2_task_assignee" style="width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;margin-bottom:18px;outline:none;background:#fff;">' +
      '<option value="">— Không chỉ định —</option>' +
      users.map(function(u){
        return '<option value="' + zV2_escapeHtml(u.username) + '">' + zV2_escapeHtml(u.ho_ten || u.username) + (u.chuc_vu ? ' (' + zV2_escapeHtml(u.chuc_vu) + ')' : '') + '</option>';
      }).join('') +
    '</select>' +
    '<div style="display:flex;gap:10px;margin-bottom:18px;">' +
      '<div style="flex:1;min-width:0;">' +
        '<label style="display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;">Hạn hoàn thành</label>' +
        '<input id="zV2_task_deadline" type="date" style="width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;outline:none;background:#fff;box-sizing:border-box;" />' +
      '</div>' +
      '<div style="flex:1;min-width:0;">' +
        '<label style="display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;">Ưu tiên</label>' +
        '<select id="zV2_task_prio" style="width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;outline:none;background:#fff;box-sizing:border-box;">' +
          '<option value="binh_thuong">Bình thường</option>' +
          '<option value="thap">Thấp</option>' +
          '<option value="cao">Cao</option>' +
          '<option value="khan_cap">Khẩn cấp</option>' +
        '</select>' +
      '</div>' +
    '</div>' +
    '<div style="display:flex;gap:10px;justify-content:flex-end;">' +
    '<button id="zV2_task_cancel" style="padding:9px 18px;border-radius:8px;border:1px solid var(--z-border);background:#fff;color:var(--z-text2);font-weight:600;cursor:pointer;">Hủy</button>' +
    '<button id="zV2_task_submit" style="padding:9px 18px;border-radius:8px;border:none;background:#0068FF;color:#fff;font-weight:600;cursor:pointer;">Tạo nhiệm vụ</button>' +
    '</div>' +
    '</div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e){ if (e.target === ov) document.body.removeChild(ov); });
  ov.querySelector('#zV2_task_cancel').addEventListener('click', function(){ document.body.removeChild(ov); });
  ov.querySelector('#zV2_task_submit').addEventListener('click', async function(){
    var title = (document.getElementById('zV2_task_title') || {}).value || '';
    var desc = (document.getElementById('zV2_task_desc') || {}).value || '';
    var assignee = (document.getElementById('zV2_task_assignee') || {}).value || '';
    var deadline = (document.getElementById('zV2_task_deadline') || {}).value || '';
    var prio = (document.getElementById('zV2_task_prio') || {}).value || 'binh_thuong';
    if (!title.trim()) { zV2_toast('Vui lòng nhập tiêu đề', 'error'); return; }
    try {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/task', {
        method: 'POST',
        body: { title: title.trim(), mo_ta: desc || null, assignee: assignee || null, deadline: deadline || null, uu_tien: prio }
      });
      zV2_toast('Đã tạo nhiệm vụ', 'success');
      document.body.removeChild(ov);
    } catch(e) {
      zV2_toast('Tạo nhiệm vụ thất bại: ' + (e.message || ''), 'error');
    }
  });
};

// ── Tạo LỊCH (calendar event) từ tin nhắn — anh Quang 2026-08-20 ──
window.zV2_openEventModal = async function(msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  if (!(window._zV2 && window._zV2.users && window._zV2.users.length)) { try { await window.zV2_loadUsers(); } catch(e){} }
  var ex = document.getElementById('zV2_event_modal'); if (ex) ex.remove();
  var me = (window._zV2.currentUser && window._zV2.currentUser.username) || '';
  var users = ((window._zV2 && window._zV2.users) || []).filter(function(u){ return u.username !== me && u.username !== 'mai_ai'; });
  function _p(n){ return (n<10?'0':'')+n; }
  function _loc(d){ return d.getFullYear()+'-'+_p(d.getMonth()+1)+'-'+_p(d.getDate())+'T'+_p(d.getHours())+':'+_p(d.getMinutes()); }
  var _s = new Date(); if (_s.getMinutes()>0) _s.setHours(_s.getHours()+1); _s.setMinutes(0,0,0);
  var _e = new Date(_s.getTime()+60*60000);
  var startV = _loc(_s), endV = _loc(_e);
  var titleGuess = zV2_truncate((msg.content || '').replace(/\n/g,' ').trim() || 'Cuộc họp', 70);
  var lbl = 'display:block;font-size:12.5px;font-weight:600;color:var(--z-text2);margin-bottom:4px;';
  var inp = 'width:100%;padding:8px 11px;border:1px solid var(--z-border);border-radius:8px;font-size:14.5px;outline:none;background:#fff;box-sizing:border-box;';
  var ov = document.createElement('div');
  ov.id = 'zV2_event_modal';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(51,33,15,.42);z-index:2147483040;display:flex;align-items:center;justify-content:center;padding:16px;';
  ov.innerHTML =
    '<div style="background:#fff;border-radius:14px;padding:22px 22px 20px;width:520px;max-width:94vw;max-height:92vh;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.25);">' +
    '<div style="font-size:17px;font-weight:700;color:#0068FF;margin-bottom:16px;">📅 Tạo lịch từ tin nhắn</div>' +
    '<label style="'+lbl+'">Tiêu đề <span style="color:#e53">*</span></label>' +
    '<input id="zV2_ev_title" type="text" value="'+zV2_escapeHtml(titleGuess)+'" style="'+inp+'margin-bottom:12px;"/>' +
    '<label style="'+lbl+'">Mô tả</label>' +
    '<textarea id="zV2_ev_desc" rows="2" placeholder="Nội dung sự kiện…" style="'+inp+'margin-bottom:12px;resize:vertical;font-family:inherit;line-height:1.5;"></textarea>' +
    '<div style="display:flex;gap:10px;margin-bottom:10px;">' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Bắt đầu <span style="color:#e53">*</span></label><input id="zV2_ev_start" type="datetime-local" value="'+startV+'" style="'+inp+'"/></div>' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Kết thúc <span style="color:#e53">*</span></label><input id="zV2_ev_end" type="datetime-local" value="'+endV+'" style="'+inp+'"/></div>' +
    '</div>' +
    '<label style="display:flex;align-items:center;gap:7px;font-size:14px;color:var(--z-text);margin-bottom:12px;cursor:pointer;"><input type="checkbox" id="zV2_ev_allday"/> Cả ngày</label>' +
    '<div style="display:flex;gap:10px;margin-bottom:12px;">' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Lặp lại</label><select id="zV2_ev_recur" style="'+inp+'"><option value="none">Không lặp</option><option value="daily">Hàng ngày</option><option value="weekday">Ngày làm việc (T2–T6)</option><option value="weekly">Hàng tuần</option><option value="monthly">Hàng tháng</option></select></div>' +
      '<div style="flex:1;min-width:0;" id="zV2_ev_recuntil_wrap"><label style="'+lbl+'">Lặp đến ngày</label><input id="zV2_ev_recuntil" type="date" style="'+inp+'"/></div>' +
    '</div>' +
    '<div style="display:flex;gap:10px;margin-bottom:12px;">' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Loại</label><select id="zV2_ev_type" style="'+inp+'"><option value="shared">Chia sẻ (mời người)</option><option value="personal">Cá nhân</option><option value="public">Công khai</option></select></div>' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Nhắc trước</label><select id="zV2_ev_remind" style="'+inp+'"><option value="">Không</option><option value="5">5 phút</option><option value="15">15 phút</option><option value="30" selected>30 phút</option><option value="60">1 giờ</option><option value="120">2 giờ</option><option value="1440">1 ngày</option></select></div>' +
    '</div>' +
    '<div style="display:flex;gap:10px;margin-bottom:14px;">' +
      '<div style="flex:2;min-width:0;"><label style="'+lbl+'">Địa điểm</label><input id="zV2_ev_loc" type="text" placeholder="Phòng họp / online…" style="'+inp+'"/></div>' +
      '<div style="flex:1;min-width:0;"><label style="'+lbl+'">Màu</label><input id="zV2_ev_color" type="color" value="#0084ff" style="'+inp+'height:38px;padding:3px;"/></div>' +
    '</div>' +
    '<label style="'+lbl+'">Mời tham gia</label>' +
    '<div id="zV2_ev_att" style="max-height:140px;overflow:auto;border:1px solid var(--z-border);border-radius:8px;padding:6px 10px;margin-bottom:18px;">' +
      (users.length ? users.map(function(u){ return '<label style="display:flex;gap:8px;align-items:center;padding:4px 2px;font-size:14px;cursor:pointer;color:var(--z-text);"><input type="checkbox" class="zV2_ev_att_cb" value="'+zV2_escapeHtml(u.username)+'"/> '+zV2_escapeHtml(u.ho_ten||u.username)+(u.chuc_vu?' <span style="color:var(--z-muted);font-size:12px;">('+zV2_escapeHtml(u.chuc_vu)+')</span>':'')+'</label>'; }).join('') : '<div style="color:var(--z-muted);font-size:13px;padding:4px 0;">Không có ai để mời</div>') +
    '</div>' +
    '<div style="display:flex;gap:10px;justify-content:flex-end;">' +
    '<button id="zV2_ev_cancel" style="padding:9px 18px;border-radius:8px;border:1px solid var(--z-border);background:#fff;color:var(--z-text2);font-weight:600;cursor:pointer;">Hủy</button>' +
    '<button id="zV2_ev_submit" style="padding:9px 18px;border-radius:8px;border:none;background:#0068FF;color:#fff;font-weight:600;cursor:pointer;">Tạo lịch</button>' +
    '</div></div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(evt){ if (evt.target === ov) ov.remove(); });
  ov.querySelector('#zV2_ev_cancel').addEventListener('click', function(){ ov.remove(); });
  var _recSel = ov.querySelector('#zV2_ev_recur'), _recWrap = ov.querySelector('#zV2_ev_recuntil_wrap');
  function _syncRec(){ _recWrap.style.visibility = (_recSel.value && _recSel.value !== 'none') ? 'visible' : 'hidden'; }
  _recSel.addEventListener('change', _syncRec); _syncRec();
  ov.querySelector('#zV2_ev_submit').addEventListener('click', async function(){
    var title = (ov.querySelector('#zV2_ev_title')||{}).value || '';
    var desc = (ov.querySelector('#zV2_ev_desc')||{}).value || '';
    var start = (ov.querySelector('#zV2_ev_start')||{}).value || '';
    var end = (ov.querySelector('#zV2_ev_end')||{}).value || '';
    var allday = !!((ov.querySelector('#zV2_ev_allday')||{}).checked);
    var recur = (ov.querySelector('#zV2_ev_recur')||{}).value || 'none';
    var recuntil = (ov.querySelector('#zV2_ev_recuntil')||{}).value || '';
    var etype = (ov.querySelector('#zV2_ev_type')||{}).value || 'shared';
    var remindV = (ov.querySelector('#zV2_ev_remind')||{}).value;
    var loc = (ov.querySelector('#zV2_ev_loc')||{}).value || '';
    var color = (ov.querySelector('#zV2_ev_color')||{}).value || '';
    if (!title.trim()) { zV2_toast('Vui lòng nhập tiêu đề', 'error'); return; }
    if (!start || !end) { zV2_toast('Chọn giờ bắt đầu và kết thúc', 'error'); return; }
    if (end <= start) { zV2_toast('Giờ kết thúc phải sau giờ bắt đầu', 'error'); return; }
    var attendees = Array.prototype.slice.call(ov.querySelectorAll('.zV2_ev_att_cb:checked')).map(function(c){ return c.value; });
    try {
      var r = await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/event', {
        method: 'POST',
        body: { title: title.trim(), description: desc||null, start_dt: start, end_dt: end, all_day: allday,
                event_type: etype, recurrence: (recur==='none'?null:recur),
                recurrence_until: (recur!=='none' && recuntil ? recuntil : null),
                color: color||null, location: loc||null,
                reminder_minutes: (remindV===''? null : parseInt(remindV,10)), attendees: attendees }
      });
      var n = (r && r.invited && r.invited.length) || 0;
      zV2_toast('Đã tạo lịch' + (n ? ' · mời ' + n + ' người' : ''), 'success');
      ov.remove();
    } catch(e) {
      zV2_toast('Tạo lịch thất bại: ' + (e.message || ''), 'error');
    }
  });
};

// ── Tạo THẺ PHÊ DUYỆT từ tin nhắn — anh Quang 2026-08-20 ──
window.zV2_openApprovalModal = async function(msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  if (!(window._zV2 && window._zV2.users && window._zV2.users.length)) { try { await window.zV2_loadUsers(); } catch(e){} }
  var ex = document.getElementById('zV2_approval_modal'); if (ex) ex.remove();
  var me = (window._zV2.currentUser && window._zV2.currentUser.username) || '';
  var users = ((window._zV2 && window._zV2.users) || []).filter(function(u){ return u.username !== me && u.username !== 'mai_ai'; });
  var titleGuess = zV2_truncate((msg.content || '').replace(/\n/g,' ').trim() || 'Yêu cầu duyệt', 70);
  var lbl = 'display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;';
  var inp = 'width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;outline:none;background:#fff;box-sizing:border-box;';
  var ov = document.createElement('div'); ov.id = 'zV2_approval_modal';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(51,33,15,.42);z-index:2147483040;display:flex;align-items:center;justify-content:center;padding:16px;';
  ov.innerHTML =
    '<div style="background:#fff;border-radius:14px;padding:24px;width:440px;max-width:92vw;max-height:90vh;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.2);">' +
    '<div style="font-size:17px;font-weight:700;color:#dd8a00;margin-bottom:14px;">🔐 Tạo yêu cầu phê duyệt</div>' +
    '<label style="'+lbl+'">Nội dung cần duyệt</label>' +
    '<input id="zV2_apr_title" type="text" value="'+zV2_escapeHtml(titleGuess)+'" style="'+inp+'margin-bottom:12px;"/>' +
    '<label style="'+lbl+'">Người duyệt</label>' +
    '<select id="zV2_apr_approver" style="'+inp+'margin-bottom:12px;"><option value="">— Chọn người duyệt —</option>' +
      users.map(function(u){ return '<option value="'+zV2_escapeHtml(u.username)+'">'+zV2_escapeHtml(u.ho_ten||u.username)+(u.chuc_vu?' ('+zV2_escapeHtml(u.chuc_vu)+')':'')+'</option>'; }).join('') +
    '</select>' +
    '<label style="'+lbl+'">Ghi chú (tuỳ chọn)</label>' +
    '<textarea id="zV2_apr_note" rows="2" placeholder="Thông tin thêm cho người duyệt…" style="'+inp+'margin-bottom:18px;resize:vertical;font-family:inherit;line-height:1.5;"></textarea>' +
    '<div style="display:flex;gap:10px;justify-content:flex-end;">' +
    '<button id="zV2_apr_cancel" style="padding:9px 18px;border-radius:8px;border:1px solid var(--z-border);background:#fff;color:var(--z-text2);font-weight:600;cursor:pointer;">Hủy</button>' +
    '<button id="zV2_apr_submit" style="padding:9px 18px;border-radius:8px;border:none;background:#dd8a00;color:#fff;font-weight:600;cursor:pointer;">Gửi duyệt</button>' +
    '</div></div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e){ if (e.target === ov) ov.remove(); });
  ov.querySelector('#zV2_apr_cancel').addEventListener('click', function(){ ov.remove(); });
  ov.querySelector('#zV2_apr_submit').addEventListener('click', async function(){
    var title = (ov.querySelector('#zV2_apr_title')||{}).value || '';
    var approver = (ov.querySelector('#zV2_apr_approver')||{}).value || '';
    var note = (ov.querySelector('#zV2_apr_note')||{}).value || '';
    if (!title.trim()) { zV2_toast('Nhập nội dung cần duyệt', 'error'); return; }
    if (!approver) { zV2_toast('Chọn người duyệt', 'error'); return; }
    try {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/approval', { method:'POST', body:{ title:title.trim(), approver:approver, note:note||null } });
      zV2_toast('Đã gửi yêu cầu duyệt', 'success'); ov.remove();
    } catch(e) { zV2_toast('Gửi thất bại: ' + (e.message||''), 'error'); }
  });
};

// ── Tạo THẺ BÌNH CHỌN từ tin nhắn — anh Quang 2026-08-20 ──
window.zV2_openPollModal = function(msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  var ex = document.getElementById('zV2_poll_modal'); if (ex) ex.remove();
  var qGuess = zV2_truncate((msg.content || '').replace(/\n/g,' ').trim(), 80);
  var lbl = 'display:block;font-size:13px;font-weight:600;color:var(--z-text2);margin-bottom:4px;';
  var inp = 'width:100%;padding:9px 12px;border:1px solid var(--z-border);border-radius:8px;font-size:15px;outline:none;background:#fff;box-sizing:border-box;';
  var ov = document.createElement('div'); ov.id = 'zV2_poll_modal';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(51,33,15,.42);z-index:2147483040;display:flex;align-items:center;justify-content:center;padding:16px;';
  ov.innerHTML =
    '<div style="background:#fff;border-radius:14px;padding:24px;width:440px;max-width:92vw;max-height:90vh;overflow:auto;box-shadow:0 12px 40px rgba(0,0,0,.2);">' +
    '<div style="font-size:17px;font-weight:700;color:#7c5cff;margin-bottom:14px;">📊 Tạo bình chọn</div>' +
    '<label style="'+lbl+'">Câu hỏi</label>' +
    '<input id="zV2_poll_q" type="text" value="'+zV2_escapeHtml(qGuess)+'" placeholder="VD: Chọn giờ họp tuần?" style="'+inp+'margin-bottom:12px;"/>' +
    '<label style="'+lbl+'">Các lựa chọn <span style="font-weight:400;color:var(--z-muted);">(mỗi dòng 1 lựa chọn, ≥2)</span></label>' +
    '<textarea id="zV2_poll_opts" rows="4" placeholder="9h sáng&#10;14h chiều&#10;16h chiều" style="'+inp+'margin-bottom:18px;resize:vertical;font-family:inherit;line-height:1.6;"></textarea>' +
    '<div style="display:flex;gap:10px;justify-content:flex-end;">' +
    '<button id="zV2_poll_cancel" style="padding:9px 18px;border-radius:8px;border:1px solid var(--z-border);background:#fff;color:var(--z-text2);font-weight:600;cursor:pointer;">Hủy</button>' +
    '<button id="zV2_poll_submit" style="padding:9px 18px;border-radius:8px;border:none;background:#7c5cff;color:#fff;font-weight:600;cursor:pointer;">Tạo bình chọn</button>' +
    '</div></div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e){ if (e.target === ov) ov.remove(); });
  ov.querySelector('#zV2_poll_cancel').addEventListener('click', function(){ ov.remove(); });
  ov.querySelector('#zV2_poll_submit').addEventListener('click', async function(){
    var q = (ov.querySelector('#zV2_poll_q')||{}).value || '';
    var raw = (ov.querySelector('#zV2_poll_opts')||{}).value || '';
    var options = raw.split('\n').map(function(s){ return s.trim(); }).filter(function(s){ return s; });
    if (!q.trim()) { zV2_toast('Nhập câu hỏi', 'error'); return; }
    if (options.length < 2) { zV2_toast('Cần ít nhất 2 lựa chọn', 'error'); return; }
    try {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/poll', { method:'POST', body:{ question:q.trim(), options:options } });
      zV2_toast('Đã tạo bình chọn', 'success'); ov.remove();
    } catch(e) { zV2_toast('Tạo thất bại: ' + (e.message||''), 'error'); }
  });
};

// ── localStorage helpers cho pin/hide conversation (client-side) ──
function zV2_lsGet(key){
  try { var v = localStorage.getItem(key); return v ? JSON.parse(v) : []; } catch(_){ return []; }
}
function zV2_lsSet(key, arr){
  try { localStorage.setItem(key, JSON.stringify(arr)); } catch(_){}
}
window.zV2_pinnedRooms = function(){ return new Set(zV2_lsGet('zV2_pinned_rooms')); };
window.zV2_hiddenRooms = function(){ return new Set(zV2_lsGet('zV2_hidden_rooms')); };
window.zV2_togglePinRoom = function(roomId){
  var s = zV2_pinnedRooms();
  if (s.has(roomId)) s.delete(roomId); else s.add(roomId);
  zV2_lsSet('zV2_pinned_rooms', Array.from(s));
  if (typeof zV2_renderRooms === 'function') zV2_renderRooms();
};
window.zV2_hideRoom = function(roomId){
  var s = zV2_hiddenRooms();
  s.add(roomId);
  zV2_lsSet('zV2_hidden_rooms', Array.from(s));
  if (typeof zV2_renderRooms === 'function') zV2_renderRooms();
  // Đóng main view (room đã ẩn, không nên hiện messages)
  var emptyEl = document.getElementById('zV2_empty_main');
  var headerEl = document.getElementById('zV2_main_header');
  var scrollEl = document.getElementById('zV2_messages_scroll');
  var composeEl= document.getElementById('zV2_compose_wrap');
  _zV2.currentRoomId = null;
  if (emptyEl)  emptyEl.style.display  = '';
  if (headerEl) headerEl.style.display = 'none';
  if (scrollEl) scrollEl.style.display = 'none';
  if (composeEl)composeEl.style.display= 'none';
};

// ── Dropdown menu khi click ℹ️ trên header ──
window.zV2_openInfoMenu = function(anchorEl){
  console.log('[zV2_openInfoMenu] called, anchor=', anchorEl, 'currentRoomId=', window._zV2 && _zV2.currentRoomId);
  // Close existing
  var existing = document.getElementById('zV2_info_menu');
  if (existing) { existing.remove(); console.log('[zV2_openInfoMenu] closed existing'); return; }
  var roomId = (window._zV2 && _zV2.currentRoomId) || null;
  if (!roomId) {
    if (typeof zV2_toast === 'function') zV2_toast('Chọn cuộc trò chuyện trước', 'info');
    return;
  }
  var isPinned = zV2_pinnedRooms().has(roomId);
  var ICON = {
    pin: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg>',
    hide: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>',
    trash: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>',
    members: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>'
  };
  var menu = document.createElement('div');
  menu.id = 'zV2_info_menu';
  menu.className = 'zV2_info_menu';
  var room = (_zV2.rooms || []).find(function(r){ return r.id === roomId; });
  var isGroup = room && room.type && room.type !== 'direct';
  menu.innerHTML =
    '<div class="zV2_info_menu_item" data-act="pin">' + ICON.pin + '<span>' + (isPinned ? 'Bỏ ghim hội thoại' : 'Ghim lên đầu danh sách') + '</span></div>' +
    (isGroup ? '<div class="zV2_info_menu_item" data-act="members">' + ICON.members + '<span>Xem thành viên nhóm</span></div>' : '') +
    '<div class="zV2_info_menu_item" data-act="hide">' + ICON.hide + '<span>Ẩn cuộc trò chuyện</span></div>' +
    '<div class="zV2_info_menu_item danger" data-act="delete">' + ICON.trash + '<span>Xoá cuộc trò chuyện</span></div>';
  document.body.appendChild(menu);
  // Position dưới anchorEl, lệch trái
  var rect = anchorEl.getBoundingClientRect();
  var menuRect = menu.getBoundingClientRect();
  var left = rect.right - menuRect.width;
  if (left < 8) left = 8;
  if (left + menuRect.width > window.innerWidth - 8) left = window.innerWidth - menuRect.width - 8;
  var top = rect.bottom + 6;
  menu.style.left = left + 'px';
  menu.style.top  = top  + 'px';
  // Click item
  menu.addEventListener('click', function(ev){
    var item = ev.target.closest('.zV2_info_menu_item');
    if (!item) return;
    var act = item.dataset.act;
    menu.remove();
    if (act === 'pin') zV2_togglePinRoom(roomId);
    else if (act === 'hide') {
      if (confirm('Ẩn cuộc trò chuyện này? Bạn có thể tìm lại qua Danh bạ.')) zV2_hideRoom(roomId);
    } else if (act === 'delete') zV2_deleteConversation(roomId);
    else if (act === 'members') {
      if (typeof zV2_openInfoPanel === 'function') {
        zV2_openInfoPanel();
        if (typeof zV2_switchInfoTab === 'function') setTimeout(function(){ zV2_switchInfoTab('thanh-vien'); }, 30);
      }
    }
  });
  // Click ngoài → đóng
  setTimeout(function(){
    document.addEventListener('click', function onDoc(e){
      if (!menu.contains(e.target)) {
        menu.remove();
        document.removeEventListener('click', onDoc);
      }
    });
  }, 0);
};

// Xoá toàn bộ cuộc hội thoại (chỉ cho DM hoặc admin group)
window.zV2_deleteConversation = function(roomId) {
  var room = (_zV2.rooms || []).find(function(r){ return r.id === roomId; });
  if (!room) return;
  var displayName = room.display_name || room.name;
  var isDirect = room.type === 'direct';
  var actionLabel = isDirect ? 'rời cuộc trò chuyện' : 'rời nhóm';
  if (!confirm('Bạn có chắc muốn ' + actionLabel + ' với "' + displayName + '"? Tin nhắn sẽ không còn hiện với bạn nữa.')) return;
  zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/leave', { method: 'POST' })
    .then(function(){
      zV2_toast('Đã ' + actionLabel, 'success');
      // Remove khỏi _zV2.rooms + re-render + đóng main
      _zV2.rooms = (_zV2.rooms || []).filter(function(r){ return r.id !== roomId; });
      _zV2.currentRoomId = null;
      if (typeof zV2_renderRooms === 'function') zV2_renderRooms();
      var emptyEl = document.getElementById('zV2_empty_main');
      var headerEl = document.getElementById('zV2_main_header');
      var scrollEl = document.getElementById('zV2_messages_scroll');
      var composeEl= document.getElementById('zV2_compose_wrap');
      if (emptyEl)  emptyEl.style.display  = '';
      if (headerEl) headerEl.style.display = 'none';
      if (scrollEl) scrollEl.style.display = 'none';
      if (composeEl)composeEl.style.display= 'none';
    })
    .catch(function(e){ zV2_toast('Không xoá được: ' + (e.message || ''), 'error'); });
};

function zV2_openDirectCallModal(displayName, mode){
  var icon = mode === 'video' ? '' : '';
  var label = mode === 'video' ? 'Gọi video' : 'Gọi thoại';
  var ov = document.createElement('div');
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(51,33,15,.32);z-index:99999;display:flex;align-items:center;justify-content:center;padding:16px;';
  ov.innerHTML =
    '<div style="background:var(--z-text);color:#fff;border-radius:18px;padding:32px 28px;width:100%;max-width:340px;text-align:center;font-family:inherit;">' +
    '<div style="font-size:22px;margin-bottom:12px;">' + icon + '</div>' +
    '<div style="font-size:17px;font-weight:600;margin-bottom:6px;">' + label + '</div>' +
    '<div style="font-size:15px;opacity:.85;margin-bottom:8px;">Đang gọi cho <b>' + (displayName || '?') + '</b>...</div>' +
    '<div style="font-size:13px;opacity:.65;margin-bottom:20px;">(Tính năng đang phát triển)</div>' +
    '<button id="zV2_call_close" style="background:var(--z-badge);color:#fff;border:none;padding:10px 22px;border-radius:24px;font-size:15px;font-weight:600;cursor:pointer;">Kết thúc</button>' +
    '</div>';
  document.body.appendChild(ov);
  ov.addEventListener('click', function(e){ if (e.target === ov) document.body.removeChild(ov); });
  ov.querySelector('#zV2_call_close').addEventListener('click', function(){ document.body.removeChild(ov); });
}
function zV2_openCallModal(mode){
  // Goi WebRTC that (module zCall) - thay modal placeholder cu
  if (window.zCall){
    if (mode === 'video') window.zCall.startVideo();
    else window.zCall.startAudio();
    return;
  }
  alert('Tính năng gọi chưa sẵn sàng — vui lòng tải lại trang (Ctrl+Shift+R).');
}

// ---------- Init bootstrap ----------
function zV2_init(){
  // Guard idempotent — gọi từ nhiều DOMContentLoaded boot block chỉ chạy 1 lần
  if (window._zV2 && window._zV2._initDone) return;
  try {
    zV2_cacheRefs();
    zV2_bind();
    zV2_applyBreakpoint();
    window.addEventListener('resize', zV2_applyBreakpoint);
    zV2_applyCurrentUser();
    zV2_wireHeaderActions();
    if (typeof window.zV2_wireUpload === 'function') zV2_wireUpload();
    zV2_switchTab(window._zV2.currentTab || 'tin-nhan');
    // Early init: load rooms + SSE để FAB badge + notification hoạt động ngay cả khi chưa mở widget
    setTimeout(function(){
      try { window.zV2_loadRooms && window.zV2_loadRooms(); } catch(_){}
      try { window.zV2_initSSE && window.zV2_initSSE(); } catch(_){}
    }, 500);
    // Hint to current user name if globally available
    try {
      var u = (window.CURRENT_USER || window._user || {});
      if (u && u.name && $midName) $midName.textContent = u.name;
      if (u && u.avatar && $midAvatar){
        $midAvatar.innerHTML = '<img src="' + u.avatar + '" alt="">';
      } else if (u && u.name && $midAvatar){
        $midAvatar.textContent = (u.name.trim().charAt(0) || 'U').toUpperCase();
      }
    } catch(_){}
    window._zV2._inited = true;
    window._zV2._initDone = true;
  } catch(err){
    console.error('[zV2] init error', err);
  }
}
window.zV2_init = zV2_init;

if (document.readyState === 'loading'){
  document.addEventListener('DOMContentLoaded', zV2_init);
} else {
  zV2_init();
}

// END_SKELETON_JS — other agents append here

/* ==== INDEXEDDB PERSISTENT MESSAGE CACHE ==== */
(function () {
  var DB_NAME  = 'zV2Chat_v2';
  var DB_VER   = 1;
  var STORE    = 'msgs';
  var MAX_MSGS = 50;  // giữ tối đa 50 tin/phòng
  var _db = null;

  function openDB() {
    return new Promise(function (res, rej) {
      if (_db) { res(_db); return; }
      var r = indexedDB.open(DB_NAME, DB_VER);
      r.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE)) {
          var st = db.createObjectStore(STORE, { keyPath: ['room_id', 'id'] });
          st.createIndex('by_room', 'room_id');
        }
      };
      r.onsuccess = function (e) { _db = e.target.result; res(_db); };
      r.onerror   = function ()  { rej(r.error); };
    });
  }

  window.zV2_dbGet = function (roomId) {
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var tx  = db.transaction(STORE, 'readonly');
        var req = tx.objectStore(STORE).index('by_room').getAll(IDBKeyRange.only(roomId));
        req.onsuccess = function () {
          res((req.result || []).sort(function (a, b) { return a.id - b.id; }));
        };
        req.onerror = function () { rej(req.error); };
      });
    });
  };

  window.zV2_dbSave = function (roomId, msgs) {
    if (!msgs || !msgs.length) return Promise.resolve();
    return openDB().then(function (db) {
      return new Promise(function (res, rej) {
        var tx    = db.transaction(STORE, 'readwrite');
        var store = tx.objectStore(STORE);
        // Upsert messages
        msgs.forEach(function (m) {
          store.put(Object.assign({}, m, { room_id: roomId, id: Number(m.id) }));
        });
        // Trim: giữ MAX_MSGS tin mới nhất — chạy sau khi upsert xong
        tx.oncomplete = function () {
          openDB().then(function (db2) {
            var tx2  = db2.transaction(STORE, 'readwrite');
            var idx2 = tx2.objectStore(STORE).index('by_room');
            var cntReq = idx2.count(IDBKeyRange.only(roomId));
            cntReq.onsuccess = function () {
              var excess = cntReq.result - MAX_MSGS;
              if (excess <= 0) { res(); return; }
              var curReq = idx2.openCursor(IDBKeyRange.only(roomId));
              curReq.onsuccess = function (ev) {
                var cur = ev.target.result;
                if (cur && excess > 0) { cur.delete(); excess--; cur.continue(); }
                else res();
              };
            };
          }).catch(res);
        };
        tx.onerror = function () { rej(tx.error); };
      });
    });
  };

  window.zV2_dbLastId = function (roomId) {
    return window.zV2_dbGet(roomId).then(function (msgs) {
      return msgs.length ? msgs[msgs.length - 1].id : null;
    });
  };
})();

/* ==== ZALO V2: CONVERSATION LIST + CONTACTS ==== */

// ---------- Utility helpers (idempotent: only define if skeleton didn't) ----------
if (typeof window.zV2_escapeHtml !== 'function') {
  window.zV2_escapeHtml = function (str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };
}
const _zV2_escapeHtml = window.zV2_escapeHtml;

if (typeof window.zV2_hashColor !== 'function') {
  window.zV2_hashColor = function (str) {
    const palette = ['#0B63CE', '#1F6F72', '#2E7D4F', '#6B4E7D', '#B02A18', '#3D5A80', '#A02C5A', '#4A4A82'];
    const s = String(str || '');
    let h = 0;
    for (let i = 0; i < s.length; i++) {
      h = (h * 31 + s.charCodeAt(i)) >>> 0;
    }
    return palette[h % palette.length];
  };
}
const _zV2_hashColor = window.zV2_hashColor;

if (typeof window.zV2_formatTime !== 'function') {
  window.zV2_formatTime = function (iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const sameDay = d.getFullYear() === now.getFullYear()
      && d.getMonth() === now.getMonth()
      && d.getDate() === now.getDate();
    if (sameDay) {
      const hh = String(d.getHours()).padStart(2, '0');
      const mm = String(d.getMinutes()).padStart(2, '0');
      return `${hh}:${mm}`;
    }
    const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const startDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffDays = Math.round((startToday - startDay) / 86400000);
    if (diffDays === 1) return 'Hôm qua';
    if (diffDays > 1 && diffDays < 7) {
      const names = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7'];
      return names[d.getDay()];
    }
    const dd = String(d.getDate()).padStart(2, '0');
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    return `${dd}/${mo}`;
  };
}
const _zV2_formatTime = window.zV2_formatTime;

function _zV2_truncate(s, n) {
  s = String(s == null ? '' : s);
  if (s.length <= n) return s;
  return s.slice(0, n) + '…';
}

function _zV2_getMe() {
  if (window.currentUsername) return window.currentUsername;
  if (window._zV2 && window._zV2.me) return window._zV2.me;
  try {
    const m = document.cookie.match(/(?:^|;\s*)username=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);
  } catch (_) {}
  return null;
}

function _zV2_initial(name) {
  const s = String(name || '?').trim();
  if (!s) return '?';
  return s.charAt(0).toUpperCase();
}

function _zV2_avatarHTML(name, url, size) {
  const px = size || 44;
  const fs = Math.round(px * 0.42);
  const initSpan = `<span style="display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#fff;font-weight:600;font-size:${fs}px;">${_zV2_escapeHtml(_zV2_initial(name))}</span>`;
  if (url) {
    // img overlay trên initials — nếu 404 tự hide để lộ chữ cái bên dưới
    return initSpan +
      `<img src="${_zV2_escapeHtml(url)}" alt="" style="position:absolute;inset:0;width:100%;height:100%;border-radius:50%;object-fit:cover;" onerror="this.style.display='none'" />`;
  }
  return initSpan;
}

function _zV2_debounce(fn, ms) {
  let t;
  return function () {
    const args = arguments;
    const ctx = this;
    clearTimeout(t);
    t = setTimeout(() => fn.apply(ctx, args), ms);
  };
}

// ---------- Rooms ----------

window.zV2_loadRooms = async function () {
  // Hiển thị cache ngay lập tức nếu có và < 60s tuổi
  try {
    var cached = JSON.parse(localStorage.getItem('zV2_rooms_cache') || 'null');
    if (cached && (Date.now() - cached.ts) < 60000 && cached.data) {
      _zV2.rooms = cached.data;
      zV2_renderContacts(cached.data);
    }
  } catch(_) {}

  // Vẫn fetch API để cập nhật fresh data
  try {
    const res = await fetch('/api/chat/rooms', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const rooms = Array.isArray(data) ? data : (data.rooms || []);
    rooms.sort((a, b) => {
      const ap = a.pinned ? 1 : 0;
      const bp = b.pinned ? 1 : 0;
      if (ap !== bp) return bp - ap;
      const at = a.last_message && a.last_message.created_at ? new Date(a.last_message.created_at).getTime() : 0;
      const bt = b.last_message && b.last_message.created_at ? new Date(b.last_message.created_at).getTime() : 0;
      return bt - at;
    });
    window._zV2.rooms = rooms;
    // Cache data vào localStorage
    try {
      localStorage.setItem('zV2_rooms_cache', JSON.stringify({
        ts: Date.now(),
        data: rooms
      }));
    } catch(_) {}
    window.zV2_renderRooms();
    window.zV2_updateUnreadBadges();
    // Preload top 3 rooms ngầm sau khi render xong
    zV2_preloadTopRooms(rooms);
  } catch (e) {
    console.error('[zV2] loadRooms failed', e);
    const c = document.getElementById('zV2_conv_list');
    if (c) c.innerHTML = `<div style="padding:24px;text-align:center;color:var(--z-muted);font-size:14px;">Không tải được danh sách. <a href="#" id="zV2_retry_rooms" style="color:#0084FF;">Thử lại</a></div>`;
    const r = document.getElementById('zV2_retry_rooms');
    if (r) r.addEventListener('click', (ev) => { ev.preventDefault(); window.zV2_loadRooms(); });
  }
};

window.zV2_renderRooms = function (filterKeyword) {
  const c = document.getElementById('zV2_conv_list');
  if (!c) return;
  const rooms = (window._zV2 && window._zV2.rooms) || [];
  // Lọc: ẩn các room đã hide trong localStorage
  const hidden = (typeof window.zV2_hiddenRooms === 'function') ? window.zV2_hiddenRooms() : new Set();
  const pinned = (typeof window.zV2_pinnedRooms === 'function') ? window.zV2_pinnedRooms() : new Set();
  let list = rooms.filter(r => !hidden.has(r.id));
  // Lọc theo tab "Tất cả" / "Chưa đọc"
  const currentFilter = (window._zV2 && _zV2.currentFilter) || 'all';
  if (currentFilter === 'unread') {
    list = list.filter(r => (r.unread_count || 0) > 0);
  }
  const q = (filterKeyword || '').trim().toLowerCase();
  if (q) {
    list = list.filter(r => {
      const dn = (r.display_name || r.name || '').toLowerCase();
      return dn.indexOf(q) !== -1;
    });
  }
  // Sort: pinned trên cùng, rồi theo last_message thời gian (đã sort sẵn từ backend)
  list = list.slice().sort((a, b) => {
    const pa = pinned.has(a.id) ? 0 : 1;
    const pb = pinned.has(b.id) ? 0 : 1;
    if (pa !== pb) return pa - pb;
    const ta = a.last_message && a.last_message.created_at ? new Date(a.last_message.created_at).getTime() : 0;
    const tb = b.last_message && b.last_message.created_at ? new Date(b.last_message.created_at).getTime() : 0;
    return tb - ta;
  });
  if (!list.length) {
    if (q) {
      c.innerHTML = `<div style="padding:24px;text-align:center;color:var(--z-muted);font-size:14px;">Không tìm thấy cuộc trò chuyện nào với từ khoá "${_zV2_escapeHtml(q)}".</div>`;
    } else if (currentFilter === 'unread') {
      c.innerHTML = `<div style="padding:32px 24px;text-align:center;color:var(--z-blue-text);font-size:14px;line-height:1.5;"><br>Bạn đã đọc hết tin nhắn rồi!<br><span style="font-size:13px;color:var(--z-muted);">Không có cuộc trò chuyện chưa đọc nào.</span></div>`;
    } else {
      c.innerHTML = `<div style="padding:24px;text-align:center;color:var(--z-muted);font-size:14px;">Chưa có cuộc trò chuyện nào.</div>`;
    }
    return;
  }
  const html = list.map(r => window.zV2_renderRoomItem(r, q)).join('');
  c.innerHTML = html;

  if (!c._zV2_bound) {
    c.addEventListener('click', function (ev) {
      const item = ev.target.closest('.zV2_conv_item');
      if (!item || !c.contains(item)) return;
      const id = parseInt(item.dataset.roomId, 10);
      if (!isNaN(id) && typeof window.zV2_openRoom === 'function') {
        window.zV2_openRoom(id);
      }
    });
    c._zV2_bound = true;
  }
  // Wire prefetch hover mỗi lần render lại (innerHTML mới)
  if (typeof window.zV2_wirePrefetchHover === 'function') {
    c._prefetchBound = false; // reset để wire lại
    window.zV2_wirePrefetchHover();
  }
};

window.zV2_renderRoomItem = function (room, highlightKw) {
  const me = _zV2_getMe();
  const displayName = room.display_name || room.name || 'Cuộc trò chuyện';
  const isActive = window._zV2 && window._zV2.currentRoomId === room.id;
  const online = window._zV2 && window._zV2.online instanceof Set ? window._zV2.online : new Set();

  // Avatar — dùng URL endpoint thay base64 (browser cache)
  const avatarBg = _zV2_hashColor(displayName);
  const _dmAvaUrl = room.type === 'direct' && room.peer_username
    ? '/api/chat/users/' + encodeURIComponent(room.peer_username) + '/avatar'
    : null;
  const avatarInner = _zV2_avatarHTML(displayName, _dmAvaUrl || room.avatar_url, 44);
  // Online dot (only direct + peer online)
  let onlineDot = '';
  if (room.type === 'direct') {
    const peer = room.peer_username || room.other_username || null;
    if (peer && online.has(peer)) {
      onlineDot = '<span class="zV2_conv_dot_online"></span>';
    } else if (room.is_online) {
      onlineDot = '<span class="zV2_conv_dot_online"></span>';
    }
  }

  // Preview text
  let preview = 'Chưa có tin nhắn';
  let lastMsgTime = '';
  if (room.last_message) {
    const lm = room.last_message;
    let prefix = '';
    if (lm.sender_username && me && lm.sender_username === me) {
      prefix = 'Bạn: ';
    } else if (room.type !== 'direct' && lm.sender_name) {
      prefix = lm.sender_name + ': ';
    }
    const content = (lm.msg_type === 'card') ? window.zV2_cardPreview(lm)
      : (lm.content || (lm.attachment_name ? '[Tệp đính kèm] ' + lm.attachment_name : ''));
    preview = _zV2_truncate(prefix + content, 60);
    lastMsgTime = _zV2_formatTime(lm.created_at);
  }

  // Highlight search
  let displayNameHTML = _zV2_escapeHtml(displayName);
  if (highlightKw) {
    const kw = highlightKw.toLowerCase();
    const idx = displayName.toLowerCase().indexOf(kw);
    if (idx >= 0) {
      const before = _zV2_escapeHtml(displayName.slice(0, idx));
      const hit = _zV2_escapeHtml(displayName.slice(idx, idx + kw.length));
      const after = _zV2_escapeHtml(displayName.slice(idx + kw.length));
      displayNameHTML = `${before}<mark class="zV2_search_active">${hit}</mark>${after}`;
    }
  }

  const badge = room.unread_count > 0
    ? `<span class="zV2_conv_badge">${room.unread_count > 99 ? '99+' : room.unread_count}</span>`
    : '';

  const hasUnread = (room.unread_count || 0) > 0;
  return `
    <div class="zV2_conv_item ${isActive ? 'zV2_conv_item--active' : ''} ${hasUnread ? 'zV2_conv_item--unread' : ''}" data-room-id="${room.id}">
      <div class="zV2_conv_avatar" style="background:${avatarBg}">
        ${avatarInner}
        ${onlineDot}
      </div>
      <div class="zV2_conv_main">
        <div class="zV2_conv_top">
          <span class="zV2_conv_name">${displayNameHTML}</span>
          <span class="zV2_conv_time">${_zV2_escapeHtml(lastMsgTime)}</span>
        </div>
        <div class="zV2_conv_bottom">
          <span class="zV2_conv_preview">${_zV2_escapeHtml(preview)}</span>
          ${badge}
        </div>
      </div>
    </div>
  `;
};

window.zV2_updateRoomItemDOM = function (roomId) {
  const rooms = (window._zV2 && window._zV2.rooms) || [];
  const room = rooms.find(r => r.id === roomId);
  if (!room) return;
  const el = document.querySelector(`#zV2_conv_list [data-room-id="${roomId}"]`);
  if (!el) {
    // Not in DOM — full re-render
    window.zV2_renderRooms();
    return;
  }
  const wrap = document.createElement('div');
  wrap.innerHTML = window.zV2_renderRoomItem(room);
  const fresh = wrap.firstElementChild;
  if (fresh) el.replaceWith(fresh);
};

// ---------- Users / Contacts ----------

window.zV2_loadUsers = async function () {
  try {
    const res = await fetch('/api/chat/users', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    const users = Array.isArray(data) ? data : (data.users || []);
    window._zV2.users = users;
    window.zV2_renderContacts();
  } catch (e) {
    console.error('[zV2] loadUsers failed', e);
    const c = document.getElementById('zV2_contacts_list');
    if (c) c.innerHTML = `<div style="padding:24px;text-align:center;color:var(--z-muted);font-size:14px;">Không tải được danh bạ.</div>`;
  }
};

window.zV2_renderContacts = function (filterKw) {
  const c = document.getElementById('zV2_contacts_list');
  if (!c) return;
  const me = _zV2_getMe();
  let users = (window._zV2 && window._zV2.users) || [];
  if (me) users = users.filter(u => u.username !== me);

  const q = (filterKw || '').trim().toLowerCase();
  if (q) {
    users = users.filter(u => {
      const name = (u.ho_ten || '').toLowerCase();
      const pb = (u.phong_ban || '').toLowerCase();
      const cv = (u.chuc_vu || '').toLowerCase();
      return name.indexOf(q) !== -1 || pb.indexOf(q) !== -1 || cv.indexOf(q) !== -1;
    });
  }

  // Group by phong_ban
  // Ưu tiên hiển thị theo chức vụ: Giám đốc → Manager → Leader → Nhân viên
  const rolePriority = (u) => {
    const cv = (u.chuc_vu || '').toLowerCase();
    if (cv.includes('giám đốc') || cv.includes('ceo') || cv.includes('director')) return 1;
    if (cv.includes('manager') || cv.includes('quản lý') || cv.includes('trưởng phòng') || cv.includes('trưởng bộ phận')) return 2;
    if (cv.includes('leader') || cv.includes('tổ trưởng') || cv.includes('phó phòng') || cv.includes('phó giám đốc')) return 3;
    return 4; // nhân viên / khác
  };
  const map = {};
  users.forEach(u => {
    const pb = u.phong_ban || 'Khác';
    if (!map[pb]) map[pb] = [];
    map[pb].push(u);
  });
  // Sort phòng ban: Giám đốc trên cùng, Công nghệ cuối, còn lại alpha
  const deptPriority = (name) => {
    const n = (name || '').toLowerCase();
    if (n.includes('giám đốc')) return 1;
    if (n.includes('công nghệ')) return 3;
    return 2;
  };
  const groups = Object.keys(map).sort((a, b) => {
    const pa = deptPriority(a), pb = deptPriority(b);
    if (pa !== pb) return pa - pb;
    return a.localeCompare(b, 'vi');
  });
  groups.forEach(g => map[g].sort((a, b) => {
    const pa = rolePriority(a), pb = rolePriority(b);
    if (pa !== pb) return pa - pb;
    return String(a.ho_ten || a.username).localeCompare(String(b.ho_ten || b.username), 'vi');
  }));

  // KHÔNG render search box riêng — dùng #zV2_search_box ở top sidebar (xem zV2_bindSearchBox)
  let bodyHTML;
  if (!groups.length) {
    bodyHTML = `<div style="padding:24px;text-align:center;color:var(--z-muted);font-size:14px;">Không có nhân viên phù hợp.</div>`;
  } else {
    bodyHTML = groups.map(g => {
      const list = map[g];
      return `
        <div class="zV2_contact_group_header">${_zV2_escapeHtml(g)} (${list.length})</div>
        ${list.map(u => window.zV2_renderContactItem(u, q)).join('')}
      `;
    }).join('');
  }

  c.innerHTML = bodyHTML;

  // Bind list click delegated (distinguish: item click → DM, call/video btn → modal)
  if (!c._zV2_bound) {
    c.addEventListener('click', function (ev) {
      const item = ev.target.closest('.zV2_contact_item');
      if (!item || !c.contains(item)) return;
      const u = item.dataset.username;
      if (!u) return;
      const btn = ev.target.closest('[data-action]');
      const act = btn && btn.dataset.action;
      if (act === 'contact-call' || act === 'contact-video') {
        ev.stopPropagation();
        // Open DM ngầm + show call modal cho user đó
        const usersList = (window._zV2 && _zV2.users) || [];
        const userObj = usersList.find(function(x){ return x.username === u; });
        const displayName = userObj ? (userObj.ho_ten || userObj.username) : u;
        zV2_openDirectCallModal(displayName, act === 'contact-video' ? 'video' : 'voice');
        return;
      }
      window.zV2_startDmWithUser(u);
    });
    c._zV2_bound = true;
  }

  // Search input đã dùng #zV2_search_box ở top — không cần bind riêng
};

window.zV2_renderContactItem = function (u, highlightKw) {
  const name = u.ho_ten || u.username || '?';
  // Hiển thị "Chức vụ • Phòng ban" — fallback nếu thiếu
  const cvParts = [];
  if (u.chuc_vu) cvParts.push(u.chuc_vu);
  if (u.phong_ban && (!u.chuc_vu || u.phong_ban.toLowerCase() !== u.chuc_vu.toLowerCase())) cvParts.push(u.phong_ban);
  const subtitle = cvParts.join(' • ') || (u.username || '');
  const online = window._zV2 && window._zV2.online instanceof Set ? window._zV2.online : new Set();
  const isOnline = online.has(u.username);
  const bg = _zV2_hashColor(name);
  const avatar = _zV2_avatarHTML(name, u.avatar_data, 40);

  let nameHTML = _zV2_escapeHtml(name);
  if (highlightKw) {
    const kw = highlightKw.toLowerCase();
    const idx = name.toLowerCase().indexOf(kw);
    if (idx >= 0) {
      const before = _zV2_escapeHtml(name.slice(0, idx));
      const hit = _zV2_escapeHtml(name.slice(idx, idx + kw.length));
      const after = _zV2_escapeHtml(name.slice(idx + kw.length));
      nameHTML = `${before}<mark class="zV2_search_active">${hit}</mark>${after}`;
    }
  }

  return `
    <div class="zV2_contact_item" data-username="${_zV2_escapeHtml(u.username)}">
      <div class="zV2_contact_avatar" style="background:${bg};">
        ${u.avatar_data
          ? `<img src="${_zV2_escapeHtml(u.avatar_data)}" alt="" />`
          : _zV2_escapeHtml(_zV2_initial(name))}
        ${isOnline ? '<span class="zV2_conv_dot_online"></span>' : ''}
      </div>
      <div class="zV2_contact_body">
        <div class="zV2_contact_name">${nameHTML}</div>
        <div class="zV2_contact_sub">${_zV2_escapeHtml(subtitle)}</div>
      </div>
      <div class="zV2_contact_actions">
        <button type="button" class="zV2_contact_btn" data-action="contact-call" title="Gọi thoại"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/></svg></button>
        <button type="button" class="zV2_contact_btn" data-action="contact-video" title="Gọi video"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"/><rect x="1" y="5" width="15" height="14" rx="2" ry="2"/></svg></button>
      </div>
    </div>
  `;
};

window.zV2_startDmWithUser = async function (username) {
  if (!username) return;
  let toastEl = null;
  try {
    if (typeof window.zV2_toast === 'function') {
      toastEl = window.zV2_toast('Đang mở cuộc trò chuyện...', 'info', 3000);
    }
    const res = await fetch(`/api/chat/rooms/direct/${encodeURIComponent(username)}`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const room = await res.json();
    if (!room || !room.id) throw new Error('invalid room');
    const rooms = window._zV2.rooms || [];
    const idx = rooms.findIndex(r => r.id === room.id);
    if (idx >= 0) {
      rooms[idx] = Object.assign({}, rooms[idx], room);
    } else {
      rooms.unshift(room);
    }
    window._zV2.rooms = rooms;
    window.zV2_renderRooms();
    if (typeof window.zV2_switchTab === 'function') window.zV2_switchTab('tin-nhan');
    if (typeof window.zV2_openRoom === 'function') window.zV2_openRoom(room.id);
  } catch (e) {
    console.error('[zV2] startDm failed', e);
    if (typeof window.zV2_toast === 'function') {
      window.zV2_toast('Không mở được cuộc trò chuyện', 'error', 3000);
    }
  } finally {
    if (toastEl && toastEl.remove) {
      try { toastEl.remove(); } catch (_) {}
    }
  }
};

// ---------- Top search box ----------

window.zV2_bindSearchBox = function () {
  const inp = document.getElementById('zV2_search_box');
  if (!inp || inp._zV2_bound) return;
  inp._zV2_bound = true;
  const handler = _zV2_debounce(function () {
    const q = inp.value || '';
    const tab = window._zV2 && window._zV2.currentTab;
    if (tab === 'danh-ba') {
      window.zV2_renderContacts(q);
    } else {
      window.zV2_renderRooms(q);
    }
  }, 200);
  inp.addEventListener('input', handler);
};

// ---------- Presence ----------

window.zV2_handlePresenceUpdate = async function () {
  // Skip nếu widget đóng — đỡ tốn CPU cho re-render khi user không xem
  if (!(window._zV2 && _zV2.open)) {
    try {
      // Vẫn fetch để update online set nhẹ, nhưng KHÔNG re-render DOM
      const res = await fetch('/api/chat/presence/all', { credentials: 'same-origin' });
      if (!res.ok) return;
      const data = await res.json();
      const list = (data && Array.isArray(data.online)) ? data.online : [];
      const set = new Set();
      list.forEach(x => { if (typeof x === 'string') set.add(x); else if (x && x.username) set.add(x.username); });
      window._zV2.online = set;
    } catch(_){}
    return;
  }
  try {
    const res = await fetch('/api/chat/presence/all', { credentials: 'same-origin' });
    if (!res.ok) return;
    const data = await res.json();
    const list = (data && Array.isArray(data.online)) ? data.online : (Array.isArray(data) ? data : []);
    const set = new Set();
    list.forEach(x => {
      if (typeof x === 'string') set.add(x);
      else if (x && x.username) set.add(x.username);
    });
    window._zV2.online = set;
    const map = {};
    if (data && Array.isArray(data.presence)) {
      data.presence.forEach(function(p){ if (p && p.username) map[p.username] = p; });
    }
    window._zV2.presenceMap = map;
    // Chỉ re-render tab hiện active (cheap)
    var currentTab = (window._zV2 && _zV2.currentTab) || 'tin-nhan';
    if (currentTab === 'tin-nhan' && document.getElementById('zV2_conv_list')) {
      const q = (document.getElementById('zV2_search_box') || {}).value || '';
      window.zV2_renderRooms(q);
    } else if (currentTab === 'danh-ba' && document.getElementById('zV2_contacts_list')) {
      const sInp = document.getElementById('zV2_search_box');
      const q = sInp ? sInp.value : '';
      window.zV2_renderContacts(q);
    }
  } catch (e) { /* silent */ }
};

window.zV2_startPresencePolling = function () {
  if (window._zV2 && window._zV2._presenceTimer) return;
  window.zV2_handlePresenceUpdate();
  const t = setInterval(window.zV2_handlePresenceUpdate, 30000);
  if (window._zV2) window._zV2._presenceTimer = t;
};

// ---------- Auto bind once DOM ready ----------

(function () {
  function init() {
    if (window._zV2) {
      if (!(window._zV2.online instanceof Set)) window._zV2.online = new Set();
      if (!Array.isArray(window._zV2.rooms)) window._zV2.rooms = [];
      if (!Array.isArray(window._zV2.users)) window._zV2.users = [];
    }
    window.zV2_bindSearchBox();
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
/* ==== ZALO V2: MESSAGES + BUBBLE + COMPOSER + SSE ==== */

// ---------- Utilities ----------
window.zV2_escapeHtml = function (s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

window.zV2_formatTime = function (iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso);
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    return hh + ':' + mm;
  } catch (e) { return ''; }
};

window.zV2_formatDateDivider = function (iso) {
  if (!iso) return '';
  try {
    var d = new Date(iso);
    var now = new Date();
    var yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
    if (d.toDateString() === now.toDateString()) return 'Hôm nay';
    if (d.toDateString() === yesterday.toDateString()) return 'Hôm qua';
    return d.getDate().toString().padStart(2, '0') + '/' +
      (d.getMonth() + 1).toString().padStart(2, '0') + '/' + d.getFullYear();
  } catch (e) { return ''; }
};

window.zV2_sameDay = function (a, b) {
  if (!a || !b) return false;
  try {
    var da = new Date(a), db = new Date(b);
    return da.toDateString() === db.toDateString();
  } catch (e) { return false; }
};

window.zV2_timeGap = function (a, b) {
  if (!a || !b) return Infinity;
  try {
    return Math.abs(new Date(a).getTime() - new Date(b).getTime()) / 1000;
  } catch (e) { return Infinity; }
};

window.zV2_truncate = function (s, n) {
  s = String(s || '');
  if (s.length <= n) return s;
  return s.slice(0, n) + '…';
};

window.zV2_formatFileSize = function (bytes) {
  if (!bytes) return '';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
};

window.zV2_getCurrentUser = function () {
  if (window._zV2 && _zV2.currentUser && _zV2.currentUser.username) return _zV2.currentUser;
  var u = { username: window.currentUsername || '', name: window.currentUserDisplayName || '' };
  if (window._zV2) _zV2.currentUser = u;
  return u;
};

window.zV2_apiFetch = async function (url, opts) {
  opts = opts || {};
  opts.credentials = opts.credentials || 'include';
  opts.headers = opts.headers || {};
  if (opts.body && typeof opts.body !== 'string' && !(opts.body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(opts.body);
  }
  var resp = await fetch(url, opts);
  if (!resp.ok) {
    var t = await resp.text().catch(function () { return ''; });
    throw new Error('HTTP ' + resp.status + ' ' + t);
  }
  if (resp.status === 204) return null;
  var ct = resp.headers.get('content-type') || '';
  if (ct.indexOf('application/json') >= 0) return await resp.json();
  return await resp.text();
};

// Toast của widget. TRƯỚC ĐÂY chỉ uỷ quyền cho zV2_showToast/showToast —
// mà KHÔNG file nào định nghĩa hai hàm đó, nên mọi thông báo ("Chuyển tiếp
// thất bại", "Chỉnh sửa thất bại"…) chỉ rơi vào console.log: người dùng thao
// tác hỏng mà không thấy gì. Đo được: gọi zV2_toast thêm 0 phần tử vào trang.
// Nay có chuỗi dự phòng đầy đủ, chốt bằng bản tự vẽ để chạy được ở cả 7 app.
window.zV2_toast = function (msg, type) {
  try {
    if (typeof window.zV2_showToast === 'function') return window.zV2_showToast(msg, type);
    if (typeof window.showToast === 'function')     return window.showToast(msg, type);
    if (typeof window.toast === 'function')         return window.toast(msg, type); // ui-common.js của ketoan
  } catch (e) { /* rơi xuống bản tự vẽ bên dưới */ }

  try {
    var t = document.createElement('div');
    t.className = 'zV2_toast zV2_toast_' + (type || 'info');
    t.setAttribute('role', type === 'error' ? 'alert' : 'status');
    t.textContent = msg;
    t.style.cssText =
      'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);' +
      'background:' + (type === 'error' ? 'var(--z-badge)'
                     : type === 'success' ? 'var(--z-ok)' : 'var(--z-text)') + ';' +
      'color:#fff;padding:10px 16px;border-radius:8px;z-index:2147483001;' +
      'font-size:14px;max-width:min(420px,90vw);box-shadow:0 4px 16px rgba(0,0,0,.25);' +
      'opacity:0;transition:opacity .2s';
    document.body.appendChild(t);
    requestAnimationFrame(function () { t.style.opacity = '1'; });
    setTimeout(function () {
      t.style.opacity = '0';
      setTimeout(function () { if (t.parentNode) t.remove(); }, 300);
    }, 2600);
  } catch (e) {
    console.log('[zV2 toast]', type || '', msg);
  }
};

// ---------- Open Room ----------
window.zV2_openRoom = async function (roomId) {
  if (!roomId) return;
  _zV2.currentRoomId = roomId;
  _zV2.replyTo = null;
  _zV2.editingMsgId = null;

  var room = (_zV2.rooms || []).find(function (r) { return r.id === roomId; });
  // Force refresh presence cho DM (đỡ stale data 120s) — fire-and-forget
  if (room && room.type === 'direct' && typeof window.zV2_handlePresenceUpdate === 'function') {
    window.zV2_handlePresenceUpdate();
  }
  var headerEl = document.getElementById('zV2_main_header');
  if (headerEl && room) {
    var displayName = room.display_name || room.name || 'Phòng chat';
    var isDirect = room.type === 'direct';
    var meta = '';
    if (isDirect) {
      var pres = zV2_getPresence(room.peer_username);
      if (_zV2.online && _zV2.online.has && _zV2.online.has(room.peer_username)) {
        meta = 'Đang hoạt động';
      } else if (pres && pres.last_seen_at) {
        meta = zV2_formatLastSeen(pres.last_seen_at);
      } else {
        meta = 'Không trực tuyến';
      }
    } else if (room.type === 'general' || room.type === 'announcement') {
      meta = 'Toàn công ty';
    } else {
      var n = room.members_count || (room.members && room.members.length) || 0;
      meta = n + ' thành viên';
    }
    // Update existing DOM (giữ class .zV2_main_action_btn cho icon emoji)
    var avEl = document.getElementById('zV2_main_avatar');
    if (avEl) {
      avEl.style.overflow = 'hidden';
      avEl.style.borderRadius = '50%';
      avEl.style.width = avEl.style.width || '40px';
      avEl.style.height = avEl.style.height || '40px';
      // Ưu tiên: room.avatar_url → URL avatar peer (DM) → ký tự đầu
      var avatarSrc = room.avatar_url ||
        (room.peer_username ? '/api/chat/users/' + encodeURIComponent(room.peer_username) + '/avatar' : '');
      if (avatarSrc) {
        avEl.innerHTML = '<img src="' + zV2_escapeHtml(avatarSrc) + '" style="width:100%;height:100%;object-fit:cover;" />';
        avEl.style.background = 'transparent';
      } else {
        var ch = (displayName.charAt(0) || '?').toUpperCase();
        var color = (typeof zV2_hashColor === 'function') ? zV2_hashColor(displayName) : '#0084FF';
        avEl.innerHTML = ch;
        avEl.style.background = color;
        avEl.style.color = '#fff';
        avEl.style.display = 'flex';
        avEl.style.alignItems = 'center';
        avEl.style.justifyContent = 'center';
        avEl.style.fontWeight = '600';
      }
    }
    var titleEl = document.getElementById('zV2_main_title');
    if (titleEl) titleEl.textContent = displayName;
    var metaEl = document.getElementById('zV2_main_meta');
    if (metaEl) metaEl.textContent = meta;
    if (window.zCall) window.zCall._setContext({roomId:roomId,type:room.type,isDirect:isDirect,peer:room.peer_username,name:displayName,memberCount:(room.members_count||(room.members&&room.members.length)||0)});
    headerEl.style.display = '';
  }

  // Active item in conv list — O(1): chỉ update 2 element thay vì scan toàn bộ list
  try {
    var _prevActive = document.querySelector('.zV2_conv_item--active');
    if (_prevActive) _prevActive.classList.remove('zV2_conv_item--active');
    var _newActive = document.querySelector('.zV2_conv_item[data-room-id="' + roomId + '"]');
    if (_newActive) _newActive.classList.add('zV2_conv_item--active');
  } catch (e) { }

  // Show messages scroll + compose, hide empty
  var scrollEl = document.getElementById('zV2_messages_scroll');
  var emptyEl  = document.getElementById('zV2_empty_main');
  var composeEl= document.getElementById('zV2_compose_wrap');
  if (scrollEl) scrollEl.style.display = '';
  if (emptyEl)  emptyEl.style.display  = 'none';
  if (composeEl)composeEl.style.display= '';
  // Mobile: switch col_middle → col_main
  var chatPanel = document.getElementById('_chat_panel');
  if (chatPanel) chatPanel.classList.add('show-main');

  // Reset reply strip
  var replyStrip = document.getElementById('zV2_reply_strip');
  if (replyStrip) replyStrip.style.display = 'none';

  // Reset composer input
  var input = document.getElementById('zV2_compose_input');
  if (input) {
    input.value = '';
    input.placeholder = 'Nhập tin nhắn...';
  }

  // Load messages — ưu tiên: in-memory → IndexedDB → API
  var _memCached = _zV2.messages && _zV2.messages[roomId] && _zV2.messages[roomId].length > 0;
  if (_memCached) {
    // 1. In-memory: hiện ngay, delta-sync ngầm
    zV2_renderMessages(roomId, function () { zV2_scrollBottom('auto'); });
    zV2_loadMessages(roomId, null, true, null).catch(function () {});
  } else {
    // 2. Thử IndexedDB (tồn tại qua F5)
    var _skInner = document.getElementById('zV2_messages_inner');
    if (_skInner) _skInner.innerHTML = '<div class="zV2_msg_skel_wrap">' +
      '<div class="zV2_msg_skel zV2_msg_skel--in"></div>' +
      '<div class="zV2_msg_skel zV2_msg_skel--in zV2_msg_skel--short"></div>' +
      '<div class="zV2_msg_skel zV2_msg_skel--out"></div>' +
      '<div class="zV2_msg_skel zV2_msg_skel--in"></div>' +
      '<div class="zV2_msg_skel zV2_msg_skel--out zV2_msg_skel--short"></div>' +
      '</div>';
    var _dbMsgs = [];
    try { _dbMsgs = await window.zV2_dbGet(roomId); } catch (_) {}
    if (_dbMsgs.length > 0) {
      // IndexedDB hit: hiện ngay, rồi delta-sync lấy tin mới hơn
      _zV2.messages = _zV2.messages || {};
      _zV2.messages[roomId] = _dbMsgs;
      var _lastDbId = _dbMsgs[_dbMsgs.length - 1].id;
      zV2_renderMessages(roomId, function () { zV2_scrollBottom('auto'); });
      zV2_loadMessages(roomId, null, true, _lastDbId).catch(function () {});
    } else {
      // 3. Không có gì: full fetch
      await zV2_loadMessages(roomId);
    }
  }

  // Đảm bảo scroll xuống tin mới nhất — chạy sau rAF + layout
  // (rAF chỉ ~16ms, nhưng background refresh API trả về ~200-400ms sau)
  var _scrollTargetRoom = roomId;
  setTimeout(function () {
    if (_zV2.currentRoomId === _scrollTargetRoom) zV2_scrollBottom('auto');
  }, 80);
  setTimeout(function () {
    if (_zV2.currentRoomId === _scrollTargetRoom) zV2_scrollBottom('auto');
  }, 500);

  // Mark read
  try {
    await zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/read', { method: 'PUT' });
  } catch (e) { console.warn('[zV2] mark read failed', e); }

  // Clear unread badge locally
  if (room) room.unread_count = 0;
  if (window.zV2_renderConvList) window.zV2_renderConvList();
};

// ---------- Load messages ----------
// afterId: chỉ lấy tin MỚI HƠN id đó (delta sync từ IndexedDB)
// backgroundRefresh: không scroll, không toast lỗi
window.zV2_loadMessages = async function (roomId, beforeId, backgroundRefresh, afterId) {
  if (!roomId) return;
  // slim=1 bỏ reactions/read_by/pinned → API trả lời nhanh hơn ~3-4x
  var url = '/api/chat/rooms/' + encodeURIComponent(roomId) + '/messages?slim=1&limit=30';
  if (beforeId) url += '&before_id=' + encodeURIComponent(beforeId);
  if (afterId)  url += '&after_id='  + encodeURIComponent(afterId);
  var scrollEl = document.getElementById('zV2_messages_scroll');
  var prevHeight = scrollEl ? scrollEl.scrollHeight : 0;
  var prevTop    = scrollEl ? scrollEl.scrollTop    : 0;
  try {
    var msgs = await zV2_apiFetch(url);
    if (!Array.isArray(msgs)) msgs = [];
    msgs = msgs.slice().reverse(); // server trả DESC → đảo thành ASC
    _zV2.messages = _zV2.messages || {};

    if (afterId) {
      // Delta: chỉ append tin mới, không xoá tin cũ
      if (msgs.length > 0) {
        var existing = _zV2.messages[roomId] || [];
        // Dedup bằng id
        var existIds = new Set(existing.map(function (m) { return m.id; }));
        var newMsgs  = msgs.filter(function (m) { return !existIds.has(m.id); });
        if (newMsgs.length > 0) {
          _zV2.messages[roomId] = existing.concat(newMsgs);
          if (_zV2HtmlCache && _zV2HtmlCache[roomId]) delete _zV2HtmlCache[roomId];
          if (_zV2.currentRoomId === roomId) {
            // Append trực tiếp vào DOM thay vì full re-render
            var inner = document.getElementById('zV2_messages_inner');
            var me = zV2_getCurrentUser();
            var arr = _zV2.messages[roomId];
            newMsgs.forEach(function (m) {
              var prevMsg = arr.length >= 2 ? arr[arr.indexOf(m) - 1] : null;
              if (inner) inner.insertAdjacentHTML('beforeend', zV2_buildMessageRow(m, prevMsg, null, me));
            });
            if (typeof window.zV2_initLazyImages === 'function') window.zV2_initLazyImages();
            // Scroll nếu đang ở cuối hoặc mình vừa gửi
            var atBottom = scrollEl ? (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight) < 120 : true;
            if (atBottom) zV2_scrollBottom('smooth');
          }
          // Lưu vào IndexedDB
          if (window.zV2_dbSave) window.zV2_dbSave(roomId, newMsgs).catch(function(){});
        }
      }
      return;
    }

    if (beforeId) {
      var existing2 = _zV2.messages[roomId] || [];
      _zV2.messages[roomId] = msgs.concat(existing2);
    } else {
      _zV2.messages[roomId] = msgs;
    }
    _zV2.oldestMsgId = _zV2.oldestMsgId || {};
    if (msgs.length > 0) _zV2.oldestMsgId[roomId] = msgs[0].id;

    // Lưu vào IndexedDB (background, không block render)
    if (window.zV2_dbSave) window.zV2_dbSave(roomId, msgs).catch(function(){});

    if (_zV2.currentRoomId !== roomId) return;
    if (_zV2HtmlCache && _zV2HtmlCache[roomId]) delete _zV2HtmlCache[roomId];

    if (beforeId && scrollEl) {
      var _pt = prevTop, _ph = prevHeight;
      zV2_renderMessages(roomId, function () {
        scrollEl.scrollTop = _pt + (scrollEl.scrollHeight - _ph);
      });
    } else if (backgroundRefresh) {
      // Scroll xuống nếu user đang ở cuối (hoặc vừa mở room)
      var _bsEl = document.getElementById('zV2_messages_scroll');
      var _bsBot = !_bsEl || (_bsEl.scrollHeight - _bsEl.scrollTop - _bsEl.clientHeight) < 100;
      zV2_renderMessages(roomId, _bsBot ? function () { zV2_scrollBottom('auto'); } : null);
    } else {
      zV2_renderMessages(roomId, function () { zV2_scrollBottom('auto'); });
    }
  } catch (e) {
    console.error('[zV2] loadMessages failed', e);
    if (!backgroundRefresh) zV2_toast('Không tải được tin nhắn', 'error');
  }
};

// ---------- HTML cache cho renderMessages (tránh build lại khi không đổi) ----------
var _zV2HtmlCache = {};  // roomId -> { cacheKey, html }
var _zV2DomRoomId = null, _zV2DomHtml = null;  // room+html dang hien tren DOM (skip rebuild thua)

// ---------- Render messages ----------
// afterRender: optional callback chạy SAU KHI innerHTML được set (dùng để scroll)
window.zV2_renderMessages = function (roomId, afterRender) {
  var inner = document.getElementById('zV2_messages_inner');
  if (!inner) return;
  var msgs = (_zV2.messages && _zV2.messages[roomId]) || [];
  var me = zV2_getCurrentUser();

  // Cache key = roomId + số tin + id tin cuối (vô hiệu hoá khi có tin mới/thu hồi/sửa)
  var lastId = msgs.length > 0 ? msgs[msgs.length - 1].id : 0;
  var cacheKey = roomId + '_' + msgs.length + '_' + lastId;

  var html;
  if (_zV2HtmlCache[roomId] && _zV2HtmlCache[roomId].cacheKey === cacheKey) {
    html = _zV2HtmlCache[roomId].html;  // reuse cached string, bỏ qua rebuild
  } else {
    var parts = [];
    var lastDate = null;
    for (var i = 0; i < msgs.length; i++) {
      var m = msgs[i];
      var prev = i > 0 ? msgs[i - 1] : null;
      var next = i < msgs.length - 1 ? msgs[i + 1] : null;
      if (!lastDate || !zV2_sameDay(lastDate, m.created_at)) {
        parts.push('<div class="zV2_date_divider"><span>' +
          zV2_escapeHtml(zV2_formatDateDivider(m.created_at)) + '</span></div>');
        lastDate = m.created_at;
      }
      parts.push(zV2_buildMessageRow(m, prev, next, me));
    }
    html = parts.join('');
    _zV2HtmlCache[roomId] = { cacheKey: cacheKey, html: html };
  }

  // rAF: yield cho browser vẽ header/title trước, rồi mới set innerHTML
  requestAnimationFrame(function () {
    if (_zV2DomRoomId === roomId && _zV2DomHtml === html) return;  // DOM da dung -> bo qua rebuild (het giat khi scroll)
    inner.innerHTML = html;
    _zV2DomRoomId = roomId; _zV2DomHtml = html;
    zV2_bindMessageEvents(roomId);
    if (typeof window.zV2_initLazyImages === 'function') window.zV2_initLazyImages();
    if (typeof afterRender === 'function') afterRender();
  });
};

// ---------- Build single row ----------
// Biến mã đơn thành LINK bấm mở (anh Quang 2026-08-20). Chỉ chạy trên HTML ĐÃ escape.
window.zV2_linkifyCodes = function(escapedHtml) {
  if (!escapedHtml) return escapedHtml;
  // Mã PO Mua Hàng: ORD-YYYY-NNN → mở app muahang
  escapedHtml = escapedHtml.replace(/\b(ORD-\d{4}-\d+)\b/g, function(m, code){
    return '<a href="https://muahang.qlpps.com/?order=' + encodeURIComponent(code) + '" target="_blank" rel="noopener" style="color:var(--z-blue-text,#0B63CE);font-weight:600;text-decoration:none;">' + code + '</a>';
  });
  return escapedHtml;
};

// Nhãn gọn cho THẺ ở preview danh sách phòng / thông báo (không hiện JSON thô)
window.zV2_cardPreview = function(msg) {
  try { var d = JSON.parse((msg && msg.content) || '{}');
    if (d.kind === 'task') return '📋 Nhiệm vụ: ' + (d.title || '');
    if (d.kind === 'event') return '📅 Lịch: ' + (d.title || '');
    if (d.kind === 'approval') return '🔐 Phê duyệt: ' + (d.title || '');
    if (d.kind === 'poll') return '📊 Bình chọn: ' + (d.question || '');
    return (msg && msg.content) || ''; }
  catch(e) { return (msg && msg.content) || ''; }
};

// ── Render THẺ (task/event) trong chat — anh Quang 2026-08-20 (tin nhắn thông minh) ──
window.zV2_renderApprovalCard = function(msg, d) {
  var me = (typeof zV2_getCurrentUser === 'function' && zV2_getCurrentUser())
    ? (zV2_getCurrentUser().username || '')
    : ((window._zV2 && window._zV2.currentUser && window._zV2.currentUser.username) || '');
  var status = d.status || 'pending';
  var isApprover = (d.approver || '').toLowerCase() === (me || '').toLowerCase();
  var accent = status === 'approved' ? '#12a150' : (status === 'rejected' ? '#e5484d' : '#f79009');
  var footer;
  if (status === 'pending') {
    if (isApprover) {
      footer = '<div style="display:flex;gap:8px;">' +
        '<button data-action="reject" data-msg-id="'+zV2_escapeHtml(msg.id)+'" style="flex:1;padding:8px 10px;border:1px solid var(--z-border);background:var(--z-white);color:#e5484d;font-weight:600;border-radius:8px;cursor:pointer;font-size:13.5px;">❌ Từ chối</button>' +
        '<button data-action="approve" data-msg-id="'+zV2_escapeHtml(msg.id)+'" style="flex:1;padding:8px 10px;border:none;background:#12a150;color:#fff;font-weight:600;border-radius:8px;cursor:pointer;font-size:13.5px;">✅ Duyệt</button>' +
        '</div>';
    } else {
      footer = '<div style="font-size:12.5px;color:var(--z-muted);">⏳ Chờ <b>'+zV2_escapeHtml(d.approver_name||'')+'</b> duyệt…</div>';
    }
  } else {
    var lbl = status === 'approved' ? '✅ Đã duyệt' : '❌ Đã từ chối';
    footer = '<div style="font-size:13px;font-weight:600;color:'+accent+';">'+lbl+' · bởi '+zV2_escapeHtml(d.decided_by_name||'')+(d.decided_at?' · '+zV2_escapeHtml(d.decided_at):'')+'</div>';
  }
  return '' +
    '<div style="display:flex;justify-content:center;padding:6px 10px;">' +
      '<div style="width:100%;max-width:460px;border:1px solid var(--z-border);border-radius:12px;background:var(--z-white);box-shadow:0 1px 5px rgba(0,0,0,.07);overflow:hidden;">' +
        '<div style="display:flex;align-items:flex-start;gap:11px;padding:12px 14px;border-left:4px solid '+accent+';">' +
          '<div style="font-size:22px;line-height:1;">🔐</div>' +
          '<div style="flex:1;min-width:0;">' +
            '<div style="font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:'+accent+';margin-bottom:2px;">Phê duyệt</div>' +
            '<div style="font-weight:600;font-size:14.5px;color:var(--z-text);line-height:1.3;word-break:break-word;">'+zV2_escapeHtml(d.title||'')+'</div>' +
            (d.note ? '<div style="font-size:12.5px;color:var(--z-muted);margin-top:3px;line-height:1.5;">'+zV2_escapeHtml(d.note)+'</div>' : '') +
            '<div style="font-size:12px;color:var(--z-muted);margin-top:4px;">Yêu cầu: '+zV2_escapeHtml(d.requester_name||'')+' → '+zV2_escapeHtml(d.approver_name||'')+'</div>' +
          '</div>' +
        '</div>' +
        '<div style="padding:10px 14px;border-top:1px solid var(--z-border);background:var(--z-bg);">'+footer+'</div>' +
      '</div>' +
    '</div>';
};

window.zV2_decideApproval = async function(cardMsgId, decision) {
  try {
    await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(cardMsgId) + '/approval-decide', { method:'POST', body:{ decision: decision } });
    zV2_toast(decision === 'approve' ? 'Đã duyệt ✅' : 'Đã từ chối', 'success');
  } catch(e) { zV2_toast('Thao tác thất bại: ' + (e.message || ''), 'error'); }
};

window.zV2_renderPollCard = function(msg, d) {
  var me = (typeof zV2_getCurrentUser === 'function' && zV2_getCurrentUser())
    ? (zV2_getCurrentUser().username || '')
    : ((window._zV2 && window._zV2.currentUser && window._zV2.currentUser.username) || '');
  var opts = d.options || [];
  var accent = '#7c5cff';
  var total = 0; opts.forEach(function(o){ total += ((o.votes||[]).length); });
  var rows = opts.map(function(o, i){
    var vc = (o.votes||[]).length;
    var pct = total ? Math.round(vc*100/total) : 0;
    var voted = (o.votes||[]).indexOf(me) >= 0;
    return '<button data-action="vote" data-msg-id="'+zV2_escapeHtml(msg.id)+'" data-opt="'+i+'" style="position:relative;display:block;width:100%;text-align:left;border:1px solid '+(voted?accent:'var(--z-border)')+';background:var(--z-white);border-radius:9px;padding:9px 12px;margin-bottom:7px;cursor:pointer;overflow:hidden;font-family:inherit;">' +
      '<div style="position:absolute;left:0;top:0;bottom:0;width:'+pct+'%;background:'+(voted?'rgba(124,92,255,.16)':'var(--z-bg)')+';z-index:0;transition:width .35s;"></div>' +
      '<div style="position:relative;z-index:1;display:flex;justify-content:space-between;gap:8px;align-items:center;">' +
        '<span style="font-size:14px;color:var(--z-text);font-weight:'+(voted?'600':'500')+';">'+(voted?'✓ ':'')+zV2_escapeHtml(o.text||'')+'</span>' +
        '<span style="font-size:12.5px;color:var(--z-muted);white-space:nowrap;">'+vc+' · '+pct+'%</span>' +
      '</div></button>';
  }).join('');
  return '' +
    '<div style="display:flex;justify-content:center;padding:6px 10px;">' +
      '<div style="width:100%;max-width:460px;border:1px solid var(--z-border);border-radius:12px;background:var(--z-white);box-shadow:0 1px 5px rgba(0,0,0,.07);overflow:hidden;">' +
        '<div style="padding:12px 14px;border-left:4px solid '+accent+';">' +
          '<div style="font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:'+accent+';margin-bottom:3px;">📊 Bình chọn</div>' +
          '<div style="font-weight:600;font-size:14.5px;color:var(--z-text);line-height:1.3;margin-bottom:10px;word-break:break-word;">'+zV2_escapeHtml(d.question||'')+'</div>' +
          rows +
          '<div style="font-size:11.5px;color:var(--z-muted);margin-top:4px;">'+total+' lượt · tạo bởi '+zV2_escapeHtml(d.by_name||'')+' · bấm để chọn/bỏ</div>' +
        '</div>' +
      '</div>' +
    '</div>';
};

window.zV2_votePoll = async function(cardMsgId, optIdx) {
  try {
    await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(cardMsgId) + '/poll-vote', { method:'POST', body:{ option_index: optIdx } });
  } catch(e) { zV2_toast('Bình chọn thất bại: ' + (e.message || ''), 'error'); }
};

window.zV2_renderCardRow = function(msg) {
  var d;
  try { d = JSON.parse(msg.content || '{}'); } catch(e) { d = null; }
  if (!d || !d.kind) {
    return '<div class="zV2_call_log"><span class="zV2_call_log_pill">' + zV2_escapeHtml(msg.content || '') + '</span></div>';
  }
  if (d.kind === 'approval') { return zV2_renderApprovalCard(msg, d); }
  if (d.kind === 'poll') { return zV2_renderPollCard(msg, d); }
  var isTask = d.kind === 'task';
  var icon = isTask ? '📋' : '📅';
  var accent = isTask ? ((d.prio === 'khan_cap' || d.prio === 'cao') ? '#e8590c' : '#0068FF') : (d.color || '#0084ff');
  var kindLabel = isTask ? 'Nhiệm vụ' : 'Lịch';
  var url = d.url || (isTask ? '/giao-viec' : '/lich-lam-viec');
  var by = zV2_escapeHtml(msg.sender_name || msg.sender_username || '');
  var metaHtml = (d.meta || []).map(function(m){ return zV2_escapeHtml(m); }).join(' &nbsp;·&nbsp; ');
  return '' +
    '<div style="display:flex;justify-content:center;padding:6px 10px;">' +
      '<div style="width:100%;max-width:460px;border:1px solid var(--z-border);border-radius:12px;background:var(--z-white);box-shadow:0 1px 5px rgba(0,0,0,.07);overflow:hidden;">' +
        '<div style="display:flex;align-items:flex-start;gap:11px;padding:12px 14px;border-left:4px solid '+accent+';">' +
          '<div style="font-size:22px;line-height:1;">'+icon+'</div>' +
          '<div style="flex:1;min-width:0;">' +
            '<div style="font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:'+accent+';margin-bottom:2px;">'+kindLabel+'</div>' +
            '<div style="font-weight:600;font-size:14.5px;color:var(--z-text);line-height:1.3;word-break:break-word;">'+zV2_escapeHtml(d.title||'')+'</div>' +
            '<div style="font-size:12.5px;color:var(--z-muted);margin-top:4px;line-height:1.5;">'+metaHtml+'</div>' +
          '</div>' +
        '</div>' +
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:9px 14px;border-top:1px solid var(--z-border);background:var(--z-bg);">' +
          '<span style="font-size:11.5px;color:var(--z-muted);">Tạo bởi '+by+'</span>' +
          '<a href="'+zV2_escapeHtml(url)+'" style="text-decoration:none;font-size:13px;font-weight:600;color:#fff;background:'+accent+';padding:6px 14px;border-radius:7px;white-space:nowrap;">Xem chi tiết →</a>' +
        '</div>' +
      '</div>' +
    '</div>';
};

window.zV2_buildMessageRow = function (msg, prev, next, currentUser) {
  var isOwn = msg.sender_username === currentUser.username;
  if (msg.msg_type === 'card' && !msg.is_deleted) { return zV2_renderCardRow(msg); }
  if (msg.msg_type === 'call') {
    var _cc = zV2_escapeHtml(msg.content || '\ud83d\udcde Cuộc gọi');
    return '<div class="zV2_call_log"><span class="zV2_call_log_pill">' + _cc + '</span></div>';
  }
  var GAP = 5 * 60; // 5 minutes

  var firstOfGroup = !prev ||
    prev.sender_username !== msg.sender_username ||
    !zV2_sameDay(prev.created_at, msg.created_at) ||
    zV2_timeGap(prev.created_at, msg.created_at) > GAP;
  var lastOfGroup = !next ||
    next.sender_username !== msg.sender_username ||
    !zV2_sameDay(next.created_at, msg.created_at) ||
    zV2_timeGap(next.created_at, msg.created_at) > GAP;

  var rowCls = ['zV2_msg_row'];
  if (isOwn) rowCls.push('zV2_msg_row--own');
  else rowCls.push('zV2_msg_row--other');
  if (firstOfGroup) rowCls.push('zV2_msg_row--first_of_group');
  if (lastOfGroup) rowCls.push('zV2_msg_row--last_of_group');

  var avatarHtml = '';
  if (!isOwn) {
    var initial = zV2_escapeHtml((msg.sender_name || msg.sender_username || '?').charAt(0).toUpperCase());
    var avaBg = zV2_avatarBg(msg.sender_name || msg.sender_username || '');
    // Dùng URL endpoint thay base64 — browser cache 1 ngày, không truyền qua wire mỗi lần
    var avaUrl = msg.sender_username
      ? '/api/chat/users/' + encodeURIComponent(msg.sender_username) + '/avatar'
      : '';
    avatarHtml = '<div class="zV2_msg_avatar" style="background:' + avaBg + ';position:relative;">' +
      '<span class="zV2_msg_avatar_initial" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;">' + initial + '</span>' +
      (avaUrl ? '<img src="' + avaUrl + '" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;border-radius:50%;z-index:1;" onerror="this.style.display=\'none\'" />' : '') +
      '</div>';
  }

  var senderName = '';
  if (!isOwn && firstOfGroup) {
    senderName = '<div class="zV2_msg_sender_name">' +
      zV2_escapeHtml(msg.sender_name || msg.sender_username || '') + '</div>';
  }

  // Build content
  var contentHtml = '';
  var bubbleCls = ['zV2_bubble'];
  if (isOwn) bubbleCls.push('zV2_bubble--own');
  if (msg.msg_type === 'image') bubbleCls.push('zV2_bubble--image');

  if (msg.is_deleted) {
    bubbleCls.push('zV2_bubble_deleted');
    contentHtml = '<span class="zV2_deleted_text">Tin nhắn đã được thu hồi</span>';
  } else {
    // Reply quote
    if (msg.reply_to_id && msg.reply_to) {
      contentHtml += '<div class="zV2_bubble_reply_quote">' +
        '<div class="zV2_reply_quote_sender">' +
        zV2_escapeHtml(msg.reply_to.sender_name || msg.reply_to.sender_username || '') + '</div>' +
        '<div class="zV2_reply_quote_text">' +
        zV2_escapeHtml(zV2_truncate(msg.reply_to.content || (msg.reply_to.file_name) || '[Đính kèm]', 120)) +
        '</div></div>';
    }
    if (msg.msg_type === 'image' && msg.file_url) {
      // Legacy URL fallback: /api/uploads/chat_X/abc → /api/chat/files/X/abc
      var imgUrl = msg.file_url.replace(/^\/api\/uploads\/chat_(\d+)\//, '/api/chat/files/$1/');
      // Reserve dung o theo kich thuoc that -> KHONG nhay/giat khi anh tai luc scroll
      var _dimAttr = (msg.img_w && msg.img_h)
        ? ' width="' + msg.img_w + '" height="' + msg.img_h + '" style="aspect-ratio:' + msg.img_w + '/' + msg.img_h + '"'
        : '';
      contentHtml += '<img class="zV2_msg_img zV2_lazy_img" data-src="' + zV2_escapeHtml(imgUrl) + '" ' +
        'data-action="lightbox" src=""' + _dimAttr + ' ' +
        'alt="' + zV2_escapeHtml(msg.file_name || '') + '" loading="lazy" />';
      if (msg.content) {
        var _rc = typeof window.zV2_renderContent==='function'?window.zV2_renderContent(msg.content,msg.mentions):zV2_escapeHtml(msg.content);
    contentHtml += '<div class="zV2_msg_text">' + _rc + '</div>';
      }
    } else if (msg.msg_type === 'file' && msg.file_url) {
      var fileUrl = msg.file_url.replace(/^\/api\/uploads\/chat_(\d+)\//, '/api/chat/files/$1/');
      contentHtml += '<a href="' + zV2_escapeHtml(fileUrl) + '" target="_blank" ' +
        'class="zV2_msg_file_card" download="' + zV2_escapeHtml(msg.file_name || '') + '">' +
        '<div class="zV2_msg_file_icon"></div>' +
        '<div class="zV2_msg_file_info">' +
        '<div class="zV2_msg_file_name">' + zV2_escapeHtml(msg.file_name || 'Tệp đính kèm') + '</div>' +
        '<div class="zV2_msg_file_meta">' + zV2_escapeHtml(zV2_formatFileSize(msg.file_size || 0)) + '</div>' +
        '</div></a>';
      if (msg.content) {
        var _rc = typeof window.zV2_renderContent==='function'?window.zV2_renderContent(msg.content,msg.mentions):zV2_escapeHtml(msg.content);
    contentHtml += '<div class="zV2_msg_text">' + _rc + '</div>';
      }
    } else {
      contentHtml += '<div class="zV2_msg_text">' + zV2_linkifyCodes(zV2_escapeHtml(msg.content || '')) + '</div>';
    }
    if (msg.edited_at) {
      contentHtml += '<span class="zV2_msg_edited">(đã chỉnh sửa)</span>';
    }
  }

  // Reactions
  var reactionsHtml = '';
  if (Array.isArray(msg.reactions) && msg.reactions.length > 0 && !msg.is_deleted) {
    reactionsHtml = '<div class="zV2_bubble_reactions">';
    msg.reactions.forEach(function (r) {
      var cls = 'zV2_reaction_chip' + (r.by_me ? ' zV2_reaction_chip--mine' : '');
      reactionsHtml += '<span class="' + cls + '" data-emoji="' + zV2_escapeHtml(r.emoji) + '" ' +
        'data-msg-id="' + zV2_escapeHtml(msg.id) + '" ' +
        'title="' + zV2_escapeHtml((r.users || []).join(', ')) + '">' +
        zV2_escapeHtml(r.emoji) + ' <span class="zV2_reaction_count">' + (r.count || 1) + '</span>' +
        '</span>';
    });
    reactionsHtml += '</div>';
  }

  // Actions floating — SVG icons (Feather style)
  var SVG = {
    reply: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 17 4 12 9 7"/><path d="M20 18v-2a4 4 0 0 0-4-4H4"/></svg>',
    react: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M8 14s1.5 2 4 2 4-2 4-2"/><line x1="9" y1="9" x2="9.01" y2="9"/><line x1="15" y1="9" x2="15.01" y2="9"/></svg>',
    forward: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="15 17 20 12 15 7"/><path d="M4 18v-2a4 4 0 0 1 4-4h12"/></svg>',
    task: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
    event: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>',
    approval: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>',
    poll: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
    pin: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg>',
    pinFill: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"><line x1="12" y1="17" x2="12" y2="22" stroke-width="2"/><path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24z"/></svg>',
    edit: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>',
    trash: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/></svg>'
  };
  var actionsHtml = '';
  if (!msg.is_deleted) {
    actionsHtml = '<div class="zV2_msg_actions">';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="reply" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Trả lời">' + SVG.reply + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="thread" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Hội thoại độc lập" style="font-size:15px;">Nhắn</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="react" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Cảm xúc">' + SVG.react + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="forward" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Chuyển tiếp">' + SVG.forward + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="task" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Tạo nhiệm vụ">' + SVG.task + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="event" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Tạo lịch">' + SVG.event + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="approval" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Yêu cầu duyệt">' + SVG.approval + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="poll" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" title="Tạo bình chọn">' + SVG.poll + '</button>';
    actionsHtml += '<button class="zV2_msg_action_btn" data-action="pin" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '" data-pinned="' + (msg.is_pinned ? '1' : '0') + '" title="Ghim">' + (msg.is_pinned ? SVG.pinFill : SVG.pin) + '</button>';
    if (isOwn && msg.msg_type === 'text') {
      actionsHtml += '<button class="zV2_msg_action_btn" data-action="edit" data-msg-id="' +
        zV2_escapeHtml(msg.id) + '" title="Chỉnh sửa">' + SVG.edit + '</button>';
    }
    if (isOwn) {
      actionsHtml += '<button class="zV2_msg_action_btn" data-action="recall" data-msg-id="' +
        zV2_escapeHtml(msg.id) + '" title="Thu hồi">' + SVG.trash + '</button>';
    }
    actionsHtml += '</div>';
  }

  // Time + ticks
  var timeHtml = '';
  if (lastOfGroup) {
    var ticks = '';
    if (isOwn && !msg.is_deleted) {
      var roomObj = (_zV2.rooms || []).find(function (r) { return r.id === msg.room_id; });
      var membersCount = (roomObj && (roomObj.members_count || (roomObj.members && roomObj.members.length))) || 2;
      var readByCount = (msg.read_by || []).filter(function (u) { return u !== currentUser.username; }).length;
      ticks = readByCount >= (membersCount - 1) && membersCount > 1
        ? '<span class="zV2_msg_ticks zV2_msg_ticks--read">✓✓</span>'
        : '<span class="zV2_msg_ticks">✓</span>';
    }
    timeHtml = '<div class="zV2_msg_time">' + zV2_escapeHtml(zV2_formatTime(msg.created_at)) + ticks + '</div>';
  }

  // Thread count badge
  var threadBadgeHtml = '';
  if (!msg.is_deleted && msg.thread_count && msg.thread_count > 0) {
    threadBadgeHtml = '<div class="zV2_thread_badge" data-action="thread" data-msg-id="' +
      zV2_escapeHtml(msg.id) + '">' + msg.thread_count + ' trả lời trong hội thoại</div>';
  }

  // Compose row HTML
  return '<div class="' + rowCls.join(' ') + '" data-msg-id="' + zV2_escapeHtml(msg.id) + '" ' +
    'data-sender="' + zV2_escapeHtml(msg.sender_username || '') + '">' +
    (isOwn ? '' : avatarHtml) +
    '<div class="zV2_msg_bubble_wrap">' +
    senderName +
    '<div class="zV2_bubble_outer">' +
    '<div class="' + bubbleCls.join(' ') + '">' + contentHtml + '</div>' +
    reactionsHtml +
    actionsHtml +
    '</div>' +
    timeHtml +
    threadBadgeHtml +
    '</div>' +
    '</div>';
};

// ---------- Bind delegated events ----------
window.zV2_bindMessageEvents = function (roomId) {
  var inner = document.getElementById('zV2_messages_inner');
  if (!inner) return;
  if (inner._zV2Bound) return;
  inner._zV2Bound = true;

  inner.addEventListener('click', function (e) {
    var t = e.target;
    // Reaction chip
    var chip = t.closest && t.closest('.zV2_reaction_chip');
    if (chip) {
      e.preventDefault();
      var msgId = chip.getAttribute('data-msg-id');
      var emoji = chip.getAttribute('data-emoji');
      zV2_toggleReaction(msgId, emoji);
      return;
    }
    // Lightbox image — dùng data-src nếu còn (chưa lazy-load), fallback về src
    if (t.getAttribute && t.getAttribute('data-action') === 'lightbox') {
      e.preventDefault();
      zV2_openLightbox(t.getAttribute('data-src') || t.src);
      return;
    }
    var btn = t.closest && t.closest('[data-action]');
    if (!btn) return;
    var action = btn.getAttribute('data-action');
    var mId = btn.getAttribute('data-msg-id');
    if (!action || !mId) return;
    switch (action) {
      case 'reply': zV2_setReplyTo(mId); break;
      case 'thread': if (typeof window.zV2_openThread === 'function') window.zV2_openThread(mId, _zV2.currentRoomId); break;
      case 'react': zV2_showEmojiPicker(mId, btn); break;
      case 'forward': zV2_openForwardModal(mId); break;
      case 'pin': zV2_togglePin(mId, btn.getAttribute('data-pinned') === '1'); break;
      case 'edit': zV2_startEditMessage(mId); break;
      case 'recall': zV2_recallMessage(mId); break;
      case 'task': zV2_openTaskModal(mId); break;
      case 'event': zV2_openEventModal(mId); break;
      case 'approval': zV2_openApprovalModal(mId); break;
      case 'approve': zV2_decideApproval(mId, 'approve'); break;
      case 'reject': zV2_decideApproval(mId, 'reject'); break;
      case 'poll': zV2_openPollModal(mId); break;
      case 'vote': zV2_votePoll(mId, parseInt((btn.getAttribute('data-opt') || '0'), 10)); break;
    }
  });
};

// ---------- Lightbox ----------
window.zV2_openLightbox = function (src) {
  if (!src) return;
  var existing = document.getElementById('zV2_lightbox_overlay');
  if (existing) existing.remove();
  var ov = document.createElement('div');
  ov.id = 'zV2_lightbox_overlay';
  ov.className = 'zV2_lightbox_overlay';
  ov.innerHTML = '<img src="' + zV2_escapeHtml(src) + '" class="zV2_lightbox_img" />' +
    '<button class="zV2_lightbox_close" type="button" aria-label="Đóng">✕</button>';

  function close() {
    ov.remove();
    document.removeEventListener('keydown', escHandler);
  }
  function escHandler(e) {
    if (e.key === 'Escape') close();
  }

  // Click backdrop hoặc nút ✕ → đóng. Click vào ảnh → KHÔNG đóng.
  ov.addEventListener('click', function (e) {
    if (e.target === ov || e.target.classList.contains('zV2_lightbox_close')) {
      close();
    }
  });
  document.addEventListener('keydown', escHandler);

  document.body.appendChild(ov);
};

// ---------- Find message helper ----------
window.zV2_findMessage = function (msgId) {
  var rid = _zV2.currentRoomId;
  if (!rid) return null;
  var arr = (_zV2.messages && _zV2.messages[rid]) || [];
  return arr.find(function (m) { return String(m.id) === String(msgId); }) || null;
};

window.zV2_findMessageAnyRoom = function (msgId) {
  var maps = _zV2.messages || {};
  for (var rid in maps) {
    var found = (maps[rid] || []).find(function (m) { return String(m.id) === String(msgId); });
    if (found) return { msg: found, roomId: rid };
  }
  return null;
};

// ---------- Send message ----------
window.zV2_sendMessage = async function (forceContent) {
  // LOCK: chống gọi đôi (nhiều listener trùng hoặc spam Enter)
  if (_zV2._sending) {
    console.warn('[zV2] sendMessage already in flight — bỏ qua');
    return;
  }
  var rid = _zV2.currentRoomId;
  if (!rid) return;
  var input = document.getElementById('zV2_compose_input');
  var content = forceContent !== undefined ? forceContent : (input ? input.value.trim() : '');

  // Nếu có ảnh đang pending (paste preview) → upload ảnh thay vì gửi text
  if (_zV2._pendingPasteFile) {
    var pendingFile = _zV2._pendingPasteFile;
    window.zV2_clearPastePreview();
    if (input) input.value = '';
    _zV2._sending = false; // release lock trước khi upload
    await zV2_uploadFile(pendingFile);
    return;
  }

  if (!content) return;
  _zV2._sending = true;

  try {
    // Editing?
    if (_zV2.editingMsgId) {
      try {
        var updated = await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(_zV2.editingMsgId), {
          method: 'PATCH',
          body: { content: content }
        });
        var arr = _zV2.messages[rid] || [];
        var idx = arr.findIndex(function (m) { return String(m.id) === String(_zV2.editingMsgId); });
        if (idx >= 0 && updated) arr[idx] = Object.assign({}, arr[idx], updated);
        _zV2.editingMsgId = null;
        if (input) {
          input.value = '';
          input.placeholder = 'Nhập tin nhắn...';
        }
        zV2_renderMessages(rid);
      } catch (e) {
        console.error('[zV2] edit failed', e);
        zV2_toast('Chỉnh sửa thất bại', 'error');
      }
      return;
    }

    var body = { content: content };
    if (_zV2.replyTo && _zV2.replyTo.id) body.reply_to_id = _zV2.replyTo.id;

    // Clear input ngay (trước khi gửi — cải thiện UX)
    if (input) input.value = '';
    _zV2.replyTo = null;
    var rs = document.getElementById('zV2_reply_strip');
    if (rs) rs.style.display = 'none';
    zV2_updateComposerButtons();

    // Optimistic bubble: hiển thị tin nhắn ngay trước khi API response
    var tempId = -Date.now();
    var optimisticMsg = {
      id: tempId,
      room_id: rid,
      sender_username: window.currentUsername,
      sender_name: window.currentUserDisplayName || window.currentUsername,
      content: content,
      msg_type: 'text',
      created_at: new Date().toISOString(),
      read_by: [],
      reactions: [],
      thread_count: 0,
      is_pinned: false,
      is_optimistic: true
    };
    var inner = document.getElementById('zV2_messages_inner');
    var me = zV2_getCurrentUser();
    if (inner) {
      var arr = _zV2.messages[rid] || [];
      var prevMsg = arr.length > 0 ? arr[arr.length - 1] : null;
      var optHtml = zV2_buildMessageRow(optimisticMsg, prevMsg, null, me);
      inner.insertAdjacentHTML('beforeend', optHtml);
      zV2_scrollBottom('smooth');
    }

    try {
      var msg = await zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/messages', {
        method: 'POST',
        body: body
      });
      // Xoá optimistic bubble (SSE sẽ thêm real bubble)
      var optEl = inner ? inner.querySelector('[data-msg-id="' + tempId + '"]') : null;
      if (optEl) optEl.remove();
      if (msg && msg.id) {
        _zV2.messages[rid] = _zV2.messages[rid] || [];
        if (!_zV2.messages[rid].some(function (x) { return String(x.id) === String(msg.id); })) {
          _zV2.messages[rid].push(msg);
        }
        zV2_renderMessages(rid);
        zV2_scrollBottom('smooth');
      }
    } catch (e) {
      console.error('[zV2] send failed', e);
      // Đánh dấu bubble thất bại bằng opacity thấp hơn
      var optEl = inner ? inner.querySelector('[data-msg-id="' + tempId + '"]') : null;
      if (optEl) optEl.style.opacity = '0.4';
      zV2_toast('Gửi tin nhắn thất bại', 'error');
    }
  } finally {
    _zV2._sending = false;
  }
};

// ---------- File / Image upload ----------
window.zV2_uploadFile = async function (file) {
  var rid = _zV2.currentRoomId;
  if (!rid || !file) return;
  if (file.size > 25 * 1024 * 1024) { zV2_toast('File quá lớn (>25MB)', 'error'); return; }
  var fd = new FormData();
  fd.append('file', file);
  var t = zV2_toast('Đang tải ' + file.name + '...', 'info', 60000);
  try {
    var res = await fetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/upload', {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    var msg = await res.json();
    if (msg && msg.id) {
      _zV2.messages[rid] = _zV2.messages[rid] || [];
      if (!_zV2.messages[rid].some(function(x){ return String(x.id) === String(msg.id); })) {
        _zV2.messages[rid].push(msg);
      }
      zV2_renderMessages(rid);
      zV2_scrollBottom('smooth');
    }
    zV2_toast('Đã gửi: ' + file.name, 'success');
  } catch(e) {
    console.error('[zV2] upload failed', e);
    zV2_toast('Tải lên thất bại: ' + (e.message || ''), 'error');
  }
  if (t && t.remove) try { t.remove(); } catch(_){}
};

// Wire toàn bộ compose buttons (gọi 1 lần sau init)
window.zV2_wireUpload = function () {
  var btnImage = document.getElementById('zV2_btn_image');
  var btnFile  = document.getElementById('zV2_btn_file');
  var btnEmoji = document.getElementById('zV2_btn_emoji');
  var btnSticker = document.getElementById('zV2_btn_sticker');
  var btnMic   = document.getElementById('zV2_btn_mic');
  var imgInput = document.getElementById('zV2_image_input');
  var fileInput= document.getElementById('zV2_file_input');
  if (btnImage && !btnImage._zV2Bound) {
    btnImage._zV2Bound = true;
    btnImage.addEventListener('click', function(){ if (imgInput) imgInput.click(); });
  }
  if (btnFile && !btnFile._zV2Bound) {
    btnFile._zV2Bound = true;
    btnFile.addEventListener('click', function(){ if (fileInput) fileInput.click(); });
  }
  if (imgInput && !imgInput._zV2Bound) {
    imgInput._zV2Bound = true;
    imgInput.addEventListener('change', function(){
      if (imgInput.files && imgInput.files[0]) zV2_uploadFile(imgInput.files[0]);
      imgInput.value = '';
    });
  }
  if (fileInput && !fileInput._zV2Bound) {
    fileInput._zV2Bound = true;
    fileInput.addEventListener('change', function(){
      if (fileInput.files && fileInput.files[0]) zV2_uploadFile(fileInput.files[0]);
      fileInput.value = '';
    });
  }
  // Emoji button: mở picker insert vào textarea
  if (btnEmoji && !btnEmoji._zV2Bound) {
    btnEmoji._zV2Bound = true;
    btnEmoji.addEventListener('click', function(ev){
      ev.stopPropagation();
      zV2_openComposeEmojiPicker(btnEmoji);
    });
  }
  if (btnSticker && !btnSticker._zV2Bound) {
    btnSticker._zV2Bound = true;
    btnSticker.addEventListener('click', function(){
      zV2_toast('Sticker — đang phát triển', 'info');
    });
  }
  if (btnMic && !btnMic._zV2Bound) {
    btnMic._zV2Bound = true;
    btnMic.addEventListener('click', function(){
      zV2_toast('Ghi âm — đang phát triển', 'info');
    });
  }
};

// ---------- Paste image preview ----------
window.zV2_showPastePreview = function (file) {
  if (!file) return;
  _zV2._pendingPasteFile = file;
  var preview = document.getElementById('zV2_paste_preview');
  var thumb   = document.getElementById('zV2_paste_thumb');
  var name    = document.getElementById('zV2_paste_name');
  if (!preview || !thumb) return;
  // Hiện thumbnail bằng object URL
  if (thumb._objUrl) URL.revokeObjectURL(thumb._objUrl);
  thumb._objUrl = URL.createObjectURL(file);
  thumb.src = thumb._objUrl;
  if (name) name.textContent = file.name || 'Ảnh đã dán';
  preview.classList.add('visible');
  // Focus vào input để có thể gõ caption và Enter ngay
  var input = document.getElementById('zV2_compose_input');
  if (input) { input.placeholder = 'Thêm chú thích (tuỳ chọn)...'; input.focus(); }
};

window.zV2_clearPastePreview = function () {
  _zV2._pendingPasteFile = null;
  var preview = document.getElementById('zV2_paste_preview');
  var thumb   = document.getElementById('zV2_paste_thumb');
  var input   = document.getElementById('zV2_compose_input');
  if (preview) preview.classList.remove('visible');
  if (thumb && thumb._objUrl) { URL.revokeObjectURL(thumb._objUrl); thumb._objUrl = null; thumb.src = ''; }
  if (input) input.placeholder = 'Nhập tin nhắn...';
};

window.zV2_wirePastePreview = function () {
  var clearBtn = document.getElementById('zV2_paste_clear');
  if (clearBtn && !clearBtn._zV2Bound) {
    clearBtn._zV2Bound = true;
    clearBtn.addEventListener('click', function () { window.zV2_clearPastePreview(); });
  }
};

// Compose emoji picker (mở từ nút dưới input — chèn emoji vào textarea)
window.zV2_openComposeEmojiPicker = function(anchorEl){
  var existing = document.getElementById('zV2_compose_emoji_pop');
  if (existing) { existing.remove(); return; }
  // Bộ emoji thông dụng cho công ty: 5 hàng × 8 emoji
  var emojis = [
    '😀','😃','😄','😁','😆','😅','😂','🤣',
    '🙂','😊','😇','🥰','😍','😘','😋','😎',
    '🤔','🤨','😐','😑','🙄','😏','😴','🤗',
    '😢','😭','😤','😠','😰','😱','🤯','😳',
    '👍','👎','👌','✌️','🤝','👏','🙏','💪',
    '❤️','🧡','💛','💚','💙','💜','🔥','⭐',
    '✅','❌','⚠️','📌','📎','📅','📊','💰',
    '🎉','🎊','🚀','💡','❓','❗','⏰','☕'
  ];
  var pop = document.createElement('div');
  pop.id = 'zV2_compose_emoji_pop';
  pop.className = 'zV2_compose_emoji_pop';
  pop.innerHTML = emojis.map(function(e){
    return '<button class="zV2_compose_emoji_btn" data-emoji="' + zV2_escapeHtml(e) + '">' + zV2_escapeHtml(e) + '</button>';
  }).join('');
  document.body.appendChild(pop);
  // Position phía trên anchor (8 cột × 36px = 288px wide)
  var r = anchorEl.getBoundingClientRect();
  var pr = pop.getBoundingClientRect();
  var left = r.left;
  if (left + pr.width > window.innerWidth - 8) left = window.innerWidth - pr.width - 8;
  if (left < 8) left = 8;
  var top = r.top - pr.height - 8;
  if (top < 8) top = r.bottom + 8;
  pop.style.left = left + 'px';
  pop.style.top  = top  + 'px';
  // Click emoji → insert vào textarea
  pop.addEventListener('click', function(ev){
    var b = ev.target.closest('.zV2_compose_emoji_btn');
    if (!b) return;
    var em = b.getAttribute('data-emoji');
    var inp = document.getElementById('zV2_compose_input');
    if (inp) {
      var start = inp.selectionStart || inp.value.length;
      var end = inp.selectionEnd || inp.value.length;
      inp.value = inp.value.slice(0, start) + em + inp.value.slice(end);
      inp.focus();
      inp.setSelectionRange(start + em.length, start + em.length);
      // Trigger input event để update send/thumbs button
      inp.dispatchEvent(new Event('input', { bubbles: true }));
    }
  });
  setTimeout(function(){
    document.addEventListener('click', function onDoc(e){
      if (!pop.contains(e.target) && e.target !== anchorEl) {
        pop.remove();
        document.removeEventListener('click', onDoc);
      }
    });
  }, 0);
};

// ---------- Reply ----------
window.zV2_setReplyTo = function (msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  _zV2.replyTo = msg;
  var rs = document.getElementById('zV2_reply_strip');
  if (rs) {
    rs.style.display = '';
    rs.innerHTML = '<div class="zV2_reply_strip_inner">' +
      '<div class="zV2_reply_strip_icon">↩</div>' +
      '<div class="zV2_reply_strip_body">' +
      '<div class="zV2_reply_strip_sender">Đang trả lời ' +
      zV2_escapeHtml(msg.sender_name || msg.sender_username || '') + '</div>' +
      '<div class="zV2_reply_strip_text">' +
      zV2_escapeHtml(zV2_truncate(msg.content || msg.file_name || '[Đính kèm]', 80)) +
      '</div></div>' +
      '<button class="zV2_reply_strip_close" data-action="reply-close">✕</button>' +
      '</div>';
    rs.querySelector('[data-action="reply-close"]').addEventListener('click', function () {
      _zV2.replyTo = null;
      rs.style.display = 'none';
    });
  }
  var input = document.getElementById('zV2_compose_input');
  if (input) input.focus();
};

// ---------- Edit ----------
window.zV2_startEditMessage = function (msgId) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  _zV2.editingMsgId = msgId;
  var input = document.getElementById('zV2_compose_input');
  if (input) {
    input.value = msg.content || '';
    input.placeholder = 'Chỉnh sửa tin nhắn... (Esc hủy)';
    input.focus();
    try {
      var len = input.value.length;
      input.setSelectionRange(len, len);
    } catch (e) { }
  }
  zV2_updateComposerButtons();
};

window.zV2_cancelEdit = function () {
  if (!_zV2.editingMsgId) return;
  _zV2.editingMsgId = null;
  var input = document.getElementById('zV2_compose_input');
  if (input) {
    input.value = '';
    input.placeholder = 'Nhập tin nhắn...';
  }
  zV2_updateComposerButtons();
};

// ---------- Recall ----------
window.zV2_recallMessage = async function (msgId) {
  if (!confirm('Thu hồi tin nhắn này? Tin sẽ bị xoá với mọi người.')) return;
  try {
    await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId), { method: 'DELETE' });
    // SSE will broadcast message_deleted; local optimistic update
    var found = zV2_findMessageAnyRoom(msgId);
    if (found) {
      found.msg.is_deleted = true;
      zV2_renderMessages(found.roomId);
    }
  } catch (e) {
    console.error('[zV2] recall failed', e);
    zV2_toast('Thu hồi thất bại', 'error');
  }
};

// ---------- Pin ----------
window.zV2_togglePin = async function (msgId, currentlyPinned) {
  var rid = _zV2.currentRoomId;
  if (!rid) return;
  try {
    if (currentlyPinned) {
      await zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/pin/' + encodeURIComponent(msgId), { method: 'DELETE' });
    } else {
      await zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/pin/' + encodeURIComponent(msgId), { method: 'POST' });
    }
  } catch (e) {
    console.error('[zV2] pin failed', e);
    zV2_toast('Ghim thất bại', 'error');
  }
};

// ---------- Reaction ----------
window.zV2_toggleReaction = async function (msgId, emoji) {
  var msg = zV2_findMessage(msgId);
  if (!msg) return;
  var existing = (msg.reactions || []).find(function (r) { return r.emoji === emoji; });
  var byMe = existing && existing.by_me;
  try {
    if (byMe) {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) +
        '/reactions/' + encodeURIComponent(emoji), { method: 'DELETE' });
    } else {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/reactions', {
        method: 'POST',
        body: { emoji: emoji }
      });
    }
  } catch (e) {
    console.error('[zV2] reaction failed', e);
  }
};

// ---------- Emoji picker ----------
window.zV2_showEmojiPicker = function (msgId, anchorEl) {
  var existing = document.getElementById('zV2_emoji_picker_pop');
  if (existing) existing.remove();
  var emojis = ['👍', '❤️', '😂', '😮', '😢', '🙏'];
  var pop = document.createElement('div');
  pop.id = 'zV2_emoji_picker_pop';
  pop.className = 'zV2_emoji_picker_pop';
  pop.innerHTML = emojis.map(function (e) {
    return '<button class="zV2_emoji_btn" data-emoji="' + zV2_escapeHtml(e) + '">' + zV2_escapeHtml(e) + '</button>';
  }).join('');
  pop.style.position = 'fixed';
  pop.style.visibility = 'hidden';
  pop.style.zIndex = 99999;
  document.body.appendChild(pop);
  // Position — center horizontally over the bubble (or anchor), above
  if (anchorEl) {
    var row = anchorEl.closest('.zV2_msg_row');
    var bubble = row ? row.querySelector('.zV2_bubble') : null;
    var anchorRect = (bubble || anchorEl).getBoundingClientRect();
    var pickerRect = pop.getBoundingClientRect();
    var pw = pickerRect.width  || 300;
    var ph = pickerRect.height || 54;
    // Center horizontally
    var left = anchorRect.left + (anchorRect.width / 2) - (pw / 2);
    var top  = anchorRect.top - ph - 10;
    // Clamp to viewport (8px padding)
    var maxL = window.innerWidth - pw - 8;
    if (left < 8)    left = 8;
    if (left > maxL) left = maxL;
    // If above viewport, place below the bubble
    if (top < 8) top = anchorRect.bottom + 10;
    pop.style.left = left + 'px';
    pop.style.top  = top  + 'px';
  }
  pop.style.visibility = '';
  pop.addEventListener('click', function (e) {
    var b = e.target.closest('.zV2_emoji_btn');
    if (!b) return;
    var em = b.getAttribute('data-emoji');
    zV2_toggleReaction(msgId, em);
    pop.remove();
  });
  setTimeout(function () {
    document.addEventListener('click', function onDoc(ev) {
      if (!pop.contains(ev.target)) {
        pop.remove();
        document.removeEventListener('click', onDoc);
      }
    });
  }, 10);
};

// ---------- Forward modal ----------
window.zV2_openForwardModal = function (msgId) {
  var existing = document.getElementById('zV2_forward_modal');
  if (existing) existing.remove();
  var rooms = (_zV2.rooms || []).filter(function (r) { return r.id !== _zV2.currentRoomId; });
  var modal = document.createElement('div');
  modal.id = 'zV2_forward_modal';
  modal.className = 'zV2_modal_overlay';
  modal.innerHTML =
    '<div class="zV2_modal_box">' +
    '<div class="zV2_modal_header">' +
    '<div class="zV2_modal_title">Chuyển tiếp tới...</div>' +
    '<button class="zV2_modal_close">✕</button>' +
    '</div>' +
    '<div class="zV2_modal_body">' +
    '<input type="text" class="zV2_modal_search" placeholder="Tìm phòng..." />' +
    '<div class="zV2_modal_list" id="zV2_forward_list">' +
    rooms.map(function (r) {
      var name = r.display_name || r.name || '';
      return '<div class="zV2_modal_item" data-room-id="' + zV2_escapeHtml(r.id) + '">' +
        '<div class="zV2_modal_item_avatar">' + zV2_escapeHtml(name.charAt(0).toUpperCase()) + '</div>' +
        '<div class="zV2_modal_item_name">' + zV2_escapeHtml(name) + '</div></div>';
    }).join('') +
    '</div></div></div>';
  document.body.appendChild(modal);

  modal.querySelector('.zV2_modal_close').addEventListener('click', function () { modal.remove(); });
  modal.addEventListener('click', function (e) {
    if (e.target === modal) modal.remove();
  });
  modal.querySelector('.zV2_modal_search').addEventListener('input', function (e) {
    var q = e.target.value.toLowerCase();
    modal.querySelectorAll('.zV2_modal_item').forEach(function (it) {
      var n = (it.querySelector('.zV2_modal_item_name').textContent || '').toLowerCase();
      it.style.display = n.indexOf(q) >= 0 ? '' : 'none';
    });
  });
  modal.querySelector('#zV2_forward_list').addEventListener('click', async function (e) {
    var item = e.target.closest('.zV2_modal_item');
    if (!item) return;
    var targetRoom = item.getAttribute('data-room-id');
    try {
      await zV2_apiFetch('/api/chat/messages/' + encodeURIComponent(msgId) + '/forward', {
        method: 'POST',
        body: { room_id: targetRoom }
      });
      zV2_toast('Đã chuyển tiếp', 'success');
      modal.remove();
    } catch (err) {
      console.error('[zV2] forward failed', err);
      zV2_toast('Chuyển tiếp thất bại', 'error');
    }
  });
};

// ---------- Typing event ----------
window.zV2_sendTyping = function () {
  var rid = _zV2.currentRoomId;
  if (!rid) return;
  if (_zV2._lastTypingTs && (Date.now() - _zV2._lastTypingTs) < 2000) return;
  _zV2._lastTypingTs = Date.now();
  zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/typing', { method: 'POST' })
    .catch(function () { });
};

// ---------- Composer ----------
window.zV2_updateComposerButtons = function () {
  var input = document.getElementById('zV2_compose_input');
  var thumbs = document.getElementById('zV2_thumbs_btn');
  var send = document.getElementById('zV2_send_btn');
  if (!input) return;
  var hasText = input.value.trim().length > 0;
  // Phải dùng 'flex' explicit (không phải '') vì CSS default cho #zV2_send_btn là display:none
  if (thumbs) thumbs.style.display = hasText ? 'none' : 'flex';
  if (send)   send.style.display   = hasText ? 'flex' : 'none';
};

window.zV2_composeBind = function () {
  var input = document.getElementById('zV2_compose_input');
  var sendBtn = document.getElementById('zV2_send_btn');
  var thumbsBtn = document.getElementById('zV2_thumbs_btn');

  if (input && !input._zV2Bound) {
    input._zV2Bound = true;
    input.addEventListener('input', function () {
      zV2_updateComposerButtons();
      zV2_sendTyping();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        zV2_sendMessage();
      } else if (e.key === 'Escape') {
        if (_zV2.editingMsgId) {
          e.preventDefault();
          zV2_cancelEdit();
        } else if (_zV2.replyTo) {
          e.preventDefault();
          _zV2.replyTo = null;
          var rs = document.getElementById('zV2_reply_strip');
          if (rs) rs.style.display = 'none';
        }
      }
    });
    // Paste ảnh từ clipboard — hiện preview trước, Enter mới gửi
    input.addEventListener('paste', function (e) {
      var cbd = e.clipboardData || window.clipboardData;
      if (!cbd) return;
      var imageFile = null;
      // Check files[] (Windows copy file)
      if (cbd.files && cbd.files.length > 0) {
        for (var fi = 0; fi < cbd.files.length; fi++) {
          if (cbd.files[fi] && cbd.files[fi].type && cbd.files[fi].type.indexOf('image') !== -1) {
            imageFile = cbd.files[fi];
            break;
          }
        }
      }
      // Check items[] (screenshot / browser copy)
      if (!imageFile) {
        var items = cbd.items || [];
        for (var i = 0; i < items.length; i++) {
          if (items[i].kind === 'file' && items[i].type && items[i].type.indexOf('image') !== -1) {
            var blob = items[i].getAsFile();
            if (blob) {
              var ext = (items[i].type.split('/')[1] || 'png').replace(/[^a-z0-9]/gi, '');
              imageFile = new File([blob], 'paste_' + Date.now() + '.' + ext, { type: items[i].type });
            }
            break;
          }
        }
      }
      if (imageFile) {
        e.preventDefault();
        zV2_showPastePreview(imageFile);
      }
    });
  }
  if (sendBtn && !sendBtn._zV2Bound) {
    sendBtn._zV2Bound = true;
    sendBtn.addEventListener('click', function () { zV2_sendMessage(); });
  }
  if (thumbsBtn && !thumbsBtn._zV2Bound) {
    thumbsBtn._zV2Bound = true;
    thumbsBtn.addEventListener('click', function () { zV2_sendMessage('👍'); });   // emoji nay tung bi xoa -> nut thanh nut chet
  }
  zV2_updateComposerButtons();
};

// ---------- Scroll ----------
window.zV2_scrollBottom = function (behavior) {
  var scrollEl = document.getElementById('zV2_messages_scroll');
  if (!scrollEl) return;
  try {
    scrollEl.scrollTo({ top: scrollEl.scrollHeight, behavior: behavior || 'smooth' });
  } catch (e) {
    scrollEl.scrollTop = scrollEl.scrollHeight;
  }
};

window.zV2_bindScroll = function () {
  var scrollEl = document.getElementById('zV2_messages_scroll');
  var btn = document.getElementById('zV2_scroll_bottom_btn');
  if (!scrollEl || scrollEl._zV2ScrollBound) return;
  scrollEl._zV2ScrollBound = true;
  var _scrollRafId = null;
  scrollEl.addEventListener('scroll', function () {
    if (_scrollRafId) return;
    _scrollRafId = requestAnimationFrame(function () {
      _scrollRafId = null;
      _zV2_scrollHandler(scrollEl, btn);
    });
  });
  if (btn && !btn._zV2Bound) {
    btn._zV2Bound = true;
    btn.addEventListener('click', function () { zV2_scrollBottom('smooth'); });
  }
};
// Tách handler ra để throttle qua rAF (gọi tối đa 1 lần/frame ~16ms)
function _zV2_scrollHandler(scrollEl, btn) {
    var atBottom = (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight) < 50;
    var distanceFromBottom = scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight;
    if (btn) btn.style.display = distanceFromBottom > 300 ? '' : 'none';

    // Top → pagination
    if (scrollEl.scrollTop < 80 && _zV2.currentRoomId) {
      var oldest = (_zV2.oldestMsgId || {})[_zV2.currentRoomId];
      if (oldest && !_zV2._loadingMore) {
        _zV2._loadingMore = true;
        // Hiện loading indicator
        var innerEl = document.getElementById('zV2_messages_inner');
        if (innerEl && !document.getElementById('zV2_load_more_indicator')) {
          var indicator = document.createElement('div');
          indicator.id = 'zV2_load_more_indicator';
          indicator.style.cssText = 'text-align:center;padding:8px;color:var(--z-muted);font-size:13px;';
          indicator.textContent = 'Đang tải thêm tin nhắn...';
          innerEl.prepend(indicator);
        }
        zV2_loadMessages(_zV2.currentRoomId, oldest).finally(function () {
          // Xoá indicator sau khi load xong
          var ind = document.getElementById('zV2_load_more_indicator');
          if (ind) ind.remove();
          setTimeout(function () { _zV2._loadingMore = false; }, 400);
        });
      }
    }

    // Bottom → mark read
    if (atBottom && _zV2.currentRoomId) {
      if (!_zV2._lastReadTs || (Date.now() - _zV2._lastReadTs) > 3000) {
        _zV2._lastReadTs = Date.now();
        zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(_zV2.currentRoomId) + '/read', { method: 'PUT' })
          .catch(function () { });
      }
    }
}

// ---------- Typing indicator ----------
// Ban dinh nghia CU o day da bi xoa: no bi ban o cuoi file de (cung ten ham),
// va ca hai deu sai giao uoc voi CSS/HTML. Ban dung duy nhat nam o muc
// "TYPING INDICATOR" gan cuoi file.

// ---------- Debounce renderConvList — tránh rebuild DOM liên tục khi nhiều SSE dồn ----------
var _zV2ConvListTimer = null;
function zV2_debouncedRenderConvList() {
  if (_zV2ConvListTimer) clearTimeout(_zV2ConvListTimer);
  _zV2ConvListTimer = setTimeout(function () {
    if (window.zV2_renderConvList) window.zV2_renderConvList();
  }, 150);
}

// ---------- SSE ----------
window.zV2_handleSSE = function (data) {
  if (!data || !data.type) return;
  var me = zV2_getCurrentUser();
  switch (data.type) {
    case 'message': {
      var m = data.message || data.data || data;
      if (!m || !m.id) return;
      var rid = m.room_id;
      // Da gui duoc tin = khong con dang soan nua
      if (m.sender_username && window.zV2_clearTyping) {
        window.zV2_clearTyping(rid, m.sender_username);
      }
      _zV2.messages = _zV2.messages || {};
      _zV2.messages[rid] = _zV2.messages[rid] || [];
      if (!_zV2.messages[rid].some(function (x) { return String(x.id) === String(m.id); })) {
        _zV2.messages[rid].push(m);
      }
      // SENDER vừa gửi tin = chắc chắn online → mark ngay (không đợi 120s poll)
      if (m.sender_username && m.sender_username !== me.username) {
        if (!_zV2.online) _zV2.online = new Set();
        _zV2.online.add(m.sender_username);
        if (!_zV2.presenceMap) _zV2.presenceMap = {};
        _zV2.presenceMap[m.sender_username] = {
          username: m.sender_username,
          online: true,
          last_seen_at: Math.floor(Date.now() / 1000),
        };
        // Nếu đang mở DM với sender → update header meta ngay
        if (rid === _zV2.currentRoomId) {
          var roomCur = (_zV2.rooms || []).find(function(r){ return r.id === rid; });
          if (roomCur && roomCur.type === 'direct') {
            var metaEl = document.getElementById('zV2_main_meta');
            if (metaEl) metaEl.textContent = 'Đang hoạt động';
          }
        }
      }
      // Update last_message + bump to top cho MỌI tin (kể cả room đang mở)
      var roomRef = (_zV2.rooms || []).find(function (r) { return r.id === rid; });
      if (roomRef) {
        roomRef.last_message = m;
        roomRef.last_message_at = m.created_at;
        // Chỉ tăng unread nếu KHÔNG phải room hiện tại VÀ sender khác mình
        if (rid !== _zV2.currentRoomId && m.sender_username !== me.username) {
          roomRef.unread_count = (roomRef.unread_count || 0) + 1;
        }
      }
      // Re-render conv list — debounce 150ms để tránh rebuild DOM liên tục
      zV2_debouncedRenderConvList();
      // Beep + notification cho tin từ người khác khi widget không open hoặc room khác
      if (m.sender_username !== me.username && (!_zV2.open || rid !== _zV2.currentRoomId)) {
        zV2_notifyNewMessage(m, roomRef);
      }
      if (rid === _zV2.currentRoomId) {
        var scrollEl = document.getElementById('zV2_messages_scroll');
        var atBottom = scrollEl ? (scrollEl.scrollHeight - scrollEl.scrollTop - scrollEl.clientHeight) < 120 : true;
        // APPEND tin mới vào DOM thay vì re-render toàn bộ (đỡ lag khi nhiều tin)
        var inner = document.getElementById('zV2_messages_inner');
        var arr = _zV2.messages[rid];
        if (inner && arr && arr.length > 0) {
          var prevMsg = arr.length >= 2 ? arr[arr.length - 2] : null;
          var rowHtml = zV2_buildMessageRow(m, prevMsg, null, me);
          // Date divider nếu sang ngày mới
          if (!prevMsg || !zV2_sameDay(prevMsg.created_at, m.created_at)) {
            rowHtml = '<div class="zV2_date_divider"><span>' +
              zV2_escapeHtml(zV2_formatDateDivider(m.created_at)) + '</span></div>' + rowHtml;
          }
          inner.insertAdjacentHTML('beforeend', rowHtml);
          if (_zV2HtmlCache && _zV2HtmlCache[rid]) delete _zV2HtmlCache[rid];
          if (typeof window.zV2_initLazyImages === 'function') window.zV2_initLazyImages();
        } else {
          if (_zV2HtmlCache && _zV2HtmlCache[rid]) delete _zV2HtmlCache[rid];
          zV2_renderMessages(rid); // fallback full render khi đặc biệt
        }
        if (atBottom || m.sender_username === me.username) zV2_scrollBottom('smooth');
        // auto-read if focused
        if (document.hasFocus && document.hasFocus()) {
          zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(rid) + '/read', { method: 'PUT' })
            .catch(function () { });
        }
      }
      break;
    }
    case 'message_deleted': {
      var info = zV2_findMessageAnyRoom(data.message_id || data.id);
      if (info) {
        info.msg.is_deleted = true;
        if (info.roomId === _zV2.currentRoomId) {
          // Surgical update: chỉ đổi bubble của tin bị thu hồi, không re-render toàn bộ
          var delEl = document.querySelector('[data-msg-id="' + info.msg.id + '"]');
          if (delEl) {
            var delBubble = delEl.querySelector('.zV2_bubble');
            if (delBubble) {
              delBubble.innerHTML = '<span style="color:var(--z-muted);font-size:13px;font-style:italic;">Tin nhắn đã được thu hồi</span>';
              delBubble.className = 'zV2_bubble zV2_bubble--deleted';
            }
            var delActions = delEl.querySelector('.zV2_msg_actions');
            if (delActions) delActions.remove();
          } else {
            if (_zV2HtmlCache && _zV2HtmlCache[info.roomId]) delete _zV2HtmlCache[info.roomId];
            zV2_renderMessages(info.roomId);
          }
        }
      }
      break;
    }
    case 'message_edited': {
      var inf = zV2_findMessageAnyRoom(data.message_id || (data.message && data.message.id));
      if (inf) {
        if (data.message) Object.assign(inf.msg, data.message);
        else {
          if (data.content !== undefined) inf.msg.content = data.content;
          inf.msg.edited_at = data.edited_at || new Date().toISOString();
        }
        if (inf.roomId === _zV2.currentRoomId) {
          // Surgical update: chỉ đổi nội dung tin được sửa, không re-render toàn bộ
          var editEl = document.querySelector('[data-msg-id="' + inf.msg.id + '"]');
          if (editEl) {
            var textEl = editEl.querySelector('.zV2_msg_text');
            if (textEl) {
              var newContent = typeof window.zV2_renderContent === 'function'
                ? window.zV2_renderContent(inf.msg.content, inf.msg.mentions)
                : zV2_escapeHtml(inf.msg.content || '');
              textEl.innerHTML = newContent;
              if (!editEl.querySelector('.zV2_msg_edited')) {
                var editedSpan = document.createElement('span');
                editedSpan.className = 'zV2_msg_edited';
                editedSpan.style.cssText = 'font-size:12px;color:var(--z-muted);margin-left:4px;';
                editedSpan.textContent = '(đã sửa)';
                textEl.appendChild(editedSpan);
              }
            }
          } else {
            if (_zV2HtmlCache && _zV2HtmlCache[inf.roomId]) delete _zV2HtmlCache[inf.roomId];
            zV2_renderMessages(inf.roomId);
          }
        }
      }
      break;
    }
    case 'reaction_added':
    case 'reaction_removed': {
      var ri = zV2_findMessageAnyRoom(data.message_id);
      if (!ri) break;
      var msg = ri.msg;
      msg.reactions = msg.reactions || [];
      var emoji = data.emoji;
      var username = data.username;
      var isMe = username === me.username;
      var rx = msg.reactions.find(function (x) { return x.emoji === emoji; });
      if (data.type === 'reaction_added') {
        if (!rx) {
          msg.reactions.push({ emoji: emoji, count: 1, by_me: isMe, users: [username] });
        } else {
          if (!rx.users) rx.users = [];
          if (rx.users.indexOf(username) < 0) {
            rx.users.push(username);
            rx.count = rx.users.length;
          }
          if (isMe) rx.by_me = true;
        }
      } else {
        if (rx) {
          rx.users = (rx.users || []).filter(function (u) { return u !== username; });
          rx.count = rx.users.length;
          if (isMe) rx.by_me = false;
          if (rx.count <= 0) {
            msg.reactions = msg.reactions.filter(function (x) { return x.emoji !== emoji; });
          }
        }
      }
      if (ri.roomId === _zV2.currentRoomId) zV2_renderMessages(ri.roomId);
      break;
    }
    case 'message_pinned':
    case 'message_unpinned': {
      var pi = zV2_findMessageAnyRoom(data.message_id);
      if (pi) {
        pi.msg.is_pinned = (data.type === 'message_pinned');
        if (pi.roomId === _zV2.currentRoomId) {
          zV2_renderMessages(pi.roomId);
          if (window.zV2_updatePinBanner) window.zV2_updatePinBanner(pi.roomId);
        }
      }
      break;
    }
    case 'typing': {
      // Ham nhan (roomId, senderName, username) — truoc day cho goi truyen moi
      // senderName vao vi tri roomId nen ham luon thoat ngay dong dau.
      if (data.username === me.username) break;
      zV2_showTypingIndicator(data.room_id,
                              data.sender_name || data.username || '',
                              data.username);
      break;
    }
    case 'read_receipt': {
      var rrRid = data.room_id;
      var reader = data.username;
      if (!rrRid || !reader) break;
      var arr = (_zV2.messages && _zV2.messages[rrRid]) || [];
      arr.forEach(function (m) {
        if (m.sender_username === me.username) {
          m.read_by = m.read_by || [];
          if (m.read_by.indexOf(reader) < 0) m.read_by.push(reader);
        }
      });
      if (rrRid === _zV2.currentRoomId) zV2_renderMessages(rrRid);
      break;
    }
    case 'room_updated':
    case 'room_member_added':
    case 'room_deleted': {
      if (data.type === 'room_deleted' && data.room_id === _zV2.currentRoomId) {
        _zV2.currentRoomId = null;
        var sc = document.getElementById('zV2_messages_scroll');
        if (sc) sc.style.display = 'none';
        var ep = document.getElementById('zV2_empty_main');
        if (ep) ep.style.display = '';
      }
      if (window.zV2_loadRooms) window.zV2_loadRooms();
      break;
    }
    case 'room_member_removed': {
      if (data.username === me.username) {
        if (data.room_id === _zV2.currentRoomId) {
          _zV2.currentRoomId = null;
          var sc2 = document.getElementById('zV2_messages_scroll');
          if (sc2) sc2.style.display = 'none';
          var ep2 = document.getElementById('zV2_empty_main');
          if (ep2) ep2.style.display = '';
        }
      }
      if (window.zV2_loadRooms) window.zV2_loadRooms();
      break;
    }
    default:
      // unknown — ignore
      break;
  }
};

// ---------- SSE init + exponential backoff reconnect ----------
var _sseReconnectDelay = 3000;  // bắt đầu 3s
var _sseReconnectTimer = null;
var _sseMaxDelay = 60000;       // tối đa 60s

function zV2_scheduleReconnect() {
  if (_sseReconnectTimer) clearTimeout(_sseReconnectTimer);
  _sseReconnectTimer = setTimeout(function () {
    zV2_initSSE();
    // Double delay mỗi lần thất bại, tối đa 60s
    _sseReconnectDelay = Math.min(_sseReconnectDelay * 2, _sseMaxDelay);
  }, _sseReconnectDelay);
}

window.zV2_initSSE = function () {
  // Guard: chỉ 1 EventSource active. Đóng cái cũ trước khi tạo mới.
  if (_zV2._sse) {
    try { _zV2._sse.close(); } catch (e) { }
    _zV2._sse = null;
  }
  if (_zV2._sseConnecting) return; // chống race condition
  _zV2._sseConnecting = true;
  try {
    var es = new EventSource('/api/chat/stream', { withCredentials: true });
    _zV2._sse = es;
    _zV2._sseConnecting = false;
    es.onopen = function () {
      // Reset delay khi connect thành công
      _sseReconnectDelay = 3000;
    };
    es.onmessage = function (ev) {
      if (!ev || !ev.data) return;
      try {
        var data = JSON.parse(ev.data);
        if (data && data.type === 'call') { if (window.zCall) window.zCall._onSignal(data.call); return; }
        zV2_handleSSE(data);
      } catch (e) {
        console.warn('[zV2 SSE] parse error', e, ev.data);
      }
    };
    es.onerror = function () {
      try { es.close(); } catch (e) { }
      _zV2._sse = null;
      _zV2._sseConnecting = false;
      zV2_scheduleReconnect();
    };
  } catch (e) {
    console.error('[zV2 SSE] init failed', e);
    _zV2._sseConnecting = false;
    zV2_scheduleReconnect();
  }
};

// ---------- Lazy image loading ----------
var _zV2LazyObserver = null;
window.zV2_initLazyImages = function () {
  if (!('IntersectionObserver' in window)) {
    // Fallback: load all immediately
    document.querySelectorAll('img.zV2_lazy_img[data-src]').forEach(function (img) {
      img.src = img.getAttribute('data-src');
      img.removeAttribute('data-src');
    });
    return;
  }
  if (!_zV2LazyObserver) {
    _zV2LazyObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          var img = entry.target;
          img.src = img.getAttribute('data-src');
          img.removeAttribute('data-src');
          _zV2LazyObserver.unobserve(img);
        }
      });
    }, { rootMargin: '200px' });
  }
  document.querySelectorAll('img.zV2_lazy_img[data-src]').forEach(function (img) {
    _zV2LazyObserver.observe(img);
  });
};

// ---------- Thread panel ----------
var _zV2Thread = { rootMsgId: null, roomId: null };

window.zV2_openThread = async function (msgId, roomId) {
  _zV2Thread.rootMsgId = msgId;
  _zV2Thread.roomId = roomId || _zV2.currentRoomId;
  var panel = document.getElementById('zV2_thread_panel');
  var rootWrap = document.getElementById('zV2_thread_root_wrap');
  var scroll = document.getElementById('zV2_thread_scroll');
  if (!panel) return;
  // Root message
  var msgs = (_zV2.messages && _zV2.messages[_zV2Thread.roomId]) || [];
  var rootMsg = msgs.find(function (m) { return String(m.id) === String(msgId); });
  if (rootWrap && rootMsg) {
    rootWrap.innerHTML =
      '<div class="thr_sender">' + zV2_escapeHtml(rootMsg.sender_name || rootMsg.sender_username) + '</div>' +
      '<div class="thr_content">' + zV2_escapeHtml((rootMsg.content || '[Đính kèm]').substring(0, 200)) + '</div>';
  }
  panel.classList.add('open');
  if (scroll) scroll.innerHTML = '<div style="text-align:center;padding:16px;color:var(--z-muted);font-size:13px;">Đang tải...</div>';
  try {
    var me = zV2_getCurrentUser();
    var url = '/api/chat/rooms/' + encodeURIComponent(_zV2Thread.roomId) +
      '/messages?thread_root_id=' + encodeURIComponent(msgId) + '&limit=200';
    var replies = await zV2_apiFetch(url);
    if (!Array.isArray(replies)) replies = [];
    window.zV2_renderThreadReplies(replies, me);
  } catch (e) {
    if (scroll) scroll.innerHTML = '<div style="text-align:center;padding:16px;color:var(--z-muted);">Không tải được.</div>';
  }
};

window.zV2_renderThreadReplies = function (replies, me) {
  var scroll = document.getElementById('zV2_thread_scroll');
  if (!scroll) return;
  if (!replies.length) {
    scroll.innerHTML = '<div style="text-align:center;padding:24px 16px;color:var(--z-muted);font-size:13px;">Chưa có trả lời.<br>Hãy bắt đầu hội thoại!</div>';
    return;
  }
  var html = replies.map(function (r) {
    var isOwn = r.sender_username === (me && me.username);
    var time = r.created_at ? new Date(r.created_at).toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' }) : '';
    return '<div class="zV2_thr_reply' + (isOwn ? ' zV2_thr_reply--own' : '') + '">' +
      (isOwn ? '' : '<div class="zV2_thr_reply_sender">' + zV2_escapeHtml(r.sender_name || r.sender_username) + '</div>') +
      '<div>' + zV2_escapeHtml(r.content || '[Đính kèm]') + '</div>' +
      '<div class="zV2_thr_reply_time">' + time + '</div>' +
      '</div>';
  }).join('');
  scroll.innerHTML = html;
  scroll.scrollTop = scroll.scrollHeight;
};

window.zV2_sendThreadReply = async function () {
  var input = document.getElementById('zV2_thread_input');
  if (!input) return;
  var content = input.value.trim();
  if (!content || !_zV2Thread.rootMsgId || !_zV2Thread.roomId) return;
  input.value = '';
  input.style.height = '';
  try {
    var msg = await zV2_apiFetch('/api/chat/rooms/' + encodeURIComponent(_zV2Thread.roomId) + '/messages', {
      method: 'POST',
      body: { content: content, reply_to_id: _zV2Thread.rootMsgId }
    });
    var scroll = document.getElementById('zV2_thread_scroll');
    if (scroll) {
      var time = new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
      scroll.insertAdjacentHTML('beforeend',
        '<div class="zV2_thr_reply zV2_thr_reply--own">' +
        '<div>' + zV2_escapeHtml(content) + '</div>' +
        '<div class="zV2_thr_reply_time">' + time + '</div>' +
        '</div>');
      scroll.scrollTop = scroll.scrollHeight;
    }
  } catch (e) { zV2_toast('Gửi thất bại', 'error'); }
};

window.zV2_wireThreadPanel = function () {
  var closeBtn = document.getElementById('zV2_thread_close');
  var sendBtn  = document.getElementById('zV2_thread_send_btn');
  var input    = document.getElementById('zV2_thread_input');
  if (closeBtn && !closeBtn._zV2Bound) {
    closeBtn._zV2Bound = true;
    closeBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var p = document.getElementById('zV2_thread_panel');
      if (p) p.classList.remove('open');
      _zV2Thread.rootMsgId = null;
    });
  }
  if (sendBtn && !sendBtn._zV2Bound) {
    sendBtn._zV2Bound = true;
    sendBtn.addEventListener('click', function () { window.zV2_sendThreadReply(); });
  }
  if (input && !input._zV2Bound) {
    input._zV2Bound = true;
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); window.zV2_sendThreadReply(); }
    });
    input.addEventListener('input', function () {
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 90) + 'px';
    });
  }
};

// ---------- Preload top N rooms ngầm khi mở widget ----------
window.zV2_preloadTopRooms = function (rooms) {
  if (!rooms || !rooms.length) return;
  // Lấy 4 room có hoạt động mới nhất chưa có cache
  var toLoad = rooms
    .filter(function (r) { return !(_zV2.messages && _zV2.messages[r.id]); })
    .slice(0, 4);
  toLoad.forEach(function (room, i) {
    setTimeout(function () {
      if (_zV2.messages && _zV2.messages[room.id]) return; // đã có từ openRoom
      var url = '/api/chat/rooms/' + encodeURIComponent(room.id) + '/messages?slim=1&limit=20';
      zV2_apiFetch(url).then(function (msgs) {
        if (!Array.isArray(msgs) || !msgs.length) return;
        msgs = msgs.slice().reverse();
        _zV2.messages = _zV2.messages || {};
        if (!_zV2.messages[room.id]) {
          _zV2.messages[room.id] = msgs;
          _zV2.oldestMsgId = _zV2.oldestMsgId || {};
          _zV2.oldestMsgId[room.id] = msgs[0].id;
          if (window.zV2_dbSave) window.zV2_dbSave(room.id, msgs).catch(function(){});
        }
      }).catch(function () {});
    }, (i + 1) * 400); // stagger 400ms/room để không flood server
  });
};

// ---------- Prefetch on hover (giảm perceived latency khi click) ----------
window.zV2_wirePrefetchHover = function () {
  var convList = document.getElementById('zV2_conv_list');
  if (!convList || convList._prefetchBound) return;
  convList._prefetchBound = true;
  convList.addEventListener('mouseover', function (e) {
    var item = e.target.closest('.zV2_conv_item');
    if (!item) return;
    var rid = parseInt(item.getAttribute('data-room-id'), 10);
    if (!rid || isNaN(rid)) return;
    if (_zV2.messages && _zV2.messages[rid]) return; // đã có
    if (item._prefetchTimer) return;
    item._prefetchTimer = setTimeout(function () {
      delete item._prefetchTimer;
      if (_zV2.messages && _zV2.messages[rid]) return;
      var url = '/api/chat/rooms/' + encodeURIComponent(rid) + '/messages?slim=1&limit=25';
      zV2_apiFetch(url).then(function (msgs) {
        if (!Array.isArray(msgs) || !msgs.length) return;
        msgs = msgs.slice().reverse();
        _zV2.messages = _zV2.messages || {};
        if (!_zV2.messages[rid]) {
          _zV2.messages[rid] = msgs;
          _zV2.oldestMsgId = _zV2.oldestMsgId || {};
          _zV2.oldestMsgId[rid] = msgs[0].id;
          if (window.zV2_dbSave) window.zV2_dbSave(rid, msgs).catch(function(){});
        }
      }).catch(function () {});
    }, 180); // hover 180ms → bắt đầu prefetch
  });
  convList.addEventListener('mouseout', function (e) {
    var item = e.target.closest('.zV2_conv_item');
    if (item && item._prefetchTimer) {
      clearTimeout(item._prefetchTimer);
      delete item._prefetchTimer;
    }
  });
};

// ---------- Boot composer / scroll on DOM ready ----------
window.zV2_messagesModuleInit = function () {
  zV2_composeBind();
  zV2_bindScroll();
  if (typeof window.zV2_wireThreadPanel === 'function') window.zV2_wireThreadPanel();
  if (typeof window.zV2_wirePastePreview === 'function') window.zV2_wirePastePreview();
  // Wire prefetch sau khi conv list đã render (retry mỗi 500ms tối đa 5 lần)
  var _pfTries = 0;
  var _pfInterval = setInterval(function () {
    _pfTries++;
    if (typeof window.zV2_wirePrefetchHover === 'function') window.zV2_wirePrefetchHover();
    var done = document.getElementById('zV2_conv_list');
    if ((done && done._prefetchBound) || _pfTries >= 5) clearInterval(_pfInterval);
  }, 500);
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', function () { zV2_messagesModuleInit(); });
} else {
  setTimeout(function () { zV2_messagesModuleInit(); }, 0);
}
/* ==== ZALO V2: INFO PANEL + GROUP ADMIN + MICRO ==== */

// ---------- helpers (assumed already defined elsewhere but fallback) ----------
if (typeof window.zV2_$ !== 'function') {
  window.zV2_$ = function (id) { return document.getElementById(id); };
}
if (typeof window.zV2_escapeHtml !== 'function') {
  window.zV2_escapeHtml = function (s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  };
}
if (typeof window.zV2_toast !== 'function') {
  window.zV2_toast = function (msg, type) {
    try {
      var t = document.createElement('div');
      t.className = 'zV2_toast zV2_toast_' + (type || 'info');
      t.textContent = msg;
      Object.assign(t.style, {
        position: 'fixed', bottom: '24px', left: '50%', transform: 'translateX(-50%)',
        background: type === 'error' ? 'var(--z-badge)' : (type === 'success' ? 'var(--z-ok)' : 'var(--z-text)'),
        color: '#fff', padding: '10px 16px', borderRadius: '8px', zIndex: 99999,
        fontSize: '14px', boxShadow: '0 4px 16px rgba(0,0,0,0.25)'
      });
      document.body.appendChild(t);
      setTimeout(function () { t.style.opacity = '0'; t.style.transition = 'opacity .3s'; }, 2200);
      setTimeout(function () { t.remove(); }, 2600);
    } catch (e) { console.warn(msg); }
  };
}
function zV2_fmtBytes(b) {
  if (!b && b !== 0) return '';
  var u = ['B', 'KB', 'MB', 'GB']; var i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return b.toFixed(b >= 10 || i === 0 ? 0 : 1) + ' ' + u[i];
}
function zV2_fmtDate(d) {
  try {
    var x = new Date(d);
    if (isNaN(x.getTime())) return '';
    var pad = function (n) { return n < 10 ? '0' + n : '' + n; };
    return pad(x.getDate()) + '/' + pad(x.getMonth() + 1) + '/' + x.getFullYear();
  } catch (e) { return ''; }
}
function zV2_avatarBg(name) {
  var colors = ['#0B63CE', '#1F6F72', '#2E7D4F', '#6B4E7D', '#B02A18', '#3D5A80', '#A02C5A', '#4A4A82'];
  var sum = 0; var s = String(name || '?');
  for (var i = 0; i < s.length; i++) sum += s.charCodeAt(i);
  return colors[sum % colors.length];
}
function zV2_avatarText(name) {
  var s = String(name || '?').trim();
  if (!s) return '?';
  var parts = s.split(/\s+/);
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
}
function zV2_currentUser() {
  try {
    var u = window._zV2 && _zV2.currentUser;
    if (u && typeof u === 'object') return u.username || '';
    if (typeof u === 'string') return u;
    return window.CURRENT_USERNAME || window.currentUsername || '';
  } catch (e) { return ''; }
}
function zV2_isAdminOf(room) {
  if (!room) return false;
  var me = zV2_currentUser();
  if (room.admin_usernames && Array.isArray(room.admin_usernames)) {
    return room.admin_usernames.indexOf(me) !== -1;
  }
  if (room.is_admin === true) return true;
  if (room.created_by && room.created_by === me) return true;
  return false;
}

// ---------- INFO PANEL ----------
window.zV2_openInfoPanel = function () {
  if (!window._zV2) return;
  _zV2.infoPanelOpen = true;
  var p = zV2_$('zV2_info_panel');
  if (p) p.classList.add('open');
  zV2_renderInfoPanel(_zV2.currentRoomId);
};

window.zV2_closeInfoPanel = function () {
  if (window._zV2) _zV2.infoPanelOpen = false;
  var p = zV2_$('zV2_info_panel');
  if (p) p.classList.remove('open');
};

window.zV2_switchInfoTab = function (tab) {
  var roomId = _zV2 && _zV2.currentRoomId;
  if (!roomId) return;
  var btns = document.querySelectorAll('#zV2_info_panel .zV2_info_tab_btn');
  for (var i = 0; i < btns.length; i++) {
    btns[i].classList.toggle('active', btns[i].getAttribute('data-tab') === tab);
  }
  var pane = zV2_$('zV2_info_panes');
  if (!pane) return;
  pane.innerHTML = '<div class="zV2_skeleton_row"></div><div class="zV2_skeleton_row"></div><div class="zV2_skeleton_row"></div>';
  var room = (_zV2.rooms || []).find(function (r) { return r.id === roomId || r.room_id === roomId; });
  if (tab === 'thong-tin') {
    fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/pinned')
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (pinned) { zV2_renderTabThongTin(room, pinned || []); })
      .catch(function () { zV2_renderTabThongTin(room, []); });
  } else if (tab === 'thanh-vien') {
    zV2_renderTabThanhVien(roomId);
  } else if (tab === 'anh-video') {
    zV2_renderTabAnhVideo(roomId);
  } else if (tab === 'file') {
    zV2_renderTabFile(roomId);
  }
};

window.zV2_renderInfoPanel = function (roomId) {
  var panel = zV2_$('zV2_info_panel');
  if (!panel) return;
  var room = ((_zV2 && _zV2.rooms) || []).find(function (r) { return r.id === roomId || r.room_id === roomId; });
  if (!room) {
    panel.innerHTML = '<div style="padding:24px;color:var(--z-text2)">Không tìm thấy phòng.</div>';
    return;
  }
  var displayName = room.display_name || room.name || room.title || 'Phòng chat';
  var isAdmin = zV2_isAdminOf(room);
  var membersCount = (room.members_count != null ? room.members_count :
    (room.member_count != null ? room.member_count :
      (Array.isArray(room.members) ? room.members.length : 0)));
  var avatarText = zV2_avatarText(displayName);
  var avatarBg = zV2_avatarBg(displayName);
  // isGroup chung cho mọi phòng nhiều người (group/general/department) — show member count, tabs đầy đủ
  var isGroup = room.type !== 'direct';
  // CustomGroup = group do user tạo, có quyền sửa name/avatar (general/department auto-managed thì không)
  var isCustomGroup = room.type === 'group';

  // Avatar có thể là ảnh URL hoặc letter
  var avatarInner = room.avatar_url
    ? '<img src="' + zV2_escapeHtml(room.avatar_url) + '" alt="" style="width:100%;height:100%;object-fit:cover;border-radius:50%;" />'
    : zV2_escapeHtml(avatarText);
  // Camera overlay (nút đổi avatar) chỉ admin của CUSTOM group được dùng
  var camOverlay = (isAdmin && isCustomGroup) ?
    '<div class="zV2_info_avatar_cam" title="Đổi avatar nhóm">' +
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>' +
    '</div>' +
    '<input type="file" id="zV2_info_avatar_input" accept="image/*" style="display:none" />' : '';

  panel.innerHTML =
    '<div class="zV2_info_header">' +
      '<button class="zV2_info_close" type="button">‹ Quay lại</button>' +
      '<span class="zV2_info_title">Thông tin</span>' +
    '</div>' +
    '<div class="zV2_info_hero">' +
      '<div class="zV2_info_avatar_wrap">' +
        '<div class="zV2_info_avatar" style="background:' + avatarBg + ';' + (room.avatar_url ? 'overflow:hidden;' : '') + '">' + avatarInner + '</div>' +
        camOverlay +
      '</div>' +
      '<div class="zV2_info_name">' + zV2_escapeHtml(displayName) + '</div>' +
      '<div class="zV2_info_meta">' + (room.type === 'direct' ? 'Cuộc trò chuyện riêng' : (membersCount + ' thành viên')) + '</div>' +
      (isAdmin && isCustomGroup ? '<button class="zV2_btn_secondary zV2_btn_rename_room" type="button">Đổi tên</button>' : '') +
    '</div>' +
    '<div class="zV2_info_tabs">' +
      '<button class="zV2_info_tab_btn active" data-tab="thong-tin" type="button">Thông tin</button>' +
      '<button class="zV2_info_tab_btn" data-tab="thanh-vien" type="button">Thành viên</button>' +
      '<button class="zV2_info_tab_btn" data-tab="anh-video" type="button">Ảnh/Video</button>' +
      '<button class="zV2_info_tab_btn" data-tab="file" type="button">File</button>' +
    '</div>' +
    '<div id="zV2_info_panes" class="zV2_info_panes"></div>';

  var closeBtn = panel.querySelector('.zV2_info_close');
  if (closeBtn) closeBtn.addEventListener('click', zV2_closeInfoPanel);
  var renameBtn = panel.querySelector('.zV2_btn_rename_room');
  if (renameBtn) renameBtn.addEventListener('click', function () { zV2_renameRoom(roomId); });
  // Đổi avatar nhóm: click camera overlay → file picker → upload
  var camBtn = panel.querySelector('.zV2_info_avatar_cam');
  var avatarInput = panel.querySelector('#zV2_info_avatar_input');
  console.log('[zV2 avatar] camBtn=', camBtn, 'avatarInput=', avatarInput, 'isAdmin=', isAdmin, 'isGroup=', isGroup);
  if (camBtn && avatarInput) {
    // Pointer-events: SVG bên trong không ăn click
    camBtn.style.cssText += '; cursor: pointer;';
    var svgs = camBtn.querySelectorAll('svg, svg *');
    for (var s = 0; s < svgs.length; s++) svgs[s].style.pointerEvents = 'none';
    camBtn.addEventListener('click', function(ev){
      ev.preventDefault();
      ev.stopPropagation();
      console.log('[zV2 avatar] camBtn clicked → opening picker');
      avatarInput.value = ''; // reset trước click để cùng file chọn lại vẫn fire change
      avatarInput.click();
    });
    avatarInput.addEventListener('change', function(){
      var f = avatarInput.files && avatarInput.files[0];
      console.log('[zV2 avatar] change event, file=', f);
      if (!f) { console.warn('[zV2 avatar] no file selected'); return; }
      if (f.size > 5 * 1024 * 1024) { zV2_toast('Ảnh quá lớn (>5MB)', 'error'); return; }
      var fd = new FormData();
      fd.append('file', f);
      var t = zV2_toast('Đang tải avatar...', 'info', 30000);
      console.log('[zV2 avatar] POST /api/chat/rooms/' + roomId + '/avatar with file', f.name, f.size);
      fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/avatar', {
        method: 'POST',
        body: fd,
        credentials: 'same-origin'
      })
        .then(async function(r){
          if (!r.ok) { var e = await r.text(); throw new Error('HTTP ' + r.status + ' ' + e); }
          return r.json();
        })
        .then(function(updatedRoom){
          console.log('[zV2 avatar] success', updatedRoom);
          zV2_toast('Đã đổi avatar nhóm', 'success');
          var roomRef = (_zV2.rooms || []).find(function(r){ return r.id === roomId; });
          if (roomRef && updatedRoom) roomRef.avatar_url = updatedRoom.avatar_url;
          zV2_renderInfoPanel(roomId);
          if (window.zV2_renderConvList) zV2_renderConvList();
          var avEl = document.getElementById('zV2_main_avatar');
          if (avEl && roomRef && roomRef.avatar_url) {
            avEl.innerHTML = '<img src="' + zV2_escapeHtml(roomRef.avatar_url) + '" style="width:100%;height:100%;object-fit:cover;" />';
            avEl.style.background = 'transparent';
          }
        })
        .catch(function(e){
          console.error('[zV2 avatar] upload failed', e);
          zV2_toast('Đổi avatar thất bại: ' + (e.message || ''), 'error');
        });
    });
  } else {
    console.warn('[zV2 avatar] camBtn or avatarInput missing — render did not include camera. isAdmin=' + isAdmin + ' isGroup=' + isGroup);
  }
  var tabBtns = panel.querySelectorAll('.zV2_info_tab_btn');
  for (var i = 0; i < tabBtns.length; i++) {
    (function (btn) {
      btn.addEventListener('click', function () {
        zV2_switchInfoTab(btn.getAttribute('data-tab'));
      });
    })(tabBtns[i]);
  }
  zV2_switchInfoTab('thong-tin');
};

window.zV2_renderTabThongTin = function (room, pinned) {
  var pane = zV2_$('zV2_info_panes');
  if (!pane) return;
  var roomId = room.id || room.room_id;
  var isGroup = room.type === 'group' || room.is_group === true;
  var isCustom = room.is_custom === true || room.created_by === zV2_currentUser();

  var muteKey = 'zV2_mute_' + roomId;
  var muted = localStorage.getItem(muteKey) === '1';

  var pinnedHtml = '';
  if (pinned && pinned.length) {
    pinnedHtml = pinned.map(function (p) {
      var preview = (p.content || '').slice(0, 80);
      return '<div class="zV2_pinned_row">' +
        '<span class="zV2_pinned_icon"></span>' +
        '<div class="zV2_pinned_body">' +
          '<div class="zV2_pinned_text">' + zV2_escapeHtml(preview) + '</div>' +
          '<div class="zV2_pinned_meta">Ghim bởi ' + zV2_escapeHtml(p.pinned_by || p.sender_name || '') + '</div>' +
        '</div>' +
      '</div>';
    }).join('');
  } else {
    pinnedHtml = '<div class="zV2_empty_hint">Chưa có tin nhắn ghim.</div>';
  }

  pane.innerHTML =
    '<div class="zV2_info_section">' +
      '<div class="zV2_info_section_label">Tin nhắn ghim</div>' +
      pinnedHtml +
    '</div>' +
    '<div class="zV2_info_section">' +
      '<div class="zV2_info_section_label">Thông báo</div>' +
      '<label class="zV2_toggle_row">' +
        '<input type="checkbox" class="zV2_toggle_mute" ' + (muted ? 'checked' : '') + '>' +
        '<span>Tắt thông báo phòng này</span>' +
      '</label>' +
    '</div>' +
    '<div class="zV2_info_section">' +
      '<div class="zV2_info_section_label">Tuỳ chọn</div>' +
      '<button class="zV2_btn_secondary zV2_btn_search_msg" type="button">Tìm tin nhắn</button>' +
      '<button class="zV2_btn_secondary zV2_btn_create_task" type="button">Tạo task</button>' +
      (isGroup && isCustom ? '<button class="zV2_btn_danger zV2_btn_leave_room" type="button">Rời nhóm</button>' : '') +
      (room.type === 'direct' ? '<button class="zV2_btn_danger zV2_btn_delete_dm" type="button">Xoá cuộc trò chuyện</button>' : '') +
    '</div>';

  var muteCb = pane.querySelector('.zV2_toggle_mute');
  if (muteCb) {
    muteCb.addEventListener('change', function () {
      if (muteCb.checked) localStorage.setItem(muteKey, '1');
      else localStorage.removeItem(muteKey);
      zV2_toast(muteCb.checked ? 'Đã tắt thông báo' : 'Đã bật thông báo', 'success');
    });
  }
  var searchBtn = pane.querySelector('.zV2_btn_search_msg');
  if (searchBtn) searchBtn.addEventListener('click', function () {
    if (typeof window.zV2_openSearchModal === 'function') zV2_openSearchModal(roomId);
    else zV2_toast('Tính năng đang phát triển');
  });
  var taskBtn = pane.querySelector('.zV2_btn_create_task');
  if (taskBtn) taskBtn.addEventListener('click', function () {
    if (typeof window.zV2_openCreateTaskModal === 'function') zV2_openCreateTaskModal(roomId);
    else zV2_toast('Tính năng đang phát triển');
  });
  var leaveBtn = pane.querySelector('.zV2_btn_leave_room');
  if (leaveBtn) leaveBtn.addEventListener('click', function () { zV2_leaveRoom(roomId); });
  var deleteDmBtn = pane.querySelector('.zV2_btn_delete_dm');
  if (deleteDmBtn) deleteDmBtn.addEventListener('click', function () { zV2_deleteConversation(roomId); });
};

window.zV2_renderTabThanhVien = function (roomId) {
  var pane = zV2_$('zV2_info_panes');
  if (!pane) return;
  pane.innerHTML = '<div class="zV2_skeleton_row"></div><div class="zV2_skeleton_row"></div><div class="zV2_skeleton_row"></div>';
  fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/members')
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (members) {
      members = members || [];
      var room = ((_zV2 && _zV2.rooms) || []).find(function (r) { return r.id === roomId || r.room_id === roomId; }) || {};
      var isAdmin = zV2_isAdminOf(room);
      var me = zV2_currentUser();
      var rows = members.map(function (m) {
        var name = m.ho_ten || m.username || '';
        var sub = [m.chuc_vu, m.phong_ban].filter(Boolean).join(' · ');
        var avatarText = zV2_avatarText(name);
        var avatarBg = zV2_avatarBg(name);
        var avatarHtml = m.avatar_data
          ? '<img class="zV2_member_avatar" src="' + zV2_escapeHtml(m.avatar_data) + '" alt="">'
          : '<div class="zV2_member_avatar" style="background:' + avatarBg + '">' + zV2_escapeHtml(avatarText) + '</div>';
        var removeBtn = '';
        if (isAdmin && m.username !== me) {
          removeBtn = '<button class="zV2_member_remove" data-username="' + zV2_escapeHtml(m.username) + '" type="button">✕</button>';
        }
        return '<div class="zV2_member_row">' +
          avatarHtml +
          '<div class="zV2_member_info">' +
            '<div class="zV2_member_name">' + zV2_escapeHtml(name) + (m.is_admin ? ' <span class="zV2_admin_chip">Admin</span>' : '') + '</div>' +
            '<div class="zV2_member_sub">' + zV2_escapeHtml(sub) + '</div>' +
          '</div>' +
          removeBtn +
        '</div>';
      }).join('');

      pane.innerHTML =
        '<div class="zV2_info_section">' +
          '<div class="zV2_info_section_label">' +
            'Thành viên (' + members.length + ')' +
            (isAdmin ? ' <button class="zV2_btn_primary zV2_btn_add_member" type="button">+ Thêm</button>' : '') +
          '</div>' +
          '<div class="zV2_member_list">' + (rows || '<div class="zV2_empty_hint">Chưa có thành viên.</div>') + '</div>' +
        '</div>';

      var addBtn = pane.querySelector('.zV2_btn_add_member');
      if (addBtn) addBtn.addEventListener('click', function () { zV2_openAddMembersModal(roomId); });
      var removeBtns = pane.querySelectorAll('.zV2_member_remove');
      for (var i = 0; i < removeBtns.length; i++) {
        (function (btn) {
          btn.addEventListener('click', function () {
            var u = btn.getAttribute('data-username');
            if (!confirm('Xoá thành viên ' + u + ' khỏi nhóm?')) return;
            fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/members/' + encodeURIComponent(u), { method: 'DELETE' })
              .then(function (r) {
                if (!r.ok) throw new Error('fail');
                zV2_toast('Đã xoá thành viên', 'success');
                zV2_renderTabThanhVien(roomId);
              })
              .catch(function () { zV2_toast('Không xoá được thành viên', 'error'); });
          });
        })(removeBtns[i]);
      }
    })
    .catch(function () {
      pane.innerHTML = '<div class="zV2_empty_hint">Lỗi tải thành viên.</div>';
    });
};

window.zV2_openAddMembersModal = async function (roomId) {
  // Load users nếu chưa
  if (!_zV2 || !_zV2.users || _zV2.users.length === 0) {
    try { if (typeof window.zV2_loadUsers === 'function') await window.zV2_loadUsers(); } catch(_){}
  }
  fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/members')
    .then(function (r) { return r.ok ? r.json() : []; })
    .then(function (existing) {
      var existingSet = {};
      (existing || []).forEach(function (m) { existingSet[m.username] = true; });
      var users = ((_zV2 && _zV2.users) || []).filter(function (u) { return !existingSet[u.username]; });
      zV2_renderUserPickerModal({
        title: 'Thêm thành viên',
        submitLabel: 'Thêm',
        users: users,
        withDepartments: true,
        onSubmit: function (payload, close) {
          // Picker mới trả {usernames, phong_ban_list}
          var sel = (payload && payload.usernames) || [];
          var depts = (payload && payload.phong_ban_list) || [];
          if (!sel.length && !depts.length) {
            zV2_toast('Chọn ít nhất 1 người hoặc 1 phòng ban', 'error');
            return;
          }
          // Nếu chọn phòng ban → expand thành usernames qua _zV2.users (filter exclude existing)
          var allUsernames = sel.slice();
          if (depts.length) {
            var allUsers = (_zV2 && _zV2.users) || [];
            depts.forEach(function(pb){
              allUsers.forEach(function(u){
                if (u.phong_ban === pb && !existingSet[u.username] && allUsernames.indexOf(u.username) === -1) {
                  allUsernames.push(u.username);
                }
              });
            });
          }
          if (!allUsernames.length) {
            zV2_toast('Không có ai mới để thêm', 'info');
            close();
            return;
          }
          fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/members', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ usernames: allUsernames })
          })
            .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
            .then(function (res) {
              zV2_toast('Đã thêm ' + ((res && res.added && res.added.length) || allUsernames.length) + ' thành viên', 'success');
              close();
              zV2_renderTabThanhVien(roomId);
            })
            .catch(function () { zV2_toast('Không thêm được thành viên', 'error'); });
        }
      });
    });
};

function zV2_renderUserPickerModal(opts) {
  var overlay = document.createElement('div');
  overlay.className = 'zV2_modal_overlay';
  var groups = {};
  (opts.users || []).forEach(function (u) {
    var pb = u.phong_ban || 'Khác';
    if (!groups[pb]) groups[pb] = [];
    groups[pb].push(u);
  });
  var groupNames = Object.keys(groups).sort();
  // Phòng ban dropdown (chỉ hiện khi withDepartments)
  var deptChipsHtml = '';
  if (opts.withDepartments) {
    deptChipsHtml =
      '<div class="zV2_dept_dropdown_wrap">' +
        '<button type="button" class="zV2_dept_dropdown_btn">' +
          '<span class="zV2_dept_dropdown_label">Chọn nhanh theo phòng ban</span>' +
          '<span class="zV2_dept_count">0</span>' +
          '<span class="zV2_dept_caret">▾</span>' +
        '</button>' +
        '<div class="zV2_dept_dropdown_menu" hidden>' +
          groupNames.map(function(g){
            return '<label class="zV2_dept_item">' +
              '<input type="checkbox" class="zV2_dept_cb" value="' + zV2_escapeHtml(g) + '">' +
              '<span class="zV2_dept_item_name">' + zV2_escapeHtml(g) + '</span>' +
              '<span class="zV2_dept_item_count">' + groups[g].length + '</span>' +
            '</label>';
          }).join('') +
        '</div>' +
      '</div>';
  }
  var listHtml = groupNames.map(function (g) {
    var rows = groups[g].map(function (u) {
      var name = u.ho_ten || u.username || '';
      return '<label class="zV2_picker_row" data-pb="' + zV2_escapeHtml(g) + '">' +
        '<input type="checkbox" class="zV2_picker_cb" value="' + zV2_escapeHtml(u.username) + '" data-name="' + zV2_escapeHtml(name) + '" data-pb="' + zV2_escapeHtml(g) + '">' +
        '<div class="zV2_picker_avatar" style="background:' + zV2_avatarBg(name) + '">' + zV2_escapeHtml(zV2_avatarText(name)) + '</div>' +
        '<div class="zV2_picker_info">' +
          '<div class="zV2_picker_name">' + zV2_escapeHtml(name) + '</div>' +
          '<div class="zV2_picker_sub">' + zV2_escapeHtml(u.chuc_vu || '') + '</div>' +
        '</div>' +
      '</label>';
    }).join('');
    return '<div class="zV2_picker_group" data-pb="' + zV2_escapeHtml(g) + '">' +
      '<div class="zV2_picker_group_label">' + zV2_escapeHtml(g) + '</div>' +
      rows +
    '</div>';
  }).join('');

  var nameField = opts.withName ? (
    '<div class="zV2_modal_field">' +
      '<label>Tên nhóm</label>' +
      '<input type="text" class="zV2_picker_groupname" placeholder="Nhập tên nhóm..." value="' + zV2_escapeHtml(opts.defaultName || '') + '">' +
    '</div>'
  ) : '';

  overlay.innerHTML =
    '<div class="zV2_modal_card">' +
      '<div class="zV2_modal_header">' +
        '<span>' + zV2_escapeHtml(opts.title || 'Chọn thành viên') + '</span>' +
        '<button class="zV2_modal_close" type="button">✕</button>' +
      '</div>' +
      '<div class="zV2_modal_body">' +
        nameField +
        deptChipsHtml +
        '<input type="text" class="zV2_picker_search" placeholder="Tìm theo tên...">' +
        '<div class="zV2_picker_list">' + (listHtml || '<div class="zV2_empty_hint">Không có người để thêm.</div>') + '</div>' +
      '</div>' +
      '<div class="zV2_modal_footer">' +
        '<button class="zV2_btn_secondary zV2_modal_cancel" type="button">Huỷ</button>' +
        '<button class="zV2_btn_primary zV2_modal_submit" type="button" disabled>' + zV2_escapeHtml(opts.submitLabel || 'OK') + ' (0)</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);

  function close() { overlay.remove(); }
  function selected() {
    var arr = [];
    var cbs = overlay.querySelectorAll('.zV2_picker_cb:checked');
    for (var i = 0; i < cbs.length; i++) arr.push(cbs[i].value);
    return arr;
  }
  function selectedDepts() {
    var arr = [];
    var seen = {};
    var cbs = overlay.querySelectorAll('.zV2_dept_cb:checked');
    for (var i = 0; i < cbs.length; i++) {
      var v = cbs[i].value;
      if (!seen[v]) { seen[v] = 1; arr.push(v); }
    }
    return arr;
  }
  function updateBtn() {
    var s = selected();
    var d = selectedDepts();
    var total = s.length + d.length;
    var btn = overlay.querySelector('.zV2_modal_submit');
    btn.disabled = total === 0;
    var label = opts.submitLabel || 'OK';
    if (d.length) {
      btn.textContent = label + ' (' + s.length + ' NV + ' + d.length + ' phòng ban)';
    } else {
      btn.textContent = label + ' (' + s.length + ')';
    }
  }
  overlay.querySelector('.zV2_modal_close').addEventListener('click', close);
  overlay.querySelector('.zV2_modal_cancel').addEventListener('click', close);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });

  // Dept dropdown: toggle menu + check phòng ban (kèm tự tick children + NV)
  var deptBtn = overlay.querySelector('.zV2_dept_dropdown_btn');
  var deptMenu = overlay.querySelector('.zV2_dept_dropdown_menu');
  var deptCount = overlay.querySelector('.zV2_dept_count');
  if (deptBtn && deptMenu) {
    deptBtn.addEventListener('click', function(e){
      e.stopPropagation();
      deptMenu.hidden = !deptMenu.hidden;
    });
    // Click ngoài → đóng menu
    document.addEventListener('click', function onDocClickDept(ev){
      if (!overlay.isConnected) { document.removeEventListener('click', onDocClickDept); return; }
      if (!deptMenu.contains(ev.target) && !deptBtn.contains(ev.target)) {
        deptMenu.hidden = true;
      }
    });
  }
  // Mapping cha → con tường minh (tên không share prefix tự nhiên)
  var _zV2_DEPT_TREE = {
    'Marketing': ['Media / Desginer', 'Quảng Cáo Ads'],
    'Kinh Doanh': ['Kinh Doanh Bán Lẻ Nhóm 1', 'Kinh Doanh Bán Lẻ Nhóm 2', 'Tư Vấn - Lễ Tân']
  };
  // Helper: tìm tất cả phòng ban CON của 1 parent
  // Match 2 cách: (1) tên CON bắt đầu bằng parent + ký tự ngắt; (2) lookup explicit map
  function _childDepts(parent) {
    var p = (parent || '').trim();
    if (!p) return [];
    var pl = p.toLowerCase();
    var children = [];
    // 1) Explicit map
    var mapList = _zV2_DEPT_TREE[p] || [];
    mapList.forEach(function(c){
      if (groupNames.indexOf(c) !== -1) children.push(c);
    });
    // 2) Prefix match (case-insensitive + ký tự ngắt hợp lệ)
    groupNames.forEach(function(g){
      var gl = (g || '').toLowerCase();
      if (gl === pl) return;
      if (gl.indexOf(pl) !== 0) return;
      var nextCh = gl.charAt(pl.length);
      if (nextCh === ' ' || nextCh === '-' || nextCh === '/' || nextCh === '_' || nextCh === ',' || nextCh === '–') {
        if (children.indexOf(g) === -1) children.push(g);
      }
    });
    return children;
  }
  function _refreshDeptBadge() {
    if (!deptCount) return;
    var n = overlay.querySelectorAll('.zV2_dept_cb:checked').length;
    deptCount.textContent = n;
    deptCount.style.display = n > 0 ? '' : 'none';
  }
  var deptCbs = overlay.querySelectorAll('.zV2_dept_cb');
  for (var k = 0; k < deptCbs.length; k++) {
    deptCbs[k].addEventListener('change', function(e){
      var pb = e.target.value;
      var checked = e.target.checked;
      // Tick/untick tất cả NV trong phòng ban đó
      function applyToRows(pbName) {
        var rows = overlay.querySelectorAll('.zV2_picker_cb[data-pb="' + pbName.replace(/"/g, '\\"') + '"]');
        for (var i = 0; i < rows.length; i++) rows[i].checked = checked;
      }
      applyToRows(pb);
      // Đồng thời tick/untick các phòng ban CON (vd "Kinh Doanh" → "Kinh Doanh Bán Lẻ Nhóm 1/2")
      var children = _childDepts(pb);
      for (var c = 0; c < children.length; c++) {
        var childPb = children[c];
        applyToRows(childPb);
        // Đồng bộ checkbox dept con
        var childCb = overlay.querySelector('.zV2_dept_cb[value="' + childPb.replace(/"/g, '\\"') + '"]');
        if (childCb) childCb.checked = checked;
      }
      _refreshDeptBadge();
      updateBtn();
    });
  }
  var cbs = overlay.querySelectorAll('.zV2_picker_cb');
  for (var i = 0; i < cbs.length; i++) cbs[i].addEventListener('change', updateBtn);

  var search = overlay.querySelector('.zV2_picker_search');
  if (search) {
    search.addEventListener('input', function () {
      var q = search.value.toLowerCase();
      var rows = overlay.querySelectorAll('.zV2_picker_row');
      for (var j = 0; j < rows.length; j++) {
        var name = (rows[j].querySelector('.zV2_picker_cb').getAttribute('data-name') || '').toLowerCase();
        rows[j].style.display = name.indexOf(q) !== -1 ? '' : 'none';
      }
    });
  }
  overlay.querySelector('.zV2_modal_submit').addEventListener('click', function () {
    var sel = selected();
    var depts = selectedDepts();
    if (opts.withName) {
      var nm = overlay.querySelector('.zV2_picker_groupname').value.trim();
      if (!nm) { zV2_toast('Nhập tên nhóm', 'error'); return; }
      opts.onSubmit({ name: nm, usernames: sel, phong_ban_list: depts }, close);
    } else {
      opts.onSubmit({ usernames: sel, phong_ban_list: depts }, close);
    }
  });
}

window.zV2_renderTabAnhVideo = function (roomId) {
  var pane = zV2_$('zV2_info_panes');
  if (!pane) return;
  var msgs = ((_zV2 && _zV2.messages && _zV2.messages[roomId]) || []).filter(function (m) {
    return m.msg_type === 'image' || m.msg_type === 'video';
  });
  if (!msgs.length) {
    pane.innerHTML = '<div class="zV2_empty_hint">Chưa có ảnh/video nào.</div>';
    return;
  }
  var html = '<div class="zV2_media_grid">';
  msgs.forEach(function (m) {
    var url = m.attachment_url || m.file_url || m.content || '';
    html += '<div class="zV2_media_cell" data-url="' + zV2_escapeHtml(url) + '">' +
      (m.msg_type === 'video'
        ? '<video src="' + zV2_escapeHtml(url) + '" muted></video><span class="zV2_media_play">▶</span>'
        : '<img src="' + zV2_escapeHtml(url) + '" alt="" loading="lazy">') +
    '</div>';
  });
  html += '</div>';
  pane.innerHTML = html;
  var cells = pane.querySelectorAll('.zV2_media_cell');
  for (var i = 0; i < cells.length; i++) {
    (function (cell) {
      cell.addEventListener('click', function () {
        var u = cell.getAttribute('data-url');
        if (typeof window.zV2_openLightbox === 'function') zV2_openLightbox(u);
        else window.open(u, '_blank');
      });
    })(cells[i]);
  }
};

window.zV2_renderTabFile = function (roomId) {
  var pane = zV2_$('zV2_info_panes');
  if (!pane) return;
  var msgs = ((_zV2 && _zV2.messages && _zV2.messages[roomId]) || []).filter(function (m) {
    return m.msg_type === 'file';
  });
  if (!msgs.length) {
    pane.innerHTML = '<div class="zV2_empty_hint">Chưa có file nào.</div>';
    return;
  }
  var html = '<div class="zV2_file_list">';
  msgs.forEach(function (m) {
    var url = m.attachment_url || m.file_url || '';
    var nm = m.file_name || m.filename || (url ? url.split('/').pop() : 'file');
    var sz = zV2_fmtBytes(m.file_size || 0);
    var dt = zV2_fmtDate(m.created_at || m.timestamp);
    var sender = m.sender_name || m.sender || '';
    html += '<a class="zV2_file_row" href="' + zV2_escapeHtml(url) + '" download target="_blank">' +
      '<span class="zV2_file_icon"></span>' +
      '<div class="zV2_file_body">' +
        '<div class="zV2_file_name">' + zV2_escapeHtml(nm) + '</div>' +
        '<div class="zV2_file_meta">' + zV2_escapeHtml(sz) + ' · ' + zV2_escapeHtml(dt) + ' · ' + zV2_escapeHtml(sender) + '</div>' +
      '</div>' +
    '</a>';
  });
  html += '</div>';
  pane.innerHTML = html;
};

window.zV2_renameRoom = function (roomId) {
  var room = ((_zV2 && _zV2.rooms) || []).find(function (r) { return r.id === roomId || r.room_id === roomId; }) || {};
  var overlay = document.createElement('div');
  overlay.className = 'zV2_modal_overlay';
  overlay.innerHTML =
    '<div class="zV2_modal_card">' +
      '<div class="zV2_modal_header"><span>Đổi tên nhóm</span><button class="zV2_modal_close" type="button">✕</button></div>' +
      '<div class="zV2_modal_body">' +
        '<input type="text" class="zV2_rename_input" value="' + zV2_escapeHtml(room.name || room.display_name || '') + '">' +
      '</div>' +
      '<div class="zV2_modal_footer">' +
        '<button class="zV2_btn_secondary zV2_modal_cancel" type="button">Huỷ</button>' +
        '<button class="zV2_btn_primary zV2_modal_submit" type="button">Lưu</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(overlay);
  function close() { overlay.remove(); }
  overlay.querySelector('.zV2_modal_close').addEventListener('click', close);
  overlay.querySelector('.zV2_modal_cancel').addEventListener('click', close);
  overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });
  overlay.querySelector('.zV2_modal_submit').addEventListener('click', function () {
    var v = overlay.querySelector('.zV2_rename_input').value.trim();
    if (!v) { zV2_toast('Tên không được trống', 'error'); return; }
    fetch('/api/chat/rooms/' + encodeURIComponent(roomId), {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: v })
    })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function () {
        zV2_toast('Đã đổi tên', 'success');
        close();
      })
      .catch(function () { zV2_toast('Không đổi tên được', 'error'); });
  });
  setTimeout(function () { var i = overlay.querySelector('.zV2_rename_input'); if (i) i.focus(); }, 30);
};

window.zV2_leaveRoom = function (roomId) {
  if (!confirm('Rời nhóm này?')) return;
  fetch('/api/chat/rooms/' + encodeURIComponent(roomId) + '/leave', { method: 'POST' })
    .then(function (r) { if (!r.ok) throw new Error('fail'); })
    .then(function () {
      zV2_toast('Đã rời nhóm', 'success');
      if (_zV2 && _zV2.rooms) {
        _zV2.rooms = _zV2.rooms.filter(function (r) { return (r.id || r.room_id) !== roomId; });
      }
      zV2_closeInfoPanel();
      if (typeof window.zV2_renderConvList === 'function') zV2_renderConvList();
      if (_zV2 && _zV2.currentRoomId === roomId) {
        _zV2.currentRoomId = null;
        var mh = zV2_$('zV2_main_header'); if (mh) mh.innerHTML = '';
        var mi = zV2_$('zV2_messages_inner'); if (mi) mi.innerHTML = '<div class="zV2_empty_hint">Chọn cuộc trò chuyện.</div>';
      }
    })
    .catch(function () { zV2_toast('Không rời được nhóm', 'error'); });
};

window.zV2_openCreateGroupModal = async function () {
  // Đảm bảo users đã được load (nếu user chưa vào tab Danh bạ)
  if (!_zV2 || !_zV2.users || _zV2.users.length === 0) {
    try {
      if (typeof window.zV2_loadUsers === 'function') await window.zV2_loadUsers();
    } catch(_){}
  }
  var users = ((_zV2 && _zV2.users) || []).filter(function (u) { return u.username !== zV2_currentUser(); });
  zV2_renderUserPickerModal({
    title: 'Tạo nhóm mới',
    submitLabel: 'Tạo nhóm',
    users: users,
    withName: true,
    withDepartments: true,
    onSubmit: function (payload, close) {
      var hasMembers = (payload.usernames || []).length > 0;
      var hasDepts = (payload.phong_ban_list || []).length > 0;
      if (!hasMembers && !hasDepts) {
        zV2_toast('Chọn ít nhất 1 thành viên hoặc 1 phòng ban', 'error');
        return;
      }
      var body = {
        name: payload.name,
        member_usernames: payload.usernames || [],
        phong_ban_list: payload.phong_ban_list || []
      };
      console.log('[zV2] Tạo nhóm body:', body);
      fetch('/api/chat/rooms', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(body)
      })
        .then(async function (r) {
          if (r.ok) return r.json();
          var errText = await r.text().catch(function(){ return ''; });
          console.error('[zV2] Tạo nhóm failed status=' + r.status, errText);
          throw new Error('HTTP ' + r.status + ' ' + errText);
        })
        .then(function (room) {
          zV2_toast('Đã tạo nhóm', 'success');
          if (_zV2 && _zV2.rooms) _zV2.rooms.unshift(room);
          close();
          if (typeof window.zV2_renderConvList === 'function') zV2_renderConvList();
          if (typeof window.zV2_openRoom === 'function') zV2_openRoom(room.id || room.room_id);
        })
        .catch(function (e) {
          console.error('[zV2] Tạo nhóm catch:', e);
          zV2_toast('Không tạo được nhóm: ' + (e.message || ''), 'error');
        });
    }
  });
};

// ---------- PRESENCE + TYPING ----------
window.zV2_setupPresencePolling = function () {
  if (window._zV2 && window._zV2._presencePollSetup) return;
  if (window._zV2) window._zV2._presencePollSetup = true;
  function tick() {
    fetch('/api/chat/presence/all', { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : []; })
      .then(function (list) {
        list = list || [];
        if (!window._zV2) return;
        var usernames = Array.isArray(list)
          ? list.map(function (x) { return typeof x === 'string' ? x : (x.username || x); })
          : [];
        _zV2.online = new Set(usernames);
        try { window.dispatchEvent(new CustomEvent('presence-changed')); }
        catch (e) {
          var ev = document.createEvent('Event'); ev.initEvent('presence-changed', true, true);
          window.dispatchEvent(ev);
        }
      })
      .catch(function () { /* silent */ });
  }
  tick();
  // Poll 2 phút/lần (TTL Redis 30 phút, JWT 30p) — refresh presence map từ server
  setInterval(tick, 120000);
  // Khi tab quay lại visible → tick ngay để mark online + refresh map
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) tick();
  });
};

// ---------- TYPING INDICATOR (ban dung duy nhat) ----------
// Giao uoc voi CSS/HTML — dung sai la tinh nang chet am tham:
//   * hien/an bang CLASS `.visible`, KHONG phai el.style.display
//     (CSS goc la display:none; gan style.display='' chi go inline style roi
//      roi lai ve none — dung loi ma comment o zV2_updateComposerButtons da
//      canh bao)
//   * ba cham la 3 span san co class `.zV2_dot` trong HTML. TUYET DOI khong
//     ghi de innerHTML cua ca khoi, lam vay la xoa mat chung + mat animation.
//     Chi duoc set textContent cua `.zV2_typing_text`.
// Ho tro nhieu nguoi cung go trong nhom, moi nguoi het han sau 5s.
var _zV2_typingBy = {};      // { roomId: { username: {ten, luc} } }
var _zV2_typingSweep = null;

window.zV2_renderTyping = function () {
  var el = (window.zV2_$ ? zV2_$('zV2_typing_indicator')
                         : document.getElementById('zV2_typing_indicator'));
  if (!el) return false;
  var khoa = String((window._zV2 && _zV2.currentRoomId) || '');
  var bay_gio = Date.now();
  var m = _zV2_typingBy[khoa] || {};
  var ten = Object.keys(m)
    .filter(function (u) { return bay_gio - m[u].luc < 5000; })
    .map(function (u) { return m[u].ten; });

  if (!ten.length) { el.classList.remove('visible'); return false; }

  var chu = ten.length === 1 ? ten[0] + ' đang soạn'
          : ten.length === 2 ? ten[0] + ' và ' + ten[1] + ' đang soạn'
          : ten[0] + ' và ' + (ten.length - 1) + ' người khác đang soạn';
  var t = el.querySelector('.zV2_typing_text');
  if (t) t.textContent = chu; else el.textContent = chu;
  el.classList.add('visible');
  return true;
};

// Quet 1s/lan de tu an khi het han HOAC khi doi phong; tu dung khi khong con ai.
function _zV2_typingBatQuet() {
  if (_zV2_typingSweep) return;
  _zV2_typingSweep = setInterval(function () {
    if (!window.zV2_renderTyping()) {
      clearInterval(_zV2_typingSweep);
      _zV2_typingSweep = null;
    }
  }, 1000);
}

window.zV2_showTypingIndicator = function (roomId, sender_name, username) {
  if (!window._zV2) return;
  var khoa = String(roomId);
  var u = username || sender_name || '?';
  _zV2_typingBy[khoa] = _zV2_typingBy[khoa] || {};
  _zV2_typingBy[khoa][u] = { ten: sender_name || u, luc: Date.now() };
  if (window.zV2_renderTyping()) _zV2_typingBatQuet();
};

// Nguoi ta gui tin roi thi thoi khong con "dang soan" — an ngay, khong doi 5s
window.zV2_clearTyping = function (roomId, username) {
  var khoa = String(roomId);
  if (_zV2_typingBy[khoa]) delete _zV2_typingBy[khoa][username];
  window.zV2_renderTyping();
};

// ---------- MOBILE BACK + HEADER WIRING ----------
// zV2_wireMobileBack ĐÃ XOÁ — nó là code chết của một phiên bản markup khác,
// sai cả ba định danh: tìm #zV2_main_header_back (thật là #zV2_main_back_btn),
// tìm #zV2_panel (thật là #_chat_panel), gỡ class zV2_mobile_show_conv (thật
// là show-main). Không khớp gì nên không làm gì.
// Nút quay lại trên mobile được nối THẬT ở zV2_bind(): $mainBackBtn -> zV2_mobileBack.
window.zV2_wireMobileBack = function () { /* giữ tên cho nơi gọi cũ, không làm gì */ };

window.zV2_wireHeaderInfoBtn = function () {
  document.addEventListener('click', function (e) {
    var t = e.target;
    while (t && t !== document) {
      if (t.classList && t.classList.contains('zV2_header_btn_info')) {
        zV2_openInfoPanel(); return;
      }
      if (t.id === 'zV2_btn_new_group' || t.id === 'zV2_btn_create_group') {
        zV2_openCreateGroupModal();
        return;
      }
      t = t.parentNode;
    }
  });
};

// ---------- IN-CHAT MESSAGE SEARCH ----------
(function(){
  var bar, input, countEl, prevBtn, nextBtn, closeBtn, toggleBtn;
  var hits = [];       // [{row, marks: [<mark>...]}]
  var activeIdx = -1;
  var lastQuery = '';

  function $id(id){ return document.getElementById(id); }

  function escapeRegex(s){ return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function clearHighlights(){
    var inner = $id('zV2_messages_inner');
    if (!inner) return;
    var marks = inner.querySelectorAll('mark.zV2_search_hit');
    for (var i = 0; i < marks.length; i++) {
      var m = marks[i];
      var parent = m.parentNode;
      if (!parent) continue;
      parent.replaceChild(document.createTextNode(m.textContent), m);
      parent.normalize();
    }
    hits = []; activeIdx = -1;
  }

  function walkTextNodes(root, fn){
    if (!root) return;
    var stack = [root];
    while (stack.length) {
      var n = stack.pop();
      for (var i = n.childNodes.length - 1; i >= 0; i--) {
        var c = n.childNodes[i];
        if (c.nodeType === 3) fn(c);
        else if (c.nodeType === 1 && c.tagName !== 'MARK' && c.tagName !== 'SCRIPT' && c.tagName !== 'STYLE') {
          stack.push(c);
        }
      }
    }
  }

  function highlightInBubble(bubble, regex){
    var marksInBubble = [];
    walkTextNodes(bubble, function(textNode){
      var text = textNode.nodeValue;
      if (!text) return;
      regex.lastIndex = 0;
      if (!regex.test(text)) return;
      regex.lastIndex = 0;
      var frag = document.createDocumentFragment();
      var lastEnd = 0; var m;
      while ((m = regex.exec(text)) !== null) {
        if (m.index > lastEnd) frag.appendChild(document.createTextNode(text.slice(lastEnd, m.index)));
        var mk = document.createElement('mark');
        mk.className = 'zV2_search_hit';
        mk.textContent = m[0];
        frag.appendChild(mk);
        marksInBubble.push(mk);
        lastEnd = m.index + m[0].length;
        if (m.index === regex.lastIndex) regex.lastIndex++;
      }
      if (lastEnd < text.length) frag.appendChild(document.createTextNode(text.slice(lastEnd)));
      textNode.parentNode.replaceChild(frag, textNode);
    });
    return marksInBubble;
  }

  function setActive(idx){
    if (!hits.length) { activeIdx = -1; updateCount(); return; }
    if (idx < 0) idx = hits.length - 1;
    if (idx >= hits.length) idx = 0;
    // unset previous
    if (activeIdx >= 0 && hits[activeIdx]) {
      hits[activeIdx].marks.forEach(function(m){ m.classList.remove('zV2_search_hit_active'); });
    }
    activeIdx = idx;
    var h = hits[activeIdx];
    h.marks.forEach(function(m){ m.classList.add('zV2_search_hit_active'); });
    var firstMark = h.marks[0];
    if (firstMark && firstMark.scrollIntoView) {
      firstMark.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    updateCount();
  }

  function updateCount(){
    if (!countEl) return;
    if (!hits.length) {
      countEl.textContent = lastQuery ? '0/0' : '';
      countEl.classList.toggle('no-match', !!lastQuery);
    } else {
      countEl.textContent = (activeIdx + 1) + '/' + hits.length;
      countEl.classList.remove('no-match');
    }
    if (prevBtn) prevBtn.disabled = hits.length < 2;
    if (nextBtn) nextBtn.disabled = hits.length < 2;
  }

  function runSearch(q){
    clearHighlights();
    lastQuery = (q || '').trim();
    if (!lastQuery) { updateCount(); return; }
    var inner = $id('zV2_messages_inner');
    if (!inner) { updateCount(); return; }
    var rx = new RegExp(escapeRegex(lastQuery), 'gi');
    var bubbles = inner.querySelectorAll('.zV2_bubble');
    for (var i = 0; i < bubbles.length; i++) {
      var marks = highlightInBubble(bubbles[i], rx);
      if (marks.length) {
        var row = bubbles[i].closest('.zV2_msg_row') || bubbles[i];
        hits.push({ row: row, marks: marks });
      }
    }
    // most recent first → reverse để hit gần đáy là #1
    hits.reverse();
    if (hits.length) setActive(0);
    else updateCount();
  }

  function openSearch(){
    if (!bar) return;
    bar.classList.add('active');
    if (input) { input.value = ''; input.focus(); }
    lastQuery = '';
    updateCount();
  }

  function closeSearch(){
    if (!bar) return;
    bar.classList.remove('active');
    clearHighlights();
    if (input) input.value = '';
    lastQuery = '';
    updateCount();
  }

  function wire(){
    bar = $id('zV2_msg_search_bar');
    input = $id('zV2_msg_search_input');
    countEl = $id('zV2_msg_search_count');
    prevBtn = $id('zV2_msg_search_prev');
    nextBtn = $id('zV2_msg_search_next');
    closeBtn = $id('zV2_msg_search_close');
    toggleBtn = $id('zV2_btn_msg_search');
    if (!bar || !toggleBtn) return;

    toggleBtn.addEventListener('click', function(){
      if (bar.classList.contains('active')) closeSearch();
      else openSearch();
    });
    closeBtn && closeBtn.addEventListener('click', closeSearch);
    prevBtn && prevBtn.addEventListener('click', function(){ if (hits.length) setActive(activeIdx - 1); });
    nextBtn && nextBtn.addEventListener('click', function(){ if (hits.length) setActive(activeIdx + 1); });

    var debounceT = null;
    input && input.addEventListener('input', function(){
      clearTimeout(debounceT);
      var v = input.value;
      debounceT = setTimeout(function(){ runSearch(v); }, 180);
    });
    input && input.addEventListener('keydown', function(e){
      if (e.key === 'Escape') { e.preventDefault(); closeSearch(); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        if (!hits.length) return;
        setActive(e.shiftKey ? activeIdx - 1 : activeIdx + 1);
      }
    });

    // Re-run search khi messages thay đổi (vd có tin mới)
    var inner = $id('zV2_messages_inner');
    if (inner && window.MutationObserver) {
      var moTimer = null;
      new MutationObserver(function(){
        if (!bar.classList.contains('active') || !lastQuery) return;
        clearTimeout(moTimer);
        moTimer = setTimeout(function(){ runSearch(lastQuery); }, 250);
      }).observe(inner, { childList: true, subtree: true });
    }

    // Ctrl/Cmd + F khi đang focus trong chat → mở search box
    document.addEventListener('keydown', function(e){
      if ((e.ctrlKey || e.metaKey) && (e.key === 'f' || e.key === 'F')) {
        var scroll = $id('zV2_messages_scroll');
        if (scroll && scroll.style.display !== 'none') {
          e.preventDefault();
          openSearch();
        }
      }
    });
  }

  // Public API
  window.zV2_openMsgSearch = openSearch;
  window.zV2_closeMsgSearch = closeSearch;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', wire);
  } else {
    wire();
  }
})();

// ---------- SKELETON LOADERS ----------
window.zV2_showRoomsSkeleton = function () {
  var el = zV2_$('zV2_conv_list');
  if (!el) return;
  var html = '';
  for (var i = 0; i < 5; i++) {
    html += '<div class="zV2_skeleton_conv">' +
      '<div class="zV2_skeleton_avatar"></div>' +
      '<div class="zV2_skeleton_lines">' +
        '<div class="zV2_skeleton_row"></div>' +
        '<div class="zV2_skeleton_row short"></div>' +
      '</div>' +
    '</div>';
  }
  el.innerHTML = html;
};

window.zV2_showMessagesSkeleton = function () {
  var el = zV2_$('zV2_messages_inner');
  if (!el) return;
  var html = '';
  for (var i = 0; i < 3; i++) {
    var side = i % 2 === 0 ? 'left' : 'right';
    html += '<div class="zV2_skeleton_bubble ' + side + '">' +
      '<div class="zV2_skeleton_row"></div>' +
      '<div class="zV2_skeleton_row short"></div>' +
    '</div>';
  }
  el.innerHTML = html;
};

// ---------- INIT ----------
document.addEventListener('DOMContentLoaded', function () {
  zV2_wireHeaderInfoBtn();
  zV2_wireMobileBack();
});

// Boot
document.addEventListener('DOMContentLoaded', () => {
  if (typeof zV2_init === 'function') zV2_init();
  if (typeof zV2_initSSE === 'function') zV2_initSSE();
  if (typeof zV2_setupPresencePolling === 'function') zV2_setupPresencePolling();
});

})();

;
/* ── @MENTION AUTOCOMPLETE ─────────────────────────────────────────────────── */
(function(){
  var _mStart=-1,_mIdx=0,_mList=[];
  function _hc(s){var p=['#0B63CE','#1F6F72','#2E7D4F','#6B4E7D','#B02A18','#3D5A80','#A02C5A','#4A4A82'];var h=0;s=String(s||'');for(var i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))>>>0;return p[h%p.length];}
  function _users(){return(window._zV2&&window._zV2.users)||[];}
  function _show(list,q){
    var dd=document.getElementById('zV2_mention_dd');if(!dd)return;
    _mList=list;_mIdx=0;
    if(!list.length){dd.classList.remove('open');return;}
    dd.innerHTML=list.map(function(u,i){
      var name=u.ho_ten||u.username||'';
      var init=(name[0]||'?').toUpperCase();
      var bg=_hc(name);
      var dept=u.phong_ban||'';
      var hl=q?name.replace(new RegExp('('+q.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+')','gi'),'<b>$1</b>'):name;
      // Đặc biệt: @all → icon loa + nền vàng cảnh báo
      if(u._is_all){
        return '<div class="zV2_mention_item'+(i===0?' active':'')+'" data-idx="'+i+'" data-name="all" style="background:var(--warning-soft);border-left:3px solid var(--z-warn)">'
          +'<div class="zV2_mention_item_ava" style="background:var(--z-warn);font-size:15px"></div>'
          +'<div><div class="zV2_mention_item_name" style="color:var(--warning-fg)">@all<span style="margin-left:6px;color:var(--warning-fg);font-weight:500">Tag cả phòng</span></div><div class="zV2_mention_item_dept">Thông báo đến mọi thành viên</div></div>'
          +'</div>';
      }
      return '<div class="zV2_mention_item'+(i===0?' active':'')+'" data-idx="'+i+'" data-name="'+name+'">'
        +'<div class="zV2_mention_item_ava" style="background:'+bg+'">'+init+'</div>'
        +'<div><div class="zV2_mention_item_name">'+hl+'</div>'+(dept?'<div class="zV2_mention_item_dept">'+dept+'</div>':'')+'</div>'
        +'</div>';
    }).join('');
    dd.classList.add('open');
    dd.querySelectorAll('.zV2_mention_item').forEach(function(el){
      el.addEventListener('mousedown',function(e){e.preventDefault();_insert(el.dataset.name);});
    });
  }
  function _hide(){var dd=document.getElementById('zV2_mention_dd');if(dd)dd.classList.remove('open');_mStart=-1;_mList=[];_mIdx=0;}
  function _insert(name){
    var inp=document.getElementById('zV2_compose_input');if(!inp||_mStart<0)return;
    var v=inp.value,cur=inp.selectionStart;
    inp.value=v.slice(0,_mStart)+'@'+name+' '+v.slice(cur);
    var np=_mStart+name.length+2;inp.setSelectionRange(np,np);inp.focus();
    if(!window._zV2_mentions)window._zV2_mentions=[];
    if(window._zV2_mentions.indexOf(name)<0)window._zV2_mentions.push(name);
    _hide();inp.dispatchEvent(new Event('input',{bubbles:true}));
  }
  function _onInput(){
    var inp=document.getElementById('zV2_compose_input');if(!inp)return;
    var v=inp.value,cur=inp.selectionStart,at=-1;
    for(var i=cur-1;i>=0;i--){if(v[i]==='@'){at=i;break;}if(v[i]===' '||v[i]==='\n')break;}
    if(at>=0){
      var q=v.slice(at+1,cur).toLowerCase();_mStart=at;
      var f=_users().filter(function(u){return((u.ho_ten||'').toLowerCase().indexOf(q)>=0||(u.username||'').toLowerCase().indexOf(q)>=0);}).slice(0,8);
      // @all luôn xuất hiện đầu danh sách khi query rỗng hoặc match 'all'
      if(!q || 'all'.indexOf(q)===0 || 'cả phòng'.indexOf(q)>=0 || 'mọi người'.indexOf(q)>=0){
        f.unshift({ho_ten:'all', username:'all', phong_ban:'Tag cả phòng', _is_all:true});
      }
      _show(f,q);
    } else _hide();
  }
  function _onKey(e){
    var dd=document.getElementById('zV2_mention_dd');if(!dd||!dd.classList.contains('open'))return;
    if(e.key==='ArrowDown'){e.preventDefault();_mIdx=Math.min(_mIdx+1,_mList.length-1);}
    else if(e.key==='ArrowUp'){e.preventDefault();_mIdx=Math.max(_mIdx-1,0);}
    else if(e.key==='Enter'||e.key==='Tab'){if(_mList.length){e.preventDefault();_insert(_mList[_mIdx].ho_ten||_mList[_mIdx].username||'');return;}}
    else if(e.key==='Escape'){_hide();return;}
    dd.querySelectorAll('.zV2_mention_item').forEach(function(el,i){el.classList.toggle('active',i===_mIdx);});
  }
  function _boot(){
    var inp=document.getElementById('zV2_compose_input');
    if(!inp){setTimeout(_boot,600);return;}
    var wrap=document.getElementById('zV2_compose_wrap')||inp.parentElement;
    if(wrap){wrap.style.position='relative';}
    if(!document.getElementById('zV2_mention_dd')){
      var dd=document.createElement('div');dd.id='zV2_mention_dd';
      if(wrap)wrap.insertBefore(dd,wrap.firstChild);else inp.parentElement.insertBefore(dd,inp);
    }
    inp.addEventListener('input',_onInput);
    inp.addEventListener('keydown',_onKey);
    // Load users khi mở phòng
    var _origOpen=window.zV2_openRoom;
    window.zV2_openRoom=function(){
      var r=_origOpen&&_origOpen.apply(this,arguments);
      if(!window._zV2)window._zV2={};
      if(!window._zV2.users||!window._zV2.users.length){
        fetch('/api/chat/users',{credentials:'include'}).then(function(res){return res.ok?res.json():[];}).then(function(u){window._zV2.users=u;}).catch(function(){});
      }
      return r;
    };
  }
  // Patch renderContent để highlight @mention (@all đậm + nền vàng)
  window.zV2_renderContent=function(content,mentions){
    if(!content)return'';
    var s=String(content).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    s=s.replace(/@([\wÀ-ɏḀ-ỿ]+(?:\s[\wÀ-ɏḀ-ỿ]+)?)/g,function(m,n){
      if(n.toLowerCase()==='all'){
        return '<span class="zV2_mention" style="background:var(--warning-soft);color:var(--warning-fg);font-weight:700;border:1px solid var(--z-warn)">@all</span>';
      }
      return '<span class="zV2_mention">@'+n+'</span>';
    });
    return s;
  };
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',_boot);else _boot();
})();

// ============================================================
// AI Morning Brief — Mai trợ lý sáng (MVP 2026-05-23)
// ============================================================
(function(){
  'use strict';
  if (window._zV2_aiBrief) return;
  window._zV2_aiBrief = { showing: false };

  // Mini markdown → HTML (chỉ basic: heading, bold, italic, list, br)
  function _md2html(s){
    if (!s) return '';
    s = String(s);
    // Escape HTML trước
    s = s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    // Headings ## và ###
    s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    s = s.replace(/^## (.+)$/gm,  '<h3>$1</h3>');
    s = s.replace(/^# (.+)$/gm,   '<h2>$1</h2>');
    // Bold **x** và italic *x*
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    // Inline code `x`
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bullet list `- x` (gom liên tiếp thành <ul>)
    s = s.replace(/(^- .+(?:\n- .+)*)/gm, function(m){
      var items = m.split(/\n/).map(function(l){
        return '<li>' + l.replace(/^- /, '') + '</li>';
      }).join('');
      return '<ul>' + items + '</ul>';
    });
    // Line breaks (paragraph)
    s = s.replace(/\n\n+/g, '</p><p>');
    s = '<p>' + s + '</p>';
    // Clean: <p></p> rỗng, <p> bao quanh block
    s = s.replace(/<p>\s*<\/p>/g, '');
    s = s.replace(/<p>(<h\d>)/g, '$1').replace(/(<\/h\d>)<\/p>/g, '$1');
    s = s.replace(/<p>(<ul>)/g, '$1').replace(/(<\/ul>)<\/p>/g, '$1');
    s = s.replace(/\n/g, '<br>');
    return s;
  }

  function _todayStr(){
    var d = new Date();
    return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0')
         + '-' + String(d.getDate()).padStart(2,'0');
  }

  function _ensureStyles(){
    if (document.getElementById('zV2_aiBrief_css')) return;
    var css = ''
      + '.zV2_aiBrief_overlay{position:fixed;inset:0;background:rgba(51,33,15,.32);z-index:10000;display:flex;align-items:center;justify-content:center;padding:16px;animation:zV2_aiBrief_fade .18s ease;}'
      + '@keyframes zV2_aiBrief_fade{from{opacity:0}to{opacity:1}}'
      + '.zV2_aiBrief_card{background:#fff;border-radius:14px;max-width:560px;width:100%;max-height:85vh;display:flex;flex-direction:column;box-shadow:0 18px 50px rgba(0,0,0,.25);overflow:hidden;}'
      + '.zV2_aiBrief_head{display:flex;align-items:center;gap:10px;padding:14px 18px;border-bottom:1px solid var(--z-active);background:linear-var(--warning-soft);}'
      + '.zV2_aiBrief_avatar{width:38px;height:38px;border-radius:50%;background:var(--z-warn);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:17px;flex-shrink:0;}'
      + '.zV2_aiBrief_title{flex:1;min-width:0;}'
      + '.zV2_aiBrief_title .name{font-weight:700;font-size:16px;color:var(--z-text);}'
      + '.zV2_aiBrief_title .sub{font-size:13px;color:var(--z-text2);}'
      + '.zV2_aiBrief_close{background:transparent;border:none;font-size:22px;cursor:pointer;color:var(--z-text2);padding:4px 8px;border-radius:8px;}'
      + '.zV2_aiBrief_close:hover{background:rgba(0,0,0,.05);}'
      + '.zV2_aiBrief_body{padding:18px 22px;overflow-y:auto;font-size:15px;line-height:1.55;color:var(--z-text);}'
      + '.zV2_aiBrief_body h2{font-size:17px;margin:12px 0 6px;color:var(--z-text);}'
      + '.zV2_aiBrief_body h3{font-size:16px;margin:10px 0 4px;color:var(--z-text);}'
      + '.zV2_aiBrief_body h4{font-size:15px;margin:8px 0 4px;color:var(--z-text);}'
      + '.zV2_aiBrief_body p{margin:6px 0;}'
      + '.zV2_aiBrief_body ul{margin:4px 0 8px 18px;padding:0;}'
      + '.zV2_aiBrief_body li{margin:2px 0;}'
      + '.zV2_aiBrief_body code{background:var(--z-hover);padding:1px 5px;border-radius:4px;font-size:13px;}'
      + '.zV2_aiBrief_body strong{color:var(--z-text);}'
      + '.zV2_aiBrief_loading{padding:32px;text-align:center;color:var(--z-text2);}'
      + '.zV2_aiBrief_actions{display:flex;gap:8px;padding:12px 18px;border-top:1px solid var(--z-active);background:var(--z-hover);}'
      + '.zV2_aiBrief_btn{flex:1;padding:9px 14px;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer;}'
      + '.zV2_aiBrief_btn_primary{background:var(--z-active);color:var(--z-blue-text);}'
      + '.zV2_aiBrief_btn_primary:hover{filter:brightness(.95);}'
      + '.zV2_aiBrief_btn_secondary{background:var(--z-hover);color:var(--z-text2);}'
      + '.zV2_aiBrief_btn_secondary:hover{background:var(--z-border);}'
      ;
    var st = document.createElement('style');
    st.id = 'zV2_aiBrief_css';
    st.textContent = css;
    document.head.appendChild(st);
  }

  function _close(){
    var ov = document.getElementById('zV2_aiBrief_ov');
    if (ov) ov.remove();
    window._zV2_aiBrief.showing = false;
  }

  function _renderModal(data){
    _ensureStyles();
    _close();
    var ov = document.createElement('div');
    ov.id = 'zV2_aiBrief_ov';
    ov.className = 'zV2_aiBrief_overlay';
    ov.innerHTML = ''
      + '<div class="zV2_aiBrief_card">'
      +   '<div class="zV2_aiBrief_head">'
      +     '<div class="zV2_aiBrief_avatar">M</div>'
      +     '<div class="zV2_aiBrief_title">'
      +       '<div class="name">Mai — Trợ lý AI</div>'
      +       '<div class="sub">Brief sáng ' + (data.date || '') + '</div>'
      +     '</div>'
      +     '<button class="zV2_aiBrief_close" type="button" aria-label="Đóng">×</button>'
      +   '</div>'
      +   '<div class="zV2_aiBrief_body">' + _md2html(data.content_md || '_(Chưa có brief)_') + '</div>'
      +   '<div class="zV2_aiBrief_actions">'
      +     '<button class="zV2_aiBrief_btn zV2_aiBrief_btn_secondary" data-act="later" type="button">Để sau</button>'
      +     '<button class="zV2_aiBrief_btn zV2_aiBrief_btn_primary" data-act="done" type="button">Đã xem ✓</button>'
      +   '</div>'
      + '</div>';
    // Click outside → close
    ov.addEventListener('click', function(e){
      if (e.target === ov) _close();
    });
    ov.querySelector('.zV2_aiBrief_close').addEventListener('click', _close);
    ov.querySelector('[data-act="later"]').addEventListener('click', _close);
    ov.querySelector('[data-act="done"]').addEventListener('click', function(){
      // Đánh dấu đã đọc + dismiss
      fetch('/api/ai-brief/read', { method:'POST', credentials:'same-origin' }).catch(function(){});
      try { localStorage.setItem('zV2_aiBrief_shown', _todayStr()); } catch(_){}
      _close();
    });
    document.body.appendChild(ov);
    window._zV2_aiBrief.showing = true;
  }

  function _renderLoading(){
    _ensureStyles();
    _close();
    var ov = document.createElement('div');
    ov.id = 'zV2_aiBrief_ov';
    ov.className = 'zV2_aiBrief_overlay';
    ov.innerHTML = ''
      + '<div class="zV2_aiBrief_card">'
      +   '<div class="zV2_aiBrief_head">'
      +     '<div class="zV2_aiBrief_avatar">M</div>'
      +     '<div class="zV2_aiBrief_title">'
      +       '<div class="name">Mai — Trợ lý AI</div>'
      +       '<div class="sub">Đang tổng hợp brief sáng…</div>'
      +     '</div>'
      +     '<button class="zV2_aiBrief_close" type="button" aria-label="Đóng">×</button>'
      +   '</div>'
      +   '<div class="zV2_aiBrief_loading">Mai đang đọc số liệu từ 6 app, viết brief riêng cho anh/chị…</div>'
      + '</div>';
    ov.addEventListener('click', function(e){ if (e.target === ov) _close(); });
    ov.querySelector('.zV2_aiBrief_close').addEventListener('click', _close);
    document.body.appendChild(ov);
    window._zV2_aiBrief.showing = true;
  }

  function _fetchAndShow(force){
    if (window._zV2_aiBrief.showing && !force) return;
    // App chưa mount /api/ai-brief: đã dò ra 404 hôm nay thì không tự bật nữa
    try { if (!force && localStorage.getItem('zV2_aiBrief_absent') === _todayStr()) return; } catch(_){}
    _renderLoading();
    fetch('/api/ai-brief', { credentials: 'same-origin' })
      .then(function(r){
        if (r.status === 404) { var e404 = new Error('HTTP 404'); e404.aiBriefAbsent = true; throw e404; }
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function(d){ _renderModal(d); })
      .catch(function(err){
        if (err && err.aiBriefAbsent) {
          try { localStorage.setItem('zV2_aiBrief_absent', _todayStr()); } catch(_){}
          if (!force) { _close(); return; }
          _renderModal({
            date: _todayStr(),
            content_md: '_Tính năng Morning Brief chưa được bật ở app này._',
          });
          return;
        }
        console.warn('[Mai] brief fetch failed:', err);
        _renderModal({
          date: _todayStr(),
          content_md: '_Mai chưa lấy được brief — anh/chị thử lại sau nhé._\n\n'
                    + '(Có thể do AI đang khởi tạo, mạng chậm, hoặc database busy.)',
        });
      });
  }

  // Public API
  window.zV2_aiBrief_show = _fetchAndShow;

  // Auto-show: lần đầu mở chat trong ngày → bật brief
  var _origOpen = window.zV2_open;
  window.zV2_open = function(){
    var r = _origOpen && _origOpen.apply(this, arguments);
    try {
      var last = localStorage.getItem('zV2_aiBrief_shown');
      if (last !== _todayStr()) {
        // 600ms delay để chat panel mở xong rồi mới popup brief
        setTimeout(function(){ _fetchAndShow(false); }, 600);
      }
    } catch(_){}
    return r;
  };
})();

;
(function(){
  if (window.zCall) return;
  var S={state:'idle',pc:null,local:null,remote:null,callId:null,peer:null,peerName:null,caller:false,media:'audio',pendOffer:null,pendCand:[],ringT:null,durT:null,durStart:0,ring:null,logRoom:null,activeStart:0,logged:false};
  var G={active:false,callId:null,roomId:null,media:'audio',peers:{},local:null,pend:{}};
  var ctx={roomId:null,type:null,isDirect:false,peer:null,name:null,memberCount:0};
  var ICE=null,iceAt=0,bc=null;
  try{bc=new BroadcastChannel('zcall');}catch(e){}

  function $(id){return document.getElementById(id);}
  function api(p){return '/api/chat'+p;}
  function genId(){return Date.now().toString(36)+Math.random().toString(36).slice(2,8);}
  function pad(n){return (n<10?'0':'')+n;}
  function avatarUrl(u){return api('/users/'+encodeURIComponent(u)+'/avatar');}

  async function fetchIce(){
    if(ICE && Date.now()-iceAt<50*60*1000) return ICE;
    try{var r=await fetch(api('/call/ice-servers'),{credentials:'include'});var j=await r.json();ICE=j.iceServers||[];iceAt=Date.now();}
    catch(e){ICE=[{urls:['stun:baogia.qlpps.com:3478']}];}
    return ICE;
  }
  function post(path,body){return fetch(api(path),{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});}
  function sig(kind,extra){return post('/call/signal',Object.assign({to:S.peer,kind:kind,call_id:S.callId,media:S.media,room_id:ctx.roomId},extra||{})).catch(function(){});}
  function gsig(target,kind,extra){return post('/call/signal',Object.assign({to:target,kind:kind,call_id:G.callId,room_id:G.roomId,media:G.media},extra||{})).catch(function(){});}
  function logCall(room_id,media,status,dur){if(!room_id)return;post('/call/log',{room_id:room_id,media:media,status:status,dur:dur||0}).catch(function(){});}

  function ringStart(){ringStop();try{var AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;var ac=new AC();S.ring={ac:ac,t:null};function ring(){var t0=ac.currentTime;[440,480,440,480].forEach(function(f,i){var o=ac.createOscillator(),g=ac.createGain();o.type='sine';o.frequency.value=f;o.connect(g);g.connect(ac.destination);var st=t0+i*0.24;g.gain.setValueAtTime(0.0001,st);g.gain.exponentialRampToValueAtTime(0.22,st+0.03);g.gain.exponentialRampToValueAtTime(0.0001,st+0.22);o.start(st);o.stop(st+0.24);});}ring();S.ring.t=setInterval(ring,3000);}catch(e){}}
  function ringStop(){if(S.ring){try{clearInterval(S.ring.t);S.ring.ac.close();}catch(e){}S.ring=null;}}

  function ensureOverlay(){
    if($('zcall_overlay'))return;
    var d=document.createElement('div');d.id='zcall_overlay';
    d.innerHTML='<div class="zcall_card"><div class="zcall_avatar" id="zcall_av"></div>'
      +'<div class="zcall_name" id="zcall_nm"></div><div class="zcall_status" id="zcall_st"></div>'
      +'<div class="zcall_btns" id="zcall_cardbtns"></div></div>'
      +'<div id="zcall_stage"><video id="zcall_remote" autoplay playsinline></video>'
      +'<div id="zcall_audioface"><div class="zcall_avatar" id="zcall_av2"></div><div class="zcall_name" id="zcall_nm2"></div></div>'
      +'<video id="zcall_local" autoplay playsinline muted></video>'
      +'<audio id="zcall_audio" autoplay playsinline></audio>'
      +'<div id="zcall_timer">00:00</div><div id="zcall_bar"></div></div>'
      +'<div id="zcall_group"><div id="zcall_ghead">Cuộc gọi nhóm</div><div id="zcall_grid"></div><div id="zcall_gbar"></div></div>';
    document.body.appendChild(d);
  }
  function avHtml(el,name,peer){var ini=(name||peer||'?').charAt(0).toUpperCase();el.textContent=ini;if(peer){var img=document.createElement('img');img.onload=function(){el.textContent='';el.appendChild(img);};img.onerror=function(){el.textContent=ini;};img.src=avatarUrl(peer);}}
  function mkBtn(cls,txt,label,fn){var w=document.createElement('div');w.style.textAlign='center';var b=document.createElement('button');b.className='zcall_btn '+cls;b.textContent=txt;b.onclick=fn;w.appendChild(b);if(label){var l=document.createElement('div');l.className='zcall_lbl';l.textContent=label;w.appendChild(l);}return w;}

  function showIncoming(){ensureOverlay();$('zcall_overlay').className='show';avHtml($('zcall_av'),S.peerName,S.peer);$('zcall_nm').textContent=S.peerName||S.peer;$('zcall_st').textContent=(S.media==='video'?'Cuộc gọi video đến…':'Cuộc gọi thoại đến…');var b=$('zcall_cardbtns');b.innerHTML='';b.appendChild(mkBtn('zcall_reject','✕','Từ chối',reject));b.appendChild(mkBtn('zcall_accept','✓','Nghe',accept));ringStart();}
  function showOutgoing(){ensureOverlay();$('zcall_overlay').className='show';avHtml($('zcall_av'),S.peerName,S.peer);$('zcall_nm').textContent=S.peerName||S.peer;$('zcall_st').textContent='Đang gọi…';var b=$('zcall_cardbtns');b.innerHTML='';b.appendChild(mkBtn('zcall_hangup','✕','Huỷ',hangup));}
  function showInCall(){$('zcall_overlay').className='show incall';S.activeStart=S.activeStart||Date.now();zcallBindRemoteAudio();var face=$('zcall_audioface');if(S.media==='video'){face.style.display='none';$('zcall_local').style.display='';}else{face.style.display='flex';$('zcall_local').style.display='none';avHtml($('zcall_av2'),S.peerName,S.peer);$('zcall_nm2').textContent=S.peerName||S.peer;}var bar=$('zcall_bar');bar.innerHTML='';var mute=mkBtn('zcall_mute','','',function(){toggleMute(mute,S.local);});bar.appendChild(mute);if(S.media==='video'){var cam=mkBtn('zcall_mute','','',function(){toggleCam(cam,S.local);});bar.appendChild(cam);}var spk=mkBtn('zcall_mute on','🔊','Loa',function(){zcallToggleSpeaker(spk);});bar.appendChild(spk);bar.appendChild(mkBtn('zcall_hangup','✕','',hangup));startTimer();}
  function startTimer(){S.durStart=Date.now();clearInterval(S.durT);S.durT=setInterval(function(){var s=Math.floor((Date.now()-S.durStart)/1000);var t=$('zcall_timer');if(t)t.textContent=pad(Math.floor(s/60))+':'+pad(s%60);},500);}
  function toggleMute(w,stream){if(!stream)return;var muted=false;stream.getAudioTracks().forEach(function(t){t.enabled=!t.enabled;muted=!t.enabled;});w.firstChild.classList.toggle('on',muted);}
  function toggleCam(w,stream){if(!stream)return;var off=false;stream.getVideoTracks().forEach(function(t){t.enabled=!t.enabled;off=!t.enabled;});w.firstChild.classList.toggle('on',off);}

  function zcallBindRemoteAudio(){var ra=$('zcall_audio');if(ra&&S.remote){try{ra.srcObject=S.remote;ra.muted=false;if(!S.spkVol&&S.spkVol!==0)S.spkVol=1;ra.volume=S.spkVol;var pa=ra.play&&ra.play();if(pa&&pa.catch)pa.catch(function(){});}catch(e){}}}
  function zcallToggleSpeaker(w){var ra=$('zcall_audio');if(!ra)return;S.spkVol=1;ra.muted=false;ra.volume=1;try{var p=ra.play&&ra.play();if(p&&p.catch)p.catch(function(){});}catch(e){}
    // Desktop: luan phien thiet bi ra (loa ngoai / tai nghe) neu trinh duyet ho tro setSinkId
    if(typeof ra.setSinkId==='function'&&navigator.mediaDevices&&navigator.mediaDevices.enumerateDevices){
      navigator.mediaDevices.enumerateDevices().then(function(ds){var outs=ds.filter(function(d){return d.kind==='audiooutput'&&d.deviceId;});if(outs.length>1){S._spkIdx=((S._spkIdx||0)+1)%outs.length;ra.setSinkId(outs[S._spkIdx].deviceId).catch(function(){});}}).catch(function(){});
    }
    if(w&&w.firstChild)w.firstChild.classList.add('on');
    if(window.zV2_toast)zV2_toast('Đã bật loa','success');}
  async function makePc(){var ice=await fetchIce();var pc=new RTCPeerConnection({iceServers:ice});pc.onicecandidate=function(e){if(e.candidate)sig('ice',{candidate:e.candidate});};pc.ontrack=function(e){S.remote=e.streams[0];var rv=$('zcall_remote');if(rv){rv.srcObject=S.remote;var p=rv.play&&rv.play();if(p&&p.catch)p.catch(function(){});}zcallBindRemoteAudio();};pc.onconnectionstatechange=function(){if(pc.connectionState==='failed')end(true,'Mất kết nối','missed');};S.pc=pc;return pc;}
  async function getMedia(){S.local=await navigator.mediaDevices.getUserMedia({audio:true,video:S.media==='video'});S.local.getTracks().forEach(function(t){S.pc.addTrack(t,S.local);});var lv=$('zcall_local');if(lv&&S.media==='video')lv.srcObject=S.local;}
  function drainCand(){S.pendCand.forEach(function(c){try{S.pc.addIceCandidate(c);}catch(e){}});S.pendCand=[];}

  async function startCall(media){if(S.state!=='idle'||G.active)return;S.caller=true;S.media=media;S.callId=genId();S.peer=ctx.peer;S.peerName=ctx.name;S.state='outgoing';S.logRoom=ctx.roomId;S.activeStart=0;S.logged=false;try{await makePc();await getMedia();var offer=await S.pc.createOffer();await S.pc.setLocalDescription(offer);showOutgoing();sig('invite',{sdp:S.pc.localDescription,media:S.media});S.ringT=setTimeout(function(){if(S.state==='outgoing'){sig('cancel');end(false,'Không trả lời','missed');}},45000);}catch(e){alert('Không truy cập được micro/camera: '+e.message);end(false,'',null);}}
  async function accept(){ringStop();clearTimeout(S.ringT);if(bc)bc.postMessage({taken:S.callId});try{await makePc();await S.pc.setRemoteDescription(S.pendOffer);await getMedia();var ans=await S.pc.createAnswer();await S.pc.setLocalDescription(ans);sig('answer',{sdp:S.pc.localDescription});drainCand();S.state='active';showInCall();}catch(e){alert('Không truy cập được micro/camera: '+e.message);sig('reject');end(false,'',null);}}
  function reject(){ringStop();clearTimeout(S.ringT);if(bc)bc.postMessage({taken:S.callId});sig('reject');end(false,'',null);}
  function hangup(){sig(S.state==='outgoing'?'cancel':'hangup');end(false,null,'missed');}
  function end(remote,msg,reason){
    // log (chỉ caller log, 1 lần)
    if(S.caller && S.callId && !S.logged && S.logRoom){
      S.logged=true;
      var dur=S.activeStart?Math.floor((Date.now()-S.activeStart)/1000):0;
      var status=S.activeStart?'completed':(reason||'missed');
      logCall(S.logRoom,S.media,status,dur);
    }
    try{clearTimeout(S.ringT);clearInterval(S.durT);}catch(e){}ringStop();
    try{if(S.local)S.local.getTracks().forEach(function(t){t.stop();});}catch(e){}
    try{if(S.pc){S.pc.onicecandidate=S.pc.ontrack=S.pc.onconnectionstatechange=null;S.pc.close();}}catch(e){}
    var rv=$('zcall_remote'),lv=$('zcall_local');if(rv)rv.srcObject=null;if(lv)lv.srcObject=null;
    S.pc=S.local=S.remote=S.pendOffer=null;S.pendCand=[];S.state='idle';S.callId=null;S.peer=null;S.peerName=null;S.caller=false;S.logRoom=null;S.activeStart=0;
    if(!G.active){var o=$('zcall_overlay');if(o)o.className='';}
  }

  function showGroupUI(){ensureOverlay();$('zcall_overlay').className='show ingroup';$('zcall_grid').innerHTML='';var bar=$('zcall_gbar');bar.innerHTML='';var mute=mkBtn('zcall_mute','','',function(){toggleMute(mute,G.local);});bar.appendChild(mute);if(G.media==='video'){var cam=mkBtn('zcall_mute','','',function(){toggleCam(cam,G.local);});bar.appendChild(cam);}bar.appendChild(mkBtn('zcall_hangup','✕','',leaveGroup));updateGHead();}
  function updateGHead(){var n=Object.keys(G.peers).length+1;var h=$('zcall_ghead');if(h)h.textContent='Cuộc gọi nhóm · '+n+' người';}
  function tileId(id){return 'zcall_tile_'+id;}
  function addGroupTile(id,name,stream,isLocal){ensureOverlay();var grid=$('zcall_grid');if(!grid)return;var ex=$(tileId(id));if(ex)ex.parentNode.removeChild(ex);var t=document.createElement('div');t.className='zcall_tile';t.id=tileId(id);var hasVideo=stream&&stream.getVideoTracks&&stream.getVideoTracks().length>0&&stream.getVideoTracks()[0].enabled;if(G.media==='video'&&hasVideo){var v=document.createElement('video');v.autoplay=true;v.playsInline=true;if(isLocal)v.muted=true;v.srcObject=stream;t.appendChild(v);}else{var av=document.createElement('div');av.className='zcall_tav';avHtml(av,name,isLocal?null:id);t.appendChild(av);}var nm=document.createElement('div');nm.className='zcall_tname';nm.textContent=isLocal?'Bạn':(name||id);t.appendChild(nm);grid.appendChild(t);updateGHead();}
  function removeGroupTile(id){var t=$(tileId(id));if(t)t.parentNode.removeChild(t);}

  function makeGroupPc(pu){if(G.peers[pu]&&G.peers[pu].pc)return G.peers[pu].pc;var pc=new RTCPeerConnection({iceServers:ICE||[]});G.peers[pu]=G.peers[pu]||{};G.peers[pu].pc=pc;pc.onicecandidate=function(e){if(e.candidate)gsig(pu,'ice',{candidate:e.candidate});};pc.ontrack=function(e){G.peers[pu].stream=e.streams[0];addGroupTile(pu,(G.peers[pu]&&G.peers[pu].name)||pu,e.streams[0],false);};pc.onconnectionstatechange=function(){if(pc.connectionState==='failed'||pc.connectionState==='closed')removeGroupPeer(pu);};return pc;}
  function addLocalTracks(pc){if(G.local)G.local.getTracks().forEach(function(t){try{pc.addTrack(t,G.local);}catch(e){}});}
  function drainGroupCand(pu){var arr=G.pend[pu]||[];var pc=G.peers[pu]&&G.peers[pu].pc;arr.forEach(function(c){try{pc.addIceCandidate(c);}catch(e){}});G.pend[pu]=[];}

  async function startGroup(media){
    if(S.state!=='idle'||G.active)return;
    if(!ctx.roomId)return;
    G.active=true;G.media=media;G.roomId=ctx.roomId;G.callId=genId();G.peers={};G.pend={};
    await fetchIce();
    try{G.local=await navigator.mediaDevices.getUserMedia({audio:true,video:media==='video'});}
    catch(e){alert('Không truy cập được micro/camera: '+e.message);G.active=false;return;}
    showGroupUI();addGroupTile('me','Bạn',G.local,true);
    post('/call/group/start',{room_id:G.roomId,call_id:G.callId,media:media}).catch(function(){});
    logCall(G.roomId,media,'group',0);
  }
  async function joinGroup(callId,roomId,media){
    if(S.state!=='idle'||G.active)return;
    G.active=true;G.media=media||'audio';G.roomId=roomId;G.callId=callId;G.peers={};G.pend={};
    await fetchIce();
    try{G.local=await navigator.mediaDevices.getUserMedia({audio:true,video:G.media==='video'});}
    catch(e){alert('Không truy cập được micro/camera: '+e.message);G.active=false;return;}
    showGroupUI();addGroupTile('me','Bạn',G.local,true);
    var res={peers:[]};
    try{res=await post('/call/group/join',{call_id:callId,room_id:roomId}).then(function(r){return r.json();});}catch(e){}
    (res.peers||[]).forEach(function(pu){createGroupOffer(pu);});
  }
  async function createGroupOffer(pu){try{var pc=makeGroupPc(pu);addLocalTracks(pc);var offer=await pc.createOffer();await pc.setLocalDescription(offer);gsig(pu,'offer',{sdp:pc.localDescription});}catch(e){}}
  async function onGroupOffer(c){try{var pu=c.from;var pc=makeGroupPc(pu);G.peers[pu].name=c.from_name||pu;addLocalTracks(pc);await pc.setRemoteDescription(c.sdp);drainGroupCand(pu);var ans=await pc.createAnswer();await pc.setLocalDescription(ans);gsig(pu,'answer',{sdp:pc.localDescription});}catch(e){}}
  function removeGroupPeer(pu){var pr=G.peers[pu];if(pr&&pr.pc){try{pr.pc.onicecandidate=pr.pc.ontrack=pr.pc.onconnectionstatechange=null;pr.pc.close();}catch(e){}}delete G.peers[pu];delete G.pend[pu];removeGroupTile(pu);updateGHead();}
  function leaveGroup(){if(G.callId)post('/call/group/leave',{call_id:G.callId}).catch(function(){});Object.keys(G.peers).forEach(function(pu){var pr=G.peers[pu];if(pr&&pr.pc){try{pr.pc.close();}catch(e){}}});try{if(G.local)G.local.getTracks().forEach(function(t){t.stop();});}catch(e){}G.active=false;G.peers={};G.pend={};G.local=null;G.callId=null;G.roomId=null;var o=$('zcall_overlay');if(o)o.className='';}
  function showGroupIncoming(c){ensureOverlay();if(G.active||S.state!=='idle')return;$('zcall_overlay').className='show';avHtml($('zcall_av'),c.from_name,c.from);$('zcall_nm').textContent=(c.from_name||c.from);$('zcall_st').textContent=(c.media==='video'?'Mời gọi video nhóm':'Mời gọi thoại nhóm');var b=$('zcall_cardbtns');b.innerHTML='';b.appendChild(mkBtn('zcall_reject','✕','Bỏ qua',function(){var o=$('zcall_overlay');if(o&&!G.active)o.className='';ringStop();}));b.appendChild(mkBtn('zcall_accept','✓','Tham gia',function(){ringStop();joinGroup(c.call_id,c.room_id,c.media);}));ringStart();setTimeout(function(){ringStop();},20000);}

  async function onSignal(c){
    if(!c)return;var k=c.kind;
    if(k==='group-invite'){showGroupIncoming(c);return;}
    if(G.active && c.call_id===G.callId){
      if(c.from)G.peers[c.from]=G.peers[c.from]||{}; if(c.from&&c.from_name)G.peers[c.from].name=c.from_name;
      if(k==='peer-join'){return;}
      if(k==='offer'){await onGroupOffer(c);return;}
      if(k==='answer'){var pr=G.peers[c.from];if(pr&&pr.pc){try{await pr.pc.setRemoteDescription(c.sdp);drainGroupCand(c.from);}catch(e){}}return;}
      if(k==='ice'){var pr2=G.peers[c.from];if(c.candidate){if(pr2&&pr2.pc&&pr2.pc.remoteDescription){try{await pr2.pc.addIceCandidate(c.candidate);}catch(e){}}else{(G.pend[c.from]=G.pend[c.from]||[]).push(c.candidate);}}return;}
      if(k==='peer-leave'){removeGroupPeer(c.from);return;}
    }
    if(k==='invite'){if(S.state!=='idle'||G.active){post('/call/signal',{to:c.from,kind:'busy',call_id:c.call_id}).catch(function(){});return;}S.caller=false;S.callId=c.call_id;S.peer=c.from;S.peerName=c.from_name;S.media=c.media||'audio';S.pendOffer=c.sdp;S.state='incoming';showIncoming();return;}
    if(c.call_id&&S.callId&&c.call_id!==S.callId)return;
    if(k==='answer'){if(S.pc&&S.caller){try{await S.pc.setRemoteDescription(c.sdp);drainCand();S.state='active';showInCall();}catch(e){}}}
    else if(k==='ice'){if(c.candidate){if(S.pc&&S.pc.remoteDescription){try{await S.pc.addIceCandidate(c.candidate);}catch(e){}}else{S.pendCand.push(c.candidate);}}}
    else if(k==='reject'){end(true,'Bị từ chối','rejected');}
    else if(k==='busy'){end(true,'Máy bận','missed');}
    else if(k==='cancel'){ringStop();clearTimeout(S.ringT);end(true,'Đã huỷ','missed');}
    else if(k==='hangup'){end(true,'Kết thúc','missed');}
  }
  if(bc)bc.onmessage=function(e){if(e.data&&e.data.taken&&e.data.taken===S.callId&&S.state==='incoming'){ringStop();clearTimeout(S.ringT);end(false,'',null);}};

  function setContext(o){
    o=o||{};ctx.roomId=o.roomId;ctx.type=o.type;ctx.isDirect=!!o.isDirect;ctx.peer=o.peer;ctx.name=o.name;ctx.memberCount=o.memberCount||0;
    ctx.canGroup=(!o.isDirect)&&(o.type==='group'||o.type==='department')&&o.memberCount>0&&o.memberCount<=5;
    var show=o.isDirect||ctx.canGroup;
    var av=$('zV2_btn_call'),vd=$('zV2_btn_video');
    if(av)av.style.display=show?'':'none';
    if(vd)vd.style.display=show?'':'none';
  }
  function start(media){if(ctx.isDirect){if(!ctx.peer)return;startCall(media);}else if(ctx.canGroup){startGroup(media);}else{alert('Chỉ gọi được trong trò chuyện 1-1 hoặc nhóm ≤5 người.');}}

  // ===== Nhận cuộc gọi từ THÔNG BÁO (pending call) =====
  function _incomingFromPending(c){
    if(!c || S.state!=='idle' || G.active) return;
    S.caller=false;S.callId=c.call_id;S.peer=c.from;S.peerName=c.from_name;S.media=c.media||'audio';S.pendOffer=c.sdp;S.state='incoming';
    showIncoming();
  }
  async function checkPending(){
    if(S.state!=='idle'||G.active) return;
    try{var j=await (await fetch(api('/call/pending'),{credentials:'include'})).json();if(j&&j.call)_incomingFromPending(j.call);}catch(e){}
  }
  try{ if(navigator.serviceWorker) navigator.serviceWorker.addEventListener('message',function(e){ if(e.data&&(e.data.type==='zcall-accept'||e.data.type==='zcall-open')) checkPending(); }); }catch(e){}
  // mở app (kể cả từ thông báo ?zcall_accept) mà có cuộc gọi đang reo → hiện ngay
  setTimeout(checkPending, 1200);

  window.zCall={_onSignal:onSignal,_setContext:setContext,startAudio:function(){start('audio');},startVideo:function(){start('video');}};
})();