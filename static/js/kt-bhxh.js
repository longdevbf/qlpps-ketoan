/* kt-bhxh.js — Bảo hiểm xã hội (chỉ xem; khung: kt-danh-sach.js). Giữ nghiệp vụ màn cũ #page-bhxh:
   lọc trạng thái tham gia (mặc định Đang đóng) + tìm tại trình duyệt; tách NLĐ 8/1,5/1 và DN 17,5/3/1 — số do máy chủ HCNS tính, màn này không tự nhân tỷ lệ. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-bhxh')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TT = { 'Đang đóng': 'success', 'Chưa đóng': 'warning', 'Tạm dừng': 'muted', 'Đã nghỉ': 'muted' };
  const K = ['luong_dong', 'nld_bhxh', 'nld_bhyt', 'nld_bhtn', 'nld_tong', 'nsdld_bhxh', 'nsdld_bhyt', 'nsdld_bhtn', 'nsdld_tong', 'tong'];
  const ct = (key, nhan, title) => ({ key, nhan, num: true, lop: 'kt-bh-ct', title, ve: (r) => KD.tien(r[key] || 0) });
  const ds = KT.danhSach({
    pfx: 'bh', // Gửi trang_thai kể cả khi rỗng: KT.url.qs bỏ giá trị '' → API dùng mặc định "Đang đóng", chọn "Tất cả" vẫn chỉ ra người đang đóng.
    // Ô chọn "Tất cả" = 'tat_ca' (giữ được trên URL khi F5) → API nhận trang_thai rỗng = mọi trạng thái.
    api: (q) => '/api/external/bhxh?trang_thai=' + encodeURIComponent(q.trang_thai === 'tat_ca' ? '' : (q.trang_thai || '')), donVi: 'nhân viên', khongTrang: true,
    macDinh: { q: '', trang_thai: 'Đang đóng', ct: '', page: 1, size: 500, sort: '' }, khongDem: ['ct'],
    chuyen: (d, q) => {
      const dong = (d.data || []).filter((x) => KT.khopTim([x.ma_nv, x.ho_ten, x.phong_ban], q.q));
      // Bấm tiêu đề cột: trước đây chỉ đổi mũi tên, bảng không sắp xếp (API trả theo phòng ban, tên) — sắp xếp tại trình duyệt.
      const [cot, chieu] = String(q.sort || '').split(/_(?=asc$|desc$)/), dau = chieu === 'asc' ? 1 : -1;
      if (cot === 'ten') dong.sort((a, b) => dau * String(a.ho_ten || '').localeCompare(String(b.ho_ten || ''), 'vi'));
      else if (cot && chieu) dong.sort((a, b) => dau * ((+a[cot] || 0) - (+b[cot] || 0)));
      const tong = { so_nv: dong.length }; K.forEach((k) => { tong[k] = dong.reduce((a, x) => a + (+x[k] || 0), 0); });
      return { dong, tong_dong: dong.length, tong, tong_may_chu: d.totals || {} }; },
    dong: { id: (r) => r.ma_nv },
    cot: [
      { key: 'ten', nhan: 'Nhân viên', sort: 'chu', ve: (r) => H.ten(r.ho_ten, (r.ma_nv || '') + (r.phong_ban ? ' · ' + r.phong_ban : '')) },
      { key: 'tt', nhan: 'Trạng thái', ve: (r) => H.pill(TT[r.trang_thai] || 'muted', r.trang_thai || 'Chưa rõ') },
      { key: 'luong_dong', nhan: 'Lương đóng BH (VND)', num: true, sort: 'so', ve: (r) => KD.tien(r.luong_dong || 0) },
      ct('nld_bhxh', 'NLĐ · BHXH 8%', 'Người lao động — bảo hiểm xã hội 8%'), ct('nld_bhyt', 'NLĐ · BHYT 1,5%', 'Người lao động — bảo hiểm y tế 1,5%'), ct('nld_bhtn', 'NLĐ · BHTN 1%', 'Người lao động — bảo hiểm thất nghiệp 1%'),
      { key: 'nld_tong', nhan: 'NLĐ đóng 10,5%', num: true, sort: 'so', title: 'Trừ vào lương — Có TK 3383, 3384, 3386', ve: (r) => '<span class="kt-bh-cong">' + KD.tien(r.nld_tong || 0) + '</span>' },
      ct('nsdld_bhxh', 'DN · BHXH 17,5%', 'Doanh nghiệp — BHXH 17,5% (gồm quỹ tai nạn lao động, bệnh nghề nghiệp 0,5%)'), ct('nsdld_bhyt', 'DN · BHYT 3%', 'Doanh nghiệp — bảo hiểm y tế 3%'), ct('nsdld_bhtn', 'DN · BHTN 1%', 'Doanh nghiệp — bảo hiểm thất nghiệp 1%'),
      { key: 'nsdld_tong', nhan: 'DN đóng 21,5%', num: true, sort: 'so', title: 'Tính vào chi phí — Nợ TK 622, 627, 641, 642', ve: (r) => '<span class="kt-bh-cong">' + KD.tien(r.nsdld_tong || 0) + '</span>' },
      { key: 'tong', nhan: 'Tổng nộp (VND)', num: true, sort: 'so', ve: (r) => '<b>' + KD.tien(r.tong || 0) + '</b>' },
    ],
    kpi: {
      nv: (d) => ({ v: H.dem(d.tong.so_nv, 'người'), phu: 'Lương đóng ' + KD.tienGon(d.tong.luong_dong) }),
      nld: (d) => ({ v: H.tienKpi(d.tong.nld_tong), title: KD.tienVnd(d.tong.nld_tong), phu: '10,5% · trừ lương' }),
      dn: (d) => ({ v: H.tienKpi(d.tong.nsdld_tong), title: KD.tienVnd(d.tong.nsdld_tong), phu: '21,5% · tính chi phí' }),
      tong: (d) => ({ v: H.tienKpi(d.tong.tong), title: KD.tienVnd(d.tong.tong), phu: '32% lương đóng' }),
    },
    cong: (d) => [{ html: 'Cộng ' + KD.soDem(d.tong.so_nv) + ' nhân viên', span: 2 }].concat(K.map((k) => ({ html: KD.tien(d.tong[k]), num: true, lop: /_(bhxh|bhyt|bhtn)$/.test(k) ? 'kt-bh-ct' : '' }))),
    phamVi: () => '',
    sauTai: () => { const el = document.querySelector('#bh-kpi [data-kpi="tong"] .kd-kpi__label'); if (el && !el.querySelector('.kd-tip')) el.insertAdjacentHTML('beforeend', ' ' + KD.tip('Nộp cơ quan BHXH hằng tháng. Đối chiếu với số dư Có TK 3383, 3384, 3386 cuối tháng ở Sổ cái trước khi nộp.', 'kd-tip--trai')); },
    rong: (d, coLoc) => (coLoc ? ['Không có nhân viên nào khớp bộ lọc', 'Thử chọn trạng thái "Tất cả" hoặc bỏ ô tìm.'] : ['Chưa có dữ liệu bảo hiểm', 'HCNS chưa khai mức lương đóng bảo hiểm cho nhân viên nào.']),
    loi: 'Không tải được dữ liệu bảo hiểm từ HCNS',

  });
  const datCt = (bat) => { $('bh-ct').checked = bat; $('bh-bang').classList.toggle('kt-bh-hien', bat); };
  datCt(ds.st.ct === '1');
  $('bh-ct').addEventListener('change', (e) => { datCt(e.target.checked); ds.st.ct = e.target.checked ? '1' : ''; try { KT.url.ghi(ds.st, { q: '', trang_thai: 'Đang đóng', ct: '', page: 1, size: 500, sort: '' }); } catch (er) { /* khung xem trước */ } });
  // Chưa có API xuất Excel BHXH (/api/external/bhxh/xuat trả 404) — khoá nút như các màn khác.
  $('bh-xuat').addEventListener('click', (e) => { e.preventDefault(); window.showToast && window.showToast('info', 'App kế toán chưa có API xuất Excel bảo hiểm xã hội.'); });
  ds.tai();
})();
