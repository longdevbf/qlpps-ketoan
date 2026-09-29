/* kt-in.js — trang in A4: chứng từ (phiếu thu / chi / kế toán), biên bản đối chiếu công nợ, báo cáo tài chính, giấy đề nghị thanh toán.
   Số liệu lấy lại từ API của màn tương ứng — trang in không tự tính số nào khác số trên màn. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-in')) return;
  const $ = (id) => document.getElementById(id), u = KT.url.doc();
  const dong = (nhan, gt) => '<p class="kt-in-dong"><span>' + esc(nhan) + ':</span><b' + (gt ? '' : ' class="is-trong"') + '>' + (gt || '&nbsp;') + '</b></p>';
  const ngayChu = (iso) => { const [y, m, d] = iso.split('-'); return 'Ngày ' + d + ' tháng ' + m + ' năm ' + y; };
  const soBc = (v) => { if (v == null) return ''; const n = Math.round(+v || 0); return !n ? '—' : n < 0 ? '(' + KD.tien(-n) + ')' : KD.tien(n); };
  function dau(dv, mau, phuMau) {
    return '<header class="kt-in-dau"><div class="kt-in-dv"><p>' + esc(dv.ten) + '</p><p class="kt-in-phu">Địa chỉ: ' + (dv.dia_chi ? esc(dv.dia_chi) : '……………………………………') + '</p><p class="kt-in-phu">Mã số thuế: ' + (dv.mst ? esc(dv.mst) : '………………………') + '</p></div>'
      + (mau ? '<div class="kt-in-mau"><strong>' + esc(mau) + '</strong>' + (phuMau ? '<p class="kt-in-phu">' + esc(phuMau) + '</p>' : '') + '</div>' : '') + '</header>';
  }
  function ky(ds, ngay) {
    return (ngay ? '<p class="kt-in-ngay">' + ngayChu(ngay) + '</p>' : '') + '<div class="kt-in-ky" data-cot="' + ds.length + '">' + ds.map((x) => '<div><strong>' + esc(x[0]) + '</strong><small>(Ký, họ tên' + (x[2] ? ', đóng dấu' : '') + ')</small><span class="kt-in-ten">' + esc(x[1] || '') + '</span></div>').join('') + '</div>';
  }
  function datTieuDe(td, phu, ve) { $('in-h1').textContent = td; $('in-h1-phu').textContent = phu || ''; $('in-h1-phu').hidden = !phu; document.title = td.charAt(0) + td.slice(1).toLowerCase() + ' — Bản in'; if (ve) { $('in-ve').href = ve; } }

  /* ── Chứng từ ── */
  async function chungTu(dv) {
    if (!u.id) throw { rong: ['Chưa chọn chứng từ', 'Mở bản in từ trang chi tiết chứng từ.'] };
    const c = await KD.api('/api/journal/' + encodeURIComponent(u.id));
    // GET /api/journal/{id} trả `lines` (loai:'no'|'co', account_code, account_name,
    // so_tien) — KHÔNG có `dong`/`tk`/`no`/`co` cấp dòng hay `loai`/`so_ct`/`dien_giai`/
    // `nguoi_lap` cấp chứng từ như bản in này giả định trước đó (bản in luôn vỡ, kể cả
    // sau khi có /api/don-vi). Quy đổi giống hệt `kt-chung-tu.js` (màn chi tiết chứng từ
    // thật đang chạy) để in được chứng từ thật — không có `doi_tuong` ở API này nên để
    // trống, KHÔNG bịa (anh Quang 2026-09-25).
    const dongCt = (c.lines || []).map((l) => ({
      tk: l.account_code, ten_tk: l.account_name || '',
      no: l.loai === 'no' ? +l.so_tien : 0, co: l.loai === 'co' ? +l.so_tien : 0,
      doi_tuong: l.doi_tuong || null,
    }));
    const soCt = c.so_ct || c.ma_but_toan, dienGiai = c.dien_giai || c.mo_ta;
    let nguoiLap = c.nguoi_lap || c.created_by || '';
    if (!c.nguoi_lap && c.created_by) { try { nguoiLap = (await KD.api('/api/don-vi/ho-ten?username=' + encodeURIComponent(c.created_by))).ho_ten; } catch (e) { /* giữ username */ } }
    const thu = c.loai === 'phieu_thu', chi = c.loai === 'phieu_chi';
    $('in-ve').href = '/ketoan/chung-tu?id=' + encodeURIComponent(c.id);
    if (thu || chi) {
      const q = dongCt.find((l) => l.tk.indexOf('111') === 0 && (thu ? l.no : l.co)) || { no: 0, co: 0 };
      const tien = thu ? q.no : q.co, doi = dongCt.filter((l) => l !== q);
      datTieuDe(thu ? 'PHIẾU THU' : 'PHIẾU CHI', ngayChu(c.ngay_ct || c.ngay), '');
      $('in-dau').innerHTML = dau(dv, 'Số: ' + soCt, 'Quyển số: ……');
      const dt = (dongCt.find((l) => l.doi_tuong) || {}).doi_tuong;
      return '<div class="kt-in-tk"><span>Nợ:</span><b>' + esc(thu ? q.tk : doi.map((l) => l.tk).join(', ')) + '</b><span>Có:</span><b>' + esc(thu ? doi.map((l) => l.tk).join(', ') : q.tk) + '</b></div>'
        + dong(thu ? 'Họ và tên người nộp tiền' : 'Họ và tên người nhận tiền', esc(c.nguoi_nop || (dt ? dt.ten : ''))) + dong('Địa chỉ', dt && dt.dia_chi ? esc(dt.dia_chi) : '') + dong(thu ? 'Lý do nộp' : 'Lý do chi', esc(dienGiai))
        + dong('Số tiền', KD.tienVnd(tien)) + dong('Viết bằng chữ', esc(KT.bangChu(tien))) + dong('Kèm theo', KD.soDem(c.kem_theo || 0) + ' chứng từ gốc')
        + ky([['Giám đốc', dv.giam_doc, true], ['Kế toán trưởng', dv.ke_toan_truong], [thu ? 'Người nộp tiền' : 'Người nhận tiền', ''], ['Người lập phiếu', nguoiLap], ['Thủ quỹ', dv.thu_quy]], c.ngay)
        + '<p class="kt-in-ghi">Đã nhận đủ số tiền (viết bằng chữ): ……………………………………………………………………</p>';
    }
    datTieuDe('PHIẾU KẾ TOÁN', ngayChu(c.ngay) + ' · Số: ' + soCt); $('in-dau').innerHTML = dau(dv, c.loai ? KT.loaiCt(c.loai).nhan : 'Chứng từ kế toán', '');
    const no = dongCt.reduce((s, l) => s + l.no, 0);
    return dong('Diễn giải', esc(dienGiai))
      + '<table class="kt-in-bang"><thead><tr><th scope="col">STT</th><th scope="col">Tài khoản</th><th scope="col">Tên tài khoản</th><th scope="col">Đối tượng</th><th scope="col">Nợ</th><th scope="col">Có</th></tr></thead><tbody>'
      + dongCt.map((l, i) => '<tr><td class="kt-in-giua">' + (i + 1) + '</td><td>' + esc(l.tk) + '</td><td>' + esc(l.ten_tk || '') + '</td><td>' + esc(l.doi_tuong ? l.doi_tuong.ten : '') + '</td><td class="num">' + (l.no ? KD.tien(l.no) : '') + '</td><td class="num">' + (l.co ? KD.tien(l.co) : '') + '</td></tr>').join('')
      + '<tr class="is-dam"><td colspan="4">Cộng</td><td class="num">' + KD.tien(no) + '</td><td class="num">' + KD.tien(dongCt.reduce((s, l) => s + l.co, 0)) + '</td></tr></tbody></table>'
      + dong('Số tiền bằng chữ', esc(KT.bangChu(no))) + ky([['Người lập', nguoiLap], ['Kế toán trưởng', dv.ke_toan_truong], ['Giám đốc', dv.giam_doc, true]], c.ngay);
  }

  /* ── Biên bản đối chiếu công nợ ──
     Không có /api/doi-tuong/so-chi-tiet hay /api/bao-cao/cong-no* (thiết kế đề xuất) → lấy ĐÚNG nguồn màn
     Chi tiết đối tượng (kt-doi-tuong.js) đang dùng: KH = /api/cong-no?loai=phai_thu&doi_tac=<tên>,
     NCC = /api/cong-no/ncc/<id>/detail. Số liệu là luỹ kế tới ngày in (API không tách số dư đầu kỳ). */
  async function doiChieu(dv) {
    if (!u.id) throw { rong: ['Chưa chọn khách hàng / nhà cung cấp', 'Mở bản in từ trang chi tiết công nợ.'] };
    const kh = u.ben !== 'ncc';
    $('in-ve').href = '/ketoan/doi-tuong?ben=' + (kh ? 'kh' : 'ncc') + '&id=' + encodeURIComponent(u.id);
    let ben, tong = 0, daTra = 0, conLai = 0, phieu = [];
    if (kh) {
      // Bỏ dòng "thu hộ qua ĐVVC" (saleadmin_vc_phai_thu) như Công nợ KH + Chi tiết đối tượng — trước đây biên bản
      // cộng cả dòng này nên lệch màn (vd Anh Tùng: màn 13.094.800 · biên bản 24.094.800).
      const rows = (await KD.api('/api/cong-no?loai=phai_thu&doi_tac=' + encodeURIComponent(u.id) + '&limit=500')).filter((r) => r.ref_source !== 'saleadmin_vc_phai_thu');
      if (!rows.length) throw { rong: ['Không có công nợ phải thu', 'Khách "' + u.id + '" chưa có phiếu công nợ nào.'] };
      rows.forEach((r) => { tong += +r.so_tien || 0; daTra += +r.da_tra || 0; conLai += +r.con_lai || 0; });
      ben = { ten: u.id, ma: '', mst: '' };
      phieu = rows.filter((r) => +r.con_lai > 0).map((r) => ({ so: r.ma_don || r.id, ngay: r.ngay, han: r.han_thanh_toan, tong: +r.so_tien || 0, con: +r.con_lai || 0 }));
    } else if (!/^\d+$/.test(String(u.id))) {
      // id là TÊN nhóm NCC (mở từ Công nợ NCC → Chi tiết đối tượng): .../ncc/<tên>/detail trả 404 → lấy đúng nhóm
      // trong /ncc-module như kt-doi-tuong.js taiNccTheoTen, để số biên bản = số màn chi tiết.
      const r = await KD.api('/api/cong-no/ncc-module?filter=all');
      const g = (r.items || []).find((x) => x.doi_tac === u.id) || (r.items || []).find((x) => (x.doi_tac || '').toLowerCase() === String(u.id).toLowerCase());
      if (!g) throw { rong: ['Không có công nợ phải trả', 'Nhà cung cấp "' + u.id + '" không có trong công nợ phải trả.'] };
      tong = +g.tong_no || 0; daTra = +g.da_tra || 0; conLai = +g.con_lai || 0;
      ben = { ten: g.doi_tac, ma: '', mst: '' };
      phieu = (g.don_list || []).filter((x) => +x.con_lai > 0).map((x) => ({ so: x.ma_don || x.id, ngay: x.ngay, han: x.han_thanh_toan, tong: +x.so_tien || 0, con: +x.con_lai || 0 }));
    } else {
      const r = await KD.api('/api/cong-no/ncc/' + encodeURIComponent(u.id) + '/detail'), s = r.summary || {};
      tong = +s.total_orders || 0; daTra = +s.total_paid || 0; conLai = +s.balance || 0;
      ben = { ten: r.supplier.name, ma: r.supplier.short_code || '', mst: '' };
      phieu = (r.no_phai_tra || []).map((x) => ({ so: x.po_ten_don || ('PO-' + x.po_id), ngay: x.ngay, han: null, tong: +x.so_tien || 0, con: null }));
    }
    datTieuDe('BIÊN BẢN ĐỐI CHIẾU CÔNG NỢ', 'Tính đến ngày ' + KD.ngay(dv.hom_nay)); $('in-dau').innerHTML = dau(dv, '', '');
    const coCon = phieu.some((p) => p.con != null);
    return '<p>Hôm nay, ' + ngayChu(dv.hom_nay).toLowerCase() + ', chúng tôi gồm:</p>'
      + dong('Bên A', esc(dv.ten)) + dong('Đại diện', dv.giam_doc ? esc(dv.giam_doc) + ' — Giám đốc' : '')
      + dong('Bên B', esc(ben.ten) + (ben.ma ? ' (' + esc(ben.ma) + ')' : '')) + dong('Mã số thuế bên B', '') + dong('Đại diện', '')
      + '<p>Cùng đối chiếu công nợ ' + (kh ? 'phải thu (TK 131)' : 'phải trả (TK 331)') + ' như sau:</p>'
      + '<table class="kt-in-bang"><thead><tr><th scope="col">Chỉ tiêu</th><th scope="col">Số tiền (VND)</th></tr></thead><tbody>'
      + [[kh ? 'Tổng giá trị hàng bán' : 'Tổng giá trị hàng mua', tong], [kh ? 'Đã thu' : 'Đã trả', daTra]].map((x) => '<tr><td>' + esc(x[0]) + '</td><td class="num">' + KD.tien(x[1]) + '</td></tr>').join('')
      + '<tr class="is-dam"><td>Còn nợ đến ngày ' + KD.ngay(dv.hom_nay) + '</td><td class="num">' + KD.tien(conLai) + '</td></tr></tbody></table>'
      + (phieu.length ? '<p>' + (coCon ? 'Chi tiết khoản còn nợ:' : 'Chi tiết đơn hàng phát sinh công nợ:') + '</p><table class="kt-in-bang"><thead><tr><th scope="col">Chứng từ</th><th scope="col">Ngày</th>' + (coCon ? '<th scope="col">Hạn thanh toán</th>' : '') + '<th scope="col">Giá trị</th>' + (coCon ? '<th scope="col">Còn nợ</th>' : '') + '</tr></thead><tbody>'
        + phieu.map((p) => '<tr><td>' + esc(p.so) + '</td><td class="kt-in-giua">' + KD.ngay(p.ngay) + '</td>' + (coCon ? '<td class="kt-in-giua">' + (p.han && /^\d{4}-/.test(p.han) ? KD.ngay(p.han) : '') + '</td>' : '') + '<td class="num">' + KD.tien(p.tong) + '</td>' + (coCon ? '<td class="num">' + KD.tien(p.con) + '</td>' : '') + '</tr>').join('') + '</tbody></table>' : '')
      + '<p><b>Kết luận:</b> Tính đến ngày ' + KD.ngay(dv.hom_nay) + ', ' + (kh ? 'Bên B còn nợ Bên A' : 'Bên A còn nợ Bên B') + ' số tiền <b>' + KD.tienVnd(conLai) + '</b> (bằng chữ: ' + esc(KT.bangChu(conLai)) + ').</p>'
      + '<p class="kt-in-ghi">Biên bản lập thành 02 bản, mỗi bên giữ 01 bản có giá trị như nhau. Trong 07 ngày kể từ ngày nhận, nếu Bên B không có ý kiến thì coi như xác nhận số liệu trên.</p>'
      + ky([['Đại diện Bên A', dv.giam_doc, true], ['Kế toán Bên A', dv.ke_toan_truong], ['Đại diện Bên B', '', true], ['Kế toán Bên B', '']]);
  }

  /* ── Báo cáo tài chính ──
     Không có /api/bao-cao/kqkd|cdkt|lctt → gọi ĐÚNG API thật mà 3 màn báo cáo đang dùng (pnl / can-doi /
     cashflow) và dựng cùng các dòng mã số như kt-kqkd.js / kt-cdkt.js / kt-lctt.js, để số in = số trên màn. */
  const MAU = { kqkd: ['BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH', 'Mẫu số B02-DN', '/ketoan/bao-cao/kqkd'], cdkt: ['BÁO CÁO TÌNH HÌNH TÀI CHÍNH', 'Mẫu số B01-DN', '/ketoan/bao-cao/cdkt'], lctt: ['BÁO CÁO LƯU CHUYỂN TIỀN TỆ', 'Mẫu số B03-DN', '/ketoan/bao-cao/lctt'] };
  const r2 = (ma, chi_tieu, cap, a, b) => ({ ma, chi_tieu, cap, ky_nay: a, ky_truoc: b == null ? null : b });
  const kyThangNay = () => { const n = new Date(); return { tu: KD.iso(new Date(n.getFullYear(), n.getMonth(), 1)), den: KD.iso(new Date(n.getFullYear(), n.getMonth() + 1, 0)) }; };
  function kyTruoc(tu, den) {
    const a = new Date(tu + 'T00:00:00'), b = new Date(den + 'T00:00:00'), n = Math.round((b - a) / 864e5) + 1;
    const d2 = new Date(a); d2.setDate(d2.getDate() - 1); const d1 = new Date(d2); d1.setDate(d1.getDate() - (n - 1));
    return { tu: KD.iso(d1), den: KD.iso(d2) };
  }
  /* KQKD: CÙNG nguồn + cách tính với màn /ketoan/bao-cao/kqkd (kt-kqkd.js): /api/bao-cao/pl từng tháng của kỳ
     (+ cùng số tháng liền trước), cộng dồn mọi số, thuế TNDN tính lại trên LNTT cả kỳ khi kỳ > 1 tháng.
     KHÔNG dùng /pnl (theo tiền thu) — số sẽ lệch màn. Phần dựng số dùng CHUNG KT.kqkd (kt-kqkd-tinh.js). */
  function dongKq(c, p) {
    const g = (o, path) => path.split('.').reduce((x, k) => (x == null ? null : x[k]), o);
    const r = (ma, chi_tieu, cap, path) => ({ ma, chi_tieu, cap, ky_nay: typeof path === 'string' ? g(c, path) || 0 : path[0], ky_truoc: typeof path === 'string' ? (p ? g(p, path) || 0 : null) : path[1] });
    const gt = (x) => x.doanh_thu.chiet_khau + x.doanh_thu.giam_tru, khac = (x) => x.thu_nhap_khac - x.cp_khac;
    return [
      r('01', 'Doanh thu bán hàng và cung cấp dịch vụ', 'muc', 'doanh_thu.dt_thuc_hien'),
      r('02', 'Các khoản giảm trừ doanh thu', 'muc', [gt(c), p ? gt(p) : null]),
      r('10', 'Doanh thu thuần về bán hàng và cung cấp dịch vụ', 'tong', 'dt_thuan'),
      r('11', 'Giá vốn hàng bán', 'muc', 'cogs'),
      r('20', 'Lợi nhuận gộp về bán hàng và cung cấp dịch vụ', 'tong', 'ln_gop'),
      r('21', 'Doanh thu hoạt động tài chính', 'muc', 'dt_tai_chinh'),
      r('22', 'Chi phí tài chính', 'muc', 'cp_tai_chinh.tong'),
      r('23', 'Trong đó: Chi phí lãi vay', 'con', 'cp_tai_chinh.lai_vay'),
      r('25', 'Chi phí bán hàng', 'muc', 'cp_ban_hang.tong'),
      r('26', 'Chi phí quản lý doanh nghiệp', 'muc', 'cp_quan_ly.tong'),
      r('30', 'Lợi nhuận thuần từ hoạt động kinh doanh', 'tong', 'ln_thuan_hdkd'),
      r('31', 'Thu nhập khác', 'muc', 'thu_nhap_khac'),
      r('32', 'Chi phí khác', 'muc', 'cp_khac'),
      r('40', 'Lợi nhuận khác', 'tong', [khac(c), p ? khac(p) : null]),
      r('50', 'Tổng lợi nhuận kế toán trước thuế', 'tong', 'ln_truoc_thue'),
      r('51', 'Chi phí thuế TNDN hiện hành', 'muc', 'thue_tndn'),
      r('60', 'Lợi nhuận sau thuế thu nhập doanh nghiệp', 'dam', 'lnst'),
    ];
  }
  /* Kỳ so sánh = đúng như màn báo cáo (KT.kySoSanh): màn truyền ?ky= (vd nam_nay → cùng kỳ năm trước);
     link cũ không có ky → coi như Tuỳ chỉnh (trọn tháng lùi đúng số tháng, lẻ ngày lùi đúng số ngày). */
  const kySs = (k) => KT.kySoSanh(u.ky || 'tuy_chinh', { tu: k.tu, den: k.den });
  async function taiKqkd(k) {
    const ss = kySs(k), t = await KT.kqkd.tai(k.tu, k.den, ss && ss.thang);
    return { ky: t.ky, dong: dongKq(t.c, t.p) };
  }
  async function taiCdkt(k) {
    const den = k.den || KD.iso(new Date()), thang = den.slice(0, 7);
    const d = await KD.api('/api/bao-cao/can-doi?thang=' + thang), ts = d.tai_san, nv = d.nguon_von;
    const [y, m] = d.thang.split('-').map(Number), c = (ma, ct, cap, x) => ({ ma, chi_tieu: ct, cap, cuoi_ky: x, dau_nam: null });
    return { den_ngay: KD.iso(new Date(y, m, 0)), dong: [
      { ma: '', chi_tieu: 'TÀI SẢN', cap: 'nhom' },
      c('110', 'Tiền và các khoản tương đương tiền', 'tong', ts.tien_va_td.tong), c('111', 'Tiền mặt', 'con', ts.tien_va_td.tien_mat_so_quy), c('112', 'Tiền gửi ngân hàng', 'con', ts.tien_va_td.tk_ngan_hang),
      c('130', 'Các khoản phải thu ngắn hạn', 'tong', ts.phai_thu), c('140', 'Hàng tồn kho', 'tong', ts.hang_ton_kho),
      c('220', 'Tài sản cố định', 'tong', ts.tscd_rong), c('221', 'Nguyên giá', 'con', ts.tscd_nguyen_gia), c('222', 'Hao mòn luỹ kế (*)', 'con', -ts.tscd_hao_mon_luy_ke),
      c('270', 'TỔNG CỘNG TÀI SẢN', 'dam', ts.tong_tai_san),
      { ma: '', chi_tieu: 'NGUỒN VỐN', cap: 'nhom' },
      c('311', 'Phải trả người bán ngắn hạn', 'muc', nv.no_phai_tra.phai_tra_ncc), c('320', 'Vay ngắn hạn', 'muc', nv.no_phai_tra.vay_ngan_han), c('338', 'Vay dài hạn', 'muc', nv.no_phai_tra.vay_dai_han),
      c('315', 'Phải trả người lao động', 'muc', nv.no_phai_tra.phai_tra_nv), c('300', 'Tổng nợ phải trả', 'tong', nv.no_phai_tra.tong),
      c('411', 'Vốn góp của chủ sở hữu', 'muc', nv.von_csh.von_gop), c('414', 'Quỹ đầu tư phát triển và quỹ khác', 'muc', nv.von_csh.quy_dn), c('421', 'Lợi nhuận sau thuế chưa phân phối', 'muc', nv.von_csh.ln_giu_lai),
      c('400', 'Tổng vốn chủ sở hữu', 'tong', nv.von_csh.tong), c('440', 'TỔNG CỘNG NGUỒN VỐN', 'dam', nv.tong_nguon_von),
    ] };
  }
  /* LCTT: cùng khoản mục + mã số B03-DN với màn /ketoan/bao-cao/lctt (kt-lctt.js): chi khác = 07 (không phải 04 —
     04 là lãi vay đã trả); quảng cáo gộp mã 02, sửa chữa lớn gộp mã 21; 33 = thu từ đi vay, 34 = trả nợ gốc vay
     (API gộp cả lãi vay vào khoản trả nợ, không tách được ra mã 04). */
  const KM_LCTT = [
    ['01', 'Tiền thu từ bán hàng, cung cấp dịch vụ và doanh thu khác', 'operating', 'thu_kh', 1],
    ['02', 'Tiền chi trả cho người cung cấp hàng hoá và dịch vụ', 'operating', 'tra_ncc', -1],
    ['02', 'Tiền chi trả quảng cáo, marketing', 'operating', 'tra_ads', -1],
    ['03', 'Tiền chi trả cho người lao động', 'operating', 'tra_luong', -1],
    ['07', 'Tiền chi khác cho hoạt động kinh doanh', 'operating', 'chi_khac', -1],
    ['21', 'Tiền chi để mua sắm, xây dựng TSCĐ và các tài sản dài hạn khác', 'investing', 'mua_ccdc', -1],
    ['21', 'Tiền chi sửa chữa lớn tài sản cố định', 'investing', 'sua_chua', -1],
    ['33', 'Tiền thu từ đi vay', 'financing', 'vay_nh', 1],
    ['34', 'Tiền trả nợ gốc vay (gồm lãi vay)', 'financing', 'tra_no_nh', -1],
  ];
  function dongLctt(d) {
    const out = [], v = (n, k) => (d[n] && d[n][k] ? +d[n][k].total || 0 : 0);
    [['I. Lưu chuyển tiền từ hoạt động kinh doanh', 'operating', '20', 'Lưu chuyển tiền thuần từ hoạt động kinh doanh'],
      ['II. Lưu chuyển tiền từ hoạt động đầu tư', 'investing', '30', 'Lưu chuyển tiền thuần từ hoạt động đầu tư'],
      ['III. Lưu chuyển tiền từ hoạt động tài chính', 'financing', '40', 'Lưu chuyển tiền thuần từ hoạt động tài chính']].forEach(([ten, n, maNet, tenNet]) => {
      out.push({ ma: '', chi_tieu: ten, cap: 'nhom' });
      KM_LCTT.filter((x) => x[2] === n).forEach(([ma, t, , k, dau]) => out.push(r2(ma, t, 'muc', dau * v(n, k))));
      out.push(r2(maNet, tenNet, 'tong', d[n].net));
    });
    out.push(r2('50', 'Lưu chuyển tiền thuần trong kỳ (50 = 20 + 30 + 40)', 'tong', d.net_cashflow));
    out.push(r2('60', 'Tiền và tương đương tiền đầu kỳ', 'muc', d.so_du_dau_ky));
    out.push(r2('70', 'Tiền và tương đương tiền cuối kỳ (70 = 50 + 60)', 'dam', d.so_du_cuoi_ky));
    return out;
  }
  async function taiLctt(k) {
    const pr = kySs(k) || kyTruoc(k.tu, k.den);
    const [d, p] = await Promise.all([KD.api('/api/bao-cao/cashflow?' + KT.url.qs({ from: k.tu, to: k.den })), KD.api('/api/bao-cao/cashflow?' + KT.url.qs({ from: pr.tu, to: pr.den })).catch(() => null)]);
    const nay = dongLctt(d), truoc = p ? dongLctt(p) : null;
    return { ky: { tu: d.from || k.tu, den: d.to || k.den }, dong: nay.map((r, i) => (r.ma && truoc ? Object.assign({}, r, { ky_truoc: truoc[i].ky_nay }) : r)) };
  }
  async function baoCao(dv) {
    const m = MAU[u.mau]; if (!m) throw { rong: ['Chưa chọn báo cáo', 'Mở bản in từ màn báo cáo tài chính.'] };
    const k0 = kyThangNay(), k = { tu: u.tu || k0.tu, den: u.den || k0.den };
    const d = await (u.mau === 'kqkd' ? taiKqkd(k) : u.mau === 'cdkt' ? taiCdkt(k) : taiLctt(k));
    $('in-ve').href = m[2] + (u.mau === 'cdkt' ? (u.den ? '?den=' + u.den : '') : u.ky && u.ky !== 'tuy_chinh' ? '?ky=' + encodeURIComponent(u.ky) : '?' + KT.url.qs({ ky: 'tuy_chinh', tu: k.tu, den: k.den }));
    const cd = u.mau === 'cdkt';
    datTieuDe(m[0], cd ? 'Tại ngày ' + KD.ngay(d.den_ngay) : (u.mau === 'lctt' ? '(Theo phương pháp trực tiếp) · ' : '') + 'Kỳ từ ' + KD.ngay(d.ky.tu) + ' đến ' + KD.ngay(d.ky.den));
    $('in-dau').innerHTML = dau(dv, m[1], '(Theo Thông tư số 99/2025/TT-BTC của Bộ Tài chính)');
    // cdkt: API chỉ có số cuối kỳ (không có số đầu năm) → in 1 cột, không để trống cột giả.
    const cot = cd ? ['cuoi_ky'] : ['ky_nay', 'ky_truoc'], nhan = cd ? ['Số cuối kỳ'] : ['Kỳ này', 'Kỳ trước'];
    const soCot = 2 + (u.mau === 'kqkd' ? 1 : 0) + cot.length;
    return '<p class="kt-in-ghi">Đơn vị tính: VND</p><table class="kt-in-bang"><thead><tr><th scope="col">Chỉ tiêu</th><th scope="col">Mã số</th>' + (u.mau === 'kqkd' ? '<th scope="col">Thuyết minh</th>' : '') + nhan.map((n) => '<th scope="col">' + n + '</th>').join('') + '</tr></thead><tbody>'
      + d.dong.map((r) => r.cap === 'nhom' ? '<tr class="is-nhom"><td colspan="' + soCot + '">' + esc(r.chi_tieu) + '</td></tr>'
        : '<tr class="' + (r.cap === 'tong' || r.cap === 'dam' ? 'is-dam' : '') + '"><td class="' + (r.cap === 'con' ? 'kt-in-con' : r.cap === 'con2' ? 'kt-in-con2' : '') + '">' + esc(r.chi_tieu.trim()) + '</td><td class="kt-in-giua">' + esc(r.ma) + '</td>' + (u.mau === 'kqkd' ? '<td class="kt-in-giua">' + esc(r.thuyet_minh || '') + '</td>' : '')
          + cot.map((key) => '<td class="num">' + soBc(r[key]) + '</td>').join('') + '</tr>').join('') + '</tbody></table>'
      + ky([['Người lập biểu', ''], ['Kế toán trưởng', dv.ke_toan_truong], ['Giám đốc', dv.giam_doc, true]], dv.hom_nay);
  }

  /* ── Giấy đề nghị thanh toán / tạm ứng ──
     Chưa có API chi tiết 1 đề nghị (GET /api/duyet-chi/<id> không tồn tại — 405) và màn Duyệt chi chưa có nút In
     → báo rõ thay vì hiện lỗi máy chủ. */
  async function deNghi() {
    throw { rong: ['Chưa hỗ trợ in đề nghị chi', 'Hệ thống chưa có dữ liệu chi tiết 1 đề nghị để in. Xem và duyệt đề nghị ở màn Duyệt chi.'] };
  }

  const LOAI = { chung_tu: chungTu, doi_chieu: doiChieu, bao_cao: baoCao, de_nghi: deNghi };
  async function tai() {
    const nd = $('in-noi-dung'); $('in-dau').innerHTML = ''; datTieuDe('Bản in', ''); nd.innerHTML = KD.KHUNG_TAI; $('in-nut').disabled = true;
    const f = LOAI[u.loai];
    if (!f) { nd.innerHTML = KD.khoiRong('Chưa chọn mẫu in', 'Mở bản in từ nút "In" ở chứng từ, công nợ, báo cáo hoặc đề nghị chi.'); return; }
    try { const dv = await KD.api('/api/don-vi'); nd.innerHTML = await f(dv); $('in-nut').disabled = false;
      nd.querySelectorAll('.kt-in-ky').forEach((k) => k.style.setProperty('--kt-in-cot', k.dataset.cot)); }
    catch (e) { if (e && e.rong) { nd.innerHTML = KD.khoiRong(e.rong[0], e.rong[1]); return; } KD.khoiLoi(nd, 'Không tải được số liệu để in', e, tai); }
  }
  $('in-nut').addEventListener('click', () => window.print());
  tai();
})();
