/* kt-ton-kho-doi-chieu.js — khối "Đối chiếu với Kho mới của Mua hàng" trên màn Tồn kho (CHỈ ĐỌC).
   Nguồn: GET /api/external/ton-kho-mh/doi-chieu-kho-moi (app/services/ton_kho_doi_chieu.py). Không ghi gì, không đổi số của bảng bên dưới.
   Hai sổ khác nhau: Kế toán đọc bảng cũ muahang.ton_kho_items, Mua hàng đã chuyển sang Kho mới (kho_sp + kho_movement).
   Nối hai sổ bằng phiếu đầu kỳ (ref_id = id dòng bảng cũ), KHÔNG nối theo tên/mã. Số liệu CHƯA KIỂM KÊ. */
(function () {
  'use strict';
  const goc = document.getElementById('dc');
  if (!goc) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const SO_COT = 5;
  let du = null;

  const dau = (v) => (+v > 0 ? '+' : '');
  const so = (v) => (+v ? KD.soDem(v) : '<span class="kd-muted" aria-label="không">—</span>');
  const tienCo = (v) => (+v ? KD.tien(v) : '<span class="kd-muted" aria-label="không">—</span>');
  const chenhSl = (v) => (+v ? dau(v) + KD.soDem(v) : '<span class="kd-muted" aria-label="không">—</span>');
  const chenhTien = (v) => (+v ? dau(v) + KD.tien(v) : '<span class="kd-muted" aria-label="không">—</span>');

  function veThe(d) {
    const dat = (k, v, phu, title) => { const o = goc.querySelector('[data-kpi="' + k + '"]'); if (!o) return;
      o.querySelector('[data-v]').innerHTML = v; o.querySelector('[data-phu]').innerHTML = phu;
      o.querySelector('[data-v]').title = title || ''; };
    dat('kt', H.tienKpi(d.ke_toan.gt),
      KD.soDem(d.ke_toan.sl) + ' cái · ' + KD.soDem(d.ke_toan.so_dong_con_ton) + ' dòng nhập còn tồn · bảng cũ', KD.tienVnd(d.ke_toan.gt));
    dat('mh', H.tienKpi(d.mua_hang.gt),
      KD.soDem(d.mua_hang.sl) + ' cái · ' + KD.soDem(d.mua_hang.so_sku_con_ton) + ' mã SKU còn tồn · giá nhập SP', KD.tienVnd(d.mua_hang.gt));
    dat('chenh', dau(d.chenh.gt) + H.tienKpi(d.chenh.gt),
      dau(d.chenh.sl) + KD.soDem(d.chenh.sl) + ' cái · Kho mới trừ Kế toán', KD.tienVnd(d.chenh.gt));
    // Phân rã chênh: cộng đúng bằng chênh tổng (kiểm ở backend).
    const p = d.phan_ra, bo = (t, x) => (+x.gt || +x.sl) ? '<li><b>' + KD.tienVnd(x.gt) + '</b> — ' + t + (+x.sl ? ' (' + KD.soDem(x.sl) + ' cái)' : '') + '</li>' : '';
    $('dc-phan-ra').innerHTML = '<span class="kd-meta">Chênh ' + KD.tienVnd(d.chenh.gt) + ' gồm:</span><ul class="kt-dc__pr">'
      + bo('Kế toán đã trừ ở bảng cũ, Kho mới chưa có phiếu xuất', p.da_tru_bang_cu)
      + bo('hàng nhập tay sau ' + (d.ngay_chuyen_kho_moi ? KD.ngay(d.ngay_chuyen_kho_moi).slice(0, 5) : 'khi chuyển kho') + ', Kế toán chưa thấy', p.nhap_tay)
      + bo('lệch số lượng chưa rõ lý do', p.khac)
      + bo('giá nhập SKU khác giá lô, hoặc gộp lô', p.lech_gia) + '</ul>';
  }

  /* Ô số hai tầng: giá trị (đậm) trên, số lượng (chú thích) dưới — gọn để bảng vừa khung 1366px không phải cuộn ngang. */
  const ocSo = (chinh, phu) => '<span class="kt-dc__v">' + chinh + '</span><span class="kt-khach__ma kt-dc__phu">' + phu + '</span>';

  function ly(r) {
    const t = [], tp = r.thanh_phan;
    if (+tp.da_tru_bang_cu > 0) t.push('Kế toán đã trừ ' + KD.soDem(tp.da_tru_bang_cu));
    if (+tp.nhap_tay > 0) t.push('nhập tay ' + KD.soDem(tp.nhap_tay));
    if (+tp.nhap_tay < 0) t.push('xuất/điều chỉnh ' + KD.soDem(tp.nhap_tay));
    if (+tp.khac) t.push('chưa rõ ' + dau(tp.khac) + KD.soDem(tp.khac));
    let h = '<div class="kt-dc__ly">' + H.pill(r.nhan_mau, r.nhan);
    if (r.nhan_ma !== 'khop' && r.nhan_ma !== 'khac_gia' && t.length) h += '<span class="kd-meta">' + esc(t.join(' · ')) + '</span>';
    if (r.khac_gia && r.nhan_ma !== 'khac_gia') h += H.pill('info', 'Khác giá', true);
    if (r.canh_bao.indexOf('gia_0') >= 0) h += '<span title="Kho mới tính giá trị = tồn × giá nhập; giá 0đ nên giá trị ra 0đ">' + H.pill('warning', 'Giá nhập 0đ', true) + '</span>';
    if (r.canh_bao.indexOf('trung_ten') >= 0) h += '<span title="Trùng tên nhưng khác mã SKU — chỉ liệt kê, KHÔNG tự nối">' + H.pill('muted', 'Trùng tên với ' + r.trung_ten_voi.slice(0, 3).join(', ')) + '</span>';
    return h + '</div>';
  }

  function ve() {
    if (!du) return;
    const chiLech = $('dc-lech').checked;
    const ds = du.dong.filter((r) => !chiLech || r.nhan_ma !== 'khop');
    $('dc-dem').textContent = KD.soDem(ds.length) + ' / ' + KD.soDem(du.dong.length) + ' mặt hàng';
    const tbody = $('dc-tbody'), tfoot = $('dc-tfoot'), tt = $('dc-tt');
    if (!ds.length) {
      tbody.innerHTML = ''; tfoot.innerHTML = ''; $('dc-cuon').hidden = true;
      tt.innerHTML = KD.khoiRong('Hai kho đang khớp nhau', 'Không có mặt hàng nào lệch giữa Kế toán và Kho mới của Mua hàng.');
      return;
    }
    $('dc-cuon').hidden = false; tt.innerHTML = '';
    tbody.innerHTML = ds.map((r) => '<tr>'
      + '<td><span class="kt-khach__ten">' + esc(r.ten_sp || '—') + '</span><span class="kt-khach__ma">' + esc(r.ma_sp) + (r.nhom ? ' · ' + esc(r.nhom) : '')
        + (r.ma_bang_cu.length ? ' · mã bảng cũ: ' + esc(r.ma_bang_cu.join(', ')) : '') + '</span></td>'
      + '<td class="num">' + ocSo(tienCo(r.kt_gt), 'SL ' + so(r.kt_sl)) + '</td>'
      + '<td class="num">' + ocSo(tienCo(r.mh_gt), 'SL ' + so(r.mh_sl) + ' · giá nhập ' + tienCo(r.mh_gia)) + '</td>'
      + '<td class="num kt-dc__chenh">' + ocSo(chenhTien(r.chenh_gt), chenhSl(r.chenh_sl) + ' cái') + '</td>'
      + '<td>' + ly(r) + '</td></tr>').join('');
    const tong = (k) => ds.reduce((a, r) => a + (+r[k] || 0), 0);
    tfoot.innerHTML = '<tr><th scope="row">Cộng ' + KD.soDem(ds.length) + ' mặt hàng đang hiện</th>'
      + '<td class="num">' + ocSo(tienCo(tong('kt_gt')), 'SL ' + so(tong('kt_sl'))) + '</td>'
      + '<td class="num">' + ocSo(tienCo(tong('mh_gt')), 'SL ' + so(tong('mh_sl'))) + '</td>'
      + '<td class="num kt-dc__chenh">' + ocSo(chenhTien(tong('chenh_gt')), chenhSl(tong('chenh_sl')) + ' cái') + '</td><td></td></tr>';
  }

  async function tai() {
    $('dc-tt').innerHTML = ''; $('dc-cuon').hidden = false;
    $('dc-tbody').innerHTML = KT.hangCho(SO_COT, 5); $('dc-tfoot').innerHTML = '';
    try {
      du = await KD.api('/api/external/ton-kho-mh/doi-chieu-kho-moi');
      $('dc-ck').textContent = du.ghi_chu;
      veThe(du); ve();
    } catch (e) {
      du = null; $('dc-cuon').hidden = true; $('dc-tbody').innerHTML = ''; $('dc-dem').textContent = '';
      KD.khoiLoi($('dc-tt'), 'Không tải được đối chiếu với Kho mới', e, tai);
    }
  }

  $('dc-lech').addEventListener('change', ve);
  tai();
})();
