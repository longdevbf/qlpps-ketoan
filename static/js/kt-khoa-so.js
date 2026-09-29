/* kt-khoa-so.js — Chốt / mở kỳ kế toán.
   API thật: app/routers/ky_ke_toan.py (prefix /api/ky-ke-toan) + app/services/period_close.py.
     GET  /api/ky-ke-toan                    12 kỳ gần nhất (chỉ kỳ đã từng chốt/mở).
     GET  /api/ky-ke-toan/ln-giu-lai/luy-ke  LN giữ lại luỹ kế hiện tại.
     GET  /api/ky-ke-toan/{thang}/xem-truoc  checklist + P&L ƯỚC TÍNH, không ghi DB (thêm mới cho màn này).
     POST /api/ky-ke-toan/{thang}/chot       chốt kỳ thật.
     POST /api/ky-ke-toan/{thang}/mo         mở lại kỳ đã chốt (cascade: chỉ mở được kỳ đã chốt GẦN NHẤT).
   Gap thật: không có bút toán kết chuyển 911/421 (P&L tính trực tiếp từ doanh thu/chi phí kỳ) — bỏ hẳn
   bảng "bút toán kết chuyển sẽ ghi" của bản thiết kế /api/khoa-so cũ. "Mở khoá" thật không nhận lý do. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-khoa-so')) return;
  // Quyền (F3 28/09): CHỐT kỳ mở cho Kế toán (ky_ke_toan.py chot: admin/ceo/assistant_ceo/manager/kt); MỞ KHOÁ chỉ admin/ceo (mo) →
  // người khác không thấy nút "Mở khoá", chỉ thấy câu nhắc cần quyền CEO.
  const MO_DUOC = ['admin', 'ceo'].includes(document.getElementById('kd-kt-khoa-so').dataset.vaiTroGoc);
  const $ = (id) => document.getElementById(id);
  const pill = (mau, nhan) => '<span class="pill pill--' + mau + '">' + esc(nhan) + '</span>';
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const thangHomNay = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  const kpi = (k, v, phu) => { const el = document.querySelector('#ks-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-phu]').innerHTML = phu || ''; };

  // Chỉ tiêu P&L hiển thị ở bảng "xem trước" — khớp field trả về từ .../xem-truoc (xem_truoc.*).
  const CHI_TIEU_PL = [
    ['dt_thuan', 'Doanh thu thuần'], ['cogs', 'Giá vốn hàng bán'], ['ln_gop', 'Lợi nhuận gộp'],
    ['cp_ban_hang', 'Chi phí bán hàng'], ['cp_quan_ly', 'Chi phí quản lý DN'],
    ['dt_tai_chinh', 'Doanh thu tài chính'], ['cp_tai_chinh', 'Chi phí tài chính'],
    ['thu_nhap_khac', 'Thu nhập khác'], ['cp_khac', 'Chi phí khác'],
    ['ln_truoc_thue', 'Lợi nhuận trước thuế'], ['thue_tndn', 'Thuế TNDN (20% trên lãi dương)'], ['lnst', 'Lợi nhuận sau thuế'],
    ['ln_giu_lai_dau_ky', 'LN giữ lại đầu kỳ'], ['co_tuc_du_kien', 'Cổ tức dự kiến chia trong kỳ'],
    ['trich_quy_du_kien', 'Trích quỹ dự kiến trong kỳ'], ['ln_giu_lai_cuoi_ky_uoc_tinh', 'LN giữ lại cuối kỳ (ước tính)'],
  ];
  const DONG_DAM = new Set(['ln_gop', 'ln_truoc_thue', 'lnst', 'ln_giu_lai_cuoi_ky_uoc_tinh']);

  let xt = null;          // kết quả /xem-truoc gần nhất (dùng khi bấm Chốt kỳ)
  let ls = [];             // lịch sử 12 kỳ
  let khoaGanNhat = null;  // kỳ 'da_chot' có thang lớn nhất — kỳ DUY NHẤT được phép Mở khoá (rule cascade)

  /* ── Tổng quan (KPI + lịch sử) ── */
  async function taiTongQuan() {
    ['ln_luy_ke', 'ky_gan_nhat', 'so_ky'].forEach((k) => kpi(k, '<span class="kd-skel kd-skel--kpi"></span>'));
    try {
      const [luyKe, dsKy] = await Promise.all([
        KD.api('/api/ky-ke-toan/ln-giu-lai/luy-ke'),
        KD.api('/api/ky-ke-toan'),
      ]);
      ls = dsKy;
      kpi('ln_luy_ke', '<span>' + KD.tien(luyKe.ln_giu_lai_luy_ke) + '</span>', luyKe.ky_chot_moi_nhat ? 'Tính đến hết kỳ ' + thangChu(luyKe.ky_chot_moi_nhat) : 'Chưa có kỳ nào chốt');
      kpi('ky_gan_nhat', luyKe.ky_chot_moi_nhat ? '<span>Tháng ' + thangChu(luyKe.ky_chot_moi_nhat) + '</span>' : '<span class="kd-muted">—</span>');
      kpi('so_ky', '<span>' + KD.soDem(luyKe.n_ky_da_chot) + '</span><span class="kd-kpi__don-vi">kỳ</span>');
      $('ks-tt').innerHTML = '';
      $('ks-than').hidden = false;
      veLichSu();
    } catch (e) {
      ['ln_luy_ke', 'ky_gan_nhat', 'so_ky'].forEach((k) => kpi(k, '<span class="kd-muted">—</span>'));
      KD.khoiLoi($('ks-tt'), 'Không tải được tình trạng khoá sổ', e, taiTongQuan);
    }
  }

  function veLichSu() {
    khoaGanNhat = ls.filter((k) => k.trang_thai === 'da_chot').sort((a, b) => (a.thang < b.thang ? 1 : -1))[0] || null;
    if (!ls.length) {
      $('ks-ls').innerHTML = '';
      $('ks-ls-tt').innerHTML = KD.khoiRong('Chưa có kỳ kế toán nào', 'Kỳ kế toán chỉ được tạo khi bấm Chốt kỳ lần đầu ở khung bên trái.');
      return;
    }
    $('ks-ls-tt').innerHTML = '';
    $('ks-ls').innerHTML = ls.slice().sort((a, b) => (a.thang < b.thang ? 1 : -1)).map((k) => {
      const daChot = k.trang_thai === 'da_chot';
      const coTheMo = MO_DUOC && daChot && khoaGanNhat && k.thang === khoaGanNhat.thang;
      return '<tr><td class="kd-strong">Tháng ' + thangChu(k.thang) + '</td>'
        + '<td>' + (daChot ? pill('success', 'Đã chốt') : pill('muted', 'Đang mở')) + '</td>'
        + '<td>' + (k.chot_luc ? KD.ngayGio(k.chot_luc) + '<span class="kt-khach__ma">' + esc(k.chot_boi || '') + '</span>' : '<span class="kd-muted">—</span>') + '</td>'
        + '<td class="num">' + (k.lnst_ky != null ? '<span class="' + (+k.lnst_ky >= 0 ? '' : 'kt-so--xau') + '">' + KD.tien(k.lnst_ky) + '</span>' : '<span class="kd-muted">—</span>') + '</td>'
        + '<td class="num">' + (k.ln_giu_lai_cuoi_ky != null ? KD.tien(k.ln_giu_lai_cuoi_ky) : '<span class="kd-muted">—</span>') + '</td>'
        + '<td class="kd-col-act">' + (coTheMo ? '<button type="button" class="kd-btn kd-btn--sm" data-mo="' + k.thang + '"><i class="bi bi-unlock" aria-hidden="true"></i>Mở khoá</button>' : '') + '</td></tr>';
    }).join('');
  }

  /* ── Kiểm tra + xem trước một kỳ ── */
  // Tên điều kiện từ backend có từ kỹ thuật ("du_thao", "post") → đổi sang chữ thường ngày khi hiển thị.
  const tenKiem = (t) => String(t || '').replace(' (du_thao)', '').replace('đã post', 'đã ghi sổ').replace(/(\d{4})-(\d{2})/g, '$2/$1');
  function veKiem(kiem) {
    $('ks-kiem').innerHTML = kiem.map((k) =>
      '<li class="is-' + (k.dat ? 'ok' : 'loi') + '"><i class="bi ' + (k.dat ? 'bi-check-circle-fill' : 'bi-x-circle-fill') + '" aria-hidden="true"></i>'
      + '<span><span class="visually-hidden">' + (k.dat ? 'Đạt: ' : 'Chưa đạt: ') + '</span>' + esc(tenKiem(k.ten)) + (!k.dat && k.chan ? ' ' + pill('danger', 'Bắt buộc') : '') + '</span>'
      + (!k.dat && k.chi_tiet ? '<small>' + esc(tenKiem(k.chi_tiet)) + '</small>' : '') + '</li>'
    ).join('');
  }

  /* Tiền VND không có số lẻ: backend trả số lẻ (vd 358.820.676,3) và mỗi dòng làm tròn riêng → cột không cộng khớp
     (T9/2026: 197.225.676 − 100.239.905 − 110.167.992 − 270.763.546 = −283.945.767 nhưng dòng LNTT hiện −283.945.766).
     Làm tròn từng khoản mục gốc rồi tính lại các dòng tổng từ số đã làm tròn → mọi dòng tổng = cộng/trừ đúng các dòng trên. */
  function lamTronPl(x0) {
    const x = {}; CHI_TIEU_PL.forEach(([k]) => { x[k] = Math.round(+x0[k] || 0); });
    x.ln_gop = x.dt_thuan - x.cogs;
    x.ln_truoc_thue = x.ln_gop - x.cp_ban_hang - x.cp_quan_ly + x.dt_tai_chinh - x.cp_tai_chinh + x.thu_nhap_khac - x.cp_khac;
    x.lnst = x.ln_truoc_thue - x.thue_tndn;
    x.ln_giu_lai_cuoi_ky_uoc_tinh = x.ln_giu_lai_dau_ky + x.lnst - x.co_tuc_du_kien - x.trich_quy_du_kien;
    return x;
  }

  function veXemTruoc(d) {
    xt = d;
    $('ks-xem-noi-dung').hidden = false;
    $('ks-xem-foot').hidden = false;
    const x = lamTronPl(d.xem_truoc);
    $('ks-xem-ghi-chu').innerHTML = 'P&amp;L ước tính tháng ' + thangChu(d.thang) + ' ' + KD.tip('Tính trên số liệu hiện tại; số thật được ghi lại đúng lúc bấm Chốt kỳ.');
    $('ks-pl').innerHTML = CHI_TIEU_PL.map(([k, ten]) => {
      const v = +x[k] || 0, am = v < 0;
      return '<tr' + (DONG_DAM.has(k) ? ' class="kd-strong"' : '') + '><th scope="row">' + esc(ten) + '</th>'
        + '<td class="num' + (am ? ' kt-so--xau' : '') + '">' + (am ? '−' : '') + KD.tien(Math.abs(v)) + '</td></tr>';
    }).join('');
    veKiem(d.kiem);
    const daChotRoi = d.trang_thai_hien_tai === 'da_chot';
    $('ks-chot-chu').textContent = 'Chốt kỳ tháng ' + thangChu(d.thang);
    $('ks-chot').disabled = !d.co_the_chot || daChotRoi;
    $('ks-chot-ghi-chu').textContent = daChotRoi
      ? 'Kỳ này đã chốt — muốn chốt lại phải Mở khoá trước' + (MO_DUOC ? '.' : ' (cần quyền CEO / Admin để mở khoá).')
      : (d.co_the_chot ? 'Đủ điều kiện — có thể chốt kỳ này.' : 'Còn mục "Bắt buộc" chưa đạt ở khung Kiểm tra.');
  }

  /* Lượt kiểm: đổi tháng liên tiếp thì chỉ kết quả của tháng CUỐI được vẽ — trước đây phản hồi cũ về muộn đè
     lên, `xt` trỏ tháng cũ và nút "Chốt kỳ" chốt nhầm tháng khác tháng đang chọn trong ô. */
  let luotKt = 0;
  async function kiemTra() {
    const thang = $('ks-thang').value, l = ++luotKt;
    xt = null; $('ks-chot').disabled = true;
    if (!thang) { $('ks-xem-tt').innerHTML = ''; $('ks-xem-noi-dung').hidden = true; $('ks-xem-foot').hidden = true; return; }
    try { KT.url.ghi({ thang }, { thang: thangHomNay() }); } catch (e) { /* khung xem */ }
    $('ks-xem-tt').innerHTML = KD.KHUNG_TAI;
    $('ks-xem-noi-dung').hidden = true;
    $('ks-xem-foot').hidden = true;
    $('ks-kiem').innerHTML = KD.KHUNG_TAI;
    try {
      const d = await KD.api('/api/ky-ke-toan/' + thang + '/xem-truoc');
      if (l !== luotKt) return;
      $('ks-xem-tt').innerHTML = '';
      veXemTruoc(d);
    } catch (e) {
      if (l !== luotKt) return;
      $('ks-kiem').innerHTML = '';
      KD.khoiLoi($('ks-xem-tt'), 'Không kiểm tra được kỳ ' + thangChu(thang), e, kiemTra);
    }
  }
  $('ks-kiem-tra').addEventListener('click', kiemTra);
  // Đổi tháng là tự kiểm luôn (trước phải bấm "Kiểm tra" — bảng vẫn hiện tháng cũ trong khi ô đã đổi).
  $('ks-thang').addEventListener('change', KD.debounce(kiemTra, 250));   // gõ tay từng chữ số năm → chỉ gọi 1 lần
  $('ks-thang').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); kiemTra(); } });

  /* ── Chốt kỳ ── */
  const dlg = $('ks-dlg');
  $('ks-chot').addEventListener('click', () => {
    if (!xt) return;
    const x = lamTronPl(xt.xem_truoc);   // cùng số với bảng xem trước
    $('ks-dlg-td').textContent = 'Chốt kỳ tháng ' + thangChu(xt.thang) + '?';
    $('ks-dlg-nd').textContent = 'LNST ước tính ' + KD.tienVnd(x.lnst) + ', LN giữ lại cuối kỳ ước tính ' + KD.tienVnd(x.ln_giu_lai_cuoi_ky_uoc_tinh) + '. Sau khi chốt, số liệu kỳ này được lưu lại thành báo cáo — muốn sửa phải Mở khoá lại' + (MO_DUOC ? '.' : ' (chỉ CEO / Admin mở khoá được).');
    KD.moHopThoai(dlg);
  });
  $('ks-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!xt) return;
    const nut = $('ks-dlg-ok'); nut.disabled = true;
    try {
      const r = await KD.api('/api/ky-ke-toan/' + xt.thang + '/chot', KD.JSON_POST({}));
      dlg.close();
      window.showToast && window.showToast('ok', 'Đã chốt kỳ tháng ' + thangChu(r.thang) + ' — LNST ' + KD.tienVnd(r.lnst_ky));
      taiTongQuan(); kiemTra();
    } catch (err) { KD.baoLoiHopThoai(dlg, err.message); } finally { nut.disabled = false; }
  });

  /* ── Mở khoá ── */
  const dlgMo = $('ks-dlg-mo');
  let thangMo = null;
  $('ks-ls').addEventListener('click', (e) => {
    const b = e.target.closest('[data-mo]'); if (!b) return;
    thangMo = b.dataset.mo;
    $('ks-mo-td').textContent = 'Mở khoá kỳ tháng ' + thangChu(thangMo) + '?';
    $('ks-mo-nd').textContent = 'Bản chụp báo cáo P&L của kỳ này sẽ bị xoá, kỳ chuyển về trạng thái "Đang mở". Việc mở khoá được ghi vào nhật ký hệ thống.';
    KD.moHopThoai(dlgMo);
  });
  $('ks-form-mo').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!thangMo) return;
    const nut = $('ks-mo-ok'); nut.disabled = true;
    try {
      const r = await KD.api('/api/ky-ke-toan/' + thangMo + '/mo', KD.JSON_POST({}));
      dlgMo.close();
      window.showToast && window.showToast('ok', 'Đã mở khoá kỳ tháng ' + thangChu(r.thang));
      taiTongQuan();
      if (xt && xt.thang === r.thang) kiemTra();
    } catch (err) { KD.baoLoiHopThoai(dlgMo, err.message); } finally { nut.disabled = false; }
  });

  const thangUrl = KT.url.doc().thang;   // mở lại link/F5 giữ đúng tháng đang kiểm
  $('ks-thang').value = /^\d{4}-(0[1-9]|1[0-2])$/.test(thangUrl || '') ? thangUrl : thangHomNay();
  taiTongQuan();
  kiemTra();
})();
