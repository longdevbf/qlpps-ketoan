/* kd-man-hinh.js — helper dùng chung cho các màn giao diện mới /kd/*.
 *
 * Không khai lại esc/escHtml/initials (đã có toàn cục ở ui-common.js, nạp qua _header.html).
 * showToast(type, msg) có ở toast.js, papConfirm(msg, opts) ở confirm.js — base.html nạp cả hai.
 * Mọi hàm gắn vào một đối tượng duy nhất window.KD để không làm bẩn phạm vi toàn cục.
 */
(function () {
  'use strict';

  // Bảng trạng thái báo giá. KHOÁ phải khớp app/services/kd_bao_gia.py (_TRANG_THAI)
  // và app/schemas/kd.py (TrangThaiBaoGia).
  // Màu: gốc theo CLAUDE.md (chờ = warning, từ chối = danger, đã duyệt = success, hết hạn = muted),
  // nhưng người dùng yêu cầu 11/09/2026 MỖI trạng thái một màu nhìn phân biệt được. Hai trạng thái
  // cùng họ được tách bằng họ khác gần nghĩa: "Chờ KT xác nhận" (đã qua quản lý, đang đi tiếp) →
  // chip xanh thương hiệu; "KT từ chối" → đỏ có viền để khác "Từ chối". Không dùng tím: tím chỉ
  // được làm nền ô icon (design-system.md, 03-mau-sac.md §2.4 quyết định 2).
  const TRANG_THAI = {
    nhap:       { nhan: 'Nháp',            lop: 'pill--info' },
    cho_duyet:  { nhan: 'Chờ duyệt',       lop: 'pill--warning' },
    cho_kt:     { nhan: 'Chờ KT xác nhận', lop: 'pill--brand' },
    tu_choi:    { nhan: 'Từ chối',         lop: 'pill--danger' },
    kt_tu_choi: { nhan: 'KT từ chối',      lop: 'pill--danger pill--vien' },
    het_han:    { nhan: 'Hết hạn',         lop: 'pill--muted' },
    da_len_don: { nhan: 'Đã lên đơn',      lop: 'pill--success' },
  };

  function pill(key) {
    const t = TRANG_THAI[key];
    if (!t) {
      // Luật frontend-ui số 2: không lộ key thô ra màn hình.
      console.warn('[KD] Trạng thái chưa có nhãn:', key);
      return '<span class="pill pill--muted">Chưa đặt tên</span>';
    }
    return '<span class="pill ' + t.lop + '">' + esc(t.nhan) + '</span>';
  }

  // Tiến trình đơn hàng. KHOÁ khớp app/services/kd_don_hang.py (TIEN_TRINH). Nhãn là NHÃN GỐC do server
  // trả (quyết định người dùng 11/09) — ở đây chỉ gán màu theo giai đoạn: chờ nhận (xám) → xưởng (vàng)
  // → có hàng / chờ giao (xanh) → đang giao (lục viền) → hoàn thành (lục) → hoàn / hủy (đỏ).
  // Hai nhãn liền kề cùng họ tách bằng viền đậm.
  const MAU_TIEN_TRINH = {
    moi: 'pill--info', cho_xac_nhan: 'pill--info pill--vien', cho_duyet: 'pill--info pill--vien',
    da_duyet_mua: 'pill--warning pill--vien', dat_hang: 'pill--warning', dang_sx: 'pill--warning pill--vien',
    da_co_hang: 'pill--brand', cho_lay_hang: 'pill--brand pill--vien', da_hen_giao: 'pill--brand pill--vien',
    da_lay_hang: 'pill--success pill--vien', dang_giao: 'pill--success pill--vien', da_giao: 'pill--success pill--vien',
    hoan_thanh: 'pill--success', hoan: 'pill--danger', da_huy: 'pill--danger pill--vien', khac: 'pill--muted',
  };
  function pillTienTrinh(key, nhan) {
    const lop = MAU_TIEN_TRINH[key];
    if (!lop) console.warn('[KD] Tiến trình đơn chưa có màu:', key);
    return '<span class="pill ' + (lop || 'pill--muted') + '">' + esc(nhan || 'Chưa đặt tên') + '</span>';
  }

  // Nhãn thanh toán — khoá khớp kd_don_hang.nhan_thanh_toan. null = không đủ dữ liệu → không vẽ gì.
  const THANH_TOAN = {
    chua_tt:   { nhan: 'Chưa thanh toán', lop: 'pill--danger' },
    da_coc:    { nhan: 'Đã cọc',          lop: 'pill--brand' },
    da_tt:     { nhan: 'Đã thanh toán',   lop: 'pill--success' },
    hoan_tien: { nhan: 'Đã hoàn tiền',    lop: 'pill--muted' },
  };
  function pillThanhToan(tt) {
    if (!tt) return '';
    const t = THANH_TOAN[tt.trang_thai];
    if (!t) {
      console.warn('[KD] Trạng thái thanh toán chưa có nhãn:', tt.trang_thai);
      return '';
    }
    const chu = t.nhan + (tt.trang_thai === 'da_coc' && tt.pct != null ? ' ' + tt.pct + '%' : '');
    return '<span class="pill ' + t.lop + '">' + esc(chu) + '</span>';
  }

  // Chặng phễu khách hàng — khoá khớp app/services/kd_khach_hang.py (CHANG). Cùng họ màu với khối phễu (CSS .kd-stage--*).
  const CHANG = {
    khach_moi:   { nhan: 'Khách mới',   lop: 'pill--brand' },
    da_lien_he:  { nhan: 'Đã liên hệ',  lop: 'pill--info' },
    dang_tu_van: { nhan: 'Đang tư vấn', lop: 'pill--warning' },
    chot_don:    { nhan: 'Chốt đơn',    lop: 'pill--success' },
    that_bai:    { nhan: 'Thất bại',    lop: 'pill--danger' },
    khac:        { nhan: 'Chưa gán chặng', lop: 'pill--muted' },
  };
  // Tiến trình thật hiện theo màu chặng của nó.
  function pillTienTrinhKhach(chang, tienTrinh) {
    const c = CHANG[chang] || CHANG.khac;
    return '<span class="pill ' + c.lop + '">' + esc(tienTrinh || c.nhan) + '</span>';
  }
  // Cột "Trạng thái" khách suy từ chặng (quyết định người dùng 11/09) — MỘT hàm, dùng cho bảng và trang chi tiết.
  function trangThaiKhach(chang) {
    if (chang === 'chot_don') return '<span class="pill pill--brand">Đã có đơn</span>';
    if (chang === 'that_bai') return '<span class="pill pill--muted">Không tiềm năng</span>';
    return '<span class="pill pill--success">Đang hoạt động</span>';
  }

  // API trả tiền kiểu Decimal dạng chuỗi ("18500000.00") → luôn qua Number trước khi định dạng.
  function so(v) {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  const dinhDang = (x, toiDa) => new Intl.NumberFormat('vi-VN', { maximumFractionDigits: toiDa }).format(x);

  // Tiền trong BẢNG — số đầy đủ, không ký hiệu (đơn vị ghi ở tiêu đề cột "(VND)"), theo ảnh mockup.
  function tien(v) { const n = so(v); return n === null ? '—' : dinhDang(Math.round(n), 0); }
  // Tiền đứng riêng (khối tổng, thẻ thông tin) — số đầy đủ kèm "VND" như ảnh.
  function tienVnd(v) { const n = so(v); return n === null ? '—' : dinhDang(Math.round(n), 0) + ' VND'; }
  // Tiền trong THẺ KPI — gọn theo ảnh: "8,42 tỷ VND" · "980 triệu" · "850.000 VND".
  // Bản tách trả số và đơn vị riêng: thẻ ở khổ 1280px hẹp hơn ảnh, "350,6 triệu" cỡ 29px
  // không vừa, nên số giữ cỡ to còn đơn vị viết nhỏ bên cạnh thay vì bị cắt "350,6 t…".
  function tienGonTach(v) {
    const n = so(v);
    if (n === null) return { so: '—', donVi: '' };
    const a = Math.abs(n);
    if (a >= 1e9) return { so: dinhDang(n / 1e9, 2), donVi: 'tỷ VND' };
    if (a >= 1e6) return { so: dinhDang(n / 1e6, 1), donVi: 'triệu' };
    return { so: dinhDang(Math.round(n), 0), donVi: 'VND' };
  }
  function tienGon(v) {
    const t = tienGonTach(v);
    return t.donVi ? t.so + ' ' + t.donVi : t.so;
  }
  function tienGonHtml(v) {
    const t = tienGonTach(v);
    return '<span>' + esc(t.so) + '</span>' + (t.donVi ? '<span class="kd-kpi__don-vi">' + esc(t.donVi) + '</span>' : '');
  }
  function soDem(v) { const n = so(v); return n === null ? '—' : dinhDang(n, 0); }
  function phanTram(v) { const n = so(v); return n === null ? '—' : dinhDang(n, 1) + '%'; }
  function dungLuong(b) {
    const n = so(b);
    if (n === null) return '';
    if (n < 1024) return dinhDang(n, 0) + ' B';
    if (n < 1024 * 1024) return dinhDang(n / 1024, 0) + ' KB';
    return dinhDang(n / 1024 / 1024, 1) + ' MB';
  }

  const p2 = (x) => String(x).padStart(2, '0');
  // Ngày giờ in ra = ĐÚNG chữ số server trả, bỏ phần múi giờ phía sau — y như app cũ (customers.html:971-976 fmtDateTime).
  // Server lọc "ngày" theo múi giờ phiên DB, nên cách này giữ ngày in ra luôn khớp ngày dùng để lọc.
  function thoiDiem(s) {
    if (!s) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(String(s));
    if (!m) return null;
    const d = new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
    return isNaN(d) ? null : d;
  }
  function ngay(s) { const d = thoiDiem(s); return d ? p2(d.getDate()) + '/' + p2(d.getMonth() + 1) + '/' + d.getFullYear() : '—'; }
  function gio(s) { const d = thoiDiem(s); return d ? p2(d.getHours()) + ':' + p2(d.getMinutes()) : ''; }
  // Mốc đúng 00:00:00 giờ máy là dữ liệu CHỈ CÓ NGÀY (DB dev 11/09/2026: 27.983/31.499 last_contact_at của khách)
  // → in "00:00" là bịa giờ, nên chỉ in ngày.
  const chiCoNgay = (d) => !d.getHours() && !d.getMinutes() && !d.getSeconds() && !d.getMilliseconds();
  function ngayGio(s) { const d = thoiDiem(s); return d ? ngay(s) + (chiCoNgay(d) ? '' : ' ' + gio(s)) : '—'; }
  function ngayNgan(s) { const d = thoiDiem(s); return d ? p2(d.getDate()) + '/' + p2(d.getMonth() + 1) : ''; }
  function iso(d) { return d.getFullYear() + '-' + p2(d.getMonth() + 1) + '-' + p2(d.getDate()); }
  // "Hôm nay 09:30" · "Hôm qua 16:20" · "12/09/2026 09:20" — cột "Lần tương tác cuối" của ảnh.
  function tuongDoi(s) {
    const d = thoiDiem(s);
    if (!d) return '—';
    const homNay = new Date();
    homNay.setHours(0, 0, 0, 0);
    const ngayD = new Date(d);
    ngayD.setHours(0, 0, 0, 0);
    const lech = Math.round((homNay - ngayD) / 86400000);
    const kem = chiCoNgay(d) ? '' : ' ' + gio(s);
    if (lech === 0) return 'Hôm nay' + kem;
    if (lech === 1) return 'Hôm qua' + kem;
    return ngayGio(s);
  }

  // Số ngày còn lại tới một ngày (âm = đã qua). Chỉ để hiển thị "còn N ngày"; hạn thì server tính.
  function conNgay(s) {
    const d = thoiDiem(s);
    if (!d) return null;
    const homNay = new Date();
    homNay.setHours(0, 0, 0, 0);
    return Math.round((d - homNay) / 86400000);
  }

  // Khoảng thời gian cho thẻ KPI. Kỳ để so sánh do server tự lùi cùng độ dài.
  const KY = [
    ['tat_ca', 'Tất cả thời gian'], ['hom_nay', 'Hôm nay'], ['7_ngay', '7 ngày qua'],
    ['30_ngay', '30 ngày qua'], ['thang_nay', 'Tháng này'], ['thang_truoc', 'Tháng trước'], ['nam_nay', 'Năm nay'],
  ];
  // Kỳ ĐỦ cho màn danh sách Báo giá / Đơn hàng (17/09/2026): một ô kỳ trên đầu trang lọc CẢ thẻ số lẫn bảng — gộp KY
  // (thẻ) với ô "Ngày tạo"/"Khoảng ngày" riêng của khung lọc trước đây (thêm Hôm qua, Năm trước, Tuỳ chỉnh…).
  // 'tuy_chinh' không có khoảng sẵn: hai ô từ–đến trong khung lọc quyết định.
  const KY_DU = [
    ['tat_ca', 'Tất cả thời gian'], ['hom_nay', 'Hôm nay'], ['hom_qua', 'Hôm qua'], ['7_ngay', '7 ngày qua'],
    ['30_ngay', '30 ngày qua'], ['thang_nay', 'Tháng này'], ['thang_truoc', 'Tháng trước'],
    ['nam_nay', 'Năm nay'], ['nam_truoc', 'Năm trước'], ['tuy_chinh', 'Tuỳ chỉnh…'],
  ];
  function khoangKy(key) {
    const nay = new Date();
    nay.setHours(0, 0, 0, 0);
    const y = nay.getFullYear(), m = nay.getMonth();
    const lui = (n) => { const t = new Date(nay); t.setDate(t.getDate() - n); return t; };
    switch (key) {
      case 'hom_nay': return [nay, nay];
      case 'hom_qua': return [lui(1), lui(1)];
      case '7_ngay': return [lui(6), nay];
      case '30_ngay': return [lui(29), nay];
      case 'thang_nay': return [new Date(y, m, 1), nay];
      case 'thang_truoc': return [new Date(y, m - 1, 1), new Date(y, m, 0)];
      case 'nam_nay': return [new Date(y, 0, 1), nay];
      case 'nam_truoc': return [new Date(y - 1, 0, 1), new Date(y - 1, 11, 31)];
      default: return [null, null];          // 'tat_ca', 'tuy_chinh', khoá lạ → không có khoảng sẵn
    }
  }
  // Chuỗi ?tu=&den= cho API từ st.tu/st.den (ngày ISO hoặc rỗng) — dùng chung cho thẻ số và bảng để hai bên cùng khoảng.
  function khoangQs(st) {
    const p = new URLSearchParams();
    if (st.tu) p.set('tu', st.tu);
    if (st.den) p.set('den', st.den);
    const s = p.toString();
    return s ? '?' + s : '';
  }
  // Khung lọc mở sẵn trên máy tính, gập sẵn dưới 768px (người dùng 17/09/2026; trước đó gập sẵn mọi cỡ, quyết định 15/09).
  const MAN_RONG = () => window.matchMedia('(min-width: 768px)').matches;

  // fetch JSON + thông báo lỗi đọc được (luật frontend-ui số 7: chuyện gì sai + làm gì tiếp).
  // Handler chung (shared/middleware/errors.py) trả lỗi kiểm kiểu của FastAPI là {"error":"validation_failed","details":[…]},
  // KHÔNG có "detail" → không in khoá kỹ thuật đó ra (luật frontend-ui số 2). Với GET, lỗi này gần như luôn do tham số lọc
  // đọc lại từ đường dẫn (vd ?tu=11/09/2026 — ô ngày trên màn chỉ gửi yyyy-mm-dd) nên đường sửa là Đặt lại bộ lọc.
  async function api(url, opts) {
    let r;
    try {
      r = await fetch(url, Object.assign({ headers: { Accept: 'application/json' } }, opts || {}));
    } catch (e) {
      throw new Error('Không kết nối được máy chủ. Kiểm tra mạng rồi bấm Thử lại.');
    }
    if (r.status === 204) return null;
    const d = await r.json().catch(() => null);
    if (!r.ok) {
      let msg = d && d.detail;
      if (!msg && d && d.error) {
        if (d.error === 'validation_failed') {
          const laGet = !(opts && opts.method) || String(opts.method).toUpperCase() === 'GET';
          msg = laGet ? 'Bộ lọc trên đường dẫn không hợp lệ — bấm Đặt lại bộ lọc.'
            : 'Dữ liệu gửi lên có ô sai định dạng — kiểm tra lại các ô vừa nhập.';
        } else if (/^[a-z_]+$/.test(d.error)) {
          // Mã như internal_error / database_error: không có câu cho người dùng → rơi về câu chung theo mã HTTP bên dưới.
          console.warn('[KD] Mã lỗi máy chủ không kèm câu giải thích:', d.error);
        } else {
          msg = d.error;
        }
      }
      if (Array.isArray(msg)) msg = msg.map((x) => x.msg).join('; ');
      if (r.status === 401) msg = 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.';
      throw new Error(msg || ('Máy chủ trả lỗi ' + r.status + '. Thử lại sau ít phút.'));
    }
    return d;
  }
  const JSON_POST = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body || {}) });

  // Thanh phân trang: ‹ 1 2 3 … 32 ›
  // Dưới 480px mỗi nút ≥ 44px (vùng bấm, kd-man-hinh.css) nên dãy đủ ‹ 1 2 3 4 5 … N › rớt 2 hàng ở 375px (GD-3, đo 11/09)
  // → màn hẹp chỉ vẽ {1, trang hiện tại, trang cuối}. Đổi khổ qua mốc 480px (xoay máy) thì vẽ lại theo tập của khổ mới.
  const KHO_RONG = window.matchMedia('(min-width: 480px)');
  const thanhDaVe = new Set();
  KHO_RONG.addEventListener('change', () => thanhDaVe.forEach((el) => {
    if (document.contains(el)) phanTrang(el, ...el._kdTrang);
    else thanhDaVe.delete(el);
  }));
  function phanTrang(el, trang, soTrang, diToi) {
    el._kdTrang = [trang, soTrang, diToi];
    thanhDaVe.add(el);
    el.textContent = '';
    if (soTrang <= 1) return;
    const nut = (html, p, o) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.innerHTML = html;
      if (o.aria) b.setAttribute('aria-label', o.aria);
      if (o.hienTai) b.setAttribute('aria-current', 'page');
      if (o.tat) b.disabled = true;
      else b.addEventListener('click', () => diToi(p));
      el.appendChild(b);
    };
    nut('<i class="bi bi-chevron-left" aria-hidden="true"></i>', trang - 1, { aria: 'Trang trước', tat: trang <= 1 });
    const tap = new Set([1, trang, soTrang]);
    if (KHO_RONG.matches) {
      [trang - 1, trang + 1].forEach((x) => tap.add(x));
      if (trang <= 3) [2, 3, 4, 5].forEach((x) => tap.add(x));
      if (trang >= soTrang - 2) [soTrang - 1, soTrang - 2, soTrang - 3, soTrang - 4].forEach((x) => tap.add(x));
    }
    let truoc = 0;
    [...tap].filter((x) => x >= 1 && x <= soTrang).sort((a, b) => a - b).forEach((p) => {
      if (p - truoc > 1) {
        const s = document.createElement('span');
        s.className = 'kd-pager__gap';
        s.textContent = '…';
        el.appendChild(s);
      }
      nut(String(p), p, { aria: 'Trang ' + p, hienTai: p === trang });
      truoc = p;
    });
    nut('<i class="bi bi-chevron-right" aria-hidden="true"></i>', trang + 1, { aria: 'Trang sau', tat: trang >= soTrang });
  }

  // Menu thao tác mở từ nút ⋯. items: [{nhan, icon, href?, target?, onClick?, danger?}] hoặc '-'.
  let menuMo = null;
  function dongMenu() {
    if (!menuMo) return;
    menuMo._neo.setAttribute('aria-expanded', 'false');
    menuMo.remove();
    menuMo = null;
    document.removeEventListener('click', clickNgoai, true);
    document.removeEventListener('keydown', phimMenu, true);
    window.removeEventListener('scroll', dongMenu, true);
  }
  function clickNgoai(e) {
    if (menuMo && !menuMo.contains(e.target) && !menuMo._neo.contains(e.target)) dongMenu();
  }
  function phimMenu(e) {
    if (!menuMo) return;
    const muc = [...menuMo.querySelectorAll('[role="menuitem"]')];
    const i = muc.indexOf(document.activeElement);
    if (e.key === 'Escape') {
      // preventDefault để handler Escape của trang (đóng panel) biết phím đã được dùng.
      e.preventDefault();
      const neo = menuMo._neo;
      dongMenu();
      neo.focus();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      (muc[i + 1] || muc[0]).focus();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      (muc[i - 1] || muc[muc.length - 1]).focus();
    } else if (e.key === 'Tab') {
      dongMenu();
    }
  }
  function menu(neo, items) {
    const dangMoChinhNo = menuMo && menuMo._neo === neo;
    dongMenu();
    if (dangMoChinhNo) return;   // bấm lại nút đang mở = đóng
    const m = document.createElement('div');
    m.className = 'kd-menu';
    m.setAttribute('role', 'menu');
    // Menu cần tên cho trình đọc màn hình — lấy từ nút mở (ui-reviewer 11/09).
    m.setAttribute('aria-label', (neo.getAttribute('aria-label') || neo.textContent || '').trim() || 'Thao tác');
    m._neo = neo;
    items.forEach((it) => {
      if (it === '-') { m.appendChild(document.createElement('hr')); return; }
      const b = document.createElement(it.href ? 'a' : 'button');
      if (it.href) {
        b.href = it.href;
        if (it.target) { b.target = it.target; b.rel = 'noopener'; }
      } else {
        b.type = 'button';
      }
      b.setAttribute('role', 'menuitem');
      if (it.danger) b.classList.add('is-danger');
      b.innerHTML = '<i class="bi ' + it.icon + '" aria-hidden="true"></i>';
      const chu = document.createElement('span');
      chu.textContent = it.nhan;
      b.appendChild(chu);
      b.addEventListener('click', (e) => {
        dongMenu();
        if (it.onClick) { e.preventDefault(); it.onClick(); }
      });
      m.appendChild(b);
    });
    // Menu thả trong <dialog> đang mở thì phải nằm trong dialog, không thì bị lớp top-layer che.
    (neo.closest('dialog[open]') || document.body).appendChild(m);
    const r = neo.getBoundingClientRect();
    const rong = m.offsetWidth, cao = m.offsetHeight;
    const trai = Math.max(8, Math.min(r.right - rong, window.innerWidth - rong - 8));
    let tren = r.bottom + 4;
    if (tren + cao > window.innerHeight - 8) tren = Math.max(8, r.top - cao - 4);
    m.style.left = trai + 'px';
    m.style.top = tren + 'px';
    menuMo = m;
    neo.setAttribute('aria-expanded', 'true');
    // Gắn listener ở vòng sự kiện sau, để chính cú click vừa mở menu không đóng nó ngay.
    setTimeout(() => {
      if (menuMo !== m) return;
      document.addEventListener('click', clickNgoai, true);
      document.addEventListener('keydown', phimMenu, true);
      window.addEventListener('scroll', dongMenu, true);
    }, 0);
    const dau = m.querySelector('[role="menuitem"]');
    if (dau) dau.focus({ preventScroll: true });
  }

  function debounce(fn, ms) {
    let t;
    return function () {
      const a = arguments;
      clearTimeout(t);
      t = setTimeout(() => fn.apply(null, a), ms);
    };
  }

  // Avatar: ảnh nếu có, lỗi / không có ảnh thì chữ viết tắt (initials toàn cục của ui-common.js).
  function avatar(ten, url, lop) {
    const cls = 'kd-avatar' + (lop ? ' ' + lop : '');
    const chu = esc(initials(ten || '?'));
    if (url) {
      return '<span class="' + cls + '" data-chu="' + chu + '"><img src="' + esc(url) + '" alt="" loading="lazy" data-kd-avatar></span>';
    }
    return '<span class="' + cls + '" aria-hidden="true">' + chu + '</span>';
  }
  // Ảnh hỏng (404, link Facebook hết hạn, tệp đã mất trên máy chủ). Sự kiện error không nổi bọt nên bắt ở pha capture.
  // Avatar → chữ viết tắt. Ảnh sản phẩm / thư viện ảnh / ảnh bình luận → ô "Không mở được ảnh" thay biểu tượng ảnh vỡ,
  // một kiểu chung cho mọi trang chi tiết.
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (!(img instanceof HTMLImageElement)) return;
    if (img.hasAttribute('data-kd-avatar')) {
      const wrap = img.parentElement;
      wrap.textContent = wrap.dataset.chu || '?';
      wrap.setAttribute('aria-hidden', 'true');   // chữ viết tắt chỉ trang trí — tên người đã có chữ bên cạnh
      return;
    }
    const lop = img.classList.contains('kd-thumb') ? 'kd-thumb kd-anh-hong'
      : img.classList.contains('kd-comment__anh') ? 'kd-comment__anh kd-anh-hong'
        : img.closest('.kd-gallery') ? 'kd-anh-hong kd-anh-hong--o' : '';
    if (!lop) return;
    const o = document.createElement('span');
    o.className = lop;
    o.setAttribute('role', 'img');
    o.setAttribute('aria-label', 'Không mở được ảnh');
    o.title = 'Không mở được ảnh — tệp có thể đã bị xoá trên máy chủ';
    o.innerHTML = '<i class="bi bi-image" aria-hidden="true"></i>';
    // Link bọc riêng tấm ảnh thì thay cả link (bấm vào cũng chỉ mở ra lỗi); link còn chữ khác thì chỉ thay ảnh.
    const a = img.parentElement;
    (a && a.tagName === 'A' && a.children.length === 1 ? a : img).replaceWith(o);
  }, true);

  // Cột "Thao tác" dính mép phải (kd-man-hinh.css, KH-11): bật .is-khuat-phai trên khung cuộn khi bên dưới cột dính còn
  // cột bị khuất (khung còn cuộn sang phải được) để CSS vẽ bóng mép trái. Bảng vẽ lại bằng innerHTML, panel mở/đóng đổi bề
  // rộng khung, tab ẩn/hiện đổi kích thước → theo dõi kích thước (ResizeObserver), không chỉ sự kiện cuộn.
  function kiemKhuat(sc) {
    sc.classList.toggle('is-khuat-phai', sc.scrollWidth - sc.clientWidth - sc.scrollLeft > 1);
    if (sc.classList.contains('kd-table-scroll--thanh')) veThanhCuon(sc);
  }

  // Thanh cuộn ngang TỰ VẼ cho khung .kd-table-scroll--thanh (chi tiết báo giá, người dùng 16/09/2026: "cho tôi 1 thanh
  // scroll mờ mờ để kéo ngang"). Vì sao không dùng thanh native: Edge/Chrome Win11 chế độ overlay ẩn thanh tới khi rê
  // chuột vào và BỎ CẢ ::-webkit-scrollbar (đã chụp với --enable-features=OverlayScrollbar) → người dùng không biết bảng
  // còn cột bên phải. Rail đặt ngay dưới khung; con trượt đồng bộ hai chiều với scrollLeft (kéo con trượt hoặc bấm rail
  // để cuộn; cuộn bằng chuột/cảm ứng thì con trượt chạy theo qua sự kiện scroll ở dưới). aria-hidden vì đây chỉ là tay
  // cầm cho chuột — bàn phím/đọc màn hình vẫn dùng khung cuộn native (CSS chỉ ẩn THANH native, không ẩn khả năng cuộn).
  function veThanhCuon(sc) {
    let ray = sc._kdRay;
    if (!ray) {
      ray = document.createElement('div');
      ray.className = 'kd-cuon';
      ray.setAttribute('aria-hidden', 'true');
      ray.innerHTML = '<div class="kd-cuon__num"></div>';
      sc.insertAdjacentElement('afterend', ray);
      sc._kdRay = ray;
      const num = ray.firstElementChild;
      let goc = null;   // { x, left, tiLe } lúc bắt đầu kéo — tiLe: 1px trên rail = bao nhiêu px nội dung
      num.addEventListener('pointerdown', (e) => {
        const du = sc.scrollWidth - sc.clientWidth, cho = ray.clientWidth - num.offsetWidth;
        goc = { x: e.clientX, left: sc.scrollLeft, tiLe: cho > 0 ? du / cho : 0 };
        num.setPointerCapture(e.pointerId);
        ray.classList.add('is-keo');
        e.preventDefault();   // không bôi đen chữ trong bảng khi kéo
      });
      num.addEventListener('pointermove', (e) => { if (goc) sc.scrollLeft = goc.left + (e.clientX - goc.x) * goc.tiLe; });
      const tha = () => { goc = null; ray.classList.remove('is-keo'); };
      num.addEventListener('pointerup', tha);
      num.addEventListener('pointercancel', tha);
      // Bấm vào rail (ngoài con trượt): nhảy một khung về phía bấm, như thanh cuộn native.
      ray.addEventListener('click', (e) => {
        if (e.target !== ray) return;
        sc.scrollBy({ left: (e.clientX < num.getBoundingClientRect().left ? -1 : 1) * sc.clientWidth, behavior: 'smooth' });
      });
    }
    const du = sc.scrollWidth - sc.clientWidth;
    ray.hidden = du <= 1;   // bảng vừa khung (hoặc tab đang ẩn: mọi số đo = 0) → không cần thanh
    if (ray.hidden) return;
    noiRay(sc);
    const num = ray.firstElementChild, rong = ray.clientWidth;
    const w = Math.max(32, sc.clientWidth / sc.scrollWidth * rong);   // con trượt tối thiểu 32px để còn nắm được
    num.style.width = w + 'px';
    num.style.left = (sc.scrollLeft / du) * (rong - w) + 'px';
  }
  // Máy tính ≥1024px (người dùng 17/09/2026): đáy khung bảng còn dưới mép màn hình mà đầu bảng đã lên → rail rời khỏi
  // dòng chảy, nổi cố định ở đáy cửa sổ đúng bề rộng khung; chèn ô chỗ cùng chiều cao để thẻ không co lại (co lại làm đáy
  // khung nhảy lên qua ngưỡng → bật/tắt liên tục). Vì sao không sticky: xem chú thích .kd-cuon.is-noi trong CSS.
  function noiRay(sc) {
    const ray = sc._kdRay;
    if (!ray || ray.hidden) return;
    const r = sc.getBoundingClientRect();
    const noi = window.matchMedia('(min-width: 1024px)').matches && r.bottom > window.innerHeight - 8 && r.top < window.innerHeight - 120;
    if (noi) {
      if (!sc._kdCho) {
        sc._kdCho = document.createElement('div');
        sc._kdCho.className = 'kd-cuon__cho';
        sc._kdCho.setAttribute('aria-hidden', 'true');
      }
      if (!sc._kdCho.isConnected) ray.insertAdjacentElement('beforebegin', sc._kdCho);
      // Lề ngang của rail đo lúc còn trong dòng chảy (lần đầu luôn là lúc đó; .is-noi đặt margin 0 nên đo sau là sai).
      if (sc._kdLe === undefined) sc._kdLe = parseFloat(getComputedStyle(ray).marginLeft) || 0;
      ray.classList.add('is-noi');
      ray.style.left = (r.left + sc._kdLe) + 'px';
      ray.style.width = (r.width - sc._kdLe * 2) + 'px';
    } else if (ray.classList.contains('is-noi')) {
      ray.classList.remove('is-noi');
      ray.style.left = '';
      ray.style.width = '';
      if (sc._kdCho) sc._kdCho.remove();
    }
  }
  let choNoiRay = 0;
  const noiMoiRay = () => {
    if (choNoiRay) return;
    choNoiRay = requestAnimationFrame(() => {
      choNoiRay = 0;
      document.querySelectorAll('.kd-table-scroll--thanh').forEach((sc) => { if (sc._kdRay) veThanhCuon(sc); });
    });
  };
  window.addEventListener('scroll', noiMoiRay, { passive: true });
  window.addEventListener('resize', noiMoiRay);
  const roBang = typeof ResizeObserver === 'function'
    ? new ResizeObserver((ds) => ds.forEach((x) => { const sc = x.target.closest('.kd-table-scroll'); if (sc) kiemKhuat(sc); }))
    : null;
  let choQuetBang = 0;
  function quetBang() {
    choQuetBang = 0;
    document.querySelectorAll('.kd-table-scroll').forEach((sc) => {
      const bang = sc.firstElementChild;   // bảng con có thể bị thay bằng innerHTML → gắn theo dõi cho bảng hiện tại
      [sc, bang].forEach((x) => { if (roBang && x && !x._kdKhuat) { x._kdKhuat = true; roBang.observe(x); } });
      kiemKhuat(sc);
    });
  }
  // Sự kiện scroll của phần tử không nổi bọt nhưng vẫn qua pha capture ở document.
  document.addEventListener('scroll', (e) => {
    const t = e.target;
    if (t instanceof Element && t.classList.contains('kd-table-scroll')) kiemKhuat(t);
  }, true);
  // Bảng dựng muộn (tab ở trang chi tiết) → quét lại sau mỗi đợt đổi DOM trong .kd-page, gộp một lần mỗi khung hình.
  function batDauTheoDoiBang() {
    quetBang();
    const mo = new MutationObserver(() => { if (!choQuetBang) choQuetBang = requestAnimationFrame(quetBang); });
    document.querySelectorAll('.kd-page').forEach((g) => mo.observe(g, { childList: true, subtree: true }));
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', batDauTheoDoiBang);
  else batDauTheoDoiBang();

  // Ô icon theo loại tệp — tile nền đặc nét trắng (icon-net-trang.md, mục "Icon loại tệp").
  function iconTep(mime, ten) {
    const s = ((mime || '') + ' ' + (ten || '')).toLowerCase();
    if (s.includes('pdf')) return { lop: 'ico-tile--danger', icon: 'bi-filetype-pdf', loai: 'Tệp PDF' };
    if (/sheet|excel|xls|csv/.test(s)) return { lop: 'ico-tile--success', icon: 'bi-file-earmark-spreadsheet', loai: 'Bảng tính' };
    if (/word|docx?\b/.test(s)) return { lop: '', icon: 'bi-file-earmark-word', loai: 'Tài liệu Word' };
    if (/image|png|jpe?g|webp|gif/.test(s)) return { lop: 'ico-tile--tim', icon: 'bi-file-earmark-image', loai: 'Hình ảnh' };
    return { lop: 'ico-tile--neutral', icon: 'bi-file-earmark', loai: 'Tệp đính kèm' };
  }

  // Tab chữ thuần (subnav dạng 2). list chứa [role=tab] có aria-controls; onChon(key) gọi mỗi lần đổi.
  function ganTab(list, onChon) {
    const tabs = [...list.querySelectorAll('[role="tab"]')];
    function chon(t, layFocus) {
      tabs.forEach((x) => {
        const la = x === t;
        x.setAttribute('aria-selected', la ? 'true' : 'false');
        x.tabIndex = la ? 0 : -1;
        const pane = document.getElementById(x.getAttribute('aria-controls'));
        if (pane) pane.hidden = !la;
      });
      if (layFocus) t.focus();
      if (onChon) onChon(t.dataset.tab);
    }
    tabs.forEach((t) => t.addEventListener('click', () => chon(t, false)));
    list.addEventListener('keydown', (e) => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const i = tabs.indexOf(document.activeElement);
      if (i < 0) return;
      e.preventDefault();
      chon(tabs[(i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length], true);
    });
    return { chon: (key) => { const t = tabs.find((x) => x.dataset.tab === key); if (t) chon(t, false); } };
  }

  // <dialog> gốc: showModal() tự bẫy focus + Esc. Nút [data-dong] đóng; trả lại focus cho nút đã mở.
  function moHopThoai(dlg) {
    const traVe = document.activeElement;
    const loi = dlg.querySelector('.kd-form-err');
    if (loi) { loi.textContent = ''; loi.hidden = true; }
    if (!dlg._ganDong) {
      dlg.addEventListener('click', (e) => { if (e.target.closest('[data-dong]')) dlg.close(); });
      // KH-5: nhấn chuột xuống nút Huỷ/X làm ô đang focus mất focus TRƯỚC cú click → trang kiểm ô lúc blur, hiện lỗi, hộp thoại
      // cao lên, nút bị đẩy khỏi con trỏ (đo 11/09: dịch 21px) nên click trượt, phải bấm lần 2. Chặn mặc định của mousedown
      // giữ focus tại chỗ, click vẫn tới nút. (preventDefault ở pointerdown KHÔNG chặn được việc chuyển focus.)
      dlg.addEventListener('mousedown', (e) => { if (e.target.closest('[data-dong]')) e.preventDefault(); });
      dlg._ganDong = true;
    }
    dlg.addEventListener('close', () => { if (traVe && document.contains(traVe)) traVe.focus(); }, { once: true });
    dlg.showModal();
    const dau = dlg.querySelector('input:not([type=hidden]):not([disabled]), select, textarea');
    if (dau) dau.focus();
  }
  function baoLoiHopThoai(dlg, msg) {
    const loi = dlg.querySelector('.kd-form-err');
    if (!loi) { showToast('err', msg); return; }
    loi.textContent = msg;
    loi.hidden = false;
  }

  // Khối lỗi có nút Thử lại (luật frontend-ui 5).
  function khoiLoi(pane, tieuDe, e, thuLai) {
    pane.textContent = '';
    const k = document.createElement('div');
    k.className = 'kd-state kd-state--gon kd-state--error';
    k.setAttribute('role', 'alert');
    k.innerHTML = '<p class="kd-state__title"></p><p class="kd-muted" data-msg></p>' +
      '<button type="button" class="kd-btn kd-btn--sm">Thử lại</button>';
    k.querySelector('.kd-state__title').textContent = tieuDe;
    k.querySelector('[data-msg]').textContent = e.message;
    k.querySelector('button').addEventListener('click', thuLai);
    pane.appendChild(k);
  }
  function khoiRong(tieuDe, goiY) {
    return '<div class="kd-state kd-state--gon"><p class="kd-state__title">' + esc(tieuDe) + '</p>' +
      (goiY ? '<p class="kd-muted">' + esc(goiY) + '</p>' : '') + '</div>';
  }
  const KHUNG_TAI = '<p><span class="kd-skel kd-skel--o"></span></p><p><span class="kd-skel kd-skel--ngan"></span></p>';

  // 4 mốc thật của vòng đời báo giá — thay cho "Tạo → Đã gửi → Khách xem → Đàm phán → Chốt đơn" của ảnh,
  // vì hệ thống không theo dõi khách đã xem hay đàm phán. Dùng chung cho panel danh sách và trang chi tiết.
  // BG-6: bước đã qua suy từ TRẠNG THÁI trước, mốc giờ sau. Mốc có thể thiếu (DB dev 11/09: 5/5 cho_kt và 98/100 tu_choi
  // mẫu không có sent_at) hoặc còn sót từ vòng duyệt trước (cho_duyet 11741 vẫn mang duyet_luc) — dựa giờ thì stepper cãi
  // nhãn trạng thái. Số dưới đây = số bước đã xong; thiếu mốc thì để trống giờ, không hạ bước. Bước hiện tại không in giờ.
  // Trạng thái không nói lên bước nào (het_han: hết hạn ở nháp hay lúc chờ duyệt đều được) → giữ cách suy theo mốc giờ.
  const BUOC_DA_XONG = { nhap: 1, cho_duyet: 2, tu_choi: 2, cho_kt: 3, kt_tu_choi: 3, da_len_don: 4 };
  function buocBaoGia(r) {
    const tuChoi = r.trang_thai === 'tu_choi';
    const ktTuChoi = r.trang_thai === 'kt_tu_choi';
    const buoc = [
      { nhan: 'Tạo báo giá', luc: r.ngay_tao },
      { nhan: 'Gửi duyệt', luc: r.gui_duyet_luc },
      { nhan: tuChoi ? 'Quản lý từ chối' : 'Quản lý duyệt', luc: r.duyet_luc, hong: tuChoi },
      { nhan: ktTuChoi ? 'Kế toán từ chối' : 'Lên đơn', luc: r.kt_duyet_luc, hong: ktTuChoi },
    ];
    const daXong = BUOC_DA_XONG[r.trang_thai];
    let conDi = true;
    return buoc.map((b, i) => {
      let lop;
      if (daXong !== undefined) lop = i < daXong ? 'is-done' : i > daXong ? 'is-todo' : b.hong ? 'is-fail' : 'is-current';
      else if (b.hong) { lop = 'is-fail'; conDi = false; }
      else if (b.luc && conDi) lop = 'is-done';
      else if (conDi) { lop = 'is-current'; conDi = false; }
      else lop = 'is-todo';
      const tg = b.luc && (lop === 'is-done' || lop === 'is-fail') ? ngayNgan(b.luc) + ' ' + gio(b.luc) : '';
      return '<li class="kd-step ' + lop + '"' + (lop === 'is-current' ? ' aria-current="step"' : '') + '>' +
        '<span class="kd-step__dot" aria-hidden="true"></span>' +
        '<span class="kd-step__label">' + b.nhan + '</span>' +
        '<span class="kd-step__time">' + tg + '</span></li>';
    }).join('');
  }

  // Dòng nhật ký (DongLichSu) → <li> của .kd-timeline.
  // Nguồn khách: vài giá trị do hệ thống tự ghi dạng mã (vd customers.py:752 ghi "kinh-doanh") — không để lộ mã
  // ra màn hình. Khách nhiều nguồn lưu "Facebook,Website" → thêm dấu cách sau dấu phẩy.
  const NGUON_MA = { 'bao-gia': 'Báo giá', 'kinh-doanh': 'Kinh doanh' };
  function nhanNguon(v) {
    return String(v || '').split(',').map((x) => x.trim()).filter(Boolean).map((x) => NGUON_MA[x] || x).join(', ');
  }

  // phong_ban của bình luận lẫn tên phòng thật ("Kinh Doanh") với KHOÁ vai trò do app khác ghi vào (DB dev 11/09/2026:
  // nhan_vien 4.229 dòng, leader 981, sa, mh, admin) → khoá đổi sang nhãn như topbar (_header.html:57). Khoá lạ thì ẩn.
  const PHONG_BAN_MA = {
    nhan_vien: 'Nhân viên', leader: 'Leader', manager: 'Manager', ceo: 'CEO', admin: 'Admin',
    assistant_ceo: 'Trợ lý CEO', sa: 'Sale Admin', mh: 'Mua Hàng', kd: 'Kinh Doanh', mkt: 'Marketing',
  };
  function nhanPhongBan(v) {
    const s = String(v || '').trim();
    if (Object.prototype.hasOwnProperty.call(PHONG_BAN_MA, s)) return PHONG_BAN_MA[s];
    if (/^[a-z_]+$/.test(s)) {
      console.warn('[KD] Phòng ban dạng khoá chưa có nhãn:', s);
      return '';
    }
    return s;
  }
  // Link / ảnh lấy từ dữ liệu người dùng gửi (hinh_anh bình luận, ảnh QC…): server không kiểm, esc() không chặn được
  // "javascript:…" trong href → chỉ nhận đường dẫn trong app ("/…", không phải "//…") hoặc http(s).
  function urlAnToan(u) {
    const s = String(u || '').trim();
    return /^\/(?!\/)/.test(s) || /^https?:\/\//i.test(s) ? s : '';
  }

  // ── QR chuyển khoản đặt cọc — nội dung + trang in chép đúng khối QR của app cũ (quote_view.html:417-466) ──
  function qrCocHtml(q) {
    return '<div class="kd-qr">' +
      '<img class="kd-qr__anh" src="' + esc(urlAnToan(q.anh_url)) + '" width="120" height="120" alt="QR chuyển khoản đặt cọc">' +
      '<div class="kd-qr__noi-dung">' +
        '<p>Ngân hàng: <b>' + esc(q.ngan_hang) + '</b> · STK: <b class="num">' + esc(q.so_tk) + '</b></p>' +
        '<p>' + esc(q.chu_tk) + '</p>' +
        '<p>Số tiền cọc: <b class="kd-qr__tien num">' + esc(tienVnd(q.so_tien)) + '</b></p>' +
        '<p>Nội dung CK: <code>' + esc(q.noi_dung) + '</code></p>' +
        '<p><button type="button" class="kd-btn kd-btn--sm" data-in-qr><i class="bi bi-printer" aria-hidden="true"></i>In QR đưa khách</button></p>' +
      '</div></div>';
  }
  // Trang in một tờ đưa khách: đúng các dòng __printQRView của app cũ; tự mở hộp in sau 250ms như cũ.
  function inQrCoc(q, ma) {
    const theme = document.querySelector('link[href*="theme.css"]');
    const anh = esc(urlAnToan(q.anh_url));
    const html = '<!doctype html><html lang="vi"><head><meta charset="utf-8"><title>' + esc('QR ' + q.noi_dung) + '</title>' +
      (theme ? '<link rel="stylesheet" href="' + esc(theme.href) + '">' : '') +
      '<style>body{text-align:center;padding:24px;color:var(--text-1)}h2{margin:0 0 6px;color:var(--brand-hover)}' +
      'img{width:340px;height:340px;margin:12px 0}.dong{margin:6px 0;font-size:var(--fs-body-lg)}' +
      '.tien{color:var(--brand);font-weight:700;font-size:var(--fs-kpi)}' +
      '.nd{background:var(--brand-soft);padding:4px 10px;border-radius:var(--r-sm)}' +
      '.goi-y{color:var(--text-3);font-size:var(--fs-body);margin-top:16px}</style></head><body>' +
      '<h2>PAPASAN NỘI THẤT</h2>' +
      '<div class="dong">Báo giá <strong>' + esc(ma) + '</strong>' + (q.ten_khach ? ' · KH: ' + esc(q.ten_khach) : '') + '</div>' +
      '<img src="' + anh + '" alt="QR"><br>' +
      '<div class="dong"><strong>' + esc(q.ngan_hang) + '</strong> · STK: <strong>' + esc(q.so_tk) + '</strong></div>' +
      '<div class="dong">' + esc(q.chu_tk) + '</div>' +
      '<div class="dong tien">' + esc(tien(q.so_tien)) + ' đ</div>' +
      '<div class="dong">Nội dung: <code class="nd">' + esc(q.noi_dung) + '</code></div>' +
      '<div class="goi-y">Quét bằng app banking để tự động điền số tiền + nội dung</div>' +
      '<script>window.onload=function(){setTimeout(function(){window.print()},250)}<\/script></body></html>';
    const w = window.open('', '_blank', 'width=640,height=880');
    if (!w) {
      showToast('err', 'Trình duyệt đang chặn cửa sổ in — cho phép cửa sổ bật lên (popup) cho trang này rồi bấm lại.');
      return;
    }
    w.document.write(html);
    w.document.close();
  }

  function dongLichSu(x) {
    const nguoi = x.nguoi ? esc(x.nguoi) + (x.nguon ? ' · ' + esc(x.nguon) : '') : (x.nguon ? esc(x.nguon) : '');
    return '<li><div class="kd-tl"><div><div class="kd-strong">' + esc(x.hanh_dong) + '</div>' +
      '<div class="kd-muted">' + ngayGio(x.luc) + '</div></div>' +
      (nguoi ? '<span class="kd-tl__who">' + nguoi + '</span>' : '') + '</div></li>';
  }

  // ── Popup "Việc cần kiểm soát" — Báo giá + Đơn hàng (17/09/2026; trước đó nằm riêng trong kd-bao-gia.js) ──
  // Cùng API, tham số, chu kỳ 120 giây với màn cũ (index.html:1952-2065). Màn cũ tải cho mọi vai trò; server tự lọc:
  // nhân viên chỉ thấy khách của mình (dashboard.py:140-142, 199-201). Markup: templates/kd/_viec_kiem_soat.html;
  // trang nào include partial đó thì gọi hàm này một lần sau khi khởi động. Trang không có partial → bỏ qua, không lỗi.
  function batViecKiemSoat() {
    const cbHop = document.getElementById('mgr-alert'), cbBong = document.getElementById('mgr-alert-bubble'),
      cbThan = document.getElementById('mgr-alert-body'), nutThuGon = document.getElementById('kd-cb-thu-gon');
    if (!cbHop || !cbBong || !cbThan || !nutThuGon) return;
    let cbThuGon = false, luotCb = 0;
    function cbHien() {
      cbHop.hidden = cbThuGon;
      cbBong.hidden = !cbThuGon;
    }
    nutThuGon.addEventListener('click', () => { cbThuGon = true; cbHien(); cbBong.focus(); });
    cbBong.addEventListener('click', () => { cbThuGon = false; cbHien(); nutThuGon.focus(); });

    // minutes_since có thể tới hàng chục nghìn phút (khách chuyển KD từ nhiều ngày trước) → đổi sang giờ / ngày cho dễ đọc.
    function thoiGianCho(phut) {
      const n = so(phut);
      if (n === null) return 'lâu';
      if (n >= 1440) return soDem(Math.floor(n / 1440)) + ' ngày';
      if (n >= 60) return soDem(Math.floor(n / 60)) + ' giờ';
      return soDem(n) + ' phút';
    }
    const gioNgan = (s) => (s ? ngayNgan(s) + ' ' + gio(s) : '');
    const rutGon = (s, n) => { const t = String(s || '').trim(); return t.length > n ? t.slice(0, n) + '…' : t; };
    const metaBl = (x) => esc([x.latest_by, gioNgan(x.latest)].filter(Boolean).join(' · '));
    function nhomCb(tieuDe, ds, tone, veMuc) {
      if (!ds || !ds.length) return '';
      return '<section class="kd-cb__nhom"><h3 class="kd-cb__nhom-td">' + esc(tieuDe) + ' (' + soDem(ds.length) + ')</h3>' +
        '<ul class="kd-cb__ds">' + ds.map((x) => '<li class="kd-cb__muc kd-cb__muc--' + tone + '">' + veMuc(x) + '</li>').join('') + '</ul></section>';
    }

    async function taiCanhBao() {
      const luot = ++luotCb;
      // Khung chờ chỉ ở lần tải đầu — các lần tải lại 120 giây giữ nội dung cũ tới khi có kết quả (màn cũ cũng không nháy).
      if (!cbThan.dataset.daTai) { cbThan.innerHTML = KHUNG_TAI; cbHien(); }
      let d;
      try {
        d = await api('/api/dashboard/manager-alerts?stale_minutes=5&cmt_window_hours=24');
        if (!d || !d.ok) throw new Error('Máy chủ chưa trả được danh sách việc. Thử lại sau ít phút.');
      } catch (e) {
        if (luot !== luotCb) return;
        khoiLoi(cbThan, 'Không tải được việc cần kiểm soát', e, taiCanhBao);
        cbHien();
        return;
      }
      if (luot !== luotCb) return;
      cbThan.dataset.daTai = '1';
      const tong = so(d.total_alerts) || 0;
      document.getElementById('kd-cb-tong').textContent = soDem(tong);
      document.getElementById('mgr-bubble-count').textContent = soDem(tong);
      cbBong.setAttribute('aria-label', 'Mở việc cần kiểm soát (' + soDem(tong) + ' việc)');
      if (!tong) {
        cbThan.innerHTML = khoiRong('Tất cả đã xử lý', 'Không có việc nào cần kiểm soát lúc này.');
        cbHien();
        return;
      }
      cbThan.innerHTML =
        nhomCb('Khách chưa đẩy tiến trình quá ' + soDem(d.stale_minutes) + ' phút', d.data_new_no_progress, 'danger', (x) =>
          '<p><span class="kd-strong">' + esc(x.ho_ten || '—') + '</span>' + (x.sdt ? ' <span class="kd-muted">' + esc(x.sdt) + '</span>' : '') + '</p>' +
          '<p class="kd-cb__meta">NV: <b>' + esc(x.kd_nhan || 'Chưa gán') + '</b> · để ' + esc(thoiGianCho(x.minutes_since)) + ' chưa cập nhật tiến trình</p>' +
          // Màn cũ dẫn về danh sách khách cũ; màn mới dẫn về danh sách khách mới, ?customer= mở thẳng khách đó.
          '<p><a class="kd-link kd-link--sm" href="/kd/khach-hang?customer=' + encodeURIComponent(x.id) + '">Mở khách hàng <i class="bi bi-arrow-right" aria-hidden="true"></i></a></p>') +
        nhomCb('Bình luận mới về khách hàng', d.comments_kh, 'warning', (x) =>
          '<p><span class="kd-strong">' + esc((x.customer && x.customer.ho_ten) || x.lead_id || '—') + '</span>' +
            ' <span class="kd-muted">· ' + soDem(x.count) + ' bình luận</span></p>' +
          '<p class="kd-cb__meta">' + metaBl(x) + '</p>' +
          (x.latest_text ? '<p class="kd-cb__nd">' + esc(rutGon(x.latest_text, 120)) + '</p>' : '')) +
        nhomCb('Bình luận mới về đơn hàng', d.comments_dh, 'brand', (x) =>
          '<p><span class="kd-strong">' + esc(x.quote_number || '—') + '</span>' +
            (x.customer && x.customer.ho_ten ? ' <span class="kd-muted">' + esc(x.customer.ho_ten) + '</span>' : '') +
            ' <span class="kd-muted">· ' + soDem(x.count) + ' bình luận</span></p>' +
          '<p class="kd-cb__meta">' + metaBl(x) + '</p>' +
          (x.latest_text ? '<p class="kd-cb__nd">' + esc(rutGon(x.latest_text, 120)) + '</p>' : ''));
      cbHien();
    }
    taiCanhBao();
    setInterval(taiCanhBao, 120000);
  }

  /* Ghi chú / giải thích phụ: KHÔNG in thành đoạn chữ trên màn (anh Quang 25/09: "nhiều chữ note, rối mắt").
     Dùng biểu tượng ⓘ cạnh nhãn — rê chuột hoặc chạm để xem. CSS: .kd-tip (kd-man-hinh.css). */
  function tip(noiDung, lop) {
    if (!noiDung) return '';
    const t = esc(noiDung);
    return '<button type="button" class="kd-tip' + (lop ? ' ' + lop : '') + '" data-tip="' + t + '" aria-label="' + t + '">' +
      '<i class="bi bi-info-circle" aria-hidden="true"></i></button>';
  }

  /* Quyền theo vai trò (đặt ở _header.html): 'ceo' = admin/ceo/assistant_ceo — quyền ghi sổ tay của API. */
  /* 'admin_ceo' = chỉ admin + ceo (vd API xoá TSCĐ/khoản vay, phân phối LN, mở khoá sổ) — vai trò gốc trên <html>. */
  function coQuyen(muc) {
    if (muc === 'ceo') return document.documentElement.hasAttribute('data-quyen-ceo');
    if (muc === 'admin_ceo') return ['admin', 'ceo'].indexOf(document.documentElement.getAttribute('data-vai-tro-goc')) >= 0;
    return true;
  }

  window.KD = {
    TRANG_THAI, KY, KY_DU, CHANG, THANH_TOAN, pill, pillTienTrinh, pillThanhToan, pillTienTrinhKhach, trangThaiKhach,
    so, tien, tienVnd, tienGon, tienGonTach, tienGonHtml, soDem, phanTram, dungLuong,
    ngay, gio, ngayGio, ngayNgan, iso, tuongDoi, conNgay, khoangKy, khoangQs, MAN_RONG, nhanNguon, nhanPhongBan, urlAnToan,
    qrCocHtml, inQrCoc,
    api, JSON_POST, phanTrang, menu, dongMenu, debounce,
    avatar, iconTep, ganTab, moHopThoai, baoLoiHopThoai, khoiLoi, khoiRong, KHUNG_TAI, buocBaoGia, dongLichSu,
    batViecKiemSoat, tip, coQuyen,
  };
})();
