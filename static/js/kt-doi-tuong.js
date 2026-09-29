/* kt-doi-tuong.js — Chi tiết công nợ một khách hàng / nhà cung cấp (L4).

   API THẬT (khác hẳn README mục 4.23 — không có "báo cáo công nợ theo đối tượng" dùng
   chung 1 shape cho cả 2 bên):
   - NCC (`?ben=ncc`): GET /api/cong-no/ncc/<id>/detail (app/routers/cong_no_ncc.py) — có id
     nhà cung cấp ổn định (muahang.suppliers.id), trả {supplier, summary, no_phai_tra[],
     thanh_toan[]}. Không có hạn thanh toán/trạng thái từng dòng — chỉ có tổng.
   - KH (`?ben=kh`): KHÔNG CÓ endpoint chi tiết theo 1 khách hàng nào cả — app/routers/cong_no.py
     chỉ có CRUD từng dòng công nợ rời rạc (CongNo, khoá bằng chuỗi `doi_tac` tự do, không có
     id khách hàng trong ketoan — khách hàng thật sống ở app "baogia"). Màn này dùng `id` trên
     URL LÀM CHÍNH TÊN ĐỐI TÁC (`doi_tac`) và gọi GET /api/cong-no?doi_tac=<id>&loai=phai_thu,
     tự cộng tổng ở trình duyệt. Không có mã KH, MST, SĐT, NV kinh doanh riêng — các ô đó để
     trống (ẩn theo đúng cách `.filter` sẵn có của màn).
   - KHÔNG có API "sổ chi tiết công nợ" kiểu sổ cái TK 131/331 luỹ kế theo đối tượng (không có
     route `/api/doi-tuong/so-chi-tiet` nào) — khối "Sổ chi tiết công nợ" hiện trạng thái rỗng
     cố định, không gọi API.
   - "Hoá đơn còn nợ" (NCC): mỗi dòng `no_phai_tra` chỉ có SỐ TIỀN PHÁT SINH, không có
     đã trả / còn lại / hạn / trạng thái riêng từng hoá đơn (chỉ có tổng ở `summary`) —
     3 cột đó hiện "—". "Lần thanh toán gần nhất" lấy từ `thanh_toan` (đề xuất trả NCC),
     không phải phiếu chi thật đã chi.
*/
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-doi-tuong')) return;
  const $ = (id) => document.getElementById(id), u = KT.url.doc();
  const kh = u.ben !== 'ncc';
  const C = kh ? { ve: ['/ketoan/cong-no-kh', 'Công nợ khách hàng'], h1: 'Chi tiết công nợ khách hàng', tk: '131', da: 'Đã thu', con: 'Còn phải thu', lap: 'Ghi nhận thu', hoSo: ['/kd/khach-hang/', 'Hồ sơ khách (Kinh doanh)'], nv: 'NV kinh doanh', ls: 'Lần thu gần nhất', du: 'Dư Nợ (phải thu)' }
    : { ve: ['/ketoan/cong-no-ncc', 'Công nợ NCC'], h1: 'Chi tiết công nợ nhà cung cấp', tk: '331', da: 'Đã trả', con: 'Còn phải trả', lap: 'Ghi nhận trả', hoSo: ['/mua-hang/nha-cung-cap/', 'Hồ sơ NCC (Mua hàng)'], nv: 'NV mua hàng', ls: 'Lần trả gần nhất', du: 'Dư Có (phải trả)' };
  const the = (ico, mau, nhan, v, phu, tip) => '<article class="kd-kpi kd-kpi--gon"><div class="kd-kpi__head"><span class="ico-tile' + (mau ? ' ico-tile--' + mau : '') + '" aria-hidden="true"><i class="bi ' + ico + '"></i></span><span class="kd-kpi__label">' + esc(nhan) + KD.tip(tip || '') + '</span></div>'
    + '<div class="kd-kpi__value num" title="' + esc(KD.tienVnd(v)) + '">' + KD.tienGonHtml(v) + '</div><p class="kd-kpi__phu">' + phu + '</p></article>';
  $('dt-ve').innerHTML = '<i class="bi bi-arrow-left" aria-hidden="true"></i>' + C.ve[1]; $('dt-ve').href = C.ve[0];
  $('dt-h1').textContent = C.h1; $('dt-lap-chu').textContent = C.lap; $('dt-cot-da').textContent = C.da; $('dt-h-ls').textContent = C.ls;
  $('dt-ico').className = 'ico-tile ico-tile--lg' + (kh ? '' : ' ico-tile--tim');

  async function tai() {
    $('dt-tt').innerHTML = KD.KHUNG_TAI; $('dt-than').hidden = true;
    if (!u.id) { $('dt-ma').textContent = '—'; $('dt-tt').innerHTML = KD.khoiRong('Chưa chọn đối tượng', 'Mở trang này từ màn Công nợ.'); return; }
    try {
      const d = kh ? await taiKh(u.id) : await taiNcc(u.id);
      $('dt-tt').innerHTML = ''; $('dt-than').hidden = false; veDau(d); veSoRong();
    } catch (e) { $('dt-ma').textContent = '—'; KD.khoiLoi($('dt-tt'), 'Không tải được công nợ', e, tai); }
  }

  /* ── NCC — 2 đường:
     · id là SỐ (muahang.suppliers.id, mở từ nơi khác) → GET /api/cong-no/ncc/<id>/detail như cũ.
     · id là TÊN (mở từ màn Công nợ NCC — ncc-module gộp theo tên, không có id NCC thật) →
       GET /api/cong-no/ncc-module rồi lấy đúng nhóm có doi_tac trùng tên. BUG FIX 2026-09-25:
       trước đây danh sách truyền id "ncc0/ncc1…" → .../ncc/ncc0/detail 422, trang lỗi. Nguồn này
       cũng CHÍNH LÀ nguồn của màn danh sách nên số ở đây khớp số dòng NCC bên đó, và có đủ
       đã trả / còn lại / hạn / ngày trả từng đơn (đường detail chỉ có tổng). ── */
  async function taiNcc(id) {
    return /^\d+$/.test(String(id)) ? taiNccTheoId(id) : taiNccTheoTen(id);
  }
  async function taiNccTheoTen(ten) {
    const r = await KD.api('/api/cong-no/ncc-module?filter=all');
    const g = (r.items || []).find((x) => x.doi_tac === ten) || (r.items || []).find((x) => (x.doi_tac || '').toLowerCase() === String(ten).toLowerCase());
    if (!g) throw new Error('Không tìm thấy nhà cung cấp "' + ten + '" trong công nợ phải trả.');
    const homNay = KD.iso(new Date());
    let quaHan = 0;
    const phieu = (g.don_list || []).map((x) => {
      const c = +x.con_lai || 0, han = /^\d{4}-\d{2}-\d{2}/.test(x.han_thanh_toan || '') ? x.han_thanh_toan.slice(0, 10) : null;
      const qh = han && han < homNay && c > 0 ? Math.round((new Date(homNay) - new Date(han)) / 864e5) : 0;
      if (qh > 0) quaHan += c;
      return {
        id: x.id, so_phieu: x.ma_don || x.id, don_hang: x.ma_don ? x.id : '', ngay: x.ngay, han_tt: han,
        tong: +x.so_tien || 0, da_thu: +x.da_tra || 0, con_lai: c, qua_han_ngay: qh,
        trang_thai: c <= 0 ? 'da_thu_du' : qh > 0 ? 'qua_han' : (+x.da_tra > 0 ? 'thu_mot_phan' : 'chua_thu'),
      };
    });
    const conLai = +g.con_lai || 0;
    return {
      khach: { id: g.doi_tac, ma: '—', ten: g.doi_tac, sdt: null, mst: null, nv_kd: null },
      tong_no: +g.tong_no || 0, da_thu: +g.da_tra || 0, con_lai: conLai, qua_han: quaHan, co_han: true,
      // Cùng quy tắc nhóm tuổi với màn Công nợ NCC (theo hoá đơn quá hạn lâu nhất) — trước luôn 'qh_1_30'.
      nhom_tuoi: conLai <= 0 ? 'da_thu_du' : nhomTheoNgay(Math.max(0, ...phieu.map((p) => p.qua_han_ngay))),
      no_thuc: +g.no_thuc_phai_tra || 0, no_du_kien: +g.no_du_kien || 0,
      phieu,
      lich_su_thu: (g.don_list || []).filter((x) => +x.da_tra > 0).map((x) => ({ ngay: x.ngay_tra || x.ngay, so_ct: x.ma_don || x.id, so_tien: +x.da_tra || 0, hinh_thuc: x.ngay_tra ? 'Đã trả' : 'Chưa ghi ngày' }))
        .sort((a, b) => (a.ngay < b.ngay ? 1 : -1)),
    };
  }
  async function taiNccTheoId(id) {
    const r = await KD.api('/api/cong-no/ncc/' + encodeURIComponent(id) + '/detail');
    const s = r.summary || {};
    const conLai = +s.balance || 0;
    return {
      khach: { id: r.supplier.id, ma: r.supplier.short_code || '—', ten: r.supplier.name, sdt: r.supplier.phone, mst: null, nv_kd: null },
      tong_no: +s.total_orders || 0, da_thu: +s.total_paid || 0, con_lai: conLai, qua_han: 0,
      nhom_tuoi: conLai <= 0 ? 'da_thu_du' : 'chua_den_han',
      phieu: (r.no_phai_tra || []).map((x) => ({
        id: x.congno_id, so_phieu: x.po_ten_don || ('PO-' + x.po_id) || ('CN-' + x.congno_id), don_hang: x.po_id ? String(x.po_id) : '',
        ngay: x.ngay, han_tt: null, tong: +x.so_tien || 0, da_thu: null, con_lai: null, trang_thai: null, qua_han_ngay: 0,
      })),
      lich_su_thu: (r.thanh_toan || []).map((x) => ({ ngay: x.ngay, so_ct: 'DXT-' + x.id, so_tien: +x.so_tien || 0, hinh_thuc: x.nguoi_duyet ? 'Đã duyệt · ' + x.nguoi_duyet : (x.trang_thai || '—') })),
    };
  }
  /* ── KH: KHÔNG có id khách hàng thật trong ketoan — `id` trên URL = tên đối tác (doi_tac),
     lọc thẳng bảng công nợ rời rạc rồi tự cộng tổng. ── */
  async function taiKh(doiTac) {
    // Bỏ dòng "thu hộ qua ĐVVC" (saleadmin_vc_phai_thu) — trùng phải thu của chính đơn báo giá; màn cũ
    // và màn Công nợ KH (kt-cong-no.js) đều loại → tổng ở đây khớp dòng khách bên danh sách.
    const rows = (await KD.api('/api/cong-no?loai=phai_thu&doi_tac=' + encodeURIComponent(doiTac) + '&limit=500'))
      .filter((r) => r.ref_source !== 'saleadmin_vc_phai_thu');
    const homNay = KD.iso(new Date());
    let tongNo = 0, daThu = 0, conLai = 0, quaHan = 0;
    const phieu = rows.map((r) => {
      const c = +r.con_lai || 0; tongNo += +r.so_tien || 0; daThu += +r.da_tra || 0; conLai += c;
      // Không ghi hạn → hạn = ngày phát sinh + 30 ngày (cùng quy tắc Tổng quan & Công nợ KH / Dashboard cũ).
      const hanOk = r.han_thanh_toan && /^\d{4}-\d{2}-\d{2}/.test(r.han_thanh_toan);
      const hanTinh = hanOk ? r.han_thanh_toan.slice(0, 10) : (r.ngay ? KD.iso(new Date(new Date(String(r.ngay).slice(0, 10) + 'T00:00:00').getTime() + 30 * 864e5)) : null);
      const quaHanNgay = hanTinh && hanTinh < homNay && c > 0 ? Math.round((new Date(homNay) - new Date(hanTinh)) / 864e5) : 0;
      if (quaHanNgay > 0) quaHan += c;
      return {
        id: r.id, so_phieu: r.ma_don || r.id, don_hang: r.ma_don ? r.id : '', ngay: r.ngay, han_tt: hanTinh,
        tong: +r.so_tien || 0, da_thu: +r.da_tra || 0, con_lai: c,
        trang_thai: r.trang_thai === 'da_tra' ? 'da_thu_du' : quaHanNgay > 0 ? 'qua_han' : (+r.da_tra > 0 ? 'thu_mot_phan' : 'chua_thu'),
        qua_han_ngay: quaHanNgay,
      };
    });
    return {
      khach: { id: doiTac, ma: '—', ten: doiTac, sdt: null, mst: null, nv_kd: null },
      tong_no: tongNo, da_thu: daThu, con_lai: conLai, qua_han: quaHan,
      nhom_tuoi: conLai <= 0 ? 'da_thu_du' : nhomTheoNgay(Math.max(0, ...phieu.map((p) => p.qua_han_ngay))),
      phieu,
      lich_su_thu: rows.filter((r) => +r.da_tra > 0).map((r) => ({ ngay: r.ngay_tra || r.ngay, so_ct: r.id, so_tien: +r.da_tra || 0, hinh_thuc: r.tai_khoan || '—' })),
    };
  }

  function nhomTheoNgay(n) { return n > 60 ? 'qh_tren_60' : n > 30 ? 'qh_31_60' : n > 0 ? 'qh_1_30' : 'chua_den_han'; }
  function veDau(d) {
    const k = d.khach; document.title = k.ten + ' — ' + C.h1;
    $('dt-crumb').textContent = k.ten; $('dt-ma').innerHTML = (k.ma && k.ma !== '—' ? '<span class="num">' + esc(k.ma) + '</span> · ' : '') + esc(k.ten);
    $('dt-pill').innerHTML = KT.pillTuoiNo(d.nhom_tuoi, !kh && d.nhom_tuoi === 'da_thu_du' ? 'Đã trả đủ' : '');
    $('dt-meta').innerHTML = [k.mst ? '<span>MST: <b>' + esc(k.mst) + '</b></span>' : '', k.sdt ? '<span>Điện thoại: <b>' + esc(k.sdt) + '</b></span>' : '', k.nv_kd ? '<span>' + C.nv + ': <b>' + esc(k.nv_kd) + '</b></span>' : ''].join('');
    // Cơ chế màn cũ: ghi nhận thu/trả từng khoản (POST /api/cong-no/{id}/tra — trừ công nợ + ghi Sổ quỹ).
    $('dt-lap').onclick = () => KTGhiNhanTra.mo({
      loai: kh ? 'phai_thu' : 'phai_tra', chonDoiTuong: k.ten, xong: tai,
      doiTuong: [{ ten: k.ten, khoan: d.phieu.filter((p) => p.con_lai != null).map((p) => ({ id: p.id, ma_don: kh ? p.so_phieu : p.so_phieu, so_tien: p.tong, da_tra: p.da_thu, con_lai: p.con_lai })) }],
    });
    $('dt-doi-chieu').href = '/ketoan/in?loai=doi_chieu&ben=' + (kh ? 'kh' : 'ncc') + '&id=' + encodeURIComponent(k.id);
    const soHd = d.phieu.filter((p) => p.con_lai == null || p.con_lai > 0).length;
    // Dòng so_tien = 0 (chỉ có da_tra: trả trước/ứng/đặt cọc) không phải hoá đơn — đếm tách ra.
    const soPs = d.phieu.filter((p) => p.tong > 0).length, soUng = d.phieu.length - soPs;
    // 4 thẻ chính; trả trước/ứng và (NCC) Nợ thực / Nợ dự kiến nằm trong ⓘ của thẻ Tổng phát sinh.
    const tipTong = [soUng ? KD.soDem(soUng) + ' khoản trả trước/ứng (không phải hoá đơn).' : '',
      d.no_thuc != null ? 'Nợ thực phải trả ' + KD.tienVnd(d.no_thuc) + ' (đơn đã xong + nhập tay) · Nợ dự kiến ' + KD.tienVnd(d.no_du_kien) + ' (đơn chưa xong).' : ''].filter(Boolean).join(' ');
    $('dt-kpi').innerHTML = the('bi-receipt', '', 'Tổng phát sinh', d.tong_no, KD.soDem(soPs) + ' hoá đơn', tipTong) + the('bi-cash-coin', 'success', C.da, d.da_thu, d.tong_no ? KD.phanTram(d.da_thu / d.tong_no * 100) + ' tổng phát sinh' : '')
      + the('bi-hourglass-split', 'warning', C.con, d.con_lai, KD.soDem(soHd) + ' hoá đơn còn nợ') + the('bi-exclamation-triangle', 'danger', 'Quá hạn', d.qua_han, kh || d.co_han ? (d.qua_han ? '<span class="pill pill--danger">' + (kh ? 'Cần đòi ngay' : 'Cần trả ngay') + '</span>' : 'Không có') : 'Chưa có dữ liệu hạn');
    $('dt-kpi').classList.remove('kt-kpi-row--6'); $('dt-kpi').classList.add('kt-kpi-row--4');
    const con = d.phieu.filter((p) => p.con_lai == null || p.con_lai > 0);
    $('dt-hd-gy').innerHTML = kh && con.length ? 'Cũ nhất trước' + KD.tip('Tiền thu được trừ vào hoá đơn cũ nhất.') : (!kh && !d.co_han ? 'Chỉ có tổng phải trả' : '');
    $('dt-hd-cuon').hidden = !con.length; $('dt-hd-tt').innerHTML = con.length ? '' : KD.khoiRong('Không còn hoá đơn nào nợ', 'Mọi hoá đơn đã được ' + (kh ? 'thu' : 'trả') + ' đủ.');
    $('dt-hd').innerHTML = con.slice().sort((a, b) => (a.ngay < b.ngay ? -1 : 1)).map((p) => '<tr><td>' + KT.linkCt(p.so_phieu, p.ngay) + (p.don_hang ? '<span class="kt-khach__ma">' + esc(p.don_hang) + '</span>' : '') + '</td><td>' + KD.ngay(p.ngay) + '</td>'
      + '<td>' + (p.han_tt ? KD.ngay(p.han_tt) + (p.qua_han_ngay > 0 ? '<span class="kt-khach__ma">Quá ' + KD.soDem(p.qua_han_ngay) + ' ngày</span>' : '') : '<span class="kd-muted">—</span>') + '</td><td class="num">' + KD.tien(p.tong) + '</td><td class="num">' + KT.tienSo(p.da_thu) + '</td><td class="num kd-strong">' + (p.con_lai == null ? '<span class="kd-muted">—</span>' : KD.tien(p.con_lai)) + '</td>'
      + '<td>' + (p.trang_thai ? KT.pillPhieu(p.trang_thai, kh ? '' : ({ chua_thu: 'Chưa trả', thu_mot_phan: 'Trả một phần', da_thu_du: 'Đã trả đủ' })[p.trang_thai] || '') : '<span class="kd-muted">—</span>') + '</td></tr>').join('');
    // Dòng cộng đối chiếu (BRIEF2): bảng chỉ gồm khoản còn nợ (con_lai > 0) nên tổng bảng lệch thẻ
    // "Còn phải thu/trả" đúng bằng phần trả trước/ứng chưa cấn trừ (con_lai < 0) — vd CHIẾN PHƯƠNG
    // bảng 728.717.049, thẻ 350.717.049, chênh -378.000.000. Hiện cả hai dòng để khớp được.
    const coSo = con.filter((p) => p.con_lai != null);
    const cg = coSo.reduce((a, p) => ({ gt: a.gt + p.tong, da: a.da + (p.da_thu || 0), con: a.con + p.con_lai }), { gt: 0, da: 0, con: 0 });
    const ung = d.phieu.reduce((a, p) => a + (p.con_lai != null && p.con_lai < 0 ? p.con_lai : 0), 0);
    $('dt-hd-cong').innerHTML = coSo.length ? '<tr><th scope="row" colspan="3">Cộng ' + KD.soDem(coSo.length) + ' hoá đơn còn nợ</th><td class="num">' + KD.tien(cg.gt) + '</td><td class="num">' + KT.tienSo(cg.da) + '</td><td class="num">' + KD.tien(cg.con) + '</td><td></td></tr>'
      + (ung ? '<tr><th scope="row" colspan="5">Trả trước/ứng chưa cấn trừ vào hoá đơn</th><td class="num">' + KD.tien(ung) + '</td><td></td></tr>'
        + '<tr><th scope="row" colspan="5">= ' + C.con + '</th><td class="num">' + KD.tien(cg.con + ung) + '</td><td></td></tr>' : '') : '';
    $('dt-kv').innerHTML = [['Mã', k.ma !== '—' ? k.ma : null], ['Tên', k.ten], ['Mã số thuế', k.mst], ['Điện thoại', k.sdt], [C.nv, k.nv_kd], ['Tài khoản', 'TK ' + C.tk]].filter((x) => x[1]).map((x) => '<dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd>').join('');
    $('dt-ls').innerHTML = (d.lich_su_thu || []).length ? '<ul class="kd-lines">' + d.lich_su_thu.slice(0, 8).map((x) => '<li><span>' + KT.linkCt(x.so_ct, x.ngay) + ' · ' + esc(x.hinh_thuc) + '</span><b class="num">' + KD.tienVnd(x.so_tien) + '</b><span class="kd-lines__sub">' + KD.ngay(x.ngay) + '</span></li>').join('') + '</ul>'
      : KD.khoiRong(kh ? 'Chưa thu lần nào' : 'Chưa trả lần nào', '');
    $('dt-lq').innerHTML = [[C.hoSo[0] + encodeURIComponent(k.id), 'bi-person-vcard', C.hoSo[1], ''], [C.ve[0], 'bi-list-ul', C.ve[1], '']]
      .map((x) => '<li><a href="' + x[0] + '"><i class="bi ' + x[1] + '" aria-hidden="true"></i><span class="kd-related__ten">' + esc(x[2]) + '</span>' + (x[3] ? '<span class="kd-related__sub">' + esc(x[3]) + '</span>' : '') + '</a></li>').join('');
  }

  /* ── Sổ chi tiết theo TK 131/331 luỹ kế: chưa có nguồn dữ liệu — ẩn cả thẻ (đợt 4: bỏ khối trống). ── */
  function veSoRong() {
    $('dt-h-so').closest('.kd-card').hidden = true;
  }
  tai();
})();
