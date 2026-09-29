/* kt-tscd-chi-tiet.js — Chi tiết TSCĐ (L4): thẻ giá trị, lịch khấu hao đầy đủ, thông tin hạch toán, bút toán.
   API THẬT: GET /api/tai-san/<id> (app/routers/tai_san.py) — KHÔNG PHẢI /api/tscd/<id> như README.

   MISMATCH so với thiết kế gốc:
   - Field đổi tên: ma_tscd/ten_tscd (không phải ma/ten), ngay_su_dung (không phải ngay_dung),
     hao_mon_luy_ke (không phải hao_mon), gia_tri_con_lai (không phải con_lai), so_thang_kh
     (không phải so_thang), so_thang_da_kh (không phải so_thang_da), so_tien_kh_thang
     (không phải kh_thang), ngay_thanh_ly (không phải thanh_ly), account_code (không có
     tk_nguyen_gia/tk_hao_mon/tk_cp riêng — xem bên dưới).
   - trang_thai thật chỉ có dang_su_dung|da_thanh_ly|hong (không có dang_khau_hao/het_khau_hao
     như thiết kế) — suy trạng thái hiển thị từ trang_thai + so sánh hao_mon_luy_ke/nguyen_gia.
   - TK hao mòn LUÔN là 214 (không lưu riêng từng tài sản); TK chi phí khấu hao suy từ
     `bo_phan` (enum ban_hang/quan_ly/tai_chinh/khac — không phải chữ tự do) qua cùng bảng
     tra app/services/tscd_calc.py:_BO_PHAN_TO_ACCOUNT dùng ở kt-tscd-phieu.js.
   - `khau_hao_logs[]` trả về chỉ gồm các tháng ĐÃ trích thật (không có lịch dự kiến các
     tháng tương lai như thiết kế) — màn này tự nối thêm các tháng còn lại (đường thẳng,
     mức = so_tien_kh_thang) để có đủ lịch từ tháng đầu tới hết so_thang_kh, đúng tinh
     thần "lịch khấu hao đầy đủ" của thiết kế.
   - Không có field `ct_ghi_tang` (chứng từ ghi tăng) hay danh sách "bút toán gần đây" có sẵn
     — panel "Bút toán gần đây" dựng lại từ journal_id của tối đa 5 khau_hao_logs gần nhất
     (gọi GET /api/journal/<id> để lấy mã + ngày thật).
*/
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-tscd-ct')) return;
  const $ = (id) => document.getElementById(id), u = KT.url.doc();
  const pill = (mau, nhan) => '<span class="pill pill--' + mau + '">' + esc(nhan) + '</span>';
  const NHOM = { nha_xuong: 'Nhà xưởng, vật kiến trúc', may_moc: 'Máy móc, thiết bị', van_tai: 'Phương tiện vận tải', thiet_bi_vp: 'Thiết bị văn phòng' };
  const BO_PHAN = { ban_hang: ['Bán hàng', '641'], quan_ly: ['Quản lý', '642'], tai_chinh: ['Tài chính', '635'], khac: ['Khác', '811'] };
  const thang = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const the = (ico, mau, nhan, v, phu) => '<article class="kd-kpi"><div class="kd-kpi__head"><span class="ico-tile' + (mau ? ' ico-tile--' + mau : '') + '" aria-hidden="true"><i class="bi ' + ico + '"></i></span><span class="kd-kpi__label">' + esc(nhan) + '</span></div>'
    + '<div class="kd-kpi__value num" title="' + esc(KD.tienVnd(v)) + '">' + KD.tienGonHtml(v) + '</div><p class="kd-kpi__phu">' + phu + '</p></article>';
  async function tai() {
    $('tc-tt').innerHTML = KD.KHUNG_TAI; $('tc-than').hidden = true;
    if (!u.id) { $('tc-ma').textContent = '—'; $('tc-tt').innerHTML = KD.khoiRong('Chưa chọn tài sản', 'Mở trang này từ danh sách Tài sản cố định.'); return; }
    try { const t = soHoa(await KD.api('/api/tai-san/' + encodeURIComponent(u.id))); $('tc-tt').innerHTML = ''; $('tc-than').hidden = false; ve(t); }
    catch (e) { $('tc-ma').textContent = '—'; KD.khoiLoi($('tc-tt'), 'Không tải được tài sản', e, tai); }
  }
  /* API trả số tiền dạng chuỗi Decimal ("371681818.29") — QA 25/09: so sánh/cộng thẳng chuỗi làm pill
     "Đã khấu hao hết" sai (so chuỗi "3…" >= "1…") và luỹ kế các tháng dự kiến bị nối chuỗi → "—". Đổi sang số 1 lần ở đây. */
  function soHoa(t) {
    ['nguyen_gia', 'hao_mon_luy_ke', 'gia_tri_con_lai', 'so_tien_kh_thang', 'chi_phi_lap_dat'].forEach((k) => { t[k] = +t[k] || 0; });
    t.khau_hao_logs = (t.khau_hao_logs || []).map((x) => Object.assign({}, x, { so_tien: +x.so_tien || 0, hao_mon_luy_ke_sau: +x.hao_mon_luy_ke_sau || 0 }))
      .sort((a, b) => (a.thang < b.thang ? -1 : 1));
    return t;
  }
  /* Nối lịch khấu hao đã trích (thật) + các tháng dự kiến còn lại (đường thẳng). */
  function xayLichDayDu(t) {
    const da = t.khau_hao_logs || [];
    const ds = da.map((x) => ({ thang: x.thang, khau_hao: x.so_tien, luy_ke: x.hao_mon_luy_ke_sau, con_lai: t.nguyen_gia - x.hao_mon_luy_ke_sau, da_trich: true }));
    let luyKe = ds.length ? ds[ds.length - 1].luy_ke : 0;
    const conThang = Math.max(0, (t.so_thang_kh || 0) - ds.length);
    let mocThang = ds.length ? ds[ds.length - 1].thang : (t.ngay_su_dung || '').slice(0, 7);
    for (let i = 0; i < conThang; i++) {
      const d = new Date(mocThang + '-01'); d.setMonth(d.getMonth() + 1); mocThang = KD.iso(d).slice(0, 7);
      const kh = i === conThang - 1 ? Math.max(0, t.nguyen_gia - luyKe) : (t.so_tien_kh_thang || 0);
      luyKe += kh;
      ds.push({ thang: mocThang, khau_hao: kh, luy_ke: luyKe, con_lai: Math.max(0, t.nguyen_gia - luyKe), da_trich: false });
    }
    return lamTronLich(ds, t.nguyen_gia);
  }
  /* Số ghi sổ có 2 số lẻ (vd 21.863.636,37/tháng) → hiện từng số đã làm tròn thì cộng dồn cột Khấu hao
     lệch cột Luỹ kế vài đồng (QA nhất quán 25/09: 116/120 dòng lệch 1–4đ). Làm tròn LUỸ KẾ trước, khấu hao
     tháng = luỹ kế tròn − luỹ kế tròn tháng trước, còn lại = nguyên giá − luỹ kế → mọi dòng tự khớp; số lẻ
     thật vẫn xem được ở tooltip. */
  function lamTronLich(ds, nguyenGia) {
    const ng = Math.round(nguyenGia); let truoc = 0;
    return ds.map((x) => { const lk = Math.round(x.luy_ke), kh = lk - truoc; truoc = lk; return Object.assign({}, x, { kh_that: x.khau_hao, khau_hao: kh, luy_ke: lk, con_lai: ng - lk }); });
  }
  async function veButToanGanDay(t) {
    const logs = (t.khau_hao_logs || []).filter((x) => x.journal_id).slice(-5).reverse();
    if (!logs.length) { $('tc-bt').innerHTML = KD.khoiRong('Chưa có bút toán', 'Khấu hao sẽ ghi khi trích tháng.'); return; }
    $('tc-bt').innerHTML = KD.KHUNG_TAI;
    try {
      const jes = await Promise.all(logs.map((l) => KD.api('/api/journal/' + l.journal_id).catch(() => null)));
      $('tc-bt').innerHTML = '<ul class="kd-lines">' + jes.map((je, i) => je
        ? '<li><span>' + KT.linkCt(je.ma_but_toan, je.ngay) + '</span><span class="kd-meta">' + KD.ngay(je.ngay) + '</span></li>'
        : '<li><span class="kd-muted">Khấu hao ' + thang(logs[i].thang) + ' — không tải được bút toán</span></li>').join('') + '</ul>';
    } catch (e) { $('tc-bt').innerHTML = KD.khoiRong('Không tải được bút toán', ''); }
  }
  function ve(t) {
    document.title = t.ma_tscd + ' — Tài sản cố định';
    $('tc-crumb').textContent = t.ma_tscd; $('tc-ma').textContent = t.ma_tscd + ' · ' + t.ten_tscd;
    const hetKh = (t.so_thang_da_kh || 0) >= t.so_thang_kh || t.hao_mon_luy_ke >= t.nguyen_gia;
    $('tc-pill').innerHTML = t.trang_thai === 'da_thanh_ly' ? pill('muted', 'Đã thanh lý') : t.trang_thai === 'hong' ? pill('danger', 'Hỏng, ngừng dùng') : hetKh ? pill('info', 'Đã khấu hao hết') : pill('success', 'Đang khấu hao');
    $('tc-meta').innerHTML = '<span>Nhóm: <b>' + esc(NHOM[t.nhom] || t.nhom || '—') + '</b></span><span>Bộ phận: <b>' + esc((BO_PHAN[t.bo_phan] || [t.bo_phan || '—'])[0]) + '</b></span><span>Đưa vào dùng: <b>' + KD.ngay(t.ngay_su_dung) + '</b></span>' + (t.ngay_thanh_ly ? '<span>Thanh lý: <b>' + KD.ngay(t.ngay_thanh_ly) + '</b></span>' : '');
    $('tc-sua').href = '/ketoan/tscd/phieu?id=' + t.id; $('tc-thanh-ly').href = '/ketoan/tscd/phieu?id=' + t.id + '&che_do=thanh_ly'; $('tc-thanh-ly').hidden = t.trang_thai === 'da_thanh_ly';
    const pt = t.nguyen_gia ? KD.phanTram(t.hao_mon_luy_ke / t.nguyen_gia * 100) : '—';
    const bp = BO_PHAN[t.bo_phan] || [t.bo_phan || '—', '—'];
    $('tc-kpi').innerHTML = the('bi-building', '', 'Nguyên giá', t.nguyen_gia, 'TK ' + esc(t.account_code || '211')) + the('bi-graph-down-arrow', 'tim', 'Hao mòn luỹ kế', t.hao_mon_luy_ke, pt + ' nguyên giá')
      + the('bi-box-seam', 'success', 'Giá trị còn lại', t.gia_tri_con_lai, KD.soDem(Math.max(0, t.so_thang_kh - t.so_thang_da_kh)) + ' tháng còn phải trích') + the('bi-calendar3', 'warning', 'Khấu hao mỗi tháng', t.so_tien_kh_thang, hetKh ? 'Không còn trích' : 'Nợ ' + bp[1] + ' / Có 214');
    const lich = xayLichDayDu(t), toi = lich.findIndex((x) => !x.da_trich);
    $('tc-lich-gy').textContent = KD.soDem(t.so_thang_kh) + ' tháng · đường thẳng · đã trích ' + KD.soDem(t.so_thang_da_kh) + ' tháng';
    $('tc-lich').innerHTML = lich.length ? lich.map((x, i) => '<tr' + (i === toi ? ' class="kt-tc-toi"' : '') + '><td>' + thang(x.thang) + '</td><td class="num"' + (Math.abs(x.kh_that - x.khau_hao) >= 0.005 ? ' title="Số ' + (x.da_trich ? 'ghi sổ' : 'dự kiến') + ' ' + esc(Number(x.kh_that).toLocaleString('vi-VN', { maximumFractionDigits: 2 })) + ' — làm tròn theo luỹ kế"' : '') + '>' + KD.tien(x.khau_hao) + '</td><td class="num">' + KD.tien(x.luy_ke) + '</td><td class="num">' + KD.tien(x.con_lai) + '</td><td>'
      + (x.da_trich ? pill('success', 'Đã trích') : i === toi ? pill('warning', 'Kỳ tới') : '<span class="kd-muted">Chưa đến</span>') + '</td></tr>').join('')
      : '<tr><td colspan="5">' + KD.khoiRong('Không có lịch khấu hao', '') + '</td></tr>';
    const r = document.querySelector('.kt-tc-toi'); if (r) { const c = r.closest('.kt-tc-cuon'); if (c) c.scrollTop = Math.max(0, r.offsetTop - 120); }
    $('tc-kv').innerHTML = [['Loại', t.loai === 'vo_hinh' ? 'Vô hình' : 'Hữu hình'], ['TK nguyên giá', t.account_code], ['TK hao mòn', '214'], ['TK chi phí khấu hao', bp[1]], ['Thời gian khấu hao', KD.soDem(t.so_thang_kh) + ' tháng'], ['Phương pháp', 'Đường thẳng'],
      ['Ngày mua', t.ngay_mua ? KD.ngay(t.ngay_mua) : ''], ['Chi phí lắp đặt', t.chi_phi_lap_dat ? KD.tienVnd(t.chi_phi_lap_dat) : ''], ['Nhà cung cấp', t.ncc], ['Ghi chú', t.ghi_chu]]
      .filter((x) => x[1]).map((x) => '<dt>' + esc(x[0]) + '</dt><dd>' + esc(x[1]) + '</dd>').join('');
    veButToanGanDay(t);
    $('tc-lq').innerHTML = [['/ketoan/so-cai?tk=' + encodeURIComponent(t.account_code || '211') + '&ky=nam_nay', 'bi-journal-text', 'Sổ cái TK ' + (t.account_code || '211'), 'Nguyên giá'],
      ['/ketoan/so-cai?tk=214&ky=nam_nay', 'bi-journal-text', 'Sổ cái TK 214', 'Hao mòn luỹ kế'], ['/ketoan/tscd', 'bi-list-ul', 'Danh sách tài sản', '']]
      .map((x) => '<li><a href="' + x[0] + '"><i class="bi ' + x[1] + '" aria-hidden="true"></i><span class="kd-related__ten">' + esc(x[2]) + '</span>' + (x[3] ? '<span class="kd-related__sub">' + esc(x[3]) + '</span>' : '') + '</a></li>').join('');
  }
  tai();
})();
