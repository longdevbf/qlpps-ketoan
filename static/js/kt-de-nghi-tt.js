/* kt-de-nghi-tt.js — Tạo đề nghị thanh toán (L4 form).
   ĐẤU NỐI THẬT (2026-09-25): thiết kế cho POST /api/duyet-chi {nguon:'de_nghi_tt', hinh_thuc, thu_huong:{...}, gui} +
   GET /api/duyet-chi/cau-hinh — CẢ HAI chưa từng được xây. Gửi thật qua workflow duyệt chi dùng chung
   (`shared/routers/duyet_chi.py`, mount /api/duyet-chi — KHÔNG sửa file đó):
     POST /api/duyet-chi  {tieu_de, loai_chi, so_tien, ngay_de_xuat, han_thanh_toan?, muc_dich, ghi_chu?}
     POST /api/duyet-chi/<id>/chung-tu  (multipart, sau khi tạo — model thật không nhận file kèm lúc tạo)
   Các điểm PHẢI GẦN ĐÚNG vì API/schema thật không có, ghi rõ tại chỗ:
     · "Loại" — model thật chỉ có 6 loại_chi cố định (di_chuyen/van_phong/tiep_thi/dao_tao/khach_hang/khac), KHÔNG có
       thanh_toan_ncc/tạm ứng/hoàn ứng như thiết kế cũ → đổi hẳn 4 nút loại sang đúng 6 loại thật (sửa cả template).
     · "Người thụ hưởng" + STK/ngân hàng + hình thức — model thật không có cột riêng, gộp vào `muc_dich` (text) để
       người duyệt vẫn đọc được, KHÔNG bịa cột mới.
     · "Bộ phận" — model thật LUÔN lấy theo phòng ban thật của người đăng nhập lúc tạo (server tự tra, không nhận
       tham số từ client) → ô này đổi thành CHỈ HIỂN THỊ (khoá), không gửi lên server.
     · "Ngày đề xuất" (ngay_de_xuat, bắt buộc) — form cũ không có ô này → tự điền = hôm nay lúc gửi.
     · Nút "Lưu nháp" — model thật KHÔNG có trạng thái nháp (mọi bản ghi tạo xong vào thẳng hàng chờ duyệt) → bỏ nút.
     · Quy trình duyệt "Giám đốc (từ ngưỡng X)" — backend thật LUÔN bắt CEO duyệt sau Kế toán, không có ngưỡng số
       tiền cấu hình qua API → bỏ điều kiện, hiện cố định 4 bước.
   Người đề nghị/bộ phận lấy từ GET /api/profile (endpoint thật, dùng chung toàn app — thay cho /api/duyet-chi/cau-hinh). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-de-nghi')) return;
  const $ = (id) => document.getElementById(id);
  const CAN = {
    di_chuyen: ['Vé xe / hoá đơn xăng dầu', 'Lý do hoặc lịch trình di chuyển'],
    van_phong: ['Hoá đơn mua văn phòng phẩm', 'Báo giá nếu từ 5 triệu trở lên'],
    tiep_thi: ['Hoá đơn / hợp đồng quảng cáo, tiếp thị', 'Báo cáo hiệu quả nếu có'],
    dao_tao: ['Kế hoạch / nội dung đào tạo', 'Hoá đơn học phí, giảng viên'],
    khach_hang: ['Hoá đơn tiếp khách', 'Tên khách hàng / đối tác được tiếp'],
    khac: ['Hoá đơn hoặc chứng từ liên quan', 'Diễn giải rõ lý do chi'],
  };
  let loai = 'khac', tep = [];   // tep: mảng File thật (upload SAU khi tạo đề nghị, API thật không nhận kèm lúc tạo)
  const LOAI_DAU = CAN[KT.url.doc().loai] ? KT.url.doc().loai : 'khac';
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;

  function doiLoai(l) {
    loai = l; $('dn-loai').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.loai === l)));
    KT.url.ghi({ loai: l }, { loai: 'khac' });   // ?loai= đã được đọc lúc mở → giữ trên URL để F5 không mất loại đang chọn
    ve();
  }
  $('dn-loai').addEventListener('click', (e) => { const b = e.target.closest('[data-loai]'); if (b && b.dataset.loai !== loai) doiLoai(b.dataset.loai); });
  $('dn-tien').addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; ve(); });
  $('dn-ht').addEventListener('change', ve);
  $('dn-tep').addEventListener('change', (e) => { tep = tep.concat([...e.target.files]); e.target.value = ''; ve(); });
  $('dn-tep-ds').addEventListener('click', (e) => { const b = e.target.closest('[data-xoa]'); if (b) { tep.splice(+b.dataset.xoa, 1); ve(); } });

  function ve() {
    const n = docSo($('dn-tien')), ck = $('dn-ht').value === 'ck';
    $('dn-tien-chu').textContent = n ? 'Bằng chữ: ' + KT.bangChu(n) : '';
    $('dn-stk-o').hidden = !ck; $('dn-nh-o').hidden = !ck;
    $('dn-qt').innerHTML = '<ol class="kd-timeline">' + ['Trưởng bộ phận (nếu có)', 'Kế toán trưởng', 'Giám đốc', 'Kế toán chi tiền'].map((b, i) => '<li><div class="kd-tl"><div><div class="kd-strong">' + (i + 1) + '. ' + esc(b) + '</div></div></div></li>').join('') + '</ol>';
    $('dn-can').innerHTML = CAN[loai].map((c, i) => '<li class="is-' + (i === 0 && tep.length ? 'ok' : 'cho') + '"><i class="bi ' + (i === 0 && tep.length ? 'bi-check-circle-fill' : 'bi-circle') + '" aria-hidden="true"></i><span>' + esc(c) + '</span></li>').join('');
    $('dn-tep-ds').innerHTML = tep.map((f, i) => '<li class="kd-file"><span class="ico-tile ico-tile--sm" aria-hidden="true"><i class="bi bi-paperclip"></i></span><div><span class="kd-file__ten">' + esc(f.name) + '</span><span class="kd-file__meta">' + KD.soDem(Math.max(1, Math.round(f.size / 1024))) + ' KB</span></div><button type="button" class="kd-icon-btn" data-xoa="' + i + '" aria-label="Bỏ tệp ' + esc(f.name) + '"><i class="bi bi-x-lg" aria-hidden="true"></i></button></li>').join('');
  }
  const baoLoi = (m) => { $('dn-loi').textContent = m; $('dn-loi').hidden = !m; };

  async function gui() {
    baoLoi('');
    const n = docSo($('dn-tien')), ck = $('dn-ht').value === 'ck';
    if (!$('dn-nd').value.trim()) { $('dn-nd').focus(); return baoLoi('Nhập nội dung đề nghị.'); }
    if (!n) { $('dn-tien').focus(); return baoLoi('Nhập số tiền.'); }
    if (!$('dn-th').value.trim()) { $('dn-th').focus(); return baoLoi('Nhập người/đơn vị thụ hưởng.'); }
    if (!$('dn-ly').value.trim()) { $('dn-ly').focus(); return baoLoi('Nhập diễn giải chi tiết — người duyệt cần biết căn cứ chi.'); }
    if (!tep.length) return baoLoi('Đính kèm ít nhất một chứng từ — người duyệt cần xem căn cứ chi.');

    // Model thật không có cột thụ hưởng/STK/hình thức riêng — gộp vào muc_dich (text) để không mất thông tin.
    let mucDich = $('dn-ly').value.trim() + '\nNgười thụ hưởng: ' + $('dn-th').value.trim();
    if (ck && ($('dn-stk').value.trim() || $('dn-nh').value.trim())) mucDich += ' — STK ' + $('dn-stk').value.trim() + ' (' + $('dn-nh').value.trim() + ')';
    mucDich += ck ? ' — Chuyển khoản' : ' — Tiền mặt';

    const nut = $('dn-gui'); nut.disabled = true;
    try {
      const r = await KD.api('/api/duyet-chi', KD.JSON_POST({
        tieu_de: $('dn-nd').value.trim(), loai_chi: loai, so_tien: n,
        ngay_de_xuat: KD.iso(new Date()), han_thanh_toan: $('dn-han').value || null,
        muc_dich: mucDich, ghi_chu: '',
      }));
      const ket = await Promise.allSettled(tep.map((f) => { const fd = new FormData(); fd.append('file', f); return KD.api('/api/duyet-chi/' + r.id + '/chung-tu', { method: 'POST', body: fd }); }));
      const loiTep = ket.filter((k) => k.status === 'rejected').length;
      window.showToast && window.showToast(loiTep ? 'warning' : 'ok', 'Đã gửi duyệt ' + r.tieu_de + (loiTep ? ' — ' + loiTep + '/' + tep.length + ' tệp đính kèm lỗi, vào Duyệt chi để đính kèm lại.' : ''));
      location.href = '/ketoan/kt-duyet?trang_thai=tat_ca&nguon=de_xuat_chi&id=' + encodeURIComponent('dx:' + r.id);
    } catch (e) { baoLoi('Chưa gửi được: ' + e.message); } finally { nut.disabled = false; }
  }
  $('dn-gui').addEventListener('click', gui);

  async function tai() {
    $('dn-tt').innerHTML = KD.KHUNG_TAI; $('dn-than').hidden = true; $('dn-thanh').hidden = true;
    try {
      const p = await KD.api('/api/profile');
      $('dn-bp').innerHTML = '<option>' + esc(p.phong_ban || '(Chưa gắn phòng ban)') + '</option>';
      $('dn-bp').disabled = true;   // backend tự lấy phòng ban theo người tạo — ô này chỉ để xem
      $('dn-bp-meta').textContent = p.phong_ban || '(Chưa gắn phòng ban)';   // cùng chữ với ô Bộ phận
      $('dn-nguoi').textContent = p.ho_ten || p.username;
      const h = new Date(); h.setDate(h.getDate() + 7); $('dn-han').value = KD.iso(h);
      $('dn-tt').innerHTML = ''; $('dn-than').hidden = false; $('dn-thanh').hidden = false; doiLoai(LOAI_DAU);
    } catch (e) { KD.khoiLoi($('dn-tt'), 'Không mở được mẫu đề nghị', e, tai); }
  }
  tai();
})();
