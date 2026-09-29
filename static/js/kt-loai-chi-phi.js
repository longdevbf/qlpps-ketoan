/* kt-loai-chi-phi.js — Danh mục loại chi phí (khung: kt-danh-sach.js). Giữ nghiệp vụ màn cũ #page-loai-chi-phi:
   thêm / sửa / tạm dừng – dùng lại / xoá; nhom_default gợi ý tài khoản chi phí (641/642/635/811 theo TT 99/2025). API trả mảng, lọc tại trình duyệt. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-loai-chi-phi')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const NHOM = { ban_hang: ['Bán hàng', '641', 'brand'], quan_ly: ['Quản lý doanh nghiệp', '642', 'info'], tai_chinh: ['Tài chính', '635', 'warning'], khac: ['Khác', '811', 'muted'] };
  const pillNhom = (k) => { const n = NHOM[k] || NHOM.khac; return H.pill(n[2], n[0]) + ' <span class="kd-chip kd-chip--xam num" title="Tài khoản gợi ý">TK ' + n[1] + '</span>'; };
  const ds = KT.danhSach({
    pfx: 'lc', api: () => '/api/loai-chi-phi?active_only=false', donVi: 'loại chi phí', khongTrang: true,
    macDinh: { q: '', nhom: '', trang_thai: '', page: 1, size: 500, sort: '' },
    chuyen: (mang, q) => { const tat = Array.isArray(mang) ? mang : (mang.items || []);
      const dong = tat.filter((x) => KT.khopTim([x.ten, x.mo_ta], q.q) && (!q.nhom || x.nhom_default === q.nhom) && (!q.trang_thai || (q.trang_thai === 'dang') === !!x.active));
      // Bấm tiêu đề "Loại chi phí": trước đây chỉ đổi mũi tên (API trả mảng, không sắp) — sắp theo tên tại trình duyệt.
      if (q.sort === 'ten_asc' || q.sort === 'ten_desc') { const dau = q.sort === 'ten_asc' ? 1 : -1; dong.sort((a, b) => dau * String(a.ten || '').localeCompare(String(b.ten || ''), 'vi')); }
      const dem = (k) => tat.filter((x) => x.active && x.nhom_default === k).length;
      return { dong, tong_dong: dong.length, tong: { ban_hang: dem('ban_hang'), quan_ly: dem('quan_ly'), tai_chinh: dem('tai_chinh'), khac: dem('khac'), dung: tat.filter((x) => !x.active).length } }; },
    dong: { id: (r) => r.id },
    cot: [
      { key: 'ten', nhan: 'Loại chi phí', sort: 'chu', ve: (r) => '<span class="kd-strong">' + esc(r.ten) + '</span>' },
      { key: 'nhom', nhan: 'Nhóm chi phí mặc định', ve: (r) => pillNhom(r.nhom_default) },
      { key: 'mo_ta', nhan: 'Mô tả', ve: (r) => (r.mo_ta ? '<span class="kd-meta">' + esc(r.mo_ta) + '</span>' : '<span class="kd-muted">—</span>') },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => (r.active ? H.pill('success', 'Đang dùng') : H.pill('muted', 'Tạm dừng')) },
      { key: 'act', nhan: 'Thao tác', act: true, nhanDong: (r) => r.ten },
    ],
    kpi: Object.fromEntries(Object.keys(NHOM).map((k) => [k, (d) => ({ v: H.dem(d.tong[k], 'loại'), phu: k === 'khac' && d.tong.dung ? 'Đang dùng · ' + KD.soDem(d.tong.dung) + ' loại tạm dừng' : 'Đang dùng' })])),
    phamVi: () => '',
    sauTai: () => { const el = document.querySelector('#lc-kpi [data-kpi="khac"] .kd-kpi__label'); if (el && !el.querySelector('.kd-tip')) el.insertAdjacentHTML('beforeend', ' ' + KD.tip('Nhóm mặc định chỉ gợi ý tài khoản khi lập phiếu; vẫn chọn lại được tài khoản cấp 2 (vd 6417, 6427). Loại đã có phiếu dùng thì chỉ tạm dừng, không xoá. Số tạm dừng tính trên mọi nhóm.', 'kd-tip--trai')); },
    rong: (d, coLoc) => (coLoc ? ['Không có loại chi phí nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc.'] : ['Chưa có loại chi phí nào', 'Bấm "Thêm loại chi phí" để tạo danh mục đầu tiên cho phiếu chi.']),
    loi: 'Không tải được danh mục loại chi phí',
    menu: (r) => [
      { nhan: 'Sửa', icon: 'bi-pencil', onClick: () => mo(r) },
      { nhan: r.active ? 'Tạm dừng' : 'Dùng lại', icon: r.active ? 'bi-pause-circle' : 'bi-play-circle', onClick: () => doiTrangThai(r) },
      '-',
      { nhan: 'Xoá', icon: 'bi-trash', danger: true, onClick: () => moXoa(r) },
    ],
  });

  /* ── Thêm / sửa ── */
  const dlg = $('lc-dlg'); let dangSua = null;
  function mo(r) { dangSua = r; $('lc-dlg-td').textContent = r ? 'Sửa loại chi phí' : 'Thêm loại chi phí';
    $('lc-f-ten').value = r ? r.ten : ''; $('lc-f-nhom').value = r ? r.nhom_default || 'khac' : 'ban_hang'; $('lc-f-mo-ta').value = r ? r.mo_ta || '' : ''; $('lc-f-ten-gy').hidden = !r;
    KD.moHopThoai(dlg); $('lc-f-ten').focus(); }
  $('lc-them').addEventListener('click', () => mo(null));
  $('lc-form').addEventListener('submit', async (e) => {
    e.preventDefault(); const ten = $('lc-f-ten').value.trim();
    if (!ten) { $('lc-f-ten').focus(); return KD.baoLoiHopThoai(dlg, 'Nhập tên loại chi phí.'); }
    const body = { ten, nhom_default: $('lc-f-nhom').value, mo_ta: $('lc-f-mo-ta').value.trim() }, nut = $('lc-f-ok'); nut.disabled = true;
    try { if (dangSua) await KD.api('/api/loai-chi-phi/' + dangSua.id, Object.assign(KD.JSON_POST(body), { method: 'PUT' })); else await KD.api('/api/loai-chi-phi', KD.JSON_POST(body));
      dlg.close(); window.showToast && window.showToast('ok', (dangSua ? 'Đã cập nhật ' : 'Đã thêm ') + '"' + ten + '"'); ds.tai(); }
    catch (err) { KD.baoLoiHopThoai(dlg, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  async function doiTrangThai(r) {
    try { await KD.api('/api/loai-chi-phi/' + r.id, Object.assign(KD.JSON_POST({ active: !r.active }), { method: 'PUT' })); window.showToast && window.showToast('ok', (r.active ? 'Đã tạm dừng "' : 'Đã dùng lại "') + r.ten + '"'); ds.tai(); }
    catch (e) { window.showToast && window.showToast('err', 'Chưa đổi được trạng thái: ' + e.message); }
  }
  /* ── Xoá ── */
  const dlgXoa = $('lc-dlg-xoa'); let dangXoa = null;
  function moXoa(r) { dangXoa = r; $('lc-xoa-td').textContent = 'Xoá loại "' + r.ten + '"?';
    $('lc-xoa-nd').textContent = 'Xoá hẳn khỏi danh mục, không hoàn tác được. Nếu đã có phiếu chi dùng loại này, máy chủ sẽ từ chối — khi đó chọn "Tạm dừng" để ẩn khỏi ô chọn mà vẫn giữ lịch sử.'; KD.moHopThoai(dlgXoa); }
  $('lc-xoa-ok').addEventListener('click', async () => { const nut = $('lc-xoa-ok'); nut.disabled = true;
    try { await KD.api('/api/loai-chi-phi/' + dangXoa.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); dlgXoa.close(); window.showToast && window.showToast('ok', 'Đã xoá "' + dangXoa.ten + '"'); ds.tai(); }
    catch (e) { KD.baoLoiHopThoai(dlgXoa, 'Chưa xoá được: ' + e.message); } finally { nut.disabled = false; } });
  ds.tai();
})();
