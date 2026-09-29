/* kt-thu-chi.js (dot3b) — Doanh thu · Chi phí · Chi phí cố định, nối API THẬT.
   ─────────────────────────────────────────────────────────────────────────
   GAP THẬT so với bản thiết kế / README mục 4.13:
   - KHÔNG có `/api/thu-chi?tab=...` gộp sẵn. 3 API thật, đều trả MẢNG PHẲNG (không
     "tong", không phân trang server):
       GET /api/doanh-thu?tu_ngay&den_ngay&loai&nv_kinh_doanh&limit(≤2000)&offset
       GET /api/chi-phi?tu_ngay&den_ngay&loai_chi_phi&quy&nhom&limit(≤2000)&offset
       GET /api/co-dinh?tu_thang&den_thang&loai_chi_phi&lap_lai&nhom&limit(≤2000)&offset
     → mỗi bảng tự tìm-kiếm/tính tổng/phân trang ở trình duyệt, trên tối đa 2000 dòng mỗi kỳ
       (giới hạn `limit` của API thật — kỳ có hơn 2000 dòng sẽ bị cắt bớt, hiếm khi xảy ra
       với 2 bảng này nhưng cần biết).
   - `DoanhThu` KHÔNG tách VAT, KHÔNG có số chứng từ/khách hàng — chỉ là "phiếu thu doanh
     số" (ngày, loại, số tiền, mã đơn, nguồn, hình thức TT). Bỏ 2 cột Chưa thuế/VAT của bản
     thiết kế (không có số thật), đổi cột "Khách hàng" → "Nguồn" (nguon_hien: nhãn luồng tự
     động hay KT tự nhập), thêm cột "Hình thức TT" (loai_thanh_toan) — đều là trường thật.
   - `ChiPhiCoDinh` là DANH MỤC khoản chi lặp (config), KHÔNG lưu vết "đã ghi sổ tháng nào" —
     bỏ hẳn khái niệm trạng thái da_ghi/tre_han/chua_den_ngay của bản thiết kế (không có dữ
     liệu thật để tính); bảng đổi thành danh mục + số tiền/tháng áp dụng cho kỳ đang chọn.
   - Dropdown "Loại chi phí" nạp động từ /api/loai-chi-phi (danh mục thật) thay vì 9 giá trị
     hard-code của bản thiết kế (không khớp tên loại thật trong DB).
   - Ghi tay (F1, 28/09/2026): form Doanh thu / Chi phí / Chi phí cố định dùng đúng API POST/PUT/DELETE
     của màn cũ /app — xem khối "Form ghi tay" phía dưới.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-thu-chi')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  // Ghi chú phạm vi số liệu: ⓘ cạnh nhãn thẻ số thay cho đoạn chữ dưới hàng thẻ (macro the_so kiểu 'strip' chưa nhận tip).
  ['dt', 'cp', 'cd'].forEach((p) => { $(p + '-pham-vi').hidden = true; });
  // Thẻ "Tiền thu từ khách" — cùng tên + số với thẻ ở Tổng quan (tổng tab Doanh thu: cọc + thanh toán).
  [['dt', 'tong', 'Tiền cọc + thanh toán đã ghi sổ trong kỳ; doanh thu kế toán chuẩn xem ở Kết quả kinh doanh'],
    ['cp', 'tong', 'Chi phí đã ghi sổ trong kỳ, không gồm giá vốn và chi phí cố định. TK theo nhóm: 641 bán hàng, 642 quản lý, 635 tài chính, 811 khác.'],
    ['cd', 'tong', 'Số tiền phân bổ vào tháng cuối của kỳ đang chọn, cùng quy tắc báo cáo Kết quả kinh doanh: khoản phân bổ N tháng chia đều rồi dừng, khoản Hằng tháng lặp từ tháng bắt đầu.'],
    ['cd', 'moi', 'Các khoản có tháng bắt đầu rơi vào tháng này, cộng nguyên số tiền gốc (chưa chia phân bổ).', 'kd-tip--trai'],
  ].forEach(([p, k, t, lop]) => { const n = document.querySelector('#' + p + '-kpi [data-kpi="' + k + '"] .kd-kpi__label'); if (n && !n.querySelector('.kd-tip')) n.insertAdjacentHTML('beforeend', KD.tip(t, lop)); });
  const MAC = { tab: 'doanh_thu', ky: 'thang_nay', tu: '', den: '' };
  const u = Object.assign({}, MAC, KT.url.doc());
  if (!['doanh_thu', 'chi_phi', 'co_dinh'].includes(u.tab)) u.tab = 'doanh_thu';
  u.ky = KT.napKy($('tc-ky'), u.ky);   // ô kỳ dùng chung 3 bảng; mỗi bảng tự gắn sự kiện (KT.ganKy trong kt-danh-sach.js)
  const ky0 = { ky: u.ky, tu: u.tu, den: u.den };
  /* Bộ lọc riêng từng bảng giữ trên URL với tiền tố bảng (dt_tim, dt_loai, dt_ht, dt_sort, cp_tim…) — bản trước chỉ
     giữ tab + kỳ nên F5 là mất ô tìm / loại / hình thức. */
  const LOC_URL = { dt: ['tim', 'loai', 'ht', 'sort'], cp: ['tim', 'loai', 'sort'] };
  const batDau = (p) => Object.assign({}, ky0, ...LOC_URL[p].filter((k) => u[p + '_' + k]).map((k) => ({ [k]: u[p + '_' + k] })));
  /* Sắp xếp theo cột bấm trên đầu bảng (st.sort = '<cột>_<asc|desc>'). Bản trước luôn xếp ngày giảm dần nên bấm
     "Số tiền" chỉ đổi mũi tên, bảng không đổi. */
  function xep(list, sort) {
    const s = sort || 'ngay_desc', i = s.lastIndexOf('_'), cot = s.slice(0, i), chieu = s.slice(i + 1) === 'asc' ? 1 : -1;
    const gt = cot === 'ngay' ? (r) => r.ngay || '' : (r) => Number(r.so_tien || 0);
    return list.sort((a, b) => { const x = gt(a), y = gt(b); return (x < y ? -1 : x > y ? 1 : a.id - b.id) * chieu; });
  }
  let tab = u.tab;
  /* Sửa / Xoá từng dòng: PUT/DELETE của cả 3 API (doanh_thu, chi_phi, co_dinh) gắn require_ceo_thuchi → chỉ
     admin/ceo/assistant_ceo. Kế toán (manager/kt) chỉ TẠO MỚI → không vẽ cột Thao tác để khỏi bấm rồi bị 403. */
  const CEO = KD.coQuyen('ceo');
  const cotThaoTac = (nhanDong) => (CEO ? [{ key: 'act', nhan: 'Thao tác', act: true, nhanDong }] : []);
  const oThaoTac = (o) => (CEO ? o.concat([{ html: '' }]) : o);
  const menuSuaXoa = (sua, xoa) => (CEO ? (r) => [{ nhan: 'Sửa', icon: 'bi-pencil', onClick: () => sua(r) }, { nhan: 'Xoá', icon: 'bi-trash', danger: true, onClick: () => xoa(r) }] : null);

  /* Phân trang + tìm-kiếm ở trình duyệt (API thật không hỗ trợ page/size/tim) */
  function phanTrangTim(list, q, truongTim) {
    const t = (q.tim || '').trim();
    const filtered = t ? list.filter((r) => KT.khopTim(truongTim(r), t)) : list;   // không phân biệt dấu + hoa/thường
    const size = +q.size || 20, page = Math.max(1, +q.page || 1);
    const tong_dong = filtered.length, so_trang = Math.max(1, Math.ceil(tong_dong / size)), trang = Math.min(page, so_trang);
    return { dong: filtered.slice((trang - 1) * size, trang * size), tong_dong, trang, so_trang,
      loc: filtered.length !== list.length, tien: () => filtered.reduce((s, r) => s + Number(r.so_tien || 0), 0) };
  }
  const tongKy = (d) => 'Kỳ ' + KD.ngay(d.ky.tu) + ' – ' + KD.ngay(d.ky.den);

  /* ── Tab Doanh thu ── */
  /* Hình thức TT của phiếu doanh thu → 'coc' | 'tt' | 'khac' — cùng quy tắc SQL của /api/doanh-thu/by-month. */
  let loaiDt = [];
  const htTT = (r) => { const v = (r.loai_thanh_toan || '').trim().toLowerCase(); return v.indexOf('cọc') !== -1 ? 'coc' : v === 'thanh toán' ? 'tt' : 'khac'; };

  /* ── Doanh thu theo tháng — toàn bộ lịch sử (GET /api/doanh-thu/by-month, như màn cũ) ── */
  let thangDs = null;
  function thangDangChon() { const k = dt.khoang(); if (!k.tu || !k.den || k.tu.slice(0, 7) !== k.den.slice(0, 7)) return ''; return k.tu.slice(0, 7); }
  function veThang() {
    if (!thangDs) return;
    const chon = thangDangChon(), max = Math.max(1, ...thangDs.map((m) => m.tong));
    const tMM = (t) => t.slice(5) + '/' + t.slice(0, 4);
    if (!thangDs.length) { $('dt-thang-ds').innerHTML = ''; $('dt-thang-tt').innerHTML = KD.khoiRong('Chưa có doanh thu nào', ''); return; }
    $('dt-thang-bieu').innerHTML = thangDs.slice().sort((a, b) => (a.thang < b.thang ? -1 : 1)).map((m) => '<button type="button" class="kt-tc-bieu__hang' + (m.thang === chon ? ' is-chon' : '') + '" data-thang="' + m.thang + '" tabindex="-1" title="' + tMM(m.thang) + ': ' + esc(KD.tienVnd(m.tong)) + ' — ' + m.count + ' phiếu">'
      + '<span class="kt-tc-bieu__nhan">' + tMM(m.thang) + '</span><span class="kt-tc-bieu__ray"><span class="kt-tc-bieu__thanh" style="width:' + Math.round(m.tong / max * 100) + '%"></span></span>'
      + '<span class="kt-tc-bieu__so">' + esc(KD.tienGon(m.tong)) + '</span></button>').join('');
    $('dt-thang-ds').innerHTML = thangDs.slice().sort((a, b) => (a.thang < b.thang ? 1 : -1)).map((m) => '<tr data-thang="' + m.thang + '" tabindex="0"' + (m.thang === chon ? ' class="is-chon" aria-current="true"' : '') + '>'
      + '<td class="kd-strong">' + tMM(m.thang) + '</td><td class="num">' + KD.soDem(m.count) + '</td><td class="num">' + KT.tienSo(m.coc) + '</td><td class="num">' + KT.tienSo(m.tt) + '</td><td class="num">' + KT.tienSo(m.tong - m.coc - m.tt) + '</td><td class="num kd-strong">' + KD.tien(m.tong) + '</td></tr>').join('');
    const S = (k) => thangDs.reduce((a, m) => a + m[k], 0);
    $('dt-thang-tong').innerHTML = '<tr><th scope="row">Cộng ' + KD.soDem(thangDs.length) + ' tháng</th><td class="num">' + KD.soDem(S('count')) + '</td><td class="num">' + KD.tien(S('coc')) + '</td><td class="num">' + KD.tien(S('tt')) + '</td><td class="num">' + KD.tien(S('tong') - S('coc') - S('tt')) + '</td><td class="num">' + KD.tien(S('tong')) + '</td></tr>';
    $('dt-thang-phu').textContent = 'Tổng cộng ' + KD.tienVnd(S('tong'));
  }
  async function napThang() {
    $('dt-thang-tt').innerHTML = ''; $('dt-thang-ds').innerHTML = KT.hangCho(5, 4);
    try { thangDs = (await KD.api('/api/doanh-thu/by-month')).map((r) => ({ thang: r.thang, tong: +r.tong || 0, coc: +r.coc || 0, tt: +r.tt || 0, count: +r.count || 0 })); veThang(); }
    catch (e) { $('dt-thang-ds').innerHTML = ''; KD.khoiLoi($('dt-thang-tt'), 'Không tải được doanh thu theo tháng', e, napThang); }
  }
  /* Bấm một tháng → chọn đúng "Tháng MM/YYYY" trong ô kỳ (bản trước giả lập Tuỳ chỉnh + 2 lần đổi ngày → tải 2-3 lần). */
  function chonThang(th) {
    KT.napKy($('tc-ky'), th);   // nạp lại để có cả tháng ngoài danh sách 24 tháng
    $('tc-ky').dispatchEvent(new Event('change'));
    $('dt-cuon').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  $('dt-thang-ds').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-thang]'); if (tr) chonThang(tr.dataset.thang); });
  $('dt-thang-ds').addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-thang]')) { e.preventDefault(); chonThang(e.target.dataset.thang); } });
  $('dt-thang-bieu').addEventListener('click', (e) => { const b = e.target.closest('[data-thang]'); if (b) chonThang(b.dataset.thang); });
  const dt = KT.danhSach({
    pfx: 'dt', kyPfx: 'tc', url: false, batDau: batDau('dt'), ghiUrl: () => ghiUrl(), dangHien: () => tab === 'doanh_thu', donVi: 'phiếu',
    api: (q) => '/api/doanh-thu?' + KT.url.qs({ tu_ngay: q.tu, den_ngay: q.den, loai: q.loai || undefined, limit: 2000 }),
    macDinh: { ky: 'thang_nay', tu: '', den: '', tim: '', loai: '', ht: '', page: 1, size: 20, sort: 'ngay_desc' },
    dong: { id: (r) => r.id },
    chuyen: (raw, q) => {
      let list = (raw || []).slice();
      if (!q.loai) loaiDt = [...new Set(list.map((r) => r.loai).filter(Boolean))].sort();
      if (q.ht) list = list.filter((r) => htTT(r) === q.ht);
      xep(list, q.sort);
      const p = phanTrangTim(list, q, (r) => [r.ma_don, r.mo_ta, r.ghi_chu, r.loai, r.nv_kinh_doanh, r.ngan_hang, r.nguon_hien]);
      const S = (f) => list.reduce((s, r) => s + f(r), 0);
      // Cùng quy tắc với /api/doanh-thu/by-month (ILIKE '%cọc%' / ILIKE 'thanh toán' — không phân biệt hoa thường).
      const dat_coc = S((r) => (htTT(r) === 'coc' ? Number(r.so_tien || 0) : 0));
      const thanh_toan = S((r) => (htTT(r) === 'tt' ? Number(r.so_tien || 0) : 0));
      const khac = S((r) => (htTT(r) === 'khac' ? Number(r.so_tien || 0) : 0));
      return Object.assign({ ky: { tu: q.tu, den: q.den }, tong: { tong: S((r) => Number(r.so_tien || 0)), so_dong: list.length, dat_coc, thanh_toan, khac,
        so_coc: list.filter((r) => htTT(r) === 'coc').length, so_tt: list.filter((r) => htTT(r) === 'tt').length, so_khac: list.filter((r) => htTT(r) === 'khac').length },
        loc_tim: p.loc, tien_loc: p.tien() }, p);
    },
    cot: [
      // Đợt 4: gộp Ngày + Số phiếu; Hình thức TT + Tài khoản nhận → bảng 6 cột thay vì 8.
      { key: 'ngay', nhan: 'Ngày · số phiếu', sort: 'so', ve: (r) => KD.ngay(r.ngay) + '<span class="kt-khach__ma kd-strong">DT-' + esc(r.id) + '</span>' },
      { key: 'don', nhan: 'Đơn hàng / NV kinh doanh', ve: (r) => (r.ma_don ? esc(r.ma_don) : '<span class="kd-muted">—</span>') + (r.nv_kinh_doanh ? '<span class="kt-khach__ma">' + esc(r.nv_kinh_doanh) + '</span>' : '') },
      { key: 'nguon', nhan: 'Loại / nguồn', ve: (r) => '<span class="kt-khach__ten">' + esc(r.loai || 'Khác') + '</span>' + (r.nguon_hien ? '<span class="kd-chip">' + esc(r.nguon_hien) + '</span>' : H.pill('muted', 'Tự nhập')) },
      { key: 'dg', nhan: 'Diễn giải', ve: (r) => '<span class="kt-tc-dg" title="' + esc(r.mo_ta || r.ghi_chu || r.loai || '') + '">' + esc(r.mo_ta || r.ghi_chu || r.loai || '—') + '</span>' + (r.mo_ta && r.ghi_chu && r.ghi_chu !== r.mo_ta ? '<span class="kt-khach__ma kt-tc-phu" title="' + esc(r.ghi_chu) + '">' + esc(r.ghi_chu) + '</span>' : '') },
      { key: 'ht', nhan: 'Hình thức · TK nhận', ve: (r) => (r.loai_thanh_toan ? '<span class="kd-chip kd-chip--xam">' + esc(r.loai_thanh_toan) + '</span>' : '—') + '<span class="kt-khach__ma">' + (r.ngan_hang ? esc(r.ngan_hang) : '—') + '</span>' },
      { key: 'tong', nhan: 'Số tiền (VND)', num: true, sort: 'so', cls: 'kd-strong', ve: (r) => KD.tien(r.so_tien) },
    ].concat(cotThaoTac((r) => 'DT-' + r.id)),
    menu: menuSuaXoa((r) => moDt(r), (r) => xoaDt(r)),
    kpi: {
      tong: (d) => ({ v: H.tienKpi(d.tong.tong), title: KD.tienVnd(d.tong.tong), phu: tongKy(d) }),
      so_dong: (d) => ({ v: H.dem(d.tong.so_dong, 'phiếu'), phu: 'Theo bộ lọc' }),
      dat_coc: (d) => ({ v: H.tienKpi(d.tong.dat_coc), title: KD.tienVnd(d.tong.dat_coc), phu: KD.soDem(d.tong.so_coc) + ' phiếu đặt cọc' }),
      // Đặt cọc + Thanh toán (+ hình thức Khác nếu có) = Doanh thu đã ghi nhận — phần Khác ghi ngay ở dòng phụ.
      thanh_toan: (d) => ({ v: H.tienKpi(d.tong.thanh_toan), title: KD.tienVnd(d.tong.thanh_toan), phu: KD.soDem(d.tong.so_tt) + ' phiếu thanh toán'
        + (d.tong.so_khac ? KD.tip('Còn ' + KD.soDem(d.tong.so_khac) + ' phiếu hình thức khác: ' + KD.tienVnd(d.tong.khac) + '.', 'kd-tip--trai') : '') }),
    },
    sauTai: () => {
      // Không có API danh mục loại doanh thu → lấy các loại có trong kỳ (khi chưa lọc loại), giữ lựa chọn đang lọc.
      if (loaiDt.length) H.napChon($('dt-loai'), loaiDt.concat(dt.st.loai && loaiDt.indexOf(dt.st.loai) < 0 ? [dt.st.loai] : []).map((x) => [x, x]), 'Tất cả', dt.st.loai);
      veThang();
    },
    cong: (d) => oThaoTac(d.loc_tim ? [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' phiếu khớp ô tìm' + KD.tip('Cả kỳ có ' + KD.soDem(d.tong.so_dong) + ' phiếu — xem thẻ số phía trên.'), span: 5 }, { html: KD.tien(d.tien_loc), num: true }]
      : [{ html: 'Cộng ' + KD.soDem(d.tong.so_dong) + ' phiếu', span: 5 }, { html: KD.tien(d.tong.tong), num: true }]),
    rong: (d, coLoc) => (coLoc ? ['Không có phiếu nào khớp ô tìm', 'Thử từ khoá khác.'] : ['Kỳ này chưa ghi nhận doanh thu', 'Doanh thu tự lên khi đơn hàng hoàn thành hoặc kế toán ghi tay.']),
    loi: 'Không tải được doanh thu',
  });
  /* ── Tab Chi phí ── */
  const NHOM_TK = { ban_hang: '641', quan_ly: '642', tai_chinh: '635', khac: '811' };
  const NHOM_NHAN = { ban_hang: 'Bán hàng', quan_ly: 'Quản lý DN', tai_chinh: 'Tài chính', khac: 'Khác' };
  const cp = KT.danhSach({
    pfx: 'cp', kyPfx: 'tc', url: false, batDau: batDau('cp'), ghiUrl: () => ghiUrl(), dangHien: () => tab === 'chi_phi', donVi: 'dòng',
    api: (q) => '/api/chi-phi?' + KT.url.qs({ tu_ngay: q.tu, den_ngay: q.den, loai_chi_phi: q.loai || undefined, limit: 2000 }),
    macDinh: { ky: 'thang_nay', tu: '', den: '', tim: '', loai: '', page: 1, size: 20, sort: 'ngay_desc' },
    dong: { id: (r) => r.id },
    chuyen: (raw, q) => {
      let list = (raw || []).slice();
      xep(list, q.sort);
      const p = phanTrangTim(list, q, (r) => [r.ten_khoan, r.mo_ta, r.ghi_chu, r.nguoi_chi, r.loai_chi_phi, r.phong_ban, r.ma_don, r.ngan_hang, r.quy, r.nguon]);
      const S = (f) => list.reduce((s, r) => s + f(r), 0);
      const theoLoai = {};
      list.forEach((r) => { const k = r.loai_chi_phi || 'Khác'; theoLoai[k] = (theoLoai[k] || 0) + Number(r.so_tien || 0); });
      let lonNhat = null;
      Object.keys(theoLoai).forEach((k) => { if (!lonNhat || theoLoai[k] > lonNhat.so_tien) lonNhat = { ten: k, so_tien: theoLoai[k] }; });
      return Object.assign({ ky: { tu: q.tu, den: q.den }, tong: { so_tien: S((r) => Number(r.so_tien || 0)), so_dong: list.length, lon_nhat: lonNhat }, loc_tim: p.loc, tien_loc: p.tien() }, p);
    },
    cot: [
      // Đợt 4: gộp Ngày + Số chứng từ; Loại + Nguồn; Người chi + Chi từ → bảng 5 cột thay vì 8.
      { key: 'ngay', nhan: 'Ngày · số CT', sort: 'so', ve: (r) => KD.ngay(r.ngay) + '<span class="kt-khach__ma kd-strong">CP-' + esc(r.id) + '</span>' },
      { key: 'dg', nhan: 'Tên khoản / diễn giải', ve: (r) => { const phu = [r.ten_khoan && r.mo_ta, r.ghi_chu, r.ma_don && 'Đơn ' + r.ma_don].filter(Boolean).join(' · ');
        return '<span class="kt-tc-dg kd-strong" title="' + esc(r.ten_khoan || r.mo_ta || r.ghi_chu || '') + '">' + esc(r.ten_khoan || r.mo_ta || r.ghi_chu || '—') + '</span>' + (phu ? '<span class="kt-khach__ma kt-tc-phu" title="' + esc(phu) + '">' + esc(phu) + '</span>' : ''); } },
      { key: 'loai', nhan: 'Loại · nguồn', ve: (r) => '<span class="kd-chip kd-chip--xam">' + esc(r.loai_chi_phi || NHOM_NHAN[r.nhom_chi_phi] || 'Khác') + '</span><span class="kt-khach__ma">TK ' + esc(NHOM_TK[r.nhom_chi_phi] || '811') + ' · ' + esc(r.nguon && r.nguon !== 'KT tự nhập' ? r.nguon : 'Tự nhập') + '</span>' },
      { key: 'nguoi', nhan: 'Người chi · chi từ', ve: (r) => (r.nguoi_chi ? esc(r.nguoi_chi) : '<span class="kd-muted">—</span>')
        + (r.phong_ban ? '<span class="kt-khach__ma">' + esc(r.phong_ban) + '</span>' : '')
        + '<span class="kt-khach__ma"><i class="bi bi-wallet2" aria-hidden="true"></i> ' + (r.ngan_hang ? esc(r.ngan_hang) : '—') + (r.quy ? ' · ' + esc(r.quy) : '') + '</span>' },
      { key: 'so_tien', nhan: 'Số tiền (VND)', num: true, sort: 'so', cls: 'kd-strong', ve: (r) => KD.tien(r.so_tien) },
    ].concat(cotThaoTac((r) => 'CP-' + r.id)),
    menu: menuSuaXoa((r) => moCp(r), (r) => xoaCp(r)),
    kpi: {
      tong: (d) => ({ v: H.tienKpi(d.tong.so_tien), title: KD.tienVnd(d.tong.so_tien), phu: tongKy(d) }),
      lon_nhat: (d) => (d.tong.lon_nhat ? { v: H.tienKpi(d.tong.lon_nhat.so_tien), title: KD.tienVnd(d.tong.lon_nhat.so_tien), phu: esc(d.tong.lon_nhat.ten) + (d.tong.so_tien ? ' · ' + KD.phanTram(d.tong.lon_nhat.so_tien / d.tong.so_tien * 100) : '') } : { v: null, phu: 'Chưa có chi phí' }),
      so_dong: (d) => ({ v: H.dem(d.tong.so_dong, 'dòng'), phu: 'Theo bộ lọc' }),
    },
    sauTai: (d) => {
      if (!cp._loaiNap) { cp._loaiNap = true;
        KD.api('/api/loai-chi-phi').then((ds2) => { H.napChon($('cp-loai'), (ds2 || []).filter((x) => x.active !== false).map((x) => [x.ten, x.ten]), 'Tất cả', cp.st.loai); }).catch(() => {}); }
    },
    cong: (d) => oThaoTac(d.loc_tim ? [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' dòng khớp ô tìm' + KD.tip('Cả kỳ có ' + KD.soDem(d.tong.so_dong) + ' dòng — xem thẻ số phía trên.'), span: 4 }, { html: KD.tien(d.tien_loc), num: true }]
      : [{ html: 'Cộng ' + KD.soDem(d.tong.so_dong) + ' dòng', span: 4 }, { html: KD.tien(d.tong.so_tien), num: true }]),
    rong: (d, coLoc) => (coLoc ? ['Không có chi phí nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Kỳ này chưa ghi sổ chi phí nào', 'Bấm "Ghi nhận chi phí" để thêm.']),
    loi: 'Không tải được chi phí',
  });

  /* ── Tab Chi phí cố định (danh mục — KHÔNG có trạng thái "đã ghi sổ tháng này" thật) ──
     Bug cũ (audit 2026-09-25): hàm này tự chế lại quy tắc phân bổ, KHÁC với quy tắc
     thật app đã dùng để tính P&L (services/pl_calculator.py:_sum_co_dinh_phan_bo) —
       1) Ưu tiên sai thứ tự: check `lap_lai` TRƯỚC `so_thang_phan_bo`, nên 1 khoản
          "lặp lại" + "phân bổ 3 tháng" (vd thuê showroom 6-7-8, so_thang_phan_bo=3,
          lap_lai=true) bị hiểu thành LẶP MÃI ở NGUYÊN so_tien_thang, thay vì đúng ra
          phải DỪNG sau 3 tháng và mỗi tháng chỉ ghi so_tien_thang/3.
       2) Dùng `ngay_bat_dau` (cột prorated_by_day riêng, có thể lệch hẳn — vd 1 dòng
          ngay_bat_dau=2025-05-01 dù thang_bat_dau=2026-05-01) thay vì `thang_bat_dau`
          (đúng cột app dùng cho phương pháp "duong_thang" — mọi dòng trong DB hiện
          đều phuong_phap_phan_bo='duong_thang').
       3) Dòng phân bổ nhiều tháng hiển thị/cộng NGUYÊN so_tien_thang thay vì chia
          đều cho so_thang_phan_bo → cộng dồn N lần số tiền thật (N = so_thang_phan_bo).
     Hậu quả đo được: tổng "Chi phí cố định" tháng 09/2026 hiển thị 166.500.000đ,
     đúng ra chỉ 25.000.000đ (gấp 6.66 lần thực tế). Fix: port đúng thuật toán từ
     pl_calculator, trả về số tiền GHI NHẬN đúng tháng (hoặc null nếu tháng đó
     khoản chi không áp dụng) thay vì chỉ true/false. */
  function soTienGhiNhanThang(r, thang) {
    const bd = (r.thang_bat_dau || '').slice(0, 7);
    if (!bd) return null;
    const soThang = r.so_thang_phan_bo || 1;
    const soTien = Number(r.so_tien_thang || 0);
    if (soThang > 1) {
      // Phân bổ đều N tháng rồi DỪNG (áp dụng cả lap_lai=true lẫn false).
      let [y, m] = bd.split('-').map(Number); m += soThang - 1;
      while (m > 12) { m -= 12; y += 1; }
      const ketThuc = y + '-' + String(m).padStart(2, '0');
      return (thang >= bd && thang <= ketThuc) ? soTien / soThang : null;
    }
    if (r.lap_lai) return thang >= bd ? soTien : null;        // lặp mãi từ start
    return thang === bd ? soTien : null;                       // 1 lần đúng tháng start
  }
  const cd = KT.danhSach({
    pfx: 'cd', kyPfx: 'tc', url: false, batDau: ky0, ghiUrl: () => ghiUrl(), dangHien: () => tab === 'co_dinh', donVi: 'khoản', khongTrang: true,
    macDinh: { ky: 'thang_nay', tu: '', den: '', page: 1, size: 100, sort: '' },
    api: () => '/api/co-dinh?' + KT.url.qs({ limit: 2000 }),
    chuyen: (raw, q) => {
      const thang = (q.den || q.tu || new Date().toISOString().slice(0, 10)).slice(0, 7);
      const list = [];
      (raw || []).forEach((r) => {
        const ghiNhan = soTienGhiNhanThang(r, thang);
        if (ghiNhan != null) list.push(Object.assign({}, r, { so_tien_ghi_nhan: ghiNhan }));
      });
      list.sort((a, b) => (a.ten_khoan || '').localeCompare(b.ten_khoan || ''));
      const tong_thang = list.reduce((s, r) => s + Number(r.so_tien_ghi_nhan || 0), 0);
      const lapLai = list.filter((r) => r.lap_lai).length;
      // Màn cũ /app#co-dinh chỉ liệt kê khoản có thang_bat_dau rơi vào tháng và cộng NGUYÊN so_tien_thang
      // (chưa chia phân bổ) — giữ lại con số đó ở thẻ "Khai báo mới trong tháng" để đối chiếu.
      const moi = (raw || []).filter((r) => (r.thang_bat_dau || '').slice(0, 7) === thang);
      return { thang, dong: list, tong: { tong_thang, so_khoan: list.length, lap_lai: lapLai, moi_so: moi.length, moi_tien: moi.reduce((s, r) => s + Number(r.so_tien_thang || 0), 0) } };
    },
    cot: [
      { key: 'ten', nhan: 'Khoản chi', ve: (r) => H.ten(r.ten_khoan || '(chưa đặt tên)', r.ghi_chu || '') },
      // Đợt 4: cột "Tài khoản" gộp làm dòng phụ của "Loại chi phí".
      { key: 'loai', nhan: 'Loại chi phí', ve: (r) => '<span class="kd-chip kd-chip--xam">' + esc(r.loai_chi_phi || NHOM_NHAN[r.nhom_chi_phi] || 'Khác') + '</span><span class="kt-khach__ma">TK ' + esc(NHOM_TK[r.nhom_chi_phi] || '811') + '</span>' },
      { key: 'ngay', nhan: 'Bắt đầu', ve: (r) => esc((r.thang_bat_dau || '').slice(5, 7) + '/' + (r.thang_bat_dau || '').slice(0, 4)) },
      { key: 'so_tien', nhan: 'Số tiền/tháng (VND)', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.so_tien_ghi_nhan) + (r.so_thang_phan_bo > 1 ? '<span class="kt-khach__ma">' + KD.tien(r.so_tien_thang) + ' / ' + r.so_thang_phan_bo + ' tháng</span>' : '') },
      { key: 'lap', nhan: 'Lặp lại', ve: (r) => (r.so_thang_phan_bo > 1 ? H.pill('muted', 'Phân bổ ' + r.so_thang_phan_bo + ' tháng') : r.lap_lai ? H.pill('success', 'Hằng tháng') : H.pill('muted', 'Một lần')) },
      { key: 'nguoi', nhan: 'Người tạo', ve: (r) => (r.created_by ? esc(r.created_by) : '<span class="kd-muted">—</span>') },
    ].concat(cotThaoTac((r) => r.ten_khoan || 'khoản #' + r.id)),
    menu: menuSuaXoa((r) => moCd(r), (r) => xoaCd(r)),
    kpi: {
      tong: (d) => ({ v: H.tienKpi(d.tong.tong_thang), title: KD.tienVnd(d.tong.tong_thang), phu: KD.soDem(d.tong.so_khoan) + ' khoản · tháng ' + d.thang.slice(5) + '/' + d.thang.slice(0, 4) }),
      so_khoan: (d) => ({ v: H.dem(d.tong.so_khoan, 'khoản'), phu: 'Đang áp dụng tháng ' + d.thang.slice(5) + '/' + d.thang.slice(0, 4) }),
      lap_lai: (d) => ({ v: H.dem(d.tong.lap_lai, 'khoản'), phu: 'Lặp mỗi tháng từ tháng bắt đầu' }),
      moi: (d) => ({ v: H.tienKpi(d.tong.moi_tien), title: KD.tienVnd(d.tong.moi_tien), phu: KD.soDem(d.tong.moi_so) + ' khoản · tiền gốc' }),
    },
    sauTai: (d) => { $('tc-dem-tre').textContent = ''; },
    cong: (d) => oThaoTac([{ html: 'Cộng ' + KD.soDem(d.tong.so_khoan) + ' khoản', span: 3 }, { html: KD.tien(d.tong.tong_thang), num: true }, { html: '', span: 2 }]),
    rong: () => ['Chưa có khoản chi phí cố định nào áp dụng tháng này', 'Bấm "Thêm chi phí cố định" để khai báo tiền thuê, internet, bảo hiểm…'],
    loi: 'Không tải được chi phí cố định',
  });

  /* ══ Form ghi tay — ĐÚNG API + trường của màn cũ /app (modal-dt/submitDoanhThu, modal-cp/submitChiPhi,
     modal-cd/submitCoDinh); router lo tác dụng phụ y như cũ:
       POST /api/doanh-thu → ketoan.doanh_thu + phiếu thu Sổ quỹ (DT-id) + cộng da_tra công nợ theo mã đơn.
       POST /api/chi-phi   → ketoan.chi_phi_phat_sinh + phiếu chi Sổ quỹ (CP-id); chặn chi âm số dư (assert_du_chi);
                             nhóm/TK tự suy từ loại (nhom_default). Loại "Ứng Lương" + người chi → HCNS trừ lương.
       POST /api/co-dinh   → ketoan.chi_phi_co_dinh (P&L tự phân bổ); không ghi Sổ quỹ.
     Như bản cũ: không gửi tai_khoan_id / cong_no_ncc_id (không tự lập bút toán kép). PUT/DELETE chỉ CEO (ở trên). ══ */
  // Khớp hcns/app/routers/payroll.py: WHERE loai_chi_phi = 'Ứng Lương' … GROUP BY TRIM(nguoi_chi) → mã NV theo họ tên.
  const LOAI_UNG_LUONG = 'Ứng Lương';
  const laUngLuong = (v) => String(v || '').trim().normalize('NFC') === LOAI_UNG_LUONG.normalize('NFC');
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  const docPhanTram = (el) => { const n = parseFloat(String(el.value || '').replace(',', '.').replace(/[^\d.]/g, '')); return isNaN(n) ? 0 : n; };
  const giaTri = (id) => $(id).value.trim() || null;
  const opt = (v, t) => '<option value="' + esc(v) + '">' + esc(t == null ? v : t) + '</option>';
  /* Đặt giá trị ô chọn; giá trị không còn trong danh mục (tài khoản ngừng dùng, NV đã nghỉ…) thì thêm tạm để khi SỬA
     không âm thầm đổi thành rỗng (màn cũ mất giá trị ở chỗ này). */
  function datChon(sel, v) {
    v = v == null ? '' : String(v);
    if (v && ![...sel.options].some((o) => o.value === v)) sel.insertAdjacentHTML('beforeend', opt(v));
    sel.value = v;
  }
  // Nhớ tài khoản / quỹ chọn lần trước — tiện riêng từng máy (kế toán nhập ~46 chi phí/tháng, gần như cùng quỹ + TK).
  const NHO = 'kt-thu-chi:';
  const nho = {
    doc: (k) => { try { return localStorage.getItem(NHO + k) || ''; } catch (e) { return ''; } },
    ghi: (k, v) => { try { if (v) localStorage.setItem(NHO + k, v); } catch (e) { /* trình duyệt chặn lưu cục bộ */ } },
  };
  const coChon = (sel, v) => v && [...sel.options].some((o) => o.value === v);
  const ngayMacDinh = (bang) => { const k = bang.khoang(), hom = KD.iso(new Date()); return k.den && k.den < hom ? k.den : hom; };
  const ngoaiKy = (bang, ngay) => { const k = bang.khoang(); return (k.tu && ngay < k.tu) || (k.den && ngay > k.den); };
  const tienSua = (el, cu) => { const n = docSo(el); return cu != null && Math.round(Number(cu)) === n ? cu : n; };   // giữ số lẻ cũ nếu không sửa tiền
  const guiLen = (url, body, sua) => KD.api(url, Object.assign(KD.JSON_POST(body), sua ? { method: 'PUT' } : {}));
  const baoXong = (msg) => { if (window.showToast) window.showToast('ok', msg); };
  const ghiChuKy = (bang, ngay) => (ngoaiKy(bang, ngay) ? ' — ngày ' + KD.ngay(ngay) + ' nằm ngoài kỳ đang xem' : '');
  ['tc-dt-tien', 'tc-cp-tien'].forEach((id) => $(id).addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; }));

  /* Danh mục cho form — nạp một lần khi mở form lần đầu (cùng nguồn màn cũ: /api/meta, /api/loai-chi-phi, HCNS). */
  let dmHua = null, dm = null;
  function napDm() {
    dmHua = dmHua || Promise.all([
      KD.api('/api/meta'),
      KD.api('/api/loai-chi-phi'),
      KD.api('/api/external/departments').then((r) => (r && r.data) || []).catch(() => []),
      KD.api('/api/external/employees?active=true').then((r) => (r && r.data) || []).catch(() => []),
    ]).then(([meta, lcp, pb, nv]) => { dm = { meta: meta || {}, lcp: (lcp || []).filter((x) => x.active !== false), pb, nv: nv.filter((n) => n.ho_ten) }; return dm; });
    dmHua.catch(() => { dmHua = null; });   // lỗi mạng → lần mở sau thử lại
    return dmHua;
  }
  const nvOpt = (n) => opt(n.ho_ten, n.ho_ten + (n.chuc_vu ? ' (' + n.chuc_vu + ')' : ''));
  const tkOpt = () => (dm.meta.tai_khoan_nh || []).map((t) => opt(t.ten_tk, t.ten_tk + (t.loai === 'tien_mat' ? ' (tiền mặt)' : ''))).join('');
  function veLoaiCp(sel, nhom) {
    const ds = dm.lcp.filter((r) => !nhom || r.nhom_default === nhom);
    const cu = sel.value;
    sel.innerHTML = opt('', '— Chọn loại chi phí —') + ds.map((r) => opt(r.ten, r.ten + (nhom ? '' : ' · ' + (NHOM_NHAN[r.nhom_default] || 'Khác')))).join('');
    if (ds.some((r) => r.ten === cu)) sel.value = cu;
  }
  /* Mở form: nạp danh mục trước (nút tạm khoá), lỗi thì báo, không mở hộp trống. */
  async function chuanBi(nut) {
    if (nut) nut.disabled = true;
    try { await napDm(); return true; }
    catch (e) { if (window.showToast) window.showToast('err', 'Không tải được danh mục để mở form: ' + e.message); return false; }
    finally { if (nut) nut.disabled = false; }
  }

  /* ── Doanh thu ── */
  const dlgDt = $('tc-dt-dlg');
  let suaDt = null;
  async function moDt(r) {
    if (!(await chuanBi($('tc-them')))) return;
    suaDt = r || null;
    const m = dm.meta, kd = dm.nv.filter((n) => /kinh\s*doanh|^kd$/i.test(n.phong_ban || ''));
    $('tc-dt-loai').innerHTML = opt('', '— Chọn loại —') + (m.loai_doanh_thu || []).map((x) => opt(x)).join('');
    $('tc-dt-ht').innerHTML = opt('', '— Chọn hình thức —') + (m.loai_thanh_toan || []).map((x) => opt(x)).join('');
    $('tc-dt-tk').innerHTML = opt('', '— Chọn tài khoản —') + tkOpt();
    $('tc-dt-nv').innerHTML = opt('', '— Không gắn —') + (kd.length ? kd : dm.nv).map(nvOpt).join('');   // như màn cũ: NV phòng Kinh doanh
    $('tc-dt-td').textContent = r ? 'Sửa doanh thu DT-' + r.id : 'Ghi nhận doanh thu';
    $('tc-dt-ngay').value = r ? r.ngay : ngayMacDinh(dt);
    datChon($('tc-dt-loai'), r ? r.loai : '');
    $('tc-dt-tien').value = r && KD.so(r.so_tien) ? KD.tien(r.so_tien) : '';
    datChon($('tc-dt-ht'), r ? r.loai_thanh_toan : '');
    datChon($('tc-dt-tk'), r ? r.ngan_hang : (coChon($('tc-dt-tk'), nho.doc('tk_thu')) ? nho.doc('tk_thu') : ''));
    datChon($('tc-dt-nv'), r ? r.nv_kinh_doanh : '');
    $('tc-dt-ma').value = (r && r.ma_don) || '';
    $('tc-dt-gc').value = (r && r.ghi_chu) || '';
    KD.moHopThoai(dlgDt);
  }
  $('tc-dt-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const s = suaDt, body = { ngay: $('tc-dt-ngay').value, loai: $('tc-dt-loai').value, so_tien: tienSua($('tc-dt-tien'), s && s.so_tien),
      nv_kinh_doanh: giaTri('tc-dt-nv'), ma_don: giaTri('tc-dt-ma'), ngan_hang: giaTri('tc-dt-tk'), loai_thanh_toan: giaTri('tc-dt-ht'), ghi_chu: giaTri('tc-dt-gc') };
    const loi = (id, msg) => { $(id).focus(); KD.baoLoiHopThoai(dlgDt, msg); };
    if (!body.ngay) return loi('tc-dt-ngay', 'Chọn ngày.');
    if (!body.loai) return loi('tc-dt-loai', 'Chọn loại doanh thu.');
    if (!Number(body.so_tien)) return loi('tc-dt-tien', 'Nhập số tiền lớn hơn 0.');
    // Màn cũ không có lựa chọn trống ở 2 ô này (luôn gửi một giá trị) → bắt chọn; dòng cũ vốn để trống thì cho giữ trống.
    if (!body.loai_thanh_toan && !(s && !s.loai_thanh_toan)) return loi('tc-dt-ht', 'Chọn hình thức thanh toán.');
    if (!body.ngan_hang && !(s && !s.ngan_hang)) return loi('tc-dt-tk', 'Chọn tài khoản nhận tiền.');
    const nut = $('tc-dt-luu'); nut.disabled = true;
    try {
      const r = await guiLen(s ? '/api/doanh-thu/' + s.id : '/api/doanh-thu', body, s);
      if (!s) nho.ghi('tk_thu', body.ngan_hang);
      dlgDt.close();
      baoXong((s ? 'Đã cập nhật' : 'Đã ghi') + ' doanh thu DT-' + r.id + ' — ' + KD.tienVnd(r.so_tien) + ghiChuKy(dt, r.ngay));
      dt.tai(); napThang();
    } catch (err) { KD.baoLoiHopThoai(dlgDt, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Chi phí phát sinh ── */
  const dlgCp = $('tc-cp-dlg');
  let suaCp = null;
  function doiLoaiCp() {
    const ten = $('tc-cp-loai').value, r = dm.lcp.find((x) => x.ten === ten), ung = laUngLuong(ten), nhom = r ? r.nhom_default : 'khac';
    // Router tự suy nhóm từ loại (_resolve_nhom: loại không có trong danh mục → 'khac' / TK 811).
    $('tc-cp-tk').textContent = ten ? 'Hạch toán TK ' + (NHOM_TK[nhom] || '811') + ' · ' + (NHOM_NHAN[nhom] || 'Khác') : '';
    ['tc-cp-ky-o', 'tc-cp-nc-sao', 'tc-cp-nc-tip'].forEach((id) => { $(id).hidden = !ung; });
  }
  function veNguoiChi(giu, ep) {
    const pb = $('tc-cp-pb').value, ds = pb ? dm.nv.filter((n) => n.phong_ban === pb) : dm.nv;
    $('tc-cp-nc').innerHTML = opt('', '— Chọn nhân viên —') + ds.map(nvOpt).join('');
    if (ep) datChon($('tc-cp-nc'), giu); else if (coChon($('tc-cp-nc'), giu)) $('tc-cp-nc').value = giu;
  }
  async function moCp(r) {
    if (!(await chuanBi($('tc-them')))) return;
    suaCp = r || null;
    const m = dm.meta;
    $('tc-cp-td').textContent = r ? 'Sửa chi phí CP-' + r.id : 'Ghi nhận chi phí';
    $('tc-cp-ngay').value = r ? r.ngay : ngayMacDinh(cp);
    $('tc-cp-tien').value = r && KD.so(r.so_tien) ? KD.tien(r.so_tien) : '';
    $('tc-cp-nhom').value = '';
    $('tc-cp-loai').value = ''; veLoaiCp($('tc-cp-loai'), '');
    datChon($('tc-cp-loai'), r ? r.loai_chi_phi : '');
    const ky = r && /^\d{4}-\d{2}$/.test(r.ref_payroll_thang_pb || '') ? r.ref_payroll_thang_pb : '';   // bỏ qua khoá cầu nối 'PAYROLL-…'
    $('tc-cp-ky').value = ky;
    doiLoaiCp();
    $('tc-cp-ten').value = (r && r.ten_khoan) || '';
    $('tc-cp-tk-chi').innerHTML = opt('', '— Chọn tài khoản —') + tkOpt();
    $('tc-cp-quy').innerHTML = opt('', '— Chọn quỹ —') + (m.quy_su_dung || []).map((q) => opt(q.ten, (q.parent_id ? '· ' : '') + q.ten)).join('');
    datChon($('tc-cp-tk-chi'), r ? r.ngan_hang : (coChon($('tc-cp-tk-chi'), nho.doc('tk_chi')) ? nho.doc('tk_chi') : ''));
    datChon($('tc-cp-quy'), r ? r.quy : (coChon($('tc-cp-quy'), nho.doc('quy')) ? nho.doc('quy') : ''));
    $('tc-cp-pb').innerHTML = opt('', '— Tất cả phòng ban —') + dm.pb.map((p) => opt(p.ten_phong_ban, p.ten_phong_ban + (p.so_nv ? ' (' + p.so_nv + ')' : ''))).join('');
    datChon($('tc-cp-pb'), r ? r.phong_ban : '');
    veNguoiChi(r ? r.nguoi_chi : '', true);
    $('tc-cp-ma').value = (r && r.ma_don) || '';
    $('tc-cp-vc').value = (r && r.don_vi_vc) || '';
    $('tc-cp-gc').value = (r && r.ghi_chu) || '';
    KD.moHopThoai(dlgCp);
  }
  $('tc-cp-nhom').addEventListener('change', () => { veLoaiCp($('tc-cp-loai'), $('tc-cp-nhom').value); doiLoaiCp(); });
  $('tc-cp-loai').addEventListener('change', doiLoaiCp);
  $('tc-cp-pb').addEventListener('change', () => veNguoiChi($('tc-cp-nc').value, false));
  $('tc-cp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const s = suaCp, loai = $('tc-cp-loai').value, ung = laUngLuong(loai);
    const body = { ngay: $('tc-cp-ngay').value, loai_chi_phi: loai, ten_khoan: giaTri('tc-cp-ten'), so_tien: tienSua($('tc-cp-tien'), s && s.so_tien),
      quy: giaTri('tc-cp-quy'), phong_ban: giaTri('tc-cp-pb'), nguoi_chi: giaTri('tc-cp-nc'), don_vi_vc: giaTri('tc-cp-vc'),
      ma_don: giaTri('tc-cp-ma'), ngan_hang: giaTri('tc-cp-tk-chi'), ghi_chu: giaTri('tc-cp-gc') };
    /* ky_luong như màn cũ (Ứng Lương → 'YYYY-MM' hoặc null). Khi SỬA chỉ gửi nếu dòng đang / đổi thành Ứng Lương: màn cũ
       luôn gửi null nên sửa một dòng lương tự sinh làm mất khoá cầu nối ref_payroll_thang_pb='PAYROLL-…'. */
    if (!s || ung || laUngLuong(s.loai_chi_phi)) body.ky_luong = ung ? ($('tc-cp-ky').value || null) : null;
    const loi = (id, msg) => { $(id).focus(); KD.baoLoiHopThoai(dlgCp, msg); };
    if (!body.ngay) return loi('tc-cp-ngay', 'Chọn ngày.');
    if (!Number(body.so_tien)) return loi('tc-cp-tien', 'Nhập số tiền lớn hơn 0.');
    if (!loai) return loi('tc-cp-loai', 'Chọn loại chi phí.');
    if (!body.ngan_hang && !(s && !s.ngan_hang)) return loi('tc-cp-tk-chi', 'Chọn tài khoản chi.');
    if (!body.quy && !(s && !s.quy)) return loi('tc-cp-quy', 'Chọn quỹ sử dụng.');
    if (ung && !body.nguoi_chi) return loi('tc-cp-nc', 'Ứng Lương cần chọn người chi (nhân viên nhận ứng) — HCNS trừ lương theo tên này.');
    const nut = $('tc-cp-luu'); nut.disabled = true;
    try {
      const r = await guiLen(s ? '/api/chi-phi/' + s.id : '/api/chi-phi', body, s);
      if (!s) { nho.ghi('tk_chi', body.ngan_hang); nho.ghi('quy', body.quy); }
      dlgCp.close();
      baoXong((s ? 'Đã cập nhật' : 'Đã ghi') + ' chi phí CP-' + r.id + ' — ' + KD.tienVnd(r.so_tien) + ghiChuKy(cp, r.ngay));
      cp.tai();
    } catch (err) { KD.baoLoiHopThoai(dlgCp, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Chi phí cố định ── */
  const dlgCd = $('tc-cd-dlg');
  let suaCd = null;
  const laPhanTram = () => $('tc-cd-pp').value === 'by_revenue_pct';   // "Theo % doanh thu": ô Thành tiền là tỷ lệ %
  function doiPpCd(xoaTien) {
    const pt = laPhanTram();
    $('tc-cd-tien-nhan').textContent = pt ? 'Tỷ lệ % doanh thu' : 'Thành tiền (VND)';
    $('tc-cd-tien').inputMode = pt ? 'decimal' : 'numeric';
    if (xoaTien) $('tc-cd-tien').value = '';
    $('tc-cd-tc').hidden = $('tc-cd-pp').value !== 'manual';
  }
  $('tc-cd-tien').addEventListener('input', (e) => { if (laPhanTram()) return; const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; });
  $('tc-cd-pp').addEventListener('change', (e) => { const truoc = e.target.dataset.truoc === 'by_revenue_pct'; doiPpCd(truoc !== laPhanTram()); e.target.dataset.truoc = e.target.value; });
  $('tc-cd-nhom').addEventListener('change', () => veLoaiCp($('tc-cd-loai'), $('tc-cd-nhom').value));
  async function moCd(r) {
    if (!(await chuanBi($('tc-them')))) return;
    suaCd = r || null;
    const k = cd.khoang();
    $('tc-cd-td').textContent = r ? 'Sửa chi phí cố định #' + r.id : 'Thêm chi phí cố định';
    $('tc-cd-thang').value = r ? (r.thang_bat_dau || '').slice(0, 7) : (k.den || KD.iso(new Date())).slice(0, 7);
    $('tc-cd-nhom').value = r ? (r.nhom_chi_phi || 'khac') : 'quan_ly';
    $('tc-cd-loai').value = ''; veLoaiCp($('tc-cd-loai'), $('tc-cd-nhom').value);
    datChon($('tc-cd-loai'), r ? r.loai_chi_phi : '');
    $('tc-cd-ten').value = (r && r.ten_khoan) || '';
    $('tc-cd-pp').value = (r && r.phuong_phap_phan_bo) || 'duong_thang';
    $('tc-cd-pp').dataset.truoc = $('tc-cd-pp').value;
    doiPpCd(true);
    if (r && KD.so(r.so_tien_thang)) $('tc-cd-tien').value = laPhanTram() ? String(Number(r.so_tien_thang)) : KD.tien(r.so_tien_thang);
    $('tc-cd-so-thang').value = (r && r.so_thang_phan_bo) || 1;
    $('tc-cd-tu').value = ((r && r.ngay_bat_dau) || '').slice(0, 10);
    $('tc-cd-den').value = ((r && r.ngay_ket_thuc) || '').slice(0, 10);
    $('tc-cd-lap').checked = r ? r.lap_lai !== false : true;   // màn cũ không có ô này → API mặc định lap_lai = true
    const tc = (r && r.phan_bo_manual) || {};
    document.querySelectorAll('#tc-cd-tc [data-mm]').forEach((el) => { const v = tc[el.dataset.mm]; el.value = v != null ? v : ''; });
    $('tc-cd-gc').value = (r && r.ghi_chu) || '';
    KD.moHopThoai(dlgCd);
  }
  $('tc-cd-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const s = suaCd, pp = $('tc-cd-pp').value, thang = $('tc-cd-thang').value, soThang = parseInt($('tc-cd-so-thang').value, 10);
    const loi = (id, msg) => { $(id).focus(); KD.baoLoiHopThoai(dlgCd, msg); };
    let tc = null;
    if (pp === 'manual') {
      tc = {};
      document.querySelectorAll('#tc-cd-tc [data-mm]').forEach((el) => { const v = docPhanTram(el); if (v > 0) tc[el.dataset.mm] = v; });
    }
    const body = { thang_bat_dau: thang ? thang + '-01' : null, ngay_bat_dau: $('tc-cd-tu').value || null, ngay_ket_thuc: $('tc-cd-den').value || null,
      loai_chi_phi: $('tc-cd-loai').value, nhom_chi_phi: $('tc-cd-nhom').value, ten_khoan: giaTri('tc-cd-ten'),
      so_tien_thang: laPhanTram() ? docPhanTram($('tc-cd-tien')) : tienSua($('tc-cd-tien'), s && s.so_tien_thang),
      so_thang_phan_bo: soThang >= 1 ? soThang : 1, phuong_phap_phan_bo: pp, phan_bo_manual: tc,
      lap_lai: $('tc-cd-lap').checked, ghi_chu: giaTri('tc-cd-gc') };
    if (!thang) return loi('tc-cd-thang', 'Chọn tháng bắt đầu.');
    if (!body.loai_chi_phi) return loi('tc-cd-loai', 'Chọn loại chi phí.');
    if (!Number(body.so_tien_thang)) return loi('tc-cd-tien', laPhanTram() ? 'Nhập tỷ lệ % lớn hơn 0.' : 'Nhập thành tiền lớn hơn 0.');
    if ($('tc-cd-so-thang').value && !(soThang >= 1)) return loi('tc-cd-so-thang', 'Số tháng phân bổ phải từ 1 trở lên.');
    if (body.ngay_bat_dau && body.ngay_ket_thuc && body.ngay_ket_thuc < body.ngay_bat_dau) return loi('tc-cd-den', 'Đến ngày phải sau hoặc bằng Từ ngày.');
    if (tc && !Object.keys(tc).length) { document.querySelector('#tc-cd-tc [data-mm]').focus(); return KD.baoLoiHopThoai(dlgCd, 'Nhập tỷ lệ % cho ít nhất một tháng.'); }
    const nut = $('tc-cd-luu'); nut.disabled = true;
    try {
      const r = await guiLen(s ? '/api/co-dinh/' + s.id : '/api/co-dinh', body, s);
      dlgCd.close();
      baoXong((s ? 'Đã cập nhật' : 'Đã thêm') + ' chi phí cố định #' + r.id + (r.ten_khoan ? ' — ' + r.ten_khoan : ''));
      cd.tai();
    } catch (err) { KD.baoLoiHopThoai(dlgCd, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Xoá (CEO) — DELETE của router tự xoá kèm phiếu Sổ quỹ (DT-/CP-id), tính lại công nợ theo mã đơn. ── */
  const dlgX = $('tc-xoa-dlg');
  let viecXoa = null;
  function moXoa(v) { viecXoa = v; $('tc-xoa-td').textContent = v.td; $('tc-xoa-nd').textContent = v.nd; KD.moHopThoai(dlgX); }
  const tuLuong = (n) => (n ? ' Dòng này sinh tự động từ luồng "' + n + '".' : '');
  function xoaDt(r) {
    moXoa({ url: '/api/doanh-thu/' + r.id, td: 'Xoá doanh thu DT-' + r.id + '?', xong: 'Đã xoá doanh thu DT-' + r.id, sau: () => { dt.tai(); napThang(); },
      nd: 'Xoá phiếu doanh thu ' + KD.tienVnd(r.so_tien) + ' ngày ' + KD.ngay(r.ngay) + ' và phiếu thu tương ứng trên Sổ quỹ.'
        + (r.ma_don ? ' Số đã thu của công nợ đơn ' + r.ma_don + ' được tính lại.' : '') + tuLuong(r.nguon_hien) });
  }
  function xoaCp(r) {
    moXoa({ url: '/api/chi-phi/' + r.id, td: 'Xoá chi phí CP-' + r.id + '?', xong: 'Đã xoá chi phí CP-' + r.id, sau: () => cp.tai(),
      nd: 'Xoá chi phí ' + KD.tienVnd(r.so_tien) + ' ngày ' + KD.ngay(r.ngay) + ' và phiếu chi tương ứng trên Sổ quỹ.'
        + (laUngLuong(r.loai_chi_phi) ? ' Khoản Ứng Lương này sẽ không còn bị trừ ở bảng lương.' : '')
        + tuLuong(r.nguon && r.nguon !== 'KT tự nhập' ? r.nguon : '') });
  }
  function xoaCd(r) {
    moXoa({ url: '/api/co-dinh/' + r.id, td: 'Xoá khoản cố định "' + (r.ten_khoan || '#' + r.id) + '"?', xong: 'Đã xoá chi phí cố định #' + r.id, sau: () => cd.tai(),
      nd: 'Báo cáo Kết quả kinh doanh các tháng liên quan sẽ không còn khoản ' + KD.tienVnd(r.so_tien_thang) + ' này.' });
  }
  $('tc-xoa-ok').addEventListener('click', async () => {
    const nut = $('tc-xoa-ok'); nut.disabled = true;
    try { await KD.api(viecXoa.url, { method: 'DELETE' }); dlgX.close(); baoXong(viecXoa.xong); viecXoa.sau(); }
    catch (e) { KD.baoLoiHopThoai(dlgX, 'Chưa xoá được: ' + e.message); } finally { nut.disabled = false; }
  });

  // Sửa một ô sau khi bị báo lỗi → ẩn dòng lỗi cũ (vd "Chọn tài khoản chi." còn đỏ dù đã chọn).
  [dlgDt, dlgCp, dlgCd].forEach((d) => d.addEventListener('change', () => { const e = d.querySelector('.kd-form-err'); if (e) e.hidden = true; }));

  /* Nút ghi tay trên dải tiêu đề đổi theo tab đang mở. */
  const NUT_THEM = { doanh_thu: ['Ghi nhận doanh thu', moDt], chi_phi: ['Ghi nhận chi phí', moCp], co_dinh: ['Thêm chi phí cố định', moCd] };
  const doiNutThem = () => { $('tc-them-nhan').textContent = NUT_THEM[tab][0]; };
  $('tc-them').addEventListener('click', () => NUT_THEM[tab][1]());

  /* ── Tab + URL ── */
  const BANG = { doanh_thu: dt, chi_phi: cp, co_dinh: cd }, BANG_P = { dt, cp };
  function ghiUrl() {
    const o = { tab, ky: dt.st.ky, tu: dt.st.tu, den: dt.st.den };
    Object.keys(LOC_URL).forEach((p) => LOC_URL[p].forEach((k) => { const v = BANG_P[p].st[k]; if (v && v !== (k === 'sort' ? 'ngay_desc' : '')) o[p + '_' + k] = v; }));
    KT.url.ghi(o, MAC);
  }
  const tabs = KD.ganTab($('tc-tabs'), (k) => { tab = k; doiNutThem(); ghiUrl(); BANG[k].taiNeuCan(); });
  tabs.chon(tab);
  if (tab !== 'co_dinh') cd.tai();
  napThang();
})();
