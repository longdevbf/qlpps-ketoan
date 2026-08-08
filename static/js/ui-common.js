/* ui-common.js — helper dùng chung cho MỌI trang.
 *
 * Nạp 1 lần trong `templates/_header.html` (partial này được 25/28 template
 * include) nên mọi trang đều có sẵn, không cần khai báo lại.
 *
 * Trước đây mỗi template tự viết lại các hàm này: `esc` 9 bản (4 biến thể),
 * `escHtml` 3 bản, `initials` 3 bản. Gom về đây để sửa 1 chỗ ăn cả hệ thống.
 *
 * Thêm helper mới vào đây khi nó được dùng từ 2 trang trở lên. Hàm chỉ 1
 * trang dùng thì để nguyên trong trang đó.
 */
(function (w) {
  'use strict';

  var ESC_MAP = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  };

  /**
   * Escape chuỗi trước khi nhét vào HTML.
   *
   * Escape đủ cả 5 ký tự — QUAN TRỌNG: nhiều chỗ dùng trong ngữ cảnh
   * thuộc tính (`title="${esc(x)}"`, `value="${esc(x)}"`). Vài bản cũ chỉ
   * escape `& < >`, giá trị chứa dấu nháy sẽ thoát ra khỏi thuộc tính.
   *
   * null/undefined → chuỗi rỗng.
   */
  function esc(s) {
    return (s === null || s === undefined ? '' : String(s))
      .replace(/[&<>"']/g, function (c) { return ESC_MAP[c]; });
  }

  /**
   * Viết tắt tên người: "Nguyễn Văn An" → "NA". Dùng cho avatar chữ.
   * Lấy chữ cái đầu của mỗi từ, tối đa 2 ký tự.
   */
  function initials(name) {
    return (name || '?')
      .trim()
      .split(/\s+/)
      .map(function (word) { return word[0]; })
      .join('')
      .toUpperCase()
      .slice(0, 2);
  }

  /* ───────────────────────────────────────────────────────────────────────
   * FORMAT TIỀN / SỐ / NGÀY — một chuẩn duy nhất cho cả app.
   *
   * Trước đây mỗi trang tự khai: `fmtMoney` 4 bản, `fmtVnd` 3 bản, `fmt` 1 bản,
   * `fmtDate` 8 bản — và đơn vị trộn `₫` (3 file) với `đ` (5 file).
   * Chuẩn chốt theo `.claude/rules/frontend-ui.md` luật 6: **`1.250.000 đ`**.
   *
   * Trang nào còn khai hàm cùng tên trong <script> của nó thì bản local vẫn
   * thắng (ui-common.js nạp trước) — không gãy gì. Dọn dần từng trang.
   * ─────────────────────────────────────────────────────────────────────── */

  var NF_VN = new Intl.NumberFormat('vi-VN');

  /** Rỗng thật sự? null/undefined/'' → hiện gạch ngang, KHÔNG hiện "0 đ". */
  function _trong(n) {
    return n === null || n === undefined || n === '';
  }

  /**
   * Tiền đầy đủ, dùng cho BẢNG CHI TIẾT: 1250000 → "1.250.000 đ".
   * Làm tròn về đồng — hệ không hiển thị hào.
   */
  function fmtVnd(n) {
    if (_trong(n)) return '—';
    return NF_VN.format(Math.round(Number(n) || 0)) + ' đ';
  }

  /* Tối đa 2 chữ số thập phân, tự bỏ số 0 thừa: 1,25 / 2,1 / 3 (không "3,00"). */
  var NF_VN_2 = new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 });

  /**
   * Tiền rút gọn, dùng cho KPI CARD: 1250000 → "1,25 tr", 2.1e9 → "2,1 tỷ".
   *
   * Hai điểm khác bản cũ `index.html:3255` (`toFixed(1)`), đều có lý do:
   *  - Dấu thập phân là DẤU PHẨY — `toFixed` luôn ra dấu chấm kiểu Anh.
   *  - 2 chữ số thay vì 1: `toFixed(1)` biến 1.250.000 thành "1,3 tr", tức
   *    làm tròn tới 100k. App kế toán không nên mất độ phân giải đó trên KPI.
   *    Chuẩn `1,25 tr` là ví dụ ghi thẳng trong `frontend-ui.md` luật 6.
   *
   * Dưới 1 triệu thì rút gọn không còn nghĩa → trả về dạng đầy đủ.
   */
  function fmtShort(n) {
    if (_trong(n)) return '—';
    var v = Math.round(Number(n) || 0);
    var abs = Math.abs(v);
    if (abs >= 1e9) return NF_VN_2.format(v / 1e9) + ' tỷ';
    if (abs >= 1e6) return NF_VN_2.format(v / 1e6) + ' tr';
    return fmtVnd(v);
  }

  /**
   * Số ĐẾM — luôn kèm đơn vị chữ để không bị đọc nhầm thành tiền
   * (luật 6): fmtSo(2520, 'data') → "2.520 data".
   */
  function fmtSo(n, donVi) {
    if (_trong(n)) return '—';
    var s = NF_VN.format(Number(n) || 0);
    return donVi ? s + ' ' + donVi : s;
  }

  /** "2026-08-08T10:30:00" → "08/08/2026". Cắt chuỗi, không qua Date: */
  /*  new Date('2026-08-08') hiểu là UTC nên ở GMT+7 vẫn ra đúng ngày,
      nhưng '2026-08-08T23:30' thì lệch sang hôm sau — cắt chuỗi thì không. */
  function fmtDate(s) {
    if (!s) return '—';
    return String(s).slice(0, 10).split('-').reverse().join('/');
  }

  /** "2026-08-08T10:30:00" → "08/08/2026 10:30". */
  function fmtDateTime(s) {
    if (!s) return '—';
    var str = String(s);
    var gio = str.slice(11, 16);
    return fmtDate(str) + (gio ? ' ' + gio : '');
  }

  /**
   * Toast — thông báo góc dưới phải.
   *
   * CSS đã có sẵn trong `components.css` (`.toast-wrap`, `.toast`,
   * `.toast-success|error|warning|info`) nhưng chưa có JS nào dùng; mỗi trang
   * tự `alert()` hoặc tự cài lại. Đây là bản dùng chung.
   *
   * `loai`: 'success' (mặc định) | 'error' | 'warning' | 'info'.
   * Lỗi để lâu hơn vì người dùng cần đọc bước tiếp theo (frontend-ui luật 7).
   */
  function toast(msg, loai) {
    loai = loai || 'success';
    var wrap = document.querySelector('.toast-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'toast-wrap';
      document.body.appendChild(wrap);
    }
    var el = document.createElement('div');
    el.className = 'toast toast-' + loai;
    el.setAttribute('role', loai === 'error' ? 'alert' : 'status');
    el.textContent = msg;          // textContent: không cần esc, không dựng HTML
    wrap.appendChild(el);

    // Chờ 1 frame rồi mới thêm .show — gắn cùng lúc thì trình duyệt gộp 2
    // trạng thái vào một lần vẽ và transition không chạy.
    requestAnimationFrame(function () { el.classList.add('show'); });

    setTimeout(function () {
      el.classList.remove('show');
      setTimeout(function () { el.remove(); }, 250);   // khớp transition .2s
    }, loai === 'error' ? 6000 : 3000);
  }

  /**
   * Đổi lỗi kỹ thuật thành CÂU NGƯỜI ĐỌC ĐƯỢC.
   *
   * Nhiều chỗ đang làm `innerHTML = esc(e.message)` mà `e.message` lại là
   * nguyên chuỗi JSON của server — người dùng nhìn thấy
   * `{"error":"Not Found","code":404}` giữa màn hình (báo 08/08/2026).
   *
   * Trả về {tieu_de, goi_y} để chỗ gọi dựng đúng trạng thái error của
   * frontend-ui luật 5: lỗi gì + làm gì tiếp.
   */
  function loiNguoiDoc(e) {
    var t = (e && e.message ? String(e.message) : '') || '';
    var ma = 0;
    try {
      var j = JSON.parse(t);
      ma = +j.code || 0;
      if (j.detail && typeof j.detail === 'string' && !/^\{/.test(j.detail)) t = j.detail;
    } catch (x) {
      var m = t.match(/(400|401|403|404|409|422|500|502|503)/);
      if (m) ma = +m[1];
    }
    var B = {
      401: ['Phiên đăng nhập đã hết hạn', 'Đăng nhập lại rồi thử lần nữa.'],
      403: ['Bạn không có quyền xem mục này', 'Liên hệ quản trị nếu cần được cấp quyền.'],
      404: ['Chưa có dữ liệu cho tài khoản này', 'Hồ sơ có thể chưa được HCNS tạo. Liên hệ HCNS để bổ sung.'],
      409: ['Dữ liệu vừa bị người khác thay đổi', 'Tải lại trang rồi thao tác lại.'],
      422: ['Dữ liệu nhập chưa hợp lệ', 'Kiểm tra lại các ô bắt buộc.'],
      500: ['Máy chủ gặp sự cố', 'Thử lại sau ít phút; nếu vẫn lỗi báo IT kèm mã 500.'],
    };
    if (B[ma]) return { tieu_de: B[ma][0], goi_y: B[ma][1] };
    if (/failed to fetch|networkerror|load failed/i.test(t))
      return { tieu_de: 'Mất kết nối tới máy chủ', goi_y: 'Kiểm tra mạng rồi thử lại.' };
    return { tieu_de: 'Không tải được dữ liệu',
             goi_y: 'Thử lại sau ít phút; nếu vẫn lỗi báo IT.' };
  }

  /** Dựng sẵn khối error đủ chuẩn: lỗi gì + làm gì tiếp + nút thử lại. */
  function khoiLoi(e, tenHamThuLai) {
    var L = loiNguoiDoc(e);
    return '<div class="empty-state">'
      + '<div style="font-weight:600;color:var(--danger-fg);margin-bottom:6px">'
      + esc(L.tieu_de) + '</div>'
      + '<div style="margin-bottom:14px;color:var(--text-2)">' + esc(L.goi_y) + '</div>'
      + (tenHamThuLai
          ? '<button type="button" class="btn btn-outline btn-sm" onclick="' + tenHamThuLai + '()">Thử lại</button>'
          : '')
      + '</div>';
  }

  w.esc = esc;
  w.escHtml = esc;   // alias — vài trang gọi tên này
  w.initials = initials;
  w.toast = toast;
  w.loiNguoiDoc = loiNguoiDoc;
  w.khoiLoi = khoiLoi;

  w.fmtVnd = fmtVnd;
  w.fmtShort = fmtShort;
  w.fmtSo = fmtSo;
  w.fmtDate = fmtDate;
  w.fmtDateTime = fmtDateTime;
})(window);
