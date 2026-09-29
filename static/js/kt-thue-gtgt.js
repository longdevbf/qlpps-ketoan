/* kt-thue-gtgt.js — Thuế GTGT: 2 bảng kê (kt-danh-sach.js, url:false) dùng chung ô kỳ kê khai; thẻ tổng hợp do trang vẽ.
   API thật: /api/thue-gtgt (app/routers/thue.py). Đầu ra = đơn báo giá đã duyệt theo ngày duyệt (cùng số "VAT đầu ra"
   của Tổng quan cũ); hệ thống chưa có hoá đơn điện tử và chưa có dữ liệu hoá đơn mua vào → bảng kê mua vào rỗng, có ghi rõ. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-thue-gtgt')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const SO_THANG = 36, SO_QUY = 12;
  const nay = new Date(), hai = (n) => String(n).padStart(2, '0');
  /* Ô kỳ: 36 tháng gần nhất + 12 quý gần nhất (tính theo ngày trên máy). Kỳ trên URL ngoài danh sách (đúng dạng) vẫn được thêm vào. */
  const cacKy = [];
  for (let i = 0; i < SO_THANG; i++) { const d = new Date(nay.getFullYear(), nay.getMonth() - i, 1); cacKy.push([d.getFullYear() + '-' + hai(d.getMonth() + 1), 'Tháng ' + hai(d.getMonth() + 1) + '/' + d.getFullYear()]); }
  for (let i = 0; i < SO_QUY; i++) { const d = new Date(nay.getFullYear(), nay.getMonth() - 3 * i, 1), q = Math.floor(d.getMonth() / 3) + 1; cacKy.push(['Q' + q + '-' + d.getFullYear(), 'Quý ' + q + '/' + d.getFullYear()]); }
  const MAC = { ky: cacKy[0][0], tab: 'ban' }, u = Object.assign({}, MAC, KT.url.doc());
  if (!cacKy.some(([v]) => v === u.ky)) {
    const mT = /^(\d{4})-(0[1-9]|1[0-2])$/.exec(u.ky || ''), mQ = /^Q([1-4])-(\d{4})$/.exec(u.ky || '');
    if (mT) cacKy.splice(SO_THANG, 0, [u.ky, 'Tháng ' + mT[2] + '/' + mT[1]]); else if (mQ) cacKy.push([u.ky, 'Quý ' + mQ[1] + '/' + mQ[2]]); else u.ky = MAC.ky;
  }
  $('tg-ky').innerHTML = cacKy.map(([v, t]) => '<option value="' + v + '">' + t + '</option>').join('');
  $('tg-ky').value = u.ky; let ky = u.ky, tab = u.tab === 'mua' ? 'mua' : 'ban';
  /* Bộ lọc riêng từng bảng kê (tìm, trang, cỡ trang, sắp xếp) giữ trên URL với tiền tố tb_ / tm_ — khung chạy url:false nên màn tự ghi. */
  const LUU = ['tim', 'page', 'size', 'sort'], MAC_BANG = { tim: '', page: 1, size: 20, sort: 'ngay_asc' };
  const batDau = (p) => { const o = {}; LUU.forEach((k) => { if (u[p + '_' + k]) o[k] = u[p + '_' + k]; }); return o; };
  /* Giải thích nguồn số liệu → ⓘ cạnh dòng phụ tiêu đề trang (không in thành đoạn chữ) */
  const tipTrang = document.querySelector('#kd-kt-thue-gtgt .kd-sub').appendChild(document.createElement('span'));
  const kpiEl = (k) => document.querySelector('#tg-kpi [data-kpi="' + k + '"]');
  function kpi(d) { ['dau_ra', 'dau_vao', 'chuyen', 'phai_nop'].forEach((k) => { const el = kpiEl(k); el.querySelector('[data-v]').innerHTML = d === 'cho' ? '<span class="kd-skel kd-skel--kpi"></span>' : '<span class="kd-muted">—</span>'; el.querySelector('[data-phu]').innerHTML = ''; }); }
  function veTongHop(d) {
    const t = d.tong_hop, dat = (k, v, phu, title) => { const el = kpiEl(k); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-v]').title = title || ''; el.querySelector('[data-phu]').innerHTML = phu || ''; };
    dat('dau_ra', H.tienKpi(t.dau_ra), KD.soDem(t.so_ban) + ' đơn có VAT' + KD.tip('Giá trị chưa thuế ' + KD.tienGon(t.doanh_thu)), KD.tienVnd(t.dau_ra));
    dat('dau_vao', H.tienKpi(t.dau_vao), t.so_mua ? KD.soDem(t.so_mua) + ' hoá đơn đủ điều kiện' : 'Chưa có hoá đơn mua vào' + KD.tip(d.nguon.dau_vao), KD.tienVnd(t.dau_vao));
    dat('chuyen', H.tienKpi(t.chuyen_sang), t.chuyen_sang ? 'Còn khấu trừ từ kỳ trước' : 'Kỳ trước không dư', KD.tienVnd(t.chuyen_sang));
    dat('phai_nop', t.phai_nop >= 0 ? H.tienKpi(t.phai_nop) : H.tienKpi(0), t.phai_nop >= 0 ? 'Hạn nộp ' + KD.ngay(d.han_nop) + (t.dau_vao ? '' : KD.tip('Chưa trừ thuế đầu vào', 'kd-tip--trai')) : H.pill('success', 'Còn khấu trừ chuyển kỳ sau ' + KD.tienGon(-t.phai_nop)), KD.tienVnd(t.phai_nop));
    const s = d.so_sach, kv = d.khong_vat;
    tipTrang.innerHTML = KD.tip('Kỳ ' + KD.ngay(d.khoang.tu) + ' – ' + KD.ngay(d.khoang.den) + ': thuế đầu ra lấy từ đơn đã duyệt trong kỳ, ghi theo số đơn.'
      + (kv.so_don ? ' ' + KD.soDem(kv.so_don) + ' đơn không tính VAT (doanh thu ' + KD.tienVnd(kv.doanh_thu) + ') không lên bảng kê.' : '')
      + (s.ps_3331 || s.ps_1331 ? ' Sổ cái: Có 3331 = ' + KD.tienVnd(s.ps_3331) + (s.ps_3331 !== t.dau_ra ? '' : ' (khớp)') + ', Nợ 133 = ' + KD.tienVnd(s.ps_1331) + '.' : ' Sổ cái chưa có bút toán thuế GTGT trong kỳ.'));
    /* Lệch sổ cái là cảnh báo cần xử lý → hiện thành nhãn đỏ, không giấu trong ⓘ */
    const lech = (s.ps_3331 || s.ps_1331) && s.ps_3331 !== t.dau_ra;
    $('tg-pham-vi').hidden = !lech;
    $('tg-pham-vi').innerHTML = lech ? H.pill('danger', 'Sổ cái TK 3331 lệch ' + KD.tienVnd(s.ps_3331 - t.dau_ra) + ' so với bảng kê') : '';
    $('tg-dem-ban').textContent = '(' + KD.soDem(t.so_ban) + ')'; $('tg-dem-mua').textContent = '(' + KD.soDem(t.so_mua) + ')';
  }
  const api = (chieu) => (q) => '/api/thue-gtgt?' + KT.url.qs(Object.assign({}, q, { chieu, ky }));
  const mst = (dt) => (dt && dt.mst ? 'MST ' + dt.mst : 'Không có MST');
  const BANG = {};
  function ghiUrl() {
    const st = { ky, tab }, mac = Object.assign({}, MAC);
    [['tb', BANG.ban], ['tm', BANG.mua]].forEach(([p, b]) => { if (b) LUU.forEach((k) => { st[p + '_' + k] = b.st[k]; mac[p + '_' + k] = MAC_BANG[k]; }); });
    KT.url.ghi(st, mac);
  }
  const chung = { url: false, ghiUrl, sauTai: (d) => veTongHop(d), khiLoi: () => { kpi('loi'); $('tg-pham-vi').textContent = ''; tipTrang.innerHTML = ''; } };
  BANG.ban = KT.danhSach(Object.assign({}, chung, {
    pfx: 'tb', api: api('ban'), donVi: 'đơn', dangHien: () => tab === 'ban', chiTiet: (r) => '/ketoan/don-hang?tim=' + encodeURIComponent(r.so_hd),
    dong: { id: (r) => r.id },
    macDinh: MAC_BANG, batDau: batDau('tb'),
    cot: [
      { key: 'ngay', nhan: 'Ngày duyệt', sort: 'so', ve: (r) => KD.ngay(r.ngay) },
      { key: 'so', nhan: 'Số đơn', title: 'Chưa có hoá đơn điện tử — ghi theo số đơn báo giá', ve: (r) => H.ma(r.so_hd) },
      { key: 'kh', nhan: 'Người mua', ve: (r) => (r.doi_tac ? H.ten(r.doi_tac.ten, mst(r.doi_tac)) : '—') },
      { key: 'gia_tri', nhan: 'Doanh thu chưa thuế', num: true, sort: 'so', ve: (r) => KD.tien(r.gia_tri) },
      { key: 'ts', nhan: 'Thuế suất', num: true, ve: (r) => KD.soDem(r.thue_suat) + '%' },
      { key: 'thue', nhan: 'Thuế GTGT (VND)', num: true, sort: 'so', cls: 'kd-strong', ve: (r) => KD.tien(r.thue) },
    ],
    cong: (d) => [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' đơn', span: 3 }, { html: KD.tien(d.cong.gia_tri), num: true }, { html: '' }, { html: KD.tien(d.cong.thue), num: true }],
    rong: (d, coLoc) => (coLoc ? ['Không có đơn nào khớp ô tìm', 'Thử từ khoá khác.'] : ['Kỳ này chưa có đơn bán ra có VAT', 'Đơn lên bảng kê khi được duyệt và có tính thuế GTGT.']),
    loi: 'Không tải được bảng kê bán ra',
  }));
  BANG.mua = KT.danhSach(Object.assign({}, chung, {
    pfx: 'tm', api: api('mua'), donVi: 'hoá đơn', dangHien: () => tab === 'mua',
    dong: { id: (r) => r.id },
    macDinh: MAC_BANG, batDau: batDau('tm'),
    cot: [
      { key: 'ngay', nhan: 'Ngày', ve: (r) => KD.ngay(r.ngay) },
      { key: 'so', nhan: 'Số hoá đơn', ve: (r) => H.ma(r.so_hd) },
      { key: 'ncc', nhan: 'Người bán', ve: (r) => H.ten(r.doi_tac.ten, mst(r.doi_tac)) },
      { key: 'gia_tri', nhan: 'Giá trị chưa thuế', num: true, ve: (r) => KD.tien(r.gia_tri) },
      { key: 'ts', nhan: 'Thuế suất', num: true, ve: (r) => KD.soDem(r.thue_suat) + '%' },
      { key: 'thue', nhan: 'Thuế GTGT (VND)', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.thue) },
    ],
    rong: (d, coLoc) => (coLoc ? ['Không có hoá đơn nào khớp ô tìm', 'Thử từ khoá khác.'] : ['Chưa có dữ liệu hoá đơn mua vào', d.ly_do_rong || '']),
    loi: 'Không tải được bảng kê mua vào',
  }));
  const cu = { ban: false, mua: false };   // cu[k]: bảng ẩn đã lỡ một lần đổi kỳ → khi hiện phải tải lại
  const tabs = KD.ganTab($('tg-tabs'), (k) => { tab = k; ghiUrl(); if (cu[k]) { cu[k] = false; BANG[k].tai(); } else BANG[k].taiNeuCan(); });
  $('tg-ky').addEventListener('change', (e) => {
    ky = e.target.value; ghiUrl(); kpi('cho'); $('tg-pham-vi').textContent = ''; tipTrang.innerHTML = '';
    ['ban', 'mua'].forEach((k) => { BANG[k].st.page = 1; BANG[k].dongPanel(); if (k === tab) BANG[k].tai(); else cu[k] = true; });
  });
  $('tg-xuat').addEventListener('click', async (e) => {
    const nut = e.currentTarget; nut.disabled = true;
    try { const r = await KD.api('/api/thue-gtgt/to-khai?ky=' + encodeURIComponent(ky));
      const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([r.noi_dung], { type: 'application/xml' })); a.download = r.ten_tep; document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      window.showToast && window.showToast('ok', 'Đã tải ' + r.ten_tep + ' — số liệu chỉ tiêu 01/GTGT để đối chiếu khi lập tờ khai trên HTKK');
    } catch (er) { window.showToast && window.showToast('err', 'Chưa xuất được dữ liệu tờ khai: ' + er.message); } finally { nut.disabled = false; }
  });
  kpi('cho'); tabs.chon(tab);
})();
