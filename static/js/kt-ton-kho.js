/* kt-ton-kho.js — Tồn kho theo dòng nhập (khung: kt-danh-sach.js). Giữ nghiệp vụ màn cũ #page-ton-kho:
   Mua hàng nhập kho + giá nhập (cột nền warning-soft), Kế toán chỉ đặt giá bán (cột nền success-soft); margin = (giá bán − giá nhập) / giá bán. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-ton-kho')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const margin = (ban, nhap) => (ban > 0 && nhap > 0 ? (ban - nhap) / ban * 100 : null);
  const pillMargin = (m) => (m == null ? '<span class="kd-muted">—</span>' : H.pill(m >= 30 ? 'success' : m >= 15 ? 'warning' : 'danger', KD.phanTram(m)));
  /* Danh mục: API /api/external/ton-kho-mh chỉ trả { data } — KHÔNG có mảng danh_muc (bản trước đọc d.danh_muc nên ô lọc
     luôn trống). Gom từ chính các dòng như màn cũ, cộng dồn qua các lần tải (lần đầu có thể đang lọc) và giữ giá trị trên URL. */
  const DM = new Set();
  function napDm(dong) {
    const truoc = DM.size; dong.forEach((x) => { if (x.danh_muc) DM.add(x.danh_muc); }); if (ds.st.danh_muc) DM.add(ds.st.danh_muc);
    if (DM.size !== truoc) H.napChon($('tk-danh_muc'), [...DM].sort((a, b) => a.localeCompare(b, 'vi')).map((x) => [x, x]), 'Tất cả danh mục', ds.st.danh_muc);
  }
  const ds = KT.danhSach({
    pfx: 'tk', api: (q) => '/api/external/ton-kho-mh?' + KT.url.qs({ q: q.q, danh_muc: q.danh_muc, ncc: q.ncc, only_remaining: q.only_remaining }), donVi: 'dòng nhập', khongTrang: true,
    macDinh: { q: '', danh_muc: '', ncc: '', only_remaining: '', page: 1, size: 500, sort: '' },
    chuyen: (d) => { const dong = d.data || []; return { dong, tong_dong: dong.length, tong: { dong: dong.length, sl: dong.reduce((a, x) => a + (+x.so_luong || 0), 0), gt: dong.reduce((a, x) => a + (+x.thanh_tien || 0), 0), chua_gia: dong.filter((x) => !(+x.gia_ban_hien_tai > 0)).length } }; },
    dong: { id: (r) => r.id },
    cot: [
      // Gọn cột (đợt 4): danh mục thành dòng phụ dưới tên sản phẩm (mã · kích thước · danh mục).
      { key: 'ten', nhan: 'Sản phẩm', ve: (r) => '<span class="kt-khach__ten">' + esc(r.ten_sp || '—') + '</span><span class="kt-khach__ma">' + esc(r.ma_sp || '—') + (r.kich_thuoc ? ' · ' + esc(r.kich_thuoc) : '') + (r.danh_muc ? ' · ' + esc(r.danh_muc) : '') + '</span>' },
      { key: 'lo', nhan: 'Lô nhập', ve: (r) => esc(r.ncc_name || '—') + '<span class="kt-khach__ma">' + (r.ngay_nhap ? 'Nhập ' + KD.ngay(r.ngay_nhap) : '—') + '</span>' + (r.ghi_chu ? '<span class="kt-khach__ma kt-cat" title="' + esc(r.ghi_chu) + '"><i class="bi bi-sticky" aria-hidden="true"></i> ' + esc(r.ghi_chu) + '</span>' : '') },
      { key: 'sl', nhan: 'Tồn', num: true, lop: 'kt-cot-mh', title: 'Mua hàng nhập — tự trừ FIFO khi đơn hoàn thành', ve: (r) => KD.soDem(r.so_luong || 0) + (r.so_luong_nhap && r.so_luong_nhap !== r.so_luong ? '<span class="kt-khach__ma">nhập ' + KD.soDem(r.so_luong_nhap) + '</span>' : '') },
      { key: 'gia_nhap', nhan: 'Giá nhập', num: true, lop: 'kt-cot-mh', title: 'Mua hàng nhập', ve: (r) => KD.tien(r.gia_nhap || 0) },
      { key: 'tt', nhan: 'Thành tiền', num: true, lop: 'kt-cot-mh', ve: (r) => KD.tien(r.thanh_tien || 0) },
      { key: 'gia_ban', nhan: 'Giá bán', num: true, lop: 'kt-cot-kt', title: 'Kế toán đặt', ve: (r) => (!r.product_master_id ? '<span class="kd-muted" title="Chưa có trong danh mục Sản phẩm">Chưa đặt</span>' : +r.gia_ban_hien_tai > 0 ? '<b>' + KD.tien(r.gia_ban_hien_tai) + '</b>' : '<span class="kd-muted">Chưa đặt</span>') },
      { key: 'margin', nhan: 'Biên lãi', num: true, lop: 'kt-cot-kt', title: '(Giá bán − giá nhập) / giá bán', ve: (r) => pillMargin(margin(+r.gia_ban_hien_tai, +r.gia_nhap)) },
      { key: 'xl', nhan: 'Xử lý', ve: (r) => '<button type="button" class="kd-btn kd-btn--sm" data-gia="' + r.id + '">' + (r.product_master_id ? 'Đặt giá' : 'Đặt giá, tạo SP') + '</button>' },
    ],
    kpi: {
      dong: (d) => ({ v: H.dem(d.tong.dong, 'dòng'), phu: d.tong.chua_gia ? H.pill('warning', KD.soDem(d.tong.chua_gia) + ' dòng chưa có giá bán') : 'Đủ giá bán' }),
      sl: (d) => ({ v: H.dem(d.tong.sl, 'đơn vị'), phu: 'Theo bộ lọc' }),
      gt: (d) => ({ v: H.tienKpi(d.tong.gt), title: KD.tienVnd(d.tong.gt), phu: 'Theo giá nhập' }),
    },
    cong: (d) => [{ html: 'Cộng ' + KD.soDem(d.tong.dong) + ' dòng', span: 2 }, { html: KD.soDem(d.tong.sl), num: true, lop: 'kt-cot-mh' }, { html: '', lop: 'kt-cot-mh' }, { html: KD.tien(d.tong.gt), num: true, lop: 'kt-cot-mh' }, { html: '', lop: 'kt-cot-kt' }, { html: '', lop: 'kt-cot-kt' }, { html: '' }],
    rong: (d, coLoc) => (coLoc ? ['Không có dòng tồn kho nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có dòng tồn kho nào', 'Tồn kho cập nhật từ phòng Mua hàng mỗi khi nhập lô mới. Kế toán không nhập trực tiếp ở đây — chỉ đặt giá bán.']),
    loi: 'Không tải được tồn kho',
    sauTai: (d) => { napDm(d.dong || []);
      $('tk-xuat').disabled = !(d.dong || []).length; },
  });

  /* ── Xuất Excel: CSV (UTF-8 có BOM để Excel đọc đúng tiếng Việt) từ đúng các dòng đang lọc ── */
  const oCsv = (v) => { const s = v == null ? '' : String(v); return /[",;\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  $('tk-xuat').addEventListener('click', () => {
    const dau = ['Mã SP', 'Tên sản phẩm', 'Kích thước', 'Danh mục', 'Nhà cung cấp', 'Ngày nhập', 'Số lượng tồn', 'Số lượng nhập', 'Giá nhập (VND)', 'Thành tiền (VND)', 'Giá bán (VND)', 'Biên lãi (%)', 'Ghi chú'];
    const dong = ds.dsHien().map((r) => { const m = margin(+r.gia_ban_hien_tai, +r.gia_nhap);
      return [r.ma_sp, r.ten_sp, r.kich_thuoc, r.danh_muc, r.ncc_name, r.ngay_nhap, +r.so_luong || 0, +r.so_luong_nhap || '', Math.round(+r.gia_nhap || 0), Math.round(+r.thanh_tien || 0), +r.gia_ban_hien_tai > 0 ? Math.round(+r.gia_ban_hien_tai) : '', m == null ? '' : m.toFixed(1), r.ghi_chu]; });
    const csv = '\uFEFF' + [dau].concat(dong).map((x) => x.map(oCsv).join(',')).join('\r\n');
    const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = 'ton-kho-' + new Date().toISOString().slice(0, 10) + '.csv'; document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  /* ── Đặt giá bán ── */
  const dlg = $('tk-dlg'); let dang = null;
  function veGy() { if (!dang) return; const g = docSo($('tk-gia').value), m = margin(g, +dang.gia_nhap);
    $('tk-gia-gy').textContent = m == null ? 'Nhập giá để xem biên lãi.' : 'Biên lãi so với giá nhập lô này: ' + KD.phanTram(m) + (m < 0 ? ' — thấp hơn giá nhập' : m < 15 ? ' — thấp' : ''); }
  $('tk-gia').addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; veGy(); });
  $('tk-goi-y').addEventListener('click', () => { $('tk-gia').value = KD.tien(Math.round(dang.gia_nhap * 1.3)); veGy(); $('tk-gia').focus(); });
  document.addEventListener('click', (e) => { const b = e.target.closest('#tk-tbody [data-gia]'); if (!b) return; const r = ds.dsHien().find((x) => String(x.id) === b.dataset.gia); if (!r) return;
    dang = r; $('tk-dlg-td').textContent = (r.product_master_id ? 'Đặt giá bán — ' : 'Tạo sản phẩm và đặt giá — ') + r.ma_sp;
    $('tk-dlg-tt').innerHTML = '<dt>Sản phẩm</dt><dd>' + esc(r.ten_sp) + '</dd><dt>Giá nhập tham khảo (lô ' + KD.ngay(r.ngay_nhap) + ')</dt><dd>' + KD.tienVnd(r.gia_nhap) + '</dd><dt>Giá bán hiện tại</dt><dd>' + (+r.gia_ban_hien_tai > 0 ? KD.tienVnd(r.gia_ban_hien_tai) : 'Chưa đặt') + '</dd>';
    $('tk-dlg-moi').hidden = !!r.product_master_id; $('tk-ly-do').value = '';
    $('tk-gia').value = +r.gia_ban_hien_tai > 0 ? KD.tien(r.gia_ban_hien_tai) : r.gia_nhap > 0 ? KD.tien(Math.round(r.gia_nhap * 1.3)) : '';
    $('tk-goi-y').hidden = !(r.gia_nhap > 0); $('tk-goi-y').textContent = 'Dùng gợi ý cộng 30% trên giá nhập: ' + KD.tienVnd(Math.round(r.gia_nhap * 1.3));
    veGy(); KD.moHopThoai(dlg); $('tk-gia').select(); }, true);
  $('tk-form').addEventListener('submit', async (e) => {
    e.preventDefault(); const g = docSo($('tk-gia').value);
    if (!g) { $('tk-gia').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập giá bán lớn hơn 0.'); }
    if (g === +dang.gia_ban_hien_tai) return KD.baoLoiHopThoai(dlg, 'Giá bán chưa thay đổi.');
    const nut = $('tk-ok'), q = KT.url.qs({ gia_ban: g, note: $('tk-ly-do').value.trim() }); nut.disabled = true;
    try { const url = dang.product_master_id ? '/api/external/products/' + dang.product_master_id + '/gia-ban?' + q : '/api/external/ton-kho-mh/' + encodeURIComponent(dang.ma_sp) + '/gia-ban?' + q;
      const kq = await KD.api(url, { method: 'PATCH', headers: { Accept: 'application/json' } }); dlg.close();
      window.showToast && window.showToast('ok', (kq.created ? 'Đã tạo sản phẩm và đặt giá ' : 'Đã đặt giá bán ') + dang.ma_sp + ': ' + KD.tienVnd(g)); ds.tai(); }
    catch (err) { KD.baoLoiHopThoai(dlg, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  ds.tai();
})();
