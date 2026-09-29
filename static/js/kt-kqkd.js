/* kt-kqkd.js — Kết quả kinh doanh B02-DN (khung: kt-bao-cao.js).
   Cách dựng số (gọi /pl từng tháng, cộng dồn, thuế) nằm ở kt-kqkd-tinh.js — DÙNG CHUNG với trang in.
   Nguồn chính: GET /api/bao-cao/pl?thang=YYYY-MM (P&L chuẩn 22 dòng — ĐÚNG nguồn màn cũ #pnl mở mặc định).
   API chỉ nhận 1 tháng → gọi từng tháng của kỳ chọn + cùng số tháng liền trước (song song), cộng dồn
   mọi số ở phía trình duyệt; thuế TNDN tính lại trên LNTT cả kỳ (giống /api/bao-cao/pl/yearly).
   Khối gập "Đối chiếu theo tiền thu thực tế": GET /api/bao-cao/pnl?from&to&compare=1 — chế độ
   "theo khoảng" của màn cũ (DT = tiền thu thực tế gồm cọc; GV theo xuất kho), đủ các dòng chi tiết,
   % doanh thu, kỳ trước, biên gộp/hoạt động/ròng, waterfall và cơ cấu chi phí. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-kqkd')) return;
  const $ = (id) => document.getElementById(id);
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const nhanKy = (ds) => (ds.length === 1 ? 'tháng ' + thangChu(ds[0]) : 'tháng ' + thangChu(ds[0]) + ' – ' + thangChu(ds[ds.length - 1]));

  /* ── Dòng B02 (mã số theo mẫu B02-DN; chi tiết lấy đúng các khoản mục màn P&L cũ) ── */
  function dongTu(c, p) {
    const g = (o, path) => path.split('.').reduce((x, k) => (x == null ? null : x[k]), o);
    const v = (path) => ({ ky_nay: g(c, path) || 0, ky_truoc: p ? g(p, path) || 0 : null });
    const r = (ma, chi_tieu, cap, path, them) => Object.assign({ ma, chi_tieu, cap }, typeof path === 'string' ? v(path) : path, them || {});
    const hieu = (fa, fb) => ({ ky_nay: fa(c) - fb(c), ky_truoc: p ? fa(p) - fb(p) : null });
    const nhomAds = Object.keys(Object.assign({}, g(c, 'cp_ban_hang.bien_phi.ads_by_nhom'), p ? g(p, 'cp_ban_hang.bien_phi.ads_by_nhom') : {}));
    return [
      r('01', 'Doanh thu bán hàng và cung cấp dịch vụ', 'muc', 'doanh_thu.dt_thuc_hien', { ghi_chu: 'Giá trị đơn hoàn thành trong kỳ, chưa VAT' }),
      r('02', 'Các khoản giảm trừ doanh thu', 'muc', { ky_nay: c.doanh_thu.chiet_khau + c.doanh_thu.giam_tru, ky_truoc: p ? p.doanh_thu.chiet_khau + p.doanh_thu.giam_tru : null }, { nhom_mo: 'gt' }),
      r('', 'Chiết khấu thương mại', 'con', 'doanh_thu.chiet_khau', { thuoc: 'gt' }),
      r('', 'Hoàn tiền khách (đơn đã ghi doanh thu)', 'con', 'doanh_thu.giam_tru', { thuoc: 'gt' }),
      r('10', 'Doanh thu thuần về bán hàng và cung cấp dịch vụ', 'tong', 'dt_thuan'),
      r('11', 'Giá vốn hàng bán', 'muc', 'cogs', { ghi_chu: 'Giá vốn NCC của đơn hoàn thành trong kỳ' }),
      r('20', 'Lợi nhuận gộp về bán hàng và cung cấp dịch vụ', 'tong', 'ln_gop'),
      r('21', 'Doanh thu hoạt động tài chính', 'muc', 'dt_tai_chinh'),
      r('22', 'Chi phí tài chính', 'muc', 'cp_tai_chinh.tong', { nhom_mo: 'tc' }),
      r('23', 'Trong đó: lãi vay theo sổ vay', 'con', 'cp_tai_chinh.lai_vay', { thuoc: 'tc' }),
      r('', 'Phí ngân hàng và lãi vay ghi ở sổ chi phí', 'con', 'cp_tai_chinh.phi_nh', { thuoc: 'tc' }),
      r('', 'Chi phí tài chính khác', 'con', 'cp_tai_chinh.khac', { thuoc: 'tc' }),
      r('25', 'Chi phí bán hàng', 'muc', 'cp_ban_hang.tong', { nhom_mo: 'bh' }),
      r('', 'Biến phí bán hàng', 'con', 'cp_ban_hang.bien_phi.tong', { thuoc: 'bh', nhom_mo: 'bhbp', gap: true }),
      r('', 'Hoa hồng', 'con2', 'cp_ban_hang.bien_phi.hoa_hong', { thuoc: 'bh bhbp', ghi_chu: 'Bảng lương KD/MKT' }),
      r('', 'Lương làm thêm KD/MKT', 'con2', 'cp_ban_hang.bien_phi.luong_ot', { thuoc: 'bh bhbp' }),
      r('', 'Quảng cáo, marketing', 'con2', 'cp_ban_hang.bien_phi.ads', { thuoc: 'bh bhbp', ghi_chu: g(c, 'cp_ban_hang.bien_phi.ads_source') ? 'Nguồn: ' + g(c, 'cp_ban_hang.bien_phi.ads_source') : '' }),
      ...nhomAds.map((n) => r('', '· Quảng cáo nhóm ' + (n === 'no_match' ? 'chưa gán nhóm hàng' : n), 'con2', { ky_nay: g(c, 'cp_ban_hang.bien_phi.ads_by_nhom')?.[n] || 0, ky_truoc: p ? (g(p, 'cp_ban_hang.bien_phi.ads_by_nhom')?.[n] || 0) : null }, { thuoc: 'bh bhbp' })),
      r('', 'Vận chuyển', 'con2', 'cp_ban_hang.bien_phi.van_chuyen', { thuoc: 'bh bhbp' }),
      r('', 'Khuyến mãi', 'con2', 'cp_ban_hang.bien_phi.khuyen_mai', { thuoc: 'bh bhbp' }),
      r('', 'Biến phí bán hàng khác', 'con2', 'cp_ban_hang.bien_phi.khac', { thuoc: 'bh bhbp' }),
      r('', 'Định phí bán hàng', 'con', 'cp_ban_hang.dinh_phi.tong', { thuoc: 'bh', nhom_mo: 'bhdp', gap: true }),
      r('', 'Lương cơ bản KD/MKT (gồm BHXH công ty)', 'con2', 'cp_ban_hang.dinh_phi.luong_co_ban_kd_mkt', { thuoc: 'bh bhdp' }),
      r('', 'Tiền thuê mặt bằng (showroom, kho, nhà…)', 'con2', 'cp_ban_hang.dinh_phi.thue_showroom', { thuoc: 'bh bhdp', ghi_chu: 'Chi phí cố định nhóm bán hàng có tên "thuê" — phân bổ theo số tháng' }),
      r('', 'Khấu hao TSCĐ bán hàng', 'con2', 'cp_ban_hang.dinh_phi.khau_hao_tscd_bh', { thuoc: 'bh bhdp' }),
      r('', 'Phí thường xuyên', 'con2', 'cp_ban_hang.dinh_phi.phi_thuong_xuyen', { thuoc: 'bh bhdp' }),
      r('26', 'Chi phí quản lý doanh nghiệp', 'muc', 'cp_quan_ly.tong', { nhom_mo: 'ql' }),
      r('', 'Biến phí quản lý', 'con', 'cp_quan_ly.bien_phi.tong', { thuoc: 'ql', nhom_mo: 'qlbp', gap: true }),
      r('', 'Văn phòng phẩm', 'con2', 'cp_quan_ly.bien_phi.vpp', { thuoc: 'ql qlbp' }),
      r('', 'Đào tạo', 'con2', 'cp_quan_ly.bien_phi.dao_tao', { thuoc: 'ql qlbp' }),
      r('', 'Hội họp, công tác', 'con2', 'cp_quan_ly.bien_phi.hoi_hop_cong_tac', { thuoc: 'ql qlbp' }),
      r('', 'Quà biếu', 'con2', 'cp_quan_ly.bien_phi.qua_bieu', { thuoc: 'ql qlbp' }),
      r('', 'Biến phí quản lý khác', 'con2', 'cp_quan_ly.bien_phi.khac', { thuoc: 'ql qlbp' }),
      r('', 'Định phí quản lý', 'con', 'cp_quan_ly.dinh_phi.tong', { thuoc: 'ql', nhom_mo: 'qldp', gap: true }),
      r('', 'Lương cơ bản HCNS/KT/CEO (gồm BHXH công ty)', 'con2', 'cp_quan_ly.dinh_phi.luong_co_ban_hcns_kt_ceo', { thuoc: 'ql qldp' }),
      r('', 'Tiền thuê mặt bằng (văn phòng, showroom…)', 'con2', 'cp_quan_ly.dinh_phi.thue_vp', { thuoc: 'ql qldp', ghi_chu: 'Chi phí cố định nhóm quản lý có tên "thuê" — phân bổ theo số tháng' }),
      r('', 'Điện nước văn phòng', 'con2', 'cp_quan_ly.dinh_phi.dien_nuoc_vp', { thuoc: 'ql qldp' }),
      r('', 'Internet, điện thoại', 'con2', 'cp_quan_ly.dinh_phi.internet_dien_thoai', { thuoc: 'ql qldp' }),
      r('', 'Khấu hao TSCĐ quản lý', 'con2', 'cp_quan_ly.dinh_phi.khau_hao_tscd_ql', { thuoc: 'ql qldp' }),
      r('', 'Dịch vụ kế toán, luật', 'con2', 'cp_quan_ly.dinh_phi.dich_vu_kt_luat', { thuoc: 'ql qldp' }),
      r('', 'Định phí quản lý khác', 'con2', 'cp_quan_ly.dinh_phi.phi_khac', { thuoc: 'ql qldp' }),
      r('30', 'Lợi nhuận thuần từ hoạt động kinh doanh', 'tong', 'ln_thuan_hdkd'),
      r('31', 'Thu nhập khác', 'muc', 'thu_nhap_khac', { ghi_chu: 'TK 711, vd lãi thanh lý TSCĐ' }),
      r('32', 'Chi phí khác', 'muc', 'cp_khac', { ghi_chu: 'TK 811 và chi phí nhóm khác' }),
      r('40', 'Lợi nhuận khác', 'tong', hieu((x) => x.thu_nhap_khac, (x) => x.cp_khac)),
      r('50', 'Tổng lợi nhuận kế toán trước thuế', 'tong', 'ln_truoc_thue'),
      r('51', 'Chi phí thuế TNDN hiện hành (' + KT.kqkd.THUE_SUAT_TNDN * 100 + '% nếu có lãi)', 'muc', 'thue_tndn'),
      r('60', 'Lợi nhuận sau thuế thu nhập doanh nghiệp', 'dam', 'lnst'),
    ];
  }

  let ke = null;   // kế hoạch gọi API của lần tải gần nhất (KT.kqkd.ke — kt-kqkd-tinh.js, dùng chung với trang in)
  function chuyen(ds) {
    const t = KT.kqkd.tach(ds, ke);
    return Object.assign(t, { dong: dongTu(t.c, t.p), meta: t.c.metadata || {} });
  }

  const soSanh = (a, b, ten) => { if (b == null) return ''; const d = a - b; if (!d) return 'Bằng ' + ten;
    return (d > 0 ? '▲ +' : '▼ −') + KD.tienGon(Math.abs(d)) + (b ? ' (' + (d > 0 ? '+' : '−') + KD.phanTram(Math.abs(d / b) * 100) + ')' : '') + ' so với ' + ten; };
  const soSanhNgan = (a, b) => { if (b == null) return ''; const d = a - b; if (!d) return 'Bằng kỳ trước';
    return (d > 0 ? '▲ ' : '▼ ') + (b ? KD.phanTram(Math.abs(d / b) * 100) : (d > 0 ? '+' : '−') + KD.tienGon(Math.abs(d))) + ' so kỳ trước'; };
  const phuKpi = (ngan, a, b) => ngan + KD.tip(soSanh(a, b, 'kỳ trước'));
  const tienKpi = (v) => ({ v: (v < 0 ? '−' : '') + KD.tienGonHtml(Math.abs(v)), title: KD.tienVnd(v) });
  const bien = (a, b) => (b ? a / b * 100 : 0);

  const bc = KT.baoCao({
    pfx: 'kq', tenFile: 'ket-qua-kinh-doanh',
    api: (k) => { ke = KT.kqkd.ke(k.tu, k.den, k.ss && k.ss.thang); return ke.urls; },
    inUrl: (k) => '/ketoan/in?' + KT.url.qs({ loai: 'bao_cao', mau: 'kqkd', tu: k.tu, den: k.den, ky: k.ky }),
    macDinh: { ky: 'thang_nay', tu: '', den: '' },
    inUrl: (k) => '/ketoan/in?' + KT.url.qs({ loai: 'bao_cao', mau: 'kqkd', tu: k.tu, den: k.den, ky: k.ky }),
    cot: [{ key: 'ma' }, { key: 'ky_nay', num: true }, { key: 'ky_truoc', num: true }, { key: 'chenh', num: true }],
    lien: { '01': '511', '11': '632', '21': '515', '22': '635', '25': '641', '26': '642', '31': '711', '32': '811', '51': '821' },
    chuyen,
    kpi: {
      dt: (d) => Object.assign(tienKpi(d.c.dt_thuan), { phu: phuKpi(soSanhNgan(d.c.dt_thuan, d.p.dt_thuan), d.c.dt_thuan, d.p.dt_thuan) }),
      ln_gop: (d) => Object.assign(tienKpi(d.c.ln_gop), { phu: phuKpi('Biên gộp ' + KD.phanTram(bien(d.c.ln_gop, d.c.dt_thuan)), d.c.ln_gop, d.p.ln_gop) }),
      ln_tt: (d) => Object.assign(tienKpi(d.c.ln_truoc_thue), { phu: phuKpi(soSanhNgan(d.c.ln_truoc_thue, d.p.ln_truoc_thue), d.c.ln_truoc_thue, d.p.ln_truoc_thue) }),
      ln_st: (d) => Object.assign(tienKpi(d.c.lnst), { phu: phuKpi('Biên ròng ' + KD.phanTram(bien(d.c.lnst, d.c.dt_thuan)), d.c.lnst, d.p.lnst) }),
    },
    phuDe: (d) => (d.thang.length === 1 ? 'Tháng ' + thangChu(d.thang[0]) + ' so với tháng ' + thangChu(d.thang_truoc[0]) : 'Kỳ ' + nhanKy(d.thang) + ' so với ' + nhanKy(d.thang_truoc)),
    phamVi: (d) => 'Doanh thu = đơn hoàn thành chưa VAT; giá vốn = giá vốn NCC của các đơn đó. Kỳ này có ' + KD.soDem(d.meta.so_don_hoan_thanh_trong_ky || 0) + ' đơn hoàn thành, '
      + KD.soDem(d.meta.so_giao_dich_chi_phi || 0) + ' giao dịch chi phí, ' + KD.soDem(d.meta.phan_bo_dinh_phi_count || 0) + ' khoản định phí phân bổ, ' + KD.soDem(d.meta.khau_hao_tscd_count || 0) + ' lần khấu hao TSCĐ.'
      + (d.thang.length > 1 ? ' Kỳ nhiều tháng: thuế TNDN tính trên lợi nhuận cả kỳ.' : ''),
    sauTai: () => { if ($('dc-khoi').open) taiDoiChieu(); else dcKhoa = null; },
    rong: ['Kỳ này chưa có doanh thu, chi phí nào', 'Chọn kỳ khác, hoặc kiểm tra đơn hàng đã hoàn thành và chi phí đã ghi sổ chưa.'],
    loi: 'Không tải được báo cáo kết quả kinh doanh',
  });

  /* ═════════ Khối đối chiếu theo tiền thu thực tế (/pnl) ═════════ */
  let dcKhoa = null, lDc = 0;
  const pct = (a, b) => (b ? KD.phanTram(a / b * 100) : '—');
  const delta = (a, b) => { if (b == null) return '—'; if (!b) return a ? '<span class="kt-so--tot">▲ mới</span>' : '—';
    const x = (a - b) / Math.abs(b) * 100; return '<span class="' + (x > 0 ? 'kt-so--tot' : x < 0 ? 'kt-so--xau' : '') + '">' + (x > 0 ? '▲ ' : x < 0 ? '▼ ' : '') + KD.phanTram(Math.abs(x)) + '</span>'; };
  function dongDc(ten, so, dt, truoc, o) {
    o = o || {};
    const dau = o.tru ? -1 : 1;   // khoản trừ viết trong ngoặc đơn như BCTC
    return '<tr class="kt-bc--' + (o.cap || 'muc') + '"><th scope="row">' + (o.tru ? '(−) ' : o.bang ? '= ' : '') + esc(ten) + '</th><td class="num">' + KT.soBc(dau * so) + '</td>'
      + '<td class="num kd-muted">' + pct(so, dt) + '</td><td class="num">' + (truoc == null ? '<span class="kd-muted">—</span>' : KT.soBc(dau * truoc)) + '</td><td class="num">' + delta(so, truoc) + '</td></tr>';
  }
  function veDoiChieu(d) {
    const c = d.current, p = d.previous || null, dt = c.doanh_thu.total, P = (f) => (p ? f(p) : null);
    const ql = c.chi_phi_quan_ly, lm = ql.luong || {}, dm = ql.dinh_phi || {};
    let h = '';
    h += dongDc('Doanh thu (tiền khách trả)', dt, dt, P((x) => x.doanh_thu.total), { cap: 'tong' });
    /* gộp hình thức thu chỉ khác hoa/thường ("Thanh toán" / "Thanh Toán") thành 1 dòng */
    const hinhThuc = [];
    (c.doanh_thu.items || []).forEach((it) => { const k = String(it.loai).trim().toLowerCase(), o = hinhThuc.find((x) => x.k === k);
      if (o) o.so_tien += it.so_tien; else hinhThuc.push({ k, loai: it.loai, so_tien: it.so_tien }); });
    hinhThuc.forEach((it) => { h += dongDc(it.loai, it.so_tien, dt, null, { cap: 'con' }); });
    h += dongDc('Giá vốn ' + ({ inventory_movement: 'theo phiếu xuất kho trong khoảng', muahang_po: 'theo đơn mua hoàn thành trong khoảng', estimate: '(ước tính)' }[c.gia_von.source] || ''), c.gia_von.total, dt, P((x) => x.gia_von.total), { tru: true });
    h += dongDc('Lợi nhuận gộp theo tiền thu', c.loi_nhuan_gop, dt, P((x) => x.loi_nhuan_gop), { bang: true, cap: 'tong' });
    h += dongDc('Chi phí bán hàng (quảng cáo theo Marketing)', c.chi_phi_ban_hang.total, dt, P((x) => x.chi_phi_ban_hang.total), { tru: true });
    (c.chi_phi_ban_hang.items || []).forEach((it) => { h += dongDc(it.kenh, it.so_tien, dt, null, { cap: 'con' }); });
    h += dongDc('Lợi nhuận hoạt động bán hàng theo tiền thu', c.loi_nhuan_hd_ban, dt, P((x) => x.loi_nhuan_hd_ban), { bang: true, cap: 'tong' });
    h += dongDc('Chi phí tài chính (lãi vay)', c.chi_phi_tai_chinh.total, dt, P((x) => x.chi_phi_tai_chinh.total), { tru: true });
    (c.chi_phi_tai_chinh.items || []).forEach((it) => { h += dongDc(it.nguon, it.so_tien, dt, null, { cap: 'con' }); });
    h += dongDc('Lợi nhuận hoạt động kinh doanh theo tiền thu', c.loi_nhuan_hd_kd, dt, P((x) => x.loi_nhuan_hd_kd), { bang: true, cap: 'tong' });
    h += dongDc('Chi phí quản lý và chi khác theo sổ chi', ql.total, dt, P((x) => x.chi_phi_quan_ly.total), { tru: true });
    h += dongDc('Lương HCNS (' + KD.soDem(lm.thang_count || 0) + ' tháng' + (lm.n_nv ? ', ' + KD.soDem(lm.n_nv) + ' nhân viên' : '') + ')', lm.total || 0, dt, P((x) => x.chi_phi_quan_ly.luong.total), { cap: 'con' });
    h += dongDc('Định phí phân bổ (' + KD.soDem(dm.n_months || 0) + ' tháng)', dm.total || 0, dt, P((x) => x.chi_phi_quan_ly.dinh_phi.total), { cap: 'con' });
    (dm.items || []).forEach((it) => { h += dongDc(it.loai_chi_phi + (it.so_tien_thang != null && it.n_months != null ? ' (' + KD.tienGon(it.so_tien_thang) + '/tháng × ' + it.n_months + ')' : ''), it.so_tien, dt, null, { cap: 'con2' }); });
    h += dongDc('Biến phí (trừ quảng cáo và lãi vay)', ql.bien_phi.total, dt, P((x) => x.chi_phi_quan_ly.bien_phi.total), { cap: 'con' });
    (ql.bien_phi.items || []).forEach((it) => { h += dongDc(it.loai, it.so_tien, dt, null, { cap: 'con2' }); });
    h += dongDc('Lợi nhuận trước thuế theo tiền thu', c.loi_nhuan_truoc_thue, dt, P((x) => x.loi_nhuan_truoc_thue), { bang: true, cap: 'tong' });
    h += dongDc('Thuế TNDN (20%)', c.thue_tndn, dt, P((x) => x.thue_tndn), { tru: true });
    h += dongDc('Lợi nhuận sau thuế theo tiền thu', c.loi_nhuan_sau_thue, dt, P((x) => x.loi_nhuan_sau_thue), { bang: true, cap: 'dam' });
    const m = c.margins || {};
    h += '<tr class="kt-bc--muc"><th scope="row">Biên lợi nhuận theo tiền thu: gộp / hoạt động / ròng</th><td class="num" colspan="4">' + KD.phanTram(m.gross) + ' / ' + KD.phanTram(m.operating) + ' / ' + KD.phanTram(m.net) + '</td></tr>';
    $('dc-tbody').innerHTML = h;

    /* Waterfall — thanh ngang tỉ lệ theo trị tuyệt đối lớn nhất */
    const buoc = [['Doanh thu', dt, 'tong'], ['Giá vốn', -c.gia_von.total, 'tru'], ['Lợi nhuận gộp', c.loi_nhuan_gop, 'con'],
      ['Chi phí bán hàng', -c.chi_phi_ban_hang.total, 'tru'], ['LN hoạt động bán hàng', c.loi_nhuan_hd_ban, 'con'],
      ['Chi phí tài chính', -c.chi_phi_tai_chinh.total, 'tru'], ['LN hoạt động kinh doanh', c.loi_nhuan_hd_kd, 'con'],
      ['Chi phí quản lý và chi khác', -ql.total, 'tru'], ['LN trước thuế', c.loi_nhuan_truoc_thue, 'con'], ['Thuế TNDN', -c.thue_tndn, 'tru'], ['LN sau thuế', c.loi_nhuan_sau_thue, 'tong']];
    const max = Math.max(1, ...buoc.map((b) => Math.abs(b[1])));
    $('dc-wf').innerHTML = buoc.map(([ten, so, loai]) => '<div class="kt-wf__o"><span class="kt-wf__ten">' + esc(ten) + '</span><span class="kt-wf__thanh"><span class="kt-wf--' + (so < 0 && loai !== 'tru' ? 'am' : loai) + '" style="width:' + Math.max(1, Math.round(Math.abs(so) / max * 100)) + '%"></span></span>'
      + '<b class="kt-wf__so num' + (so < 0 ? ' kt-so--xau' : '') + '" title="' + KD.tienVnd(so || 0) + '">' + (so < 0 ? '−' : '') + KD.tienGon(Math.abs(so)) + '</b></div>').join('');

    /* Cơ cấu chi phí — thanh xếp chồng + chú giải (cùng 6 mảng như biểu đồ tròn màn cũ) */
    const mau = ['var(--tile-slate, #475569)', 'var(--warning, #b45309)', 'var(--tile-violet, #7c3aed)', 'var(--info, #0e7490)', 'var(--success, #15803d)', 'var(--danger, #b91c1c)', 'var(--brand, #2563eb)'];
    const cc = [['Giá vốn', c.gia_von.total], ['Bán hàng', c.chi_phi_ban_hang.total], ['Lương', lm.total || 0], ['Định phí', dm.total || 0], ['Biến phí', ql.bien_phi.total], ['Tài chính', c.chi_phi_tai_chinh.total], ['Thuế TNDN', c.thue_tndn]]
      .map((x, i) => x.concat(mau[i])).filter((x) => x[1] > 0);
    const tong = cc.reduce((a, x) => a + x[1], 0);
    /* % làm tròn 1 chữ số theo phần dư lớn nhất → các % cộng đúng 100% */
    const ptBase = cc.map((x) => (tong ? x[1] / tong * 1000 : 0)), ptSan = ptBase.map(Math.floor);
    let ptDu = (tong ? 1000 : 0) - ptSan.reduce((a, x) => a + x, 0);
    ptBase.map((v, i) => [v - ptSan[i], i]).sort((a, b) => b[0] - a[0]).forEach(([, i]) => { if (ptDu > 0) { ptSan[i] += 1; ptDu -= 1; } });
    cc.forEach((x, i) => { x[3] = ptSan[i] / 10; });
    $('dc-cc').innerHTML = !tong ? KD.khoiRong('Chưa có chi phí trong kỳ', '') : '<div class="kt-cc__thanh" role="img" aria-label="Cơ cấu chi phí">' + cc.map((x) => '<span style="width:' + (x[1] / tong * 100) + '%;background:' + x[2] + '" title="' + esc(x[0]) + ' ' + KD.phanTram(x[3]) + '"></span>').join('') + '</div>'
      + '<ul class="kd-legend kt-cc__chu">' + cc.map((x) => '<li><span class="kd-legend__cham" style="background:' + x[2] + '"></span><span class="kd-legend__ten">' + esc(x[0]) + '</span><span class="kd-meta">' + KD.phanTram(x[3]) + '</span><b class="num">' + KD.tienGon(x[1]) + '</b></li>').join('')
      + '<li class="kt-cc__tong"><span class="kd-legend__ten">Tổng chi phí</span><b class="num">' + KD.tienVnd(tong) + '</b></li></ul>';

    $('dc-pham-vi').innerHTML = KD.ngay(d.from) + ' – ' + KD.ngay(d.to) + ' (' + KD.soDem(d.n_days) + ' ngày)' + (p ? ' · so với ' + KD.ngay(p.from) + ' – ' + KD.ngay(p.to) : '')
      + KD.tip('Giá vốn: ' + (c.gia_von.note || ({ inventory_movement: 'theo phiếu xuất kho', muahang_po: 'theo đơn mua hàng hoàn thành' }[c.gia_von.source] || c.gia_von.source)) + '. Khác bảng B02 vì doanh thu tính theo tiền thu (gồm cọc).');
  }
  const isoNgay = (x) => x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0');
  function kyTruocTronThang(k) {
    const a = new Date(k.tu + 'T00:00:00'), b = new Date(k.den + 'T00:00:00');
    if (a.getDate() !== 1 || new Date(b.getFullYear(), b.getMonth(), b.getDate() + 1).getDate() !== 1) return null;
    const n = (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth() + 1;
    return { tu: isoNgay(new Date(a.getFullYear(), a.getMonth() - n, 1)), den: isoNgay(new Date(a.getFullYear(), a.getMonth(), 0)) };
  }
  async function taiDoiChieu() {
    const k = bc.khoang(), khoa = k.tu + '_' + k.den; if (dcKhoa === khoa) return;
    const l = ++lDc; dcKhoa = khoa; $('dc-tt').innerHTML = ''; $('dc-cuon').hidden = false; $('dc-bieu-do').hidden = false;
    $('dc-tbody').innerHTML = KT.hangCho(5, 10); $('dc-wf').innerHTML = KD.KHUNG_TAI; $('dc-cc').innerHTML = KD.KHUNG_TAI; $('dc-pham-vi').textContent = '';
    try {
      /* Kỳ trọn tháng → kỳ trước = đúng các tháng liền trước như bảng B02 (không phải "cùng số ngày" của /pnl compare=1) */
      const kt = kyTruocTronThang(k);
      const [d, dp] = await Promise.all([KD.api('/api/bao-cao/pnl?' + KT.url.qs(kt ? { from: k.tu, to: k.den } : { from: k.tu, to: k.den, compare: 1 })),
        kt ? KD.api('/api/bao-cao/pnl?' + KT.url.qs({ from: kt.tu, to: kt.den })) : null]);
      if (l !== lDc) return;
      if (dp) d.previous = dp.current;
      veDoiChieu(d);
    } catch (e) { if (l !== lDc) return; dcKhoa = null; $('dc-cuon').hidden = true; $('dc-bieu-do').hidden = true; KD.khoiLoi($('dc-tt'), 'Không tải được số liệu đối chiếu', e, taiDoiChieu); }
  }
  $('dc-khoi').addEventListener('toggle', () => { if ($('dc-khoi').open) taiDoiChieu(); });

  bc.tai();
})();
