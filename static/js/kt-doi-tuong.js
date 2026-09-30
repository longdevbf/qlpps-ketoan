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
   - Bảng "Hoá đơn" (NCC, đường id số): mỗi dòng `no_phai_tra` chỉ có SỐ TIỀN PHÁT SINH, không có
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
    // Tạm ẩn nợ dự kiến (đơn/PO chưa hoàn thành, nhom === 'du_kien') cho KHỚP màn Công nợ NCC (kt-cong-no.js, chuyenNCC — cùng quy tắc:
    // lọc rồi tự cộng lại, KHÔNG dùng g.tong_no/g.da_tra/g.con_lai vì backend vẫn gộp cả hai nhóm). Người dùng chốt 29/09/2026;
    // muốn bật lại thì bỏ dòng lọc này Ở CẢ HAI file.
    const dsDon = (g.don_list || []).filter((x) => x.nhom !== 'du_kien');
    const cong = (k) => dsDon.reduce((a, x) => a + (Number(x[k]) || 0), 0);
    const homNay = KD.iso(new Date());
    let quaHan = 0;
    const phieu = dsDon.map((x) => {
      const c = +x.con_lai || 0, han = /^\d{4}-\d{2}-\d{2}/.test(x.han_thanh_toan || '') ? x.han_thanh_toan.slice(0, 10) : null;
      const qh = han && han < homNay && c > 0 ? Math.round((new Date(homNay) - new Date(han)) / 864e5) : 0;
      if (qh > 0) quaHan += c;
      return {
        id: x.id, so_phieu: x.ma_don || x.id, don_hang: '', ngay: x.ngay, han_tt: han,
        tong: +x.so_tien || 0, da_thu: +x.da_tra || 0, con_lai: c, qua_han_ngay: qh,
        trang_thai: c <= 0 ? 'da_thu_du' : qh > 0 ? 'qua_han' : (+x.da_tra > 0 ? 'thu_mot_phan' : 'chua_thu'),
      };
    });
    const conLai = cong('con_lai');
    // BƯỚC 3 30/09/2026: tra_truoc dương khi conLai < 0 (đã trả nhiều hơn hoá đơn thực).
    const traTruoc = Math.max(0, -conLai);
    return {
      khach: { id: g.doi_tac, ma: '—', ten: g.doi_tac, sdt: null, mst: null, nv_kd: null },
      tong_no: cong('so_tien'), da_thu: cong('da_tra'), con_lai: conLai, tra_truoc: traTruoc, qua_han: quaHan, co_han: true,
      // Cùng quy tắc nhóm tuổi với màn Công nợ NCC (theo hoá đơn quá hạn lâu nhất) — trước luôn 'qh_1_30'.
      nhom_tuoi: conLai <= 0 ? 'da_thu_du' : nhomTheoNgay(Math.max(0, ...phieu.map((p) => p.qua_han_ngay))),
      phieu,
      lich_su_thu: dsDon.filter((x) => +x.da_tra > 0).map((x) => ({ ngay: x.ngay_tra || x.ngay, so_ct: x.ma_don || x.id, ma_cn: x.id, so_tien: +x.da_tra || 0, hinh_thuc: x.ngay_tra ? 'Đã trả' : 'Chưa ghi ngày' }))
        .sort((a, b) => (a.ngay < b.ngay ? 1 : -1)),
    };
  }
  async function taiNccTheoId(id) {
    const r = await KD.api('/api/cong-no/ncc/' + encodeURIComponent(id) + '/detail');
    const s = r.summary || {};
    // Tạm ẩn nợ dự kiến (nhom_no==='du_kien') — quyết định người dùng 29/09/2026, cùng quy tắc
    // với taiNccTheoTen/kt-cong-no.js. total_orders_thuc/summary đã lọc sẵn ở backend; ở đây lọc
    // thêm bảng "Hoá đơn" hiển thị cho khớp. total_paid không tách theo nhóm được nên trừ thẳng.
    const conLai = (+s.total_orders_thuc || 0) - (+s.total_paid || 0);
    // BƯỚC 3 30/09/2026: backend đã tính sẵn tra_truoc (xem cong_no_ncc.py::ncc_detail).
    const traTruoc = +s.tra_truoc || 0;
    return {
      khach: { id: r.supplier.id, ma: r.supplier.short_code || '—', ten: r.supplier.name, sdt: r.supplier.phone, mst: null, nv_kd: null },
      tong_no: +s.total_orders_thuc || 0, da_thu: +s.total_paid || 0, con_lai: conLai, tra_truoc: traTruoc, qua_han: 0,
      nhom_tuoi: conLai <= 0 ? 'da_thu_du' : 'chua_den_han',
      phieu: (r.no_phai_tra || []).filter((x) => x.nhom_no !== 'du_kien').map((x) => ({
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
        id: r.id, so_phieu: r.ma_don || r.id, don_hang: '', ngay: r.ngay, han_tt: hanTinh,
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

  /* ── Bảng hoá đơn có bộ lọc Tất cả / Chưa trả / Đã trả. "Chưa trả" = còn nợ (kể cả trả một phần), "Đã trả" = trả đủ.
     Trước 29/09/2026 bảng chỉ có khoản còn nợ nên hoá đơn đã trả không hiện ở đâu cả. ── */
  // dangXem là biến cấp IIFE để listener nút lọc (gắn MỘT lần, ở dưới) vẽ lại đúng dữ liệu vừa tải mà không gọi lại API;
  // loc cũng ở đây để giữ bộ lọc khi tải lại sau "Ghi nhận trả".
  let loc = 'tat_ca', dangXem = null;
  const xepNgay = (a, b) => (a.ngay < b.ngay ? -1 : a.ngay > b.ngay ? 1 : String(a.id).localeCompare(String(b.id)));
  // MỘT nơi định nghĩa "hoá đơn" (bảng, nút lọc và số đếm ở thẻ KPI cùng dùng): tong > 0. Dòng so_tien 0 là trả trước/ứng, không phải
  // hoá đơn. Hoá đơn thu/trả DƯ (tong > 0, con_lai < 0, đã da_tra — DB dev 29/09/2026 có 8 dòng) vẫn là hoá đơn ĐÃ trả.
  const laHoaDon = (p) => p.tong > 0;
  const chuaTra = (p) => laHoaDon(p) && (p.con_lai == null || p.con_lai > 0);
  const daTra = (p) => laHoaDon(p) && p.con_lai != null && p.con_lai <= 0;
  // Dòng phụ dưới mã hoá đơn: mã công nợ CN-… (+ mã đơn hàng nếu có). Bỏ khi mã hiển thị đã CHÍNH LÀ mã CN (dòng nhập tay không
  // gắn đơn), nếu không cùng một mã in hai lần trên hai dòng liền nhau.
  const moTaHd = (p) => { const phu = [p.so_phieu !== p.id ? p.id : '', p.don_hang].filter(Boolean).map(esc).join(' · '); return phu ? '<span class="kt-khach__ma">' + phu + '</span>' : ''; };
  function veHoaDon() {
    const d = dangXem; if (!d) return;
    const viec = kh ? 'thu' : 'trả';
    // Đường NCC theo id số chỉ có số tiền từng dòng, không có đã trả/còn lại (con_lai null) → không phân được, ẩn bộ lọc.
    const coTinhTrang = d.phieu.some((p) => p.con_lai != null);
    const cheDo = coTinhTrang ? loc : 'tat_ca';
    const dsHd = d.phieu.filter(laHoaDon), soChua = dsHd.filter(chuaTra).length;
    const nhan = { tat_ca: ['Tất cả', dsHd.length], chua: ['Chưa ' + viec, soChua], da: [C.da, dsHd.length - soChua] };
    $('dt-loc').hidden = !coTinhTrang;
    $('dt-loc').querySelectorAll('button').forEach((b) => { const n = nhan[b.dataset.loc]; b.textContent = n[0] + ' (' + KD.soDem(n[1]) + ')'; b.setAttribute('aria-pressed', String(b.dataset.loc === cheDo)); });
    const hien = (cheDo === 'chua' ? dsHd.filter(chuaTra) : cheDo === 'da' ? dsHd.filter(daTra) : dsHd.slice()).sort(xepNgay);
    // Khoản con_lai < 0 KHÔNG nằm trong bảng đang hiện được liệt kê TỪNG khoản ở chân bảng (mã CN + đơn + ngày) để số âm truy ngược
    // được về dòng gốc, không gộp thành một số "−5.000.000" không nói của đơn nào. Có hai loại: trả trước/ứng (tong = 0) và — chỉ ở chế
    // độ "Chưa trả", vì lúc đó chúng không nằm trong bảng — hoá đơn thu/trả dư; thiếu chúng thì "= Còn phải thu/trả" lệch thẻ.
    // Chưa gắn link: Sổ cái không có bút toán nào cho các dòng ứng (kiểm DB 29/09/2026: 0/31), Sổ quỹ chỉ có ở 27/31 — chưa có đích
    // bấm được cho cả loại. Khai trước khi quyết định ẩn bảng: khách/NCC hết hoá đơn nợ mà còn khoản ứng vẫn phải hiện bảng, nếu không
    // thẻ "Còn phải thu/trả" âm mà không giải thích. Chế độ "Đã trả" không có: hoá đơn đã trả không liên quan số còn phải trả.
    const dangHien = new Set(hien);
    const dsAm = cheDo === 'da' ? [] : d.phieu.filter((p) => p.con_lai != null && p.con_lai < 0 && !dangHien.has(p)).sort(xepNgay);
    const tongAm = dsAm.reduce((a, p) => a + p.con_lai, 0);
    // Ghi chú dưới tiêu đề: nhãn nút "Chưa trả" gồm cả hoá đơn trả MỘT PHẦN (trong bảng nhãn đó là "Trả một phần"), nói rõ để khỏi hiểu nhầm.
    const gy = [];
    if (coTinhTrang) gy.push('“Chưa ' + viec + '” gồm cả hoá đơn ' + viec + ' một phần');
    if (kh && cheDo !== 'da' && hien.length) gy.push('Cũ nhất trước' + (cheDo === 'chua' ? KD.tip('Tiền thu được trừ vào hoá đơn cũ nhất.') : ''));
    if (!kh && !d.co_han) gy.push('Chỉ có tổng phải trả');
    $('dt-hd-gy').innerHTML = gy.join(' · ');
    const rong = cheDo === 'da' ? ['Chưa có hoá đơn nào đã ' + viec, 'Hoá đơn được ' + viec + ' đủ sẽ hiện ở đây.']
      : cheDo === 'chua' ? ['Không còn hoá đơn nào nợ', 'Mọi hoá đơn đã được ' + viec + ' đủ.'] : ['Chưa có hoá đơn nào', 'Hoá đơn phát sinh từ đơn hàng sẽ hiện ở đây.'];
    $('dt-hd-cuon').hidden = !hien.length && !dsAm.length; $('dt-hd-tt').innerHTML = hien.length ? '' : KD.khoiRong(rong[0], rong[1]);
    // LỖI 9 (kiểm chứng độc lập 30/09/2026, chỉ NCC): ở chế độ "Đã trả"/"Tất cả", hoá đơn trả DƯ
    // (con_lai < 0) không nằm trong dsAm (chỉ tách ở chế độ khác "da" — dòng 172) nên lộ số âm
    // trần + pill "Đã trả đủ" trong bảng chính, ngược với "Trả trước X" đã hiện ở thẻ KPI cùng
    // màn. Đổi cách hiện — KHÔNG đổi dữ liệu/số, chỉ đổi cách đọc cho nhất quán toàn màn.
    $('dt-hd').innerHTML = hien.map((p) => {
      const laTraTruocHd = !kh && p.con_lai != null && p.con_lai < 0;
      const oConLai = p.con_lai == null ? '<span class="kd-muted">—</span>'
        : laTraTruocHd ? '<span class="kt-so--tra-truoc">Trả trước ' + KD.tien(-p.con_lai) + '</span>' : KD.tien(p.con_lai);
      const oTrangThai = laTraTruocHd ? '<span class="pill pill--muted">Trả trước</span>'
        : (p.trang_thai ? KT.pillPhieu(p.trang_thai, kh ? '' : ({ chua_thu: 'Chưa trả', thu_mot_phan: 'Trả một phần', da_thu_du: 'Đã trả đủ' })[p.trang_thai] || '') : '<span class="kd-muted">—</span>');
      return '<tr><td>' + KT.linkCt(p.so_phieu, p.ngay) + moTaHd(p) + '</td><td>' + KD.ngay(p.ngay) + '</td>'
        + '<td>' + (p.han_tt ? KD.ngay(p.han_tt) + (p.qua_han_ngay > 0 ? '<span class="kt-khach__ma">Quá ' + KD.soDem(p.qua_han_ngay) + ' ngày</span>' : '') : '<span class="kd-muted">—</span>') + '</td><td class="num">' + KD.tien(p.tong) + '</td><td class="num">' + KT.tienSo(p.da_thu) + '</td><td class="num kd-strong">' + oConLai + '</td>'
        + '<td>' + oTrangThai + '</td></tr>';
    }).join('');
    // Dòng cộng đối chiếu (BRIEF2): thẻ "Còn phải thu/trả" là số RÒNG nên = tổng cột "Còn lại" của bảng + các khoản âm chưa nằm trong
    // bảng (dsAm) — vd CHIẾN PHƯƠNG (đo 29/09/2026) bảng 746.017.049, thẻ 368.017.049, chênh −378.000.000. Hiện cả hai dòng để khớp được.
    const coSo = hien.filter((p) => p.con_lai != null);
    const cg = coSo.reduce((a, p) => ({ gt: a.gt + p.tong, da: a.da + (p.da_thu || 0), con: a.con + p.con_lai }), { gt: 0, da: 0, con: 0 });
    const moTaAm = (p) => (p.tong > 0 ? (kh ? 'Thu' : 'Trả') + ' thừa so với hoá đơn' : 'Trả trước/ứng chưa cấn trừ vào hoá đơn') + ' <span class="kt-khach__ma">' + esc(p.id) + (p.so_phieu && p.so_phieu !== p.id ? ' · đơn ' + esc(p.so_phieu) : '') + ' · ' + KD.ngay(p.ngay) + '</span>';
    const hauTo = cheDo === 'chua' ? ' còn nợ' : cheDo === 'da' ? ' đã ' + viec : '';
    // Ba ô số Giá trị · Đã trả · Còn lại của một dòng chân bảng, cùng cột với thân bảng để cộng dọc được; null = để trống.
    const o = (v, dinhDang) => '<td class="num">' + (v == null ? '' : dinhDang(v)) + '</td>';
    const o3 = (gt, da, con) => o(gt, (x) => KT.tienSo(x)) + o(da, (x) => KT.tienSo(x)) + o(con, (x) => KD.tien(x)) + '<td></td>';
    const tongAmGt = dsAm.reduce((a, p) => a + p.tong, 0), tongAmDa = dsAm.reduce((a, p) => a + (p.da_thu || 0), 0);
    // Chế độ "Tất cả": dòng cuối cộng đủ 3 cột và PHẢI bằng 3 thẻ Tổng phát sinh / Đã trả / Còn phải trả (khoản trả trước/ứng có da_tra
    // nhưng so_tien 0 nên nếu không cộng vào thì cột Đã trả lệch thẻ đúng bằng tổng ứng). Chế độ "Chưa trả" chỉ đối chiếu số còn phải trả.
    // LỖI 9 (kiểm chứng độc lập 30/09/2026, chỉ NCC): tổng cộng < 0 khớp cùng ý "Trả trước còn
    // lại" đã đổi ở thẻ KPI (xem laTraTruocDt phía trên) — đổi nhãn/số cho khớp, không đổi cách tính.
    const tongConCuoi = cg.con + tongAm;
    const laTraTruocCuoi = !kh && tongConCuoi < 0;
    const oConCuoi = laTraTruocCuoi ? '<td class="num"><span class="kt-so--tra-truoc">Trả trước ' + KD.tien(-tongConCuoi) + '</span></td><td></td>' : o(tongConCuoi, (x) => KD.tien(x)) + '<td></td>';
    const dongCuoi = cheDo === 'tat_ca'
      ? '<tr><th scope="row" colspan="3">= Tổng cộng, khớp các thẻ phía trên</th>' + o(cg.gt + tongAmGt, (x) => KT.tienSo(x)) + o(cg.da + tongAmDa, (x) => KT.tienSo(x)) + oConCuoi + '</tr>'
      : '<tr><th scope="row" colspan="3">= ' + (laTraTruocCuoi ? 'Trả trước còn lại' : C.con) + '</th><td></td><td></td>' + oConCuoi + '</tr>';
    // SỬA (đợt 2 kiểm chứng độc lập 30/09/2026): dòng "Cộng N hoá đơn" dùng o3(...cg.con) in số
    // RÒNG trần — bị bỏ sót khi sửa mục 9 lần đầu (chỉ sửa dongCuoi, không sửa dòng này). Khi
    // cg.con < 0 (hoá đơn duy nhất/nhóm hoá đơn đang hiện bị trả dư ròng) đổi nhãn cột + hiện
    // "Trả trước X" thay số âm, cùng cách đã làm ở oConLai từng dòng và oConCuoi.
    const laTraTruocCong = !kh && cg.con < 0;
    const oConCong = laTraTruocCong
      ? '<td class="num"><span class="kt-so--tra-truoc">Trả trước ' + KD.tien(-cg.con) + '</span></td><td></td>'
      : o(cg.con, (x) => KD.tien(x)) + '<td></td>';
    $('dt-hd-cong').innerHTML = (coSo.length ? '<tr><th scope="row" colspan="3">Cộng ' + KD.soDem(coSo.length) + ' hoá đơn' + hauTo + '</th>' + o(cg.gt, (x) => KT.tienSo(x)) + o(cg.da, (x) => KT.tienSo(x)) + oConCong + '</tr>' : '')
      + (dsAm.length ? dsAm.map((p) => '<tr><th scope="row" colspan="3">' + moTaAm(p) + '</th>' + o3(p.tong, p.da_thu, p.con_lai) + '</tr>').join('')
        + (dsAm.length > 1 ? '<tr><th scope="row" colspan="3">Cộng ' + KD.soDem(dsAm.length) + ' khoản trả trước/thừa</th>' + o3(tongAmGt, tongAmDa, tongAm) + '</tr>' : '')
        + dongCuoi : '');
  }
  $('dt-loc').addEventListener('click', (e) => { const b = e.target.closest('button[data-loc]'); if (b && b.dataset.loc !== loc) { loc = b.dataset.loc; veHoaDon(); } });

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
    const soHd = d.phieu.filter(chuaTra).length;
    // Dòng so_tien = 0 (chỉ có da_tra: trả trước/ứng/đặt cọc) không phải hoá đơn — đếm tách ra. Cùng định nghĩa với bảng + nút lọc (laHoaDon).
    const soPs = d.phieu.filter(laHoaDon).length, soUng = d.phieu.length - soPs;
    // 4 thẻ chính; khoản trả trước/ứng nằm trong ⓘ của thẻ Tổng phát sinh. (Câu "Nợ thực · Nợ dự kiến" đã bỏ cùng lúc ẩn nợ dự kiến — xem taiNccTheoTen.)
    const tipTong = soUng ? KD.soDem(soUng) + ' khoản trả trước/ứng (không phải hoá đơn).' : '';
    // BƯỚC 3 30/09/2026 (quyết định người dùng, chỉ NCC): con_lai < 0 = trả nhiều hơn hoá đơn
    // thực — TÀI SẢN (tiền ứng trước), không phải "nợ âm". Thẻ "Còn nợ" đổi nhãn/màu/giá trị.
    const laTraTruocDt = !kh && d.con_lai < 0;
    const theCon = laTraTruocDt
      ? the('bi-arrow-return-left', '', 'Trả trước còn lại', d.tra_truoc, 'Đã chi nhiều hơn hoá đơn hiện có — chưa có hoá đơn để trừ')
      : the('bi-hourglass-split', 'warning', C.con, d.con_lai, KD.soDem(soHd) + ' hoá đơn còn nợ');
    $('dt-kpi').innerHTML = the('bi-receipt', '', 'Tổng phát sinh', d.tong_no, KD.soDem(soPs) + ' hoá đơn', tipTong) + the('bi-cash-coin', 'success', C.da, d.da_thu, d.tong_no ? KD.phanTram(d.da_thu / d.tong_no * 100) + ' tổng phát sinh' : '')
      + theCon + the('bi-exclamation-triangle', 'danger', 'Quá hạn', d.qua_han, kh || d.co_han ? (d.qua_han ? '<span class="pill pill--danger">' + (kh ? 'Cần đòi ngay' : 'Cần trả ngay') + '</span>' : 'Không có') : 'Chưa có dữ liệu hạn');
    $('dt-kpi').classList.remove('kt-kpi-row--6'); $('dt-kpi').classList.add('kt-kpi-row--4');
    dangXem = d; veHoaDon();
    $('dt-kv').innerHTML = [['Mã', k.ma !== '—' ? k.ma : null], ['Tên', k.ten], ['Mã số thuế', k.mst], ['Điện thoại', k.sdt], [C.nv, k.nv_kd], ['Tài khoản', 'TK ' + C.tk]].filter((x) => x[1]).map((x) => '<dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd>').join('');
    $('dt-ls').innerHTML = (d.lich_su_thu || []).length ? '<ul class="kd-lines">' + d.lich_su_thu.slice(0, 8).map((x) => '<li><span>' + KT.linkCt(x.so_ct, x.ngay) + ' · ' + esc(x.hinh_thuc) + '</span><b class="num">' + KD.tienVnd(x.so_tien) + '</b><span class="kd-lines__sub">' + (x.ma_cn && x.ma_cn !== x.so_ct ? esc(x.ma_cn) + ' · ' : '') + KD.ngay(x.ngay) + '</span></li>').join('') + '</ul>'
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
