/* kt-duyet.js — Duyệt chi (khung: kt-danh-sach.js). Hàng chờ duyệt + chi tiền GỘP 3 luồng THẬT (giống màn cũ /chi-tap-trung):
     · de_xuat_chi  — Đề xuất chi nội bộ: workflow dùng chung 8 app `shared/routers/duyet_chi.py` (/api/duyet-chi — KHÔNG sửa file đó)
                      Trưởng bộ phận → Kế toán → Giám đốc → Kế toán chi. Duyệt: PUT /api/duyet-chi/<id>/duyet · Chi: POST /api/duyet-chi/<id>/chi
     · de_nghi_tt   — Đề nghị thanh toán ĐVVC từ Sale Admin (app/routers/de_nghi_tt.py, bảng saleadmin.denghitt)
                      Kế toán duyệt ở đây → Giám đốc duyệt ở app Sale Admin → Kế toán chi. /api/de-nghi-tt/<id>/kt-approve|kt-reject|chi
     · de_xuat_ncc  — Đề xuất trả nợ NCC từ Mua Hàng (app/routers/ncc_de_xuat.py, bảng muahang.congno loai='de_xuat_tra')
                      Kế toán duyệt ở đây → Giám đốc duyệt ở app Mua Hàng → Kế toán chi. /api/ncc-de-xuat/<id>/kt-approve|kt-reject|chi
   Thiết kế gốc gọi API đề xuất /api/duyet-chi/xu-ly, /api/duyet-chi/<id>, /api/duyet-chi/chi — chưa từng được xây. Hàm `chuyen()` gộp
   dữ liệu thật về đúng hình dạng khung cần và tự lọc / sắp xếp / phân trang / tính thẻ số phía client (API thật không phân trang).
   Điểm PHẢI GẦN ĐÚNG vì dữ liệu thật không có:
     · Mã phiếu đề xuất chi: model không có cột mã → "DX" + id. (DNTT / NCC dùng mã thật DNTT-… / CN-….)
     · Người thụ hưởng đề xuất chi: model không lưu → lấy người đề nghị; STK người nhận nằm trong phần "Mục đích" do người gửi tự ghi.
     · Người đang chờ duyệt: backend chỉ biết CẤP chờ (nhiều quản lý cùng phòng đều duyệt được) → hiện vai trò/phòng ban, không phải tên.
     · Không có ngưỡng "Giám đốc duyệt từ X đồng": cả 3 luồng thật đều LUÔN qua Giám đốc.
     · Hạn chi: chỉ đề xuất chi có (han_thanh_toan); DNTT / NCC không có cột hạn → không tính quá hạn.
   Panel chi tiết dùng thẳng dữ liệu dòng (các list thật đã trả đủ lịch sử duyệt + chứng từ), không cần endpoint chi tiết riêng. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-duyet')) return;
  /* Link cũ "?trang_thai=" (rỗng = tất cả, vd link đã lưu từ màn Đề nghị / Đề xuất NCC bản trước) → 'tat_ca' TRƯỚC khi khung đọc URL
     (khung trả giá trị không có trong ô chọn về mặc định "Chờ tôi duyệt"). */
  try { const q0 = new URLSearchParams(location.search); if (q0.has('trang_thai') && !q0.get('trang_thai')) { q0.set('trang_thai', 'tat_ca'); history.replaceState(null, '', location.pathname + '?' + q0 + location.hash); } } catch (e) { /* khung xem trước */ }
  const H = KT.H, $ = (id) => document.getElementById(id), u = KT.url.doc();
  const LOAI_CHI = { di_chuyen: 'Di chuyển / Xăng xe', van_phong: 'Văn phòng phẩm', tiep_thi: 'Tiếp thị / Quảng cáo', dao_tao: 'Đào tạo', khach_hang: 'Tiếp khách', khac: 'Chi phí khác' };
  const NGUON = { de_xuat_chi: ['Đề xuất chi', 'muted', 'bi-receipt'], de_nghi_tt: ['Đề nghị TT', 'info', 'bi-truck'], de_xuat_ncc: ['Trả NCC', 'brand', 'bi-building'] };
  const VAI = { manager: 'Trưởng bộ phận', ketoan: 'Kế toán', ceo: 'Giám đốc', chi: 'Kế toán' };   // 'chi' = Kế toán từ chối ngoài cấp của mình / sau khi đã duyệt xong (de_xuat_chi_tu_choi.py)
  const THU_TU = { manager: 0, ketoan: 1, ceo: 2, done: 3, rejected: 3 };
  const KT_ROLES = ['manager', 'admin'];   // ai được KT duyệt cấp 1 DNTT / NCC — khớp _KT_ROLES của de_nghi_tt.py / ncc_de_xuat.py
  const TT = { cho_duyet: ['warning', 'Chờ duyệt'], cho_chi: ['info', 'Chờ chi'], da_chi: ['success', 'Đã chi'], tu_choi: ['danger', 'Bị từ chối'], hoan_tat: ['success', 'Hoàn tất'] };
  const pillTT = (r) => { const x = TT[r.trang_thai] || ['muted', 'Chưa đặt tên']; const ngoai = r.chi_ngoai && r.trang_thai === 'da_chi'; return H.pill(ngoai ? 'muted' : x[0], r.cho_toi ? 'Chờ bạn duyệt' : ngoai ? (r.nguon === 'de_xuat_ncc' ? 'Đã chi ở luồng Đề nghị TT' : 'Đã chi ở luồng Trả NCC') : x[1], r.cho_toi); };
  /* Một dòng phụ ngắn dưới nhãn trạng thái (bước đang chờ / ngày chi); chi tiết đầy đủ nằm trong panel. */
  const tienTrinh = (r) => {
    const phu = r.trang_thai === 'cho_duyet' && r.buoc_hien_tai ? (r.cho_toi ? 'Gửi ' : 'Chờ ' + r.buoc_hien_tai.vai + ' · gửi ') + KD.soDem(r.cho_ngay) + ' ngày trước'
      : r.trang_thai === 'da_chi' ? (r.ngay_chi ? KD.ngay(r.ngay_chi) + ' · ' : '') + (r.tai_khoan_chi || '—') : '';
    return (phu ? '<span class="kt-dc-tt">' + esc(phu) + '</span>' : '')
      + (r.qua_han_chi ? '<span class="kt-dc-tt">' + H.pill('danger', 'Quá hạn ' + KD.ngay(r.can_chi_truoc)) + '</span>' : '');
  };
  /* BẢN VÁ 30/09/2026 (giám đốc yêu cầu, ưu tiên #1): nút "Từ chối" phải HIỆN RÕ trên dòng (không
     chỉ trong menu ⋯), ở CẢ tab Chờ duyệt lẫn Chờ chi. Bảng luồng × trạng thái → API từ chối:
       · cho_toi (Chờ duyệt, đúng cấp của mình)  → CẢ 3 luồng: de_xuat_chi PUT /duyet {tu_choi}
         (shared/routers/duyet_chi.py:519, có gate _can_approve_at theo ĐÚNG CẤP — không mở quá
         quyền), de_nghi_tt/de_xuat_ncc POST .../kt-reject (chỉ cấp 1 cho_duyet, backend tự chặn).
       · cho_chi (đã duyệt xong, CHƯA chi) → CHỈ de_nghi_tt + de_xuat_ncc, API MỚI
         POST .../tu-choi-truoc-chi (CHI_ROLES, 409 nếu da_chi/da_chi_ngoai).
         BỔ SUNG 01/10/2026 (giám đốc: "đơn chờ chi quá hạn cũng cần nút Từ chối"): de_xuat_chi cũng có nút ở tab này —
         shared/routers/duyet_chi.py không có API từ chối sau khi duyệt xong và shared/ không deploy được, nên đường riêng
         POST /api/de-xuat-chi/{id}/tu-choi-truoc-chi nằm ở app Kế toán (app/routers/de_xuat_chi_tu_choi.py), cùng cổng quyền với nút Chi. */
  /* BỔ SUNG 01/10/2026 lần 2 (giám đốc: "anh Thành duyệt và từ chối được trong quyền của anh — ví dụ ứng lương"): Đề xuất chi còn
     ĐANG CHỜ DUYỆT ở cấp không phải của mình (vd chờ Giám đốc sau khi Kế toán đã duyệt) cũng từ chối được — chỉ TỪ CHỐI, không phải
     duyệt. Cùng đường API với từ chối chờ chi; cổng quyền khớp `_duoc_tu_choi` (de_xuat_chi_tu_choi.py). */
  const DX_TC_ROLES = ['ceo', 'admin', 'assistant_ceo', 'manager', 'leader', 'kt'];
  const tuChoiThem = (r) => (r.trang_thai === 'cho_chi' && chiDuoc(r))
    || (r.nguon === 'de_xuat_chi' && r.trang_thai === 'cho_duyet' && !r.cho_toi && DX_TC_ROLES.includes(vaiTro));
  const nutTuChoi = (r, grow) => '<button type="button" class="kd-btn' + (grow ? ' kd-btn--grow' : ' kt-dc-nut') + ' kd-btn--danger" data-nut="tu_choi" data-id="' + esc(r.id) + '"><i class="bi bi-x-lg" aria-hidden="true"></i>Từ chối</button>';
  /* Nút chính trên từng dòng: Duyệt (đang chờ mình) · Chi tiền (đã duyệt xong) · Từ chối (rõ, cả 2 tab khi API cho) · còn lại chỉ có ⋯ */
  const nutDong = (r) => (r.cho_toi ? '<button type="button" class="kd-btn kd-btn--primary kt-dc-nut" data-nut="duyet" data-id="' + esc(r.id) + '"><i class="bi bi-check2" aria-hidden="true"></i>Duyệt</button>' + nutTuChoi(r, false)
    : chiDuoc(r) ? '<button type="button" class="kd-btn kd-btn--primary kt-dc-nut" data-nut="chi" data-id="' + esc(r.id) + '"><i class="bi bi-cash-coin" aria-hidden="true"></i>Chi tiền</button>' + (tuChoiThem(r) ? nutTuChoi(r, false) : '') : (tuChoiThem(r) ? nutTuChoi(r, false) : ''))
    + '<button type="button" class="kd-icon-btn" data-menu="' + esc(r.id) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác khác với ' + esc(r.ma) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button>';
  const soNgay = (iso) => Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 86400000));

  /* ── Nguồn phụ (DNTT, NCC) + "chờ tôi" của đề xuất chi: nạp trước mỗi lần tải bảng. Khung danh sách chỉ gọi 1 URL
     (/api/duyet-chi), `chuyen()` chạy đồng bộ nên các nguồn còn lại được nạp sẵn ở đây. Một nguồn lỗi (vd không có quyền)
     không làm hỏng cả màn — ghi lại để báo ở dòng phạm vi. */
  let choToiIds = new Set(), dntt = [], ncc = [], vaiTro = '', toiLa = '', loiNguon = [], daChi = [];
  /* Ai được bấm "Chi tiền" (F3 28/09) — theo đúng cổng API từng luồng:
     · de_xuat_chi: _can_chi (duyet_chi.py) = CEO/admin/trợ lý CEO hoặc manager/leader/kt có app ketoan → mọi người vào được màn này;
     · de_nghi_tt: _CHI_ROLES (de_nghi_tt.py) · de_xuat_ncc: _KT_ROLES ∪ _CEO_ROLES (ncc_de_xuat.py) → manager/admin/ceo/assistant_ceo
       (KHÔNG gồm vai trò 'kt' — trước đây nút vẫn hiện với 'kt' rồi API trả 403). */
  const CHI_ROLES = ['manager', 'admin', 'ceo', 'assistant_ceo'];
  const chiDuoc = (r) => r.trang_thai === 'cho_chi' && (r.nguon === 'de_xuat_chi' || CHI_ROLES.includes(vaiTro));
  async function taiPhu() {
    const [q, a, b, p] = await Promise.allSettled([KD.api('/api/duyet-chi/queue/me'), KD.api('/api/de-nghi-tt?limit=500'), KD.api('/api/ncc-de-xuat?limit=500'), vaiTro ? Promise.resolve(null) : KD.api('/api/profile')]);
    loiNguon = [];
    if (q.status === 'fulfilled') choToiIds = new Set(q.value.map((x) => x.id));
    if (a.status === 'fulfilled') dntt = a.value; else loiNguon.push('Đề nghị TT');
    if (b.status === 'fulfilled') ncc = b.value; else loiNguon.push('Trả NCC');
    if (p.status === 'fulfilled' && p.value) { vaiTro = (p.value.role || '').toLowerCase(); toiLa = p.value.username || ''; }
  }

  function trangThaiDx(r) {
    if (r.approval_level === 'rejected' || r.trang_thai === 'tu_choi') return 'tu_choi';
    if (r.approval_level === 'done' || r.trang_thai === 'da_duyet') return r.da_chi ? 'da_chi' : 'cho_chi';
    // Dữ liệu cũ trang_thai='duyet' (id 32, 33, 96 — cấp vẫn 'ceo'): theo màn cũ (_dcNhom trong duyet_chi_core.html) là "xong",
    // nhãn "Hoàn tất" (hoặc "Đã chi" nếu da_chi). Không vào hàng chờ duyệt, không vào "chờ chi" (backend chỉ chi approval_level='done',
    // /chi-tap-trung cũng không liệt kê). Anh Quang chốt 25/09/2026: hiển thị y màn cũ, không sửa DB.
    if (r.trang_thai === 'duyet') return r.da_chi ? 'da_chi' : 'hoan_tat';
    return 'cho_duyet';
  }
  function tuDx(r) {
    const tt = trangThaiDx(r), hist = r.approval_history || [];
    const cap = tt === 'cho_duyet' ? r.approval_level : tt === 'tu_choi' ? 'rejected' : 'done';   // hoan_tat → 'done': mọi bước coi như xong
    const aiCho = (lv) => (lv === 'manager' ? 'Quản lý ' + (r.phong_ban || 'phòng') : lv === 'ketoan' ? 'Phòng Kế toán' : 'CEO');
    const buoc = ['manager', 'ketoan', 'ceo'].map((lv) => {
      const h = hist.slice().reverse().find((x) => x.level === lv);
      if (h) return { vai: VAI[lv], ai: h.ho_ten || h.username, trang_thai: h.action === 'reject' ? 'tu_choi' : 'da_duyet', luc: h.at };
      if (cap === lv) return { vai: VAI[lv], ai: aiCho(lv), trang_thai: 'cho' };
      // cấp đã qua mà không có lịch sử = backend bỏ qua (phòng không có quản lý / CEO duyệt thay) → xong
      if (cap !== 'rejected' && THU_TU[lv] < THU_TU[cap]) return { vai: VAI[lv], ai: 'Bỏ qua', trang_thai: 'da_duyet' };
      return { vai: VAI[lv], ai: '', trang_thai: 'chua' };
    });
    return {
      id: 'dx:' + r.id, goc: r.id, nguon: 'de_xuat_chi', ma: 'DX' + String(r.id).padStart(4, '0'), gui_luc: r.created_at,
      noi_dung: r.tieu_de, muc_dich: r.muc_dich, ghi_chu: r.ghi_chu, nguoi_de_nghi: r.ho_ten || r.username, bo_phan: r.phong_ban || '',
      loai: r.loai_chi || '', nguoi_tao: r.username || '',
      loai_nhan: LOAI_CHI[r.loai_chi] || r.loai_chi, hach_toan: LOAI_CHI[r.loai_chi] || 'Chi phí khác',
      thu_huong: r.ho_ten || r.username, so_tien: +r.so_tien || 0, can_chi_truoc: r.han_thanh_toan,
      qua_han_chi: !!(r.han_thanh_toan && r.han_thanh_toan < KD.iso(new Date()) && (tt === 'cho_duyet' || tt === 'cho_chi')),
      cho_ngay: soNgay(r.created_at), trang_thai: tt, cap, cho_toi: tt === 'cho_duyet' && choToiIds.has(r.id),
      buoc_hien_tai: tt === 'cho_duyet' ? { vai: VAI[cap] || cap, ai: aiCho(cap) } : null, buoc,
      ngay_chi: r.ngay_chi, tai_khoan_chi: r.tai_khoan_chi,
      chung_tu: (r.chung_tu_urls && r.chung_tu_urls.length ? r.chung_tu_urls : r.chung_tu_url ? [r.chung_tu_url] : []).map((url) => ({ ten: url.split('/').pop(), url })),
      nhat_ky: [{ viec: 'Gửi đề xuất', ai: r.ho_ten, luc: r.created_at }]
        .concat(hist.map((h) => ({ viec: (VAI[h.level] || h.level) + (h.action === 'reject' ? ' từ chối' : ' duyệt') + (h.comment ? ' — ' + h.comment : ''), ai: h.ho_ten || h.username || 'Hệ thống', luc: h.at })))
        .concat(r.da_chi ? [{ viec: 'Chi tiền qua ' + (r.tai_khoan_chi || '—'), ai: 'Kế toán', luc: r.ngay_chi }] : []),
    };
  }
  /* DNTT & NCC cùng khuôn 2 cấp: cho_duyet (chờ KT) → kt_duyet (chờ CEO ở app nguồn) → duyet (chờ chi) ; kt_tu_choi / tu_choi. */
  function tuHaiCap(r, nguon) {
    const laNcc = nguon === 'de_xuat_ncc', daChi = !!(r.da_chi || r.da_chi_ngoai), s = r.trang_thai;
    const tt = s === 'duyet' ? (daChi ? 'da_chi' : 'cho_chi') : (s === 'tu_choi' || s === 'kt_tu_choi') ? 'tu_choi' : (s === 'da_chi' ? 'da_chi' : 'cho_duyet');
    const appNguon = laNcc ? 'Mua Hàng' : 'Sale Admin';
    const capCho = s === 'cho_duyet' ? 'ketoan' : s === 'kt_duyet' ? 'ceo' : null;
    const buoc = [
      r.kt_duyet_boi ? { vai: 'Kế toán', ai: r.kt_duyet_boi_ten || r.kt_duyet_boi, trang_thai: s === 'kt_tu_choi' ? 'tu_choi' : 'da_duyet', luc: r.kt_duyet_luc }
        : capCho === 'ketoan' ? { vai: 'Kế toán', ai: 'Phòng Kế toán', trang_thai: 'cho' } : s === 'kt_tu_choi' ? { vai: 'Kế toán', ai: '', trang_thai: 'tu_choi' }
          : { vai: 'Kế toán', ai: tt === 'cho_duyet' ? '' : 'Bỏ qua', trang_thai: tt === 'cho_duyet' ? 'chua' : 'da_duyet' },
      r.nguoi_duyet ? { vai: 'Giám đốc', ai: r.nguoi_duyet_ten || r.nguoi_duyet, trang_thai: s === 'tu_choi' ? 'tu_choi' : 'da_duyet', luc: r.ngay_duyet }
        : capCho === 'ceo' ? { vai: 'Giám đốc', ai: 'CEO (app ' + appNguon + ')', trang_thai: 'cho' } : { vai: 'Giám đốc', ai: '', trang_thai: s === 'tu_choi' ? 'tu_choi' : 'chua' },
    ];
    const nguoi = r.nguoi_tao_ten || r.nv_mua_hang_ten || r.nguoi_tao || '—';
    const noiDung = laNcc ? 'Trả nợ NCC ' + (r.ncc_name || r.ncc_id || '') : 'Thanh toán ĐVVC ' + (r.don_vi_vc || '') + (r.ma_don ? ' · ' + r.ma_don : '');
    const ghi = laNcc ? (r.ghi_chu_duyet || r.kt_ghi_chu) : (r.kt_ghi_chu || r.ghi_chu);
    return {
      id: (laNcc ? 'ncc:' : 'tt:') + r.id, goc: r.id, nguon, ma: r.id, gui_luc: r.created_at,
      noi_dung: noiDung, muc_dich: laNcc ? r.mo_ta : r.ly_do, ghi_chu: ghi, nguoi_de_nghi: nguoi, bo_phan: appNguon, loai: '', nguoi_tao: r.nguoi_tao || '',
      loai_nhan: laNcc ? 'Trả nợ nhà cung cấp' : 'Thanh toán vận chuyển', hach_toan: laNcc ? 'Trả nợ NCC — giảm công nợ' : 'Chi phí phải trả ĐVVC',
      thu_huong: laNcc ? (r.ncc_name || r.ncc_id) : r.don_vi_vc, so_tien: +r.so_tien || 0, can_chi_truoc: null, qua_han_chi: false,
      cho_ngay: soNgay(r.created_at), trang_thai: tt, cap: capCho, cho_toi: s === 'cho_duyet' && KT_ROLES.includes(vaiTro),
      buoc_hien_tai: capCho ? { vai: VAI[capCho], ai: capCho === 'ceo' ? 'duyệt ở app ' + appNguon : 'Phòng Kế toán' } : null, buoc,
      // da_chi_ngoai: DNTT nối từ đề xuất NCC đã được chi ở luồng Trả NCC → KHÔNG cộng tiền lần nữa (tránh đếm đôi, như màn cũ /chi-tap-trung).
      // Chiều ngược lại (BUG đếm đôi 2026-09-25): đề xuất NCC được chi QUA DNTT nối với nó (DNTT.ref_congno = id NCC,
      // DNTT da_chi) — backend đánh da_chi cho CẢ HAI nhưng sổ quỹ chỉ có MỘT phiếu chi (từ DNTT). Vd DNTT-2026-0042 và
      // CN-2026-0392 cùng 70.000.000 ngày 16/09 → trước đây "Đã chi tháng này" cộng 2 lần. Giữ DNTT, NCC coi như chi ngoài.
      chi_ngoai: laNcc ? !!(r.da_chi && nccChiQuaDntt.has(r.id)) : !!(r.da_chi_ngoai && !r.da_chi),
      ngay_chi: r.ngay_chi, tai_khoan_chi: !laNcc && r.da_chi_ngoai && !r.da_chi ? 'Đã chi ở luồng Trả NCC' : laNcc && r.da_chi && nccChiQuaDntt.has(r.id) ? 'Đã chi ở luồng Đề nghị TT (' + nccChiQuaDntt.get(r.id) + ')' : r.tai_khoan_chi,
      don: laNcc ? r.ref_order_id : r.ma_don, dntt_ncc: !laNcc && r.ref_congno ? r.ref_congno : null,
      chung_tu: r.chung_tu_url ? [{ ten: r.chung_tu_url.split('/').pop(), url: r.chung_tu_url }] : [],
      nhat_ky: [{ viec: laNcc ? 'Mua Hàng gửi đề xuất trả NCC' : 'Gửi đề nghị thanh toán', ai: nguoi, luc: r.created_at }]
        .concat(r.kt_duyet_luc ? [{ viec: 'Kế toán ' + (s === 'kt_tu_choi' ? 'từ chối' : 'duyệt') + (r.kt_ghi_chu ? ' — ' + r.kt_ghi_chu : ''), ai: r.kt_duyet_boi_ten || r.kt_duyet_boi, luc: r.kt_duyet_luc }] : [])
        .concat(r.ngay_duyet ? [{ viec: 'Giám đốc ' + (s === 'tu_choi' ? 'từ chối' : 'duyệt') + (laNcc && r.ghi_chu_duyet ? ' — ' + r.ghi_chu_duyet : ''), ai: r.nguoi_duyet_ten || r.nguoi_duyet, luc: r.ngay_duyet }] : [])
        .concat(r.da_chi ? [{ viec: 'Chi tiền qua ' + (r.tai_khoan_chi || '—'), ai: 'Kế toán', luc: r.ngay_chi }] : []),
    };
  }

  let nccChiQuaDntt = new Map();   // id đề xuất NCC → mã DNTT đã chi thay nó
  const CAP_CHO = { cho_manager: 'manager', cho_ketoan: 'ketoan', cho_ceo: 'ceo' };
  /* Ô "Ngày gửi" (màn cũ /duyet-chi có: Tất cả thời gian / Tháng này / Tháng trước / 30 ngày / tự chọn) → [từ, đến] ISO; lọc theo ngày gửi hiển thị ở cột Mã. */
  function khoangGui(q) {
    const h = new Date(), y = h.getFullYear(), m = h.getMonth(), D = (yy, mm, dd) => KD.iso(new Date(yy, mm, dd));
    if (q.thoi_gian === 'thang_nay') return [D(y, m, 1), D(y, m + 1, 0)];
    if (q.thoi_gian === 'thang_truoc') return [D(y, m - 1, 1), D(y, m, 0)];
    if (q.thoi_gian === '30_ngay') return [D(y, m, h.getDate() - 29), KD.iso(h)];
    if (q.thoi_gian === 'tuy_chinh') { const a = q.tu_ngay || '', b = q.den_ngay || ''; return a && b && a > b ? [b, a] : [a, b]; }
    return ['', ''];
  }
  function chuyen(raw, q) {
    nccChiQuaDntt = new Map(dntt.filter((r) => r.da_chi && r.ref_congno).map((r) => [r.ref_congno, r.id]));
    const rows = (raw || []).map(tuDx).concat(dntt.map((r) => tuHaiCap(r, 'de_nghi_tt')), ncc.map((r) => tuHaiCap(r, 'de_xuat_ncc')));
    const thangNay = KD.iso(new Date()).slice(0, 7);
    const o = () => ({ tien: 0, so: 0, theo: {} });
    const tong = { cho_toi: o(), cho_chi: o(), qua_han_chi: o(), da_chi_thang: o() };
    const cong = (k, r) => { tong[k].tien += r.so_tien; tong[k].so++; const t = tong[k].theo[r.nguon] = tong[k].theo[r.nguon] || { so: 0, tien: 0 }; t.so++; t.tien += r.so_tien; };
    rows.forEach((r) => {
      if (r.cho_toi) cong('cho_toi', r);
      if (r.trang_thai === 'cho_chi') cong('cho_chi', r);
      if (r.qua_han_chi) cong('qua_han_chi', r);
      if (r.trang_thai === 'da_chi' && !r.chi_ngoai && String(r.ngay_chi || '').slice(0, 7) === thangNay) cong('da_chi_thang', r);
    });
    daChi = rows.filter((r) => r.trang_thai === 'da_chi' && !r.chi_ngoai).sort((a, b) => String(b.ngay_chi || '').localeCompare(String(a.ngay_chi || '')));
    const boPhan = [...new Set(rows.map((r) => r.bo_phan).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'vi'));

    let loc = rows;
    const tim = (q.tim || '').trim();
    // Tìm cả phần Mục đích (STK, người thụ hưởng người gửi tự ghi) — như ô tìm màn cũ /duyet-chi. Không phân biệt dấu + hoa/thường.
    if (tim) loc = loc.filter((r) => KT.khopTim([r.ma, r.noi_dung, r.muc_dich, r.nguoi_de_nghi, r.bo_phan, r.thu_huong, r.don], tim));
    // Mỗi thẻ số có đúng một lựa chọn lọc cho ra CÙNG tập dòng (BRIEF2): Quá hạn chi / Đã chi tháng này.
    // "Đã chi" loại các DNTT đã chi ở luồng Trả NCC (chi_ngoai) — giống thẻ và khối "Đã chi gần đây"
    // (trước: lọc "Đã chi" 184 đề nghị nhưng "Đã chi gần đây" 181, chênh 3 DNTT = 90.320.000đ đếm đôi).
    // 'tat_ca' = không lọc trạng thái ('' ở link cũ cũng vậy). Chờ từng cấp = bộ lọc "Chờ Manager / Kế Toán / CEO" của màn cũ.
    if (q.trang_thai === 'cho_toi') loc = loc.filter((r) => r.cho_toi);
    else if (CAP_CHO[q.trang_thai]) loc = loc.filter((r) => r.trang_thai === 'cho_duyet' && r.cap === CAP_CHO[q.trang_thai]);
    else if (q.trang_thai === 'cua_toi') loc = loc.filter((r) => !!toiLa && r.nguoi_tao === toiLa);
    else if (q.trang_thai === 'qua_han') loc = loc.filter((r) => r.qua_han_chi);
    else if (q.trang_thai === 'da_chi_thang') loc = loc.filter((r) => r.trang_thai === 'da_chi' && !r.chi_ngoai && String(r.ngay_chi || '').slice(0, 7) === thangNay);
    else if (q.trang_thai === 'da_chi') loc = loc.filter((r) => r.trang_thai === 'da_chi' && !r.chi_ngoai);
    else if (q.trang_thai === 'chi_ngoai') loc = loc.filter((r) => r.chi_ngoai && r.trang_thai === 'da_chi');
    else if (q.trang_thai && q.trang_thai !== 'tat_ca') loc = loc.filter((r) => r.trang_thai === q.trang_thai);
    if (q.nguon) loc = loc.filter((r) => r.nguon === q.nguon);
    if (q.loai) loc = loc.filter((r) => r.loai === q.loai);
    if (q.bo_phan) loc = loc.filter((r) => r.bo_phan === q.bo_phan);
    const [gTu, gDen] = khoangGui(q);
    if (gTu || gDen) loc = loc.filter((r) => { const n = String(r.gui_luc || '').slice(0, 10); return (!gTu || n >= gTu) && (!gDen || n <= gDen); });

    const m = /^(.*)_(asc|desc)$/.exec(String(q.sort || '')) || [null, 'gui', 'desc'];
    const KEY = { gui: 'gui_luc', so_tien: 'so_tien', han: 'can_chi_truoc' }[m[1]] || 'gui_luc', chieu = m[2] === 'asc' ? 1 : -1;
    loc = loc.slice().sort((a, b) => { const x = a[KEY], y = b[KEY]; if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (x < y ? -1 : x > y ? 1 : 0) * chieu; });

    const size = +q.size || 20, soTrang = Math.max(1, Math.ceil(loc.length / size)), trang = Math.min(Math.max(1, +q.page || 1), soTrang);
    return { dong: loc.slice((trang - 1) * size, trang * size), tong, bo_phan: boPhan, tong_dong: loc.length, trang, so_trang: soTrang };
  }
  // Tách theo luồng (đủ cả 3 luồng, kể cả luồng 0đ — giống 3 thẻ của màn cũ /chi-tap-trung) → đưa vào ⓘ cạnh dòng phụ của thẻ.
  const theoNguon = (t) => Object.keys(NGUON).map((k) => { const x = t.theo[k] || { so: 0, tien: 0 }; return NGUON[k][0] + ' ' + KD.tien(x.tien) + ' (' + KD.soDem(x.so) + ')'; }).join(' · ');
  const phuThe = (t, dv, lop) => KD.soDem(t.so) + ' ' + dv + ' ' + KD.tip('Theo luồng: ' + theoNguon(t), lop);

  /* Trạng thái trên URL: bộ lọc bảng chính (khung lo) + các khoá riêng của màn: tab, luồng ở tab Đã chi (dc_nguon),
     khoảng ngày tự chọn (tu_ngay/den_ngay), bộ lọc tab Báo cáo (bc_*). Tháng báo cáo để trống = 'tat_ca'. */
  const THANG_NAY = KD.iso(new Date()).slice(0, 7);
  const MAC = { tim: '', trang_thai: 'cho_toi', nguon: '', loai: '', bo_phan: '', thoi_gian: '', tu_ngay: '', den_ngay: '', page: 1, size: 20, sort: 'gui_desc',
    tab: '', dc_nguon: '', bc_thang: THANG_NAY, bc_pb: '', bc_tt: '', bc_cap: '' };
  function ghiUrl() { KT.url.ghi(ds.st, Object.assign({}, MAC, { ky: 'thang_nay' })); }
  /* Chọn "Ngày gửi" khác "Tự chọn" → bỏ khoảng ngày cũ. Gắn TRƯỚC khung danh sách để chạy trước lượt tải khung kích hoạt. */
  function hienKhoangGui() { const tc = $('dc-thoi_gian').value === 'tuy_chinh'; $('dc-o-tu-ngay').hidden = !tc; $('dc-o-den-ngay').hidden = !tc; }
  $('dc-thoi_gian').addEventListener('change', (e) => {
    if (e.target.value !== 'tuy_chinh') { ds.st.tu_ngay = ''; ds.st.den_ngay = ''; $('dc-tu-ngay').value = ''; $('dc-den-ngay').value = ''; }
    hienKhoangGui();
  });
  const ds = KT.danhSach({
    pfx: 'dc', api: () => '/api/duyet-chi', donVi: 'đề nghị', chuyen,
    macDinh: MAC,
    dong: { cls: (r) => (r.cho_toi ? 'kt-dc-toi' : '') },
    cot: [
      { key: 'gui', nhan: 'Mã', sort: 'so', ve: (r) => H.ma(r.ma) + '<span class="kt-khach__ma">' + KD.ngay(r.gui_luc) + '</span>' },
      { key: 'nd', nhan: 'Nội dung', cls: 'kt-dc-nd', ve: (r) => H.ten(r.noi_dung, NGUON[r.nguon][0] + ' · ' + r.loai_nhan) },
      { key: 'ng', nhan: 'Người đề nghị', cls: 'kt-dc-ng', ve: (r) => H.ten(r.nguoi_de_nghi, r.bo_phan) },
      { key: 'so_tien', nhan: 'Số tiền (VND)', num: true, sort: 'so', cls: 'kt-dc-tien', ve: (r) => KD.tien(r.so_tien) },
      { key: 'tien_trinh', nhan: 'Trạng thái', cls: 'kt-dc-tien-trinh', ve: (r) => pillTT(r) + tienTrinh(r) },
      { key: 'nut', nhan: 'Thao tác', lop: 'kt-dc-thao-tac', ve: nutDong },
    ],
    kpi: {
      cho_toi: (d) => ({ v: H.tienKpi(d.tong.cho_toi.tien), title: KD.tienVnd(d.tong.cho_toi.tien), phu: KD.soDem(d.tong.cho_toi.so) + ' đề nghị chờ bạn' }),
      cho_chi: (d) => ({ v: H.tienKpi(d.tong.cho_chi.tien), title: KD.tienVnd(d.tong.cho_chi.tien), phu: phuThe(d.tong.cho_chi, 'đề nghị') }),
      qua_han: (d) => ({ v: H.tienKpi(d.tong.qua_han_chi.tien), title: KD.tienVnd(d.tong.qua_han_chi.tien), phu: d.tong.qua_han_chi.so ? H.pill('danger', KD.soDem(d.tong.qua_han_chi.so) + ' đề nghị trễ hạn') : H.pill('success', 'Không có') }),
      da_chi: (d) => ({ v: H.tienKpi(d.tong.da_chi_thang.tien), title: KD.tienVnd(d.tong.da_chi_thang.tien), phu: phuThe(d.tong.da_chi_thang, 'khoản', 'kd-tip--trai') }),
    },
    phamVi: () => (loiNguon.length ? 'Không tải được: ' + loiNguon.join(', ') + '.' : ''),
    rong: (d, coLoc) => (coLoc ? ['Không có đề nghị nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Không có đề nghị nào đang chờ bạn duyệt', 'Chọn "Tất cả" ở ô Trạng thái để xem các đề nghị khác.']),
    loi: 'Không tải được danh sách đề nghị chi',
    sauTai: (d) => { veDaChi();
      // Bộ phận đang lọc (từ URL / lần trước) vẫn phải có trong danh sách, nếu không ô hiện "Tất cả" trong khi bảng đang lọc.
      const bp = (d.bo_phan || []).slice(); if (ds.st.bo_phan && !bp.includes(ds.st.bo_phan)) bp.push(ds.st.bo_phan);
      H.napChon($('dc-bo_phan'), bp.map((b) => [b, b]), 'Tất cả', ds.st.bo_phan);
      if (ds.st.thoi_gian !== 'tuy_chinh' && (ds.st.tu_ngay || ds.st.den_ngay)) { ds.st.tu_ngay = ''; ds.st.den_ngay = ''; $('dc-tu-ngay').value = ''; $('dc-den-ngay').value = ''; ghiUrl(); }
      hienKhoangGui();
      $('dc-dem-cho_toi').textContent = KD.soDem(d.tong.cho_toi.so); $('dc-dem-cho_chi').textContent = KD.soDem(d.tong.cho_chi.so); dongBoTab();
      // sauTai chạy TRƯỚC khi khung vẽ bảng → mở panel ở vòng sự kiện sau, khi dòng đã có trong DOM.
      if (u.id && !moLanDau) { moLanDau = true; setTimeout(() => { const tr = document.querySelector('#dc-tbody tr[data-id="' + CSS.escape(u.id) + '"]'); if (tr) tr.click(); }, 0); } },
    panel: {
      ve: (x) => {
        const cac = x.buoc.concat([{ vai: 'Chi tiền', ai: 'Kế toán', trang_thai: x.trang_thai === 'da_chi' || x.trang_thai === 'hoan_tat' ? 'da_duyet' : x.trang_thai === 'cho_chi' ? 'cho' : 'chua', luc: x.ngay_chi }]);
        const dangO = cac.findIndex((b) => b.trang_thai === 'cho' || b.trang_thai === 'tu_choi');
        const step = '<ol class="kd-stepper kt-dc-buoc" data-buoc="' + cac.length + '" aria-label="Các bước duyệt">' + cac.map((b, i) => { const c = b.trang_thai === 'da_duyet' ? 'is-done' : b.trang_thai === 'tu_choi' ? 'is-fail' : i === dangO ? 'is-current' : 'is-todo';
          return '<li class="kd-step ' + c + '"' + (i === dangO ? ' aria-current="step"' : '') + ' title="' + esc(b.ai || '') + '"><span class="kd-step__dot" aria-hidden="true"></span><span class="kd-step__label">' + esc(b.trang_thai === 'tu_choi' ? b.vai + ' từ chối' : b.vai) + '</span><span class="kd-step__time">' + (b.luc ? KD.ngay(b.luc).slice(0, 5) : '') + '</span></li>'; }).join('') + '</ol>';
        const kv = [['Số tiền', KD.tienVnd(x.so_tien), true], ['Nguồn', esc(NGUON[x.nguon][0] + ' · ' + x.loai_nhan)], ['Người thụ hưởng', esc(x.thu_huong || '—')],
          x.don ? [x.nguon === 'de_xuat_ncc' ? 'Đơn mua' : 'Mã đơn', esc(x.don)] : null, x.dntt_ncc ? ['Từ đề xuất NCC', esc(x.dntt_ncc)] : null,
          ['Cần chi trước', x.can_chi_truoc ? KD.ngay(x.can_chi_truoc) + (x.qua_han_chi ? ' · quá hạn' : '') : '—'], ['Người đề nghị', esc(x.nguoi_de_nghi + (x.bo_phan ? ' · ' + x.bo_phan : ''))],
          x.trang_thai === 'da_chi' ? ['Đã chi', KD.ngay(x.ngay_chi) + ' · ' + esc(x.tai_khoan_chi || '—')] : null];
        return H.dauPanel(NGUON[x.nguon][2], (TT[x.trang_thai] || ['muted'])[0], x.ma, esc(x.noi_dung), pillTT(x))
          + step
          + H.khoi('bi-cash-stack', 'Số tiền và thụ hưởng', H.kv(kv))
          + (x.muc_dich || x.ghi_chu ? H.khoi('bi-card-text', 'Mục đích / diễn giải', (x.muc_dich ? '<p class="kt-dc-md">' + esc(x.muc_dich) + '</p>' : '') + (x.ghi_chu ? '<p class="kd-meta">Ghi chú: ' + esc(x.ghi_chu) + '</p>' : '')) : '')
          + H.khoi('bi-paperclip', 'Chứng từ kèm', x.chung_tu.length ? '<ul class="kd-files">' + x.chung_tu.map((f) => '<li class="kd-file"><span class="ico-tile ico-tile--sm" aria-hidden="true"><i class="bi ' + (/\.pdf$/i.test(f.ten) ? 'bi-filetype-pdf' : 'bi-image') + '"></i></span><div><a class="kd-file__ten" href="' + esc(f.url) + '" target="_blank" rel="noopener">' + esc(f.ten) + '</a></div></li>').join('') + '</ul>' : KD.khoiRong('Chưa đính kèm chứng từ', 'Nên yêu cầu hoá đơn / hợp đồng trước khi duyệt.'))
          + H.khoi('bi-clock-history', 'Nhật ký', '<ol class="kd-timeline">' + x.nhat_ky.map((n) => '<li><div class="kd-tl"><div><div class="kd-strong">' + esc(n.viec) + '</div><div class="kd-muted">' + KD.ngayGio(n.luc) + '</div></div><span class="kd-tl__who">' + esc(n.ai || '') + '</span></div></li>').join('') + '</ol>');
      },
      sau: (el) => { const s = el.querySelector('.kd-stepper'); if (s) s.style.setProperty('--kd-buoc', s.dataset.buoc); },
      nut: (x) => (x.cho_toi ? '<button type="button" class="kd-btn kd-btn--primary kd-btn--grow" data-xl="duyet" data-id="' + esc(x.id) + '"><i class="bi bi-check2" aria-hidden="true"></i>Duyệt</button><button type="button" class="kd-btn kd-btn--grow" data-xl="tu_choi" data-id="' + esc(x.id) + '"><i class="bi bi-x-lg" aria-hidden="true"></i>Từ chối</button>'
        : chiDuoc(x) ? '<button type="button" class="kd-btn kd-btn--primary kd-btn--grow" data-xl="chi" data-id="' + esc(x.id) + '"><i class="bi bi-cash-coin" aria-hidden="true"></i>Chi tiền</button>' + (tuChoiThem(x) ? '<button type="button" class="kd-btn kd-btn--grow" data-xl="tu_choi" data-id="' + esc(x.id) + '"><i class="bi bi-x-lg" aria-hidden="true"></i>Từ chối</button>' : '') : (tuChoiThem(x) ? '<button type="button" class="kd-btn kd-btn--grow" data-xl="tu_choi" data-id="' + esc(x.id) + '"><i class="bi bi-x-lg" aria-hidden="true"></i>Từ chối</button>' : '')),
    },
    menu: (r) => [
      r.cho_toi ? { nhan: 'Duyệt', icon: 'bi-check2', onClick: () => moXl('duyet', r) } : null,
      r.cho_toi ? { nhan: 'Từ chối', icon: 'bi-x-lg', danger: true, onClick: () => moXl('tu_choi', r) } : null,
      chiDuoc(r) ? { nhan: 'Chi tiền', icon: 'bi-cash-coin', onClick: () => moChi(r) } : null,
      tuChoiThem(r) ? { nhan: 'Từ chối', icon: 'bi-x-lg', danger: true, onClick: () => moXl('tu_choi', r) } : null,
      { nhan: 'Xem chi tiết', icon: 'bi-eye', onClick: () => { const tr = document.querySelector('#dc-tbody tr[data-id="' + CSS.escape(r.id) + '"]'); if (tr) tr.click(); } },
    ].filter(Boolean),
  });
  let moLanDau = false;
  /* Khoảng ngày tự chọn: 2 ô ngày không thuộc khung (không đếm riêng — đã đếm ở ô "Ngày gửi"), tự ghi vào trạng thái + URL. */
  $('dc-tu-ngay').value = ds.st.tu_ngay || ''; $('dc-den-ngay').value = ds.st.den_ngay || ''; hienKhoangGui();
  [['dc-tu-ngay', 'tu_ngay'], ['dc-den-ngay', 'den_ngay']].forEach(([id, k]) => $(id).addEventListener('change', (e) => {
    ds.st[k] = e.target.value; ds.st.page = 1; ds.dongPanel(); ds.tai(); }));
  const taiLai = async () => { await taiPhu(); ds.tai(); taiBaoCao(); };

  /* ── Duyệt / từ chối — mỗi nguồn một API thật ── */
  const dlg = $('dc-dlg-duyet'); let dang = null, hanhDong = 'duyet';
  const SAU = { manager: 'Kế toán', ketoan: 'Giám đốc', ceo: 'Kế toán chi tiền' };
  function moXl(hd, r) {
    dang = r; hanhDong = hd; const tc = hd === 'tu_choi';
    // BẢN VÁ 30/09/2026: từ chối khi dòng đang Ở "Chờ chi" (đã duyệt xong, r.cho_toi=false) là
    // ĐƯỜNG MỚI (API tu-choi-truoc-chi), khác hẳn từ chối cấp 1 khi cho_toi=true (kt-reject) —
    // đổi câu thông báo cho đúng ngữ cảnh, không nói "chờ cấp tiếp theo" khi thực ra đã xong hết.
    const oChoChi = tc && !r.cho_toi && r.trang_thai === 'cho_chi';
    const oCapKhac = tc && !r.cho_toi && r.trang_thai === 'cho_duyet';   // đang chờ cấp khác — từ chối thay
    $('dc-duyet-td').textContent = (tc ? 'Từ chối ' : 'Duyệt ') + r.ma + '?';
    const sau = r.nguon === 'de_xuat_chi' ? (SAU[r.cap] || 'cấp tiếp theo') : 'Giám đốc (duyệt ở app ' + r.bo_phan + ')';
    $('dc-duyet-nd').textContent = oChoChi ? 'Đề nghị ĐÃ ĐƯỢC DUYỆT, chưa chi. Từ chối sẽ trả về ' + (r.nguoi_de_nghi || 'người lập') + ' — họ sửa, bổ sung rồi gửi lại từ đầu.'
      : oCapKhac ? 'Đề nghị đang chờ ' + ((r.buoc_hien_tai && r.buoc_hien_tai.vai) || 'cấp khác') + ' duyệt. Bạn từ chối thay thì đề nghị trả về ' + (r.nguoi_de_nghi || 'người lập') + ' — họ sửa, bổ sung rồi gửi lại từ đầu.'
      : tc ? 'Đề nghị trả về ' + r.nguoi_de_nghi + '. Họ sửa, bổ sung rồi gửi lại từ đầu.'
      : KD.tienVnd(r.so_tien) + ' — ' + r.noi_dung + '. Sau bạn, đề nghị chuyển ' + sau + '.';
    $('dc-duyet-gc-nhan').innerHTML = tc ? 'Lý do từ chối <span class="kd-field__req" aria-hidden="true">*</span>' : 'Ghi chú (không bắt buộc)';
    $('dc-duyet-gc').value = ''; $('dc-duyet-ok').textContent = tc ? 'Từ chối' : 'Duyệt'; $('dc-duyet-ok').classList.toggle('kd-btn--danger', tc); $('dc-duyet-ok').classList.toggle('kd-btn--primary', !tc);
    KD.moHopThoai(dlg);
  }
  function goiDuyet(r, tc, gc) {
    const id = encodeURIComponent(r.goc);
    if (r.nguon === 'de_xuat_chi' && tc && !r.cho_toi) return KD.api('/api/de-xuat-chi/' + id + '/tu-choi-truoc-chi', KD.JSON_POST({ ly_do: gc }));   // đã duyệt xong, chưa chi
    if (r.nguon === 'de_xuat_chi') return KD.api('/api/duyet-chi/' + id + '/duyet', Object.assign(KD.JSON_POST({ trang_thai: tc ? 'tu_choi' : 'da_duyet', nhan_xet_duyet: gc }), { method: 'PUT' }));
    const goc = r.nguon === 'de_nghi_tt' ? '/api/de-nghi-tt/' : '/api/ncc-de-xuat/';
    // Từ chối khi đã ở "Chờ chi" (không phải cho_toi) → API MỚI tu-choi-truoc-chi, KHÁC kt-reject
    // (kt-reject chỉ nhận trang_thai='cho_duyet', backend trả 409 nếu gọi nhầm lúc đã 'duyet').
    const duong = tc && !r.cho_toi ? '/tu-choi-truoc-chi' : (tc ? '/kt-reject' : '/kt-approve');
    return KD.api(goc + id + duong, KD.JSON_POST(tc ? { ly_do: gc } : { kt_ghi_chu: gc || null }));
  }
  $('dc-form-duyet').addEventListener('submit', async (e) => {
    e.preventDefault(); const gc = $('dc-duyet-gc').value.trim(), tc = hanhDong === 'tu_choi';
    if (tc && !gc) { $('dc-duyet-gc').focus(); return KD.baoLoiHopThoai(dlg, 'Ghi lý do từ chối.'); }
    const nut = $('dc-duyet-ok'); nut.disabled = true;
    try { await goiDuyet(dang, tc, gc); dlg.close(); ds.dongPanel(); window.showToast && window.showToast('ok', (tc ? 'Đã từ chối ' : 'Đã duyệt ') + dang.ma); await taiLai(); }
    catch (err) { KD.baoLoiHopThoai(dlg, err.message); } finally { nut.disabled = false; }
  });

  /* ── Chi tiền — cả 3 API nhận {tai_khoan (TÊN TK tiền/ngân hàng), ngay_chi, ghi_chu}; khoản mục hạch toán do backend tự chọn theo
     luồng. Danh sách TK lấy từ GET /api/tai-khoan (TK ngân hàng/tiền mặt thật, đúng chuỗi mà sổ quỹ dùng), KHÔNG PHẢI mã TT200. ── */
  const dlgChi = $('dc-dlg-chi');
  let dsTk = null;
  async function napTk() { if (!dsTk) dsTk = (await KD.api('/api/tai-khoan')).filter((t) => t.active); return dsTk; }
  async function moChi(r) {
    dang = r; $('dc-chi-td').textContent = 'Chi tiền ' + r.ma;
    $('dc-chi-tt').innerHTML = '<dt>Nội dung</dt><dd>' + esc(r.noi_dung) + '</dd><dt>Người thụ hưởng</dt><dd>' + esc(r.thu_huong || '—') + '</dd><dt class="is-dam">Số tiền</dt><dd>' + KD.tienVnd(r.so_tien) + '</dd>';
    $('dc-chi-no').value = r.hach_toan; $('dc-chi-gc').value = '';
    $('dc-chi-ngay').value = KD.iso(new Date());   // mặc định hôm nay, kế toán lùi được
    const sel = $('dc-chi-co');
    try { const tk = await napTk(); sel.innerHTML = '<option value="">— Chọn tài khoản —</option>' + tk.map((t) => '<option value="' + esc(t.ten_tk) + '">' + esc(t.ten_tk + (t.so_tk ? ' · ' + t.so_tk : '')) + '</option>').join(''); }
    catch (e) { sel.innerHTML = '<option value="">Không tải được danh sách tài khoản</option>'; }
    KD.moHopThoai(dlgChi);
  }
  $('dc-form-chi').addEventListener('submit', async (e) => {
    e.preventDefault(); const tk = $('dc-chi-co').value, ngay = $('dc-chi-ngay').value;
    if (!tk) { $('dc-chi-co').focus(); return KD.baoLoiHopThoai(dlgChi, 'Chọn tài khoản chi tiền.'); }
    if (!ngay) { $('dc-chi-ngay').focus(); return KD.baoLoiHopThoai(dlgChi, 'Nhập ngày chi.'); }
    if (ngay > KD.iso(new Date())) { $('dc-chi-ngay').focus(); return KD.baoLoiHopThoai(dlgChi, 'Ngày chi không được ở tương lai.'); }
    const nut = $('dc-chi-ok'); nut.disabled = true;
    const goc = { de_xuat_chi: '/api/duyet-chi/', de_nghi_tt: '/api/de-nghi-tt/', de_xuat_ncc: '/api/ncc-de-xuat/' }[dang.nguon];
    try { await KD.api(goc + encodeURIComponent(dang.goc) + '/chi', KD.JSON_POST({ tai_khoan: tk, ngay_chi: ngay, ghi_chu: $('dc-chi-gc').value.trim() || null }));
      dlgChi.close(); ds.dongPanel(); window.showToast && window.showToast('ok', 'Đã chi ' + dang.ma + ' qua ' + tk + ' — đã lên sổ quỹ'); await taiLai(); }
    catch (err) { KD.baoLoiHopThoai(dlgChi, 'Chưa chi được: ' + err.message); } finally { nut.disabled = false; }
  });
  $('dc-tbody').addEventListener('click', (e) => { const b = e.target.closest('[data-nut]'); if (!b) return;
    const r = ds.dsHien().find((x) => String(x.id) === b.dataset.id); if (!r) return;
    if (b.dataset.nut === 'chi') moChi(r); else if (b.dataset.nut === 'tu_choi') moXl('tu_choi', r); else moXl('duyet', r); });
  document.addEventListener('click', (e) => { const b = e.target.closest('#dc-p-nut [data-xl]'); if (!b) return; const r = ds.dsHien().find((x) => String(x.id) === b.dataset.id); if (!r) return; if (b.dataset.xl === 'chi') moChi(r); else moXl(b.dataset.xl, r); });

  /* ── Đã chi gần đây — thay tab "Đã chi" của màn cũ /chi-tap-trung: gộp 3 luồng, mới nhất trước, có phân trang + lọc luồng. ── */
  let dcTrang = 1; const DC_CO = 20;
  function veDaChi() {
    const ng = $('dc-dc-nguon').value, ds2 = ng ? daChi.filter((r) => r.nguon === ng) : daChi;
    const so = Math.max(1, Math.ceil(ds2.length / DC_CO)); dcTrang = Math.min(dcTrang, so);
    const tong = ds2.reduce((t, r) => t + r.so_tien, 0);
    const thangNay = KD.iso(new Date()).slice(0, 7), thang = ds2.filter((r) => String(r.ngay_chi || '').slice(0, 7) === thangNay);
    $('dc-dc-tong').innerHTML = KD.soDem(ds2.length) + ' khoản · <b>' + KD.tienVnd(tong) + '</b> '
      + KD.tip('Tháng này ' + KD.soDem(thang.length) + ' khoản · ' + KD.tienVnd(thang.reduce((t, r) => t + r.so_tien, 0)) + ' (= thẻ "Đã chi tháng này"). Khoản chi ở luồng nối nhau (Đề nghị TT ↔ Trả NCC) chỉ tính một lần.');
    if (!ds2.length) { $('dc-dc-cuon').hidden = true; $('dc-dc-tt').innerHTML = KD.khoiRong('Chưa có khoản nào đã chi', ''); $('dc-dc-foot').hidden = true; return; }
    $('dc-dc-tt').innerHTML = ''; $('dc-dc-cuon').hidden = false; $('dc-dc-foot').hidden = false;
    $('dc-dc-tb').innerHTML = ds2.slice((dcTrang - 1) * DC_CO, dcTrang * DC_CO).map((r) => '<tr data-id="' + esc(r.id) + '" tabindex="0"><td>' + KD.ngay(r.ngay_chi) + '</td>'
      + '<td>' + H.ma(r.ma) + '<span class="kt-khach__ma">' + esc(NGUON[r.nguon][0]) + '</span></td><td class="kt-dc-nd">' + H.ten(r.noi_dung, r.nguoi_de_nghi + (r.bo_phan ? ' · ' + r.bo_phan : '')) + '</td><td class="kt-dc-ng">' + esc(r.thu_huong || '—') + '</td><td>' + esc(r.tai_khoan_chi || '—') + '</td><td class="num kt-dc-tien">' + KD.tien(r.so_tien) + '</td></tr>').join('');
    $('dc-dc-hien').textContent = 'Hiển thị ' + KD.soDem((dcTrang - 1) * DC_CO + 1) + ' - ' + KD.soDem(Math.min(dcTrang * DC_CO, ds2.length)) + ' / ' + KD.soDem(ds2.length) + ' khoản';
    KD.phanTrang($('dc-dc-trang'), dcTrang, so, (p) => { dcTrang = p; veDaChi(); });
  }
  $('dc-dc-nguon').value = ds.st.dc_nguon || '';
  $('dc-dc-nguon').addEventListener('change', (e) => { dcTrang = 1; ds.st.dc_nguon = e.target.value; ghiUrl(); veDaChi(); });
  $('dc-dc-tb').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-id]'); if (!tr) return;
    // Mở đúng khoản trên bảng chính: bỏ các lọc khác (trạng thái "Tất cả"), tìm theo mã.
    ['nguon', 'loai', 'bo_phan', 'thoi_gian', 'tu_ngay', 'den_ngay'].forEach((k) => { ds.st[k] = ''; if ($('dc-' + k)) $('dc-' + k).value = ''; });
    $('dc-tu-ngay').value = ''; $('dc-den-ngay').value = '';
    ds.st.trang_thai = 'tat_ca'; $('dc-trang_thai').value = 'tat_ca'; ds.st.tim = tr.querySelector('.kd-strong').textContent; $('dc-tim').value = ds.st.tim; ds.st.page = 1;
    u.id = tr.dataset.id; moLanDau = false; ds.st.tab = ''; hienNgan('ds'); ds.tai(); $('dc-main').scrollIntoView({ behavior: 'smooth' }); });

  /* ── Tab: Chờ duyệt / Chờ chi = bảng chính với ô lọc Trạng thái tương ứng; Đã chi, Báo cáo = ngăn riêng. ── */
  const TAB_LOC = { cho_duyet: 'cho_toi', cho_chi: 'cho_chi' };
  const tabs = [...document.querySelectorAll('#dc-tabs [role="tab"]')];
  function chonTab(key) { tabs.forEach((t) => { const la = t.dataset.tab === key; t.setAttribute('aria-selected', String(la)); t.tabIndex = la ? 0 : -1; }); }
  function hienNgan(ngan) { ['ds', 'da_chi', 'bao_cao'].forEach((k) => { $('dc-p-' + k).hidden = k !== ngan; }); if (ngan === 'ds') chonTab(ds.st.trang_thai === 'cho_chi' ? 'cho_chi' : 'cho_duyet'); }
  // Bảng chính đang hiện: tab sáng theo ô lọc Trạng thái (người dùng đổi lọc bằng tay cũng khớp).
  function dongBoTab() { if (!$('dc-p-ds').hidden) chonTab(ds.st.trang_thai === 'cho_chi' ? 'cho_chi' : 'cho_duyet'); }
  function moTab(key) {
    if (TAB_LOC[key]) {
      ds.st.tab = '';
      if (ds.st.trang_thai !== TAB_LOC[key]) { ds.st.trang_thai = TAB_LOC[key]; $('dc-trang_thai').value = ds.st.trang_thai; ds.st.page = 1; ds.dongPanel(); ds.tai(); } else ghiUrl();
      hienNgan('ds');
    } else { ds.st.tab = key; ghiUrl(); ds.dongPanel(); hienNgan(key); chonTab(key); }
  }
  // Mở lại link / F5 khi đang ở tab Đã chi hoặc Báo cáo → hiện đúng tab đó.
  if (ds.st.tab === 'da_chi' || ds.st.tab === 'bao_cao') { hienNgan(ds.st.tab); chonTab(ds.st.tab); } else ds.st.tab = '';
  tabs.forEach((t) => t.addEventListener('click', () => moTab(t.dataset.tab)));
  $('dc-tabs').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true'), n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    moTab(n.dataset.tab); n.focus();
  });

  /* ── Báo cáo đề xuất chi — GET /api/duyet-chi/report (y như màn cũ /bao-cao/duyet-chi: tổng đơn, tổng tiền, đang chờ, SLA,
     theo phòng ban, theo loại chi; lọc tháng / phòng ban / cấp duyệt). ── */
  const bcThang = $('dc-bc-thang'), bcPb = $('dc-bc-pb'), bcCap = $('dc-bc-cap'), bcTt = $('dc-bc-trang-thai');
  /* Bộ lọc báo cáo nằm trên URL (bc_thang · bc_pb · bc_tt · bc_cap). Tháng để trống = mọi tháng → ghi 'tat_ca'. */
  bcThang.value = ds.st.bc_thang === 'tat_ca' ? '' : (/^\d{4}-\d{2}$/.test(ds.st.bc_thang || '') ? ds.st.bc_thang : THANG_NAY);
  bcCap.value = ds.st.bc_cap || ''; bcTt.value = ds.st.bc_tt || '';
  /* Danh sách phòng ban cộng dồn qua các lần tải (trước: chỉ nạp lần đầu theo tháng mặc định → phòng không có đề xuất tháng này
     thì không bao giờ chọn được). Bỏ "(Không rõ)": API gom phong_ban rỗng dưới nhãn này nhưng lọc phong_ban='(Không rõ)' ra 0 đơn. */
  const bcDsPb = new Set(ds.st.bc_pb ? [ds.st.bc_pb] : []);
  const KHONG_RO = '(Không rõ)';
  function napBcPb() { const giu = ds.st.bc_pb || ''; bcPb.innerHTML = '<option value="">Tất cả</option>' + [...bcDsPb].sort((a, b) => a.localeCompare(b, 'vi')).map((k) => '<option value="' + esc(k) + '">' + esc(k) + '</option>').join(''); bcPb.value = giu; }
  napBcPb();
  let bcLuot = 0;
  async function taiBaoCao() {
    const l = ++bcLuot, q = new URLSearchParams();
    if (bcThang.value) q.set('thang', bcThang.value); if (bcPb.value) q.set('phong_ban', bcPb.value); if (bcTt.value) q.set('trang_thai', bcTt.value); if (bcCap.value) q.set('approval_level', bcCap.value);
    $('dc-bc-tt').innerHTML = KD.KHUNG_TAI; $('dc-bc-nd').hidden = true;
    try {
      const d = await KD.api('/api/duyet-chi/report?' + q); if (l !== bcLuot) return;
      const sm = d.summary || {}, pb = d.by_phong_ban || {}, lc = d.by_loai_chi || {};
      const truoc = bcDsPb.size; Object.keys(pb).forEach((k) => { if (k !== KHONG_RO) bcDsPb.add(k); }); if (bcDsPb.size !== truoc) napBcPb();
      $('dc-bc-tt').innerHTML = '';
      if (!sm.total) { $('dc-bc-tt').innerHTML = KD.khoiRong('Không có đề xuất chi nào trong phạm vi lọc', 'Đổi tháng hoặc bỏ bớt điều kiện lọc.'); return; }
      const o = (t, v, phu) => '<div><dt>' + esc(t) + '</dt><dd>' + v + (phu ? ' <small>' + phu + '</small>' : '') + '</dd></div>';
      $('dc-bc-so').innerHTML = o('Tổng đơn', KD.soDem(sm.total)) + o('Tổng tiền', KD.tien(sm.total_amount), 'VND') + o('Đang chờ duyệt', KD.soDem((sm.by_trang_thai || {}).cho_duyet || 0))
        + o('Thời gian duyệt TB', d.sla_hours_avg != null ? KD.soDem(d.sla_hours_avg) + ' giờ' : '—', d.sla_hours_avg != null ? KD.soDem(d.sla_sample_size) + ' đơn' : '');
      const dsPb = Object.entries(pb).sort((a, b) => b[1].amount - a[1].amount), dsLc = Object.entries(lc).sort((a, b) => b[1].amount - a[1].amount);
      const cong = (ds, k) => ds.reduce((t, [, v]) => t + (v[k] || 0), 0);
      $('dc-bc-pb-tb').innerHTML = dsPb.map(([k, v]) => '<tr><td>' + esc(k) + '</td><td class="num">' + KD.soDem(v.total) + '</td><td class="num">' + KD.soDem(v.da_duyet || 0) + '</td><td class="num">' + KD.soDem(v.cho_duyet || 0) + '</td><td class="num">' + KD.soDem(v.tu_choi || 0) + '</td><td class="num kd-strong">' + KD.tien(v.amount) + '</td></tr>').join('')
        + '<tr class="kt-dc-bc__cong"><th scope="row">Cộng</th><td class="num">' + KD.soDem(cong(dsPb, 'total')) + '</td><td class="num">' + KD.soDem(cong(dsPb, 'da_duyet')) + '</td><td class="num">' + KD.soDem(cong(dsPb, 'cho_duyet')) + '</td><td class="num">' + KD.soDem(cong(dsPb, 'tu_choi')) + '</td><td class="num kd-strong">' + KD.tien(cong(dsPb, 'amount')) + '</td></tr>';
      $('dc-bc-lc-tb').innerHTML = dsLc.map(([k, v]) => '<tr><td>' + esc(LOAI_CHI[k] || v.label || k) + '</td><td class="num">' + KD.soDem(v.total) + '</td><td class="num kd-strong">' + KD.tien(v.amount) + '</td></tr>').join('')
        + '<tr class="kt-dc-bc__cong"><th scope="row">Cộng</th><td class="num">' + KD.soDem(cong(dsLc, 'total')) + '</td><td class="num kd-strong">' + KD.tien(cong(dsLc, 'amount')) + '</td></tr>';
      $('dc-bc-nd').hidden = false;
    } catch (e) { if (l === bcLuot) KD.khoiLoi($('dc-bc-tt'), 'Không tải được báo cáo đề xuất chi', e, taiBaoCao); }
  }
  [bcThang, bcPb, bcTt, bcCap].forEach((el) => el.addEventListener('change', () => {
    ds.st.bc_thang = bcThang.value || 'tat_ca'; ds.st.bc_pb = bcPb.value; ds.st.bc_tt = bcTt.value; ds.st.bc_cap = bcCap.value; ghiUrl(); taiBaoCao(); }));

  taiLai();
})();
