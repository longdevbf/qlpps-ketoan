/* kt-khoan-vay-phieu.js — Hợp đồng vay (L4): thêm, sửa. API THẬT: app/routers/khoan_vay.py
   (prefix /api/khoan-vay).

   MISMATCH so với thiết kế gốc:
   - Backend thật CHỈ theo dõi "đi vay" (Nợ 112/Có 311|341) — không có "cho vay" (1283) ở
     app/services/khoan_vay.py._khoan_vay_account/journal posting. Nút "Cho vay" bị khoá.
   - Không có `muc_dich` — gộp vào `ghi_chu`.
   - Không có ô "Ngày đáo hạn" trực tiếp: backend nhận `ky_han_thang` (số tháng) rồi tự tính
     `ngay_dao_han` (app/routers/khoan_vay.py:_add_months, có clamp ngày cuối tháng nên có
     thể lệch vài ngày so với ngày người dùng chọn) — màn vẫn giữ ô ngày đáo hạn (trực quan
     hơn) và tự quy đổi sang số tháng khi gửi.
   - `phuong_thuc_tra` thật là 1 enum gộp cả cách trả gốc lẫn lãi
     (tu_do|tra_deu|chi_lai_dinh_ky|goc_lai_cuoi_ky) — không tách 2 ô "Trả lãi"/"Trả gốc"
     độc lập như thiết kế (không map 1-1 được, vd "Hằng quý"+"Đều hằng tháng" không có enum
     tương ứng) → gộp thành 1 ô chọn theo đúng 4 giá trị thật, ẩn ô "Trả gốc" cũ.
   - `loai_vay` (tin_chap|the_chap|tra_gop_xe|tra_gop_nha|khac): ô chọn "Hình thức vay" thật
     (QA 25/09: bản trước suy từ "Tài sản đảm bảo" nên SỬA một khoản "Trả góp xe" sẽ ghi đè
     thành tín chấp/thế chấp). Khi thêm mới, gõ tài sản đảm bảo mà chưa đổi ô → gợi ý "Thế chấp".
   - Sửa hợp đồng mà không đổi ngày: gửi lại đúng ky_han_thang đang lưu (không quy đổi lại từ
     2 ngày — tránh lệch kỳ hạn do làm tròn 30,44 ngày/tháng).
   - TK theo dõi khoản vay (311/341) do máy chủ tự chọn theo kỳ hạn — không phải field client
     gửi lên; ô tương ứng chỉ hiển thị (readonly).
   - TK nhận tiền giải ngân lấy DANH SÁCH THẬT từ GET /api/tai-khoan (tài khoản ngân hàng/tiền
     mặt của công ty — đúng ý nghĩa cần ở đây) — vừa gửi `tai_khoan_id` (định khoản kép) vừa
     `tai_khoan_giai_ngan` = tên TK đó (bắt buộc khớp `TaiKhoanNH.ten_tk` đang active).
   - Sửa hợp đồng: khoá số tiền gốc/ngày giải ngân/TK nhận tiền như thiết kế gốc (giữ nguyên
     chủ đích tránh sửa nhầm gốc vay đã giải ngân), dù backend thật (KhoanVayUpdate) về mặt
     kỹ thuật cho sửa các trường này.
*/
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-khoan-vay-phieu')) return;
  const $ = (id) => document.getElementById(id);
  const u = KT.url.doc();
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  const pill = (mau, nhan) => '<span class="pill pill--' + mau + '">' + esc(nhan) + '</span>';
  const PT_TRA = [['tra_deu', 'Trả đều gốc + lãi mỗi tháng'], ['chi_lai_dinh_ky', 'Trả lãi hằng tháng, gốc cuối kỳ'], ['goc_lai_cuoi_ky', 'Trả gốc + lãi 1 lần cuối kỳ'], ['tu_do', 'Tự do — không lịch cố định']];
  let loai = 'di_vay', hd = null, tkDs = [];
  const homNay = () => KD.iso(new Date());

  function veChonTk(sel, ds, chonId) {
    sel.innerHTML = '<option value="">— Chọn tài khoản —</option>' + ds.map((t) => '<option value="' + t.id + '" data-ten="' + esc(t.ten_tk) + '">' + esc(t.ten_tk + (t.so_tk ? ' — ' + t.so_tk : '')) + '</option>').join('');
    sel.value = chonId ? String(chonId) : '';
  }
  function addMonths(iso, n) { const d = new Date(iso); const day = d.getDate(); d.setDate(1); d.setMonth(d.getMonth() + n);
    const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate(); d.setDate(Math.min(day, last)); return KD.iso(d); }
  function soThangGiua(a, b) { if (!a || !b) return 0; return Math.max(1, Math.round((new Date(b) - new Date(a)) / (864e5 * 30.44))); }

  async function tai() {
    $('vp-tt').innerHTML = KD.KHUNG_TAI; $('vp-than').hidden = true; $('vp-thanh').hidden = true;
    try {
      const ds = await KD.api('/api/tai-khoan'); tkDs = ds.filter((t) => t.active);
      if (u.id) hd = await KD.api('/api/khoan-vay/' + encodeURIComponent(u.id));
      $('vp-tt').innerHTML = ''; $('vp-than').hidden = false; $('vp-thanh').hidden = false; dung();
    } catch (e) { $('vp-ma').textContent = '—'; KD.khoiLoi($('vp-tt'), u.id ? 'Không tải được hợp đồng' : 'Không mở được mẫu hợp đồng', e, tai); }
  }
  function dung() {
    $('vp-loai').hidden = !!hd;
    $('vp-tra-lai').innerHTML = PT_TRA.map(([k, ten]) => '<option value="' + k + '">' + esc(ten) + '</option>').join('');
    $('vp-h1').textContent = hd ? 'Sửa hợp đồng vay' : 'Thêm hợp đồng vay';
    $('vp-crumb').textContent = hd ? hd.ma_khoan : 'Thêm hợp đồng';
    $('vp-ico').className = 'ico-tile ico-tile--lg ico-tile--danger'; $('vp-ico').innerHTML = '<i class="bi bi-bank"></i>';
    $('vp-ma').textContent = hd ? hd.ma_khoan : 'Hợp đồng mới';
    $('vp-pill').innerHTML = hd ? (hd.status === 'da_tat_toan' ? pill('muted', 'Đã tất toán') : hd.status === 'qua_han' ? pill('danger', 'Quá hạn') : pill('success', 'Đang vay')) : pill('muted', 'Chưa lưu');
    $('vp-meta').innerHTML = hd ? '<span>Dư nợ gốc: <b>' + KD.tienVnd(hd.con_lai_goc) + '</b></span><span>Đáo hạn: <b>' + KD.ngay(hd.ngay_dao_han) + '</b></span>' : '<span>Ngày hôm nay: <b>' + KD.ngay(homNay()) + '</b></span>';
    $('vp-ghi-o').hidden = !!hd;
    veChonTk($('vp-tk-tien'), tkDs, hd ? null : null);
    if (hd) {
      $('vp-so').value = hd.ma_khoan; $('vp-so').readOnly = true;
      $('vp-ben').value = hd.nguon_vay; $('vp-md').value = hd.ghi_chu || ''; $('vp-goc').value = KD.tien(hd.so_tien_vay); $('vp-ls').value = hd.lai_suat_hien_tai != null ? hd.lai_suat_hien_tai : '';
      $('vp-tsdb').value = hd.tai_san_the_chap || ''; $('vp-ngay').value = hd.ngay_vay; $('vp-dh').value = hd.ngay_dao_han || '';
      $('vp-tra-lai').value = hd.phuong_thuc_tra; $('vp-loai-vay').value = hd.loai_vay || 'khac'; $('vp-tk-goc').value = hd.ky_han_thang <= 12 ? '311 — Vay ngắn hạn' : '341 — Vay dài hạn';
      if (hd.tai_khoan_giai_ngan) { const opt = [...$('vp-tk-tien').options].find((o) => o.dataset.ten === hd.tai_khoan_giai_ngan); if (opt) $('vp-tk-tien').value = opt.value; else { const o2 = document.createElement('option'); o2.value = ''; o2.textContent = hd.tai_khoan_giai_ngan + ' (đã ngừng dùng)'; $('vp-tk-tien').insertBefore(o2, $('vp-tk-tien').firstChild.nextSibling); $('vp-tk-tien').value = ''; } }
      ['vp-goc', 'vp-ngay', 'vp-tk-tien', 'vp-ls'].forEach((id) => { $(id).disabled = true; });
    } else {
      $('vp-ngay').value = homNay(); $('vp-dh').value = addMonths(homNay(), 12); $('vp-tra-lai').value = 'tu_do'; $('vp-tk-goc').value = '341 — Vay dài hạn (dự kiến)';
    }
    ve();
  }
  $('vp-loai-vay').addEventListener('change', (e) => { e.target.dataset.daChon = '1'; });
  $('vp-tsdb').addEventListener('input', (e) => { if (!hd && !$('vp-loai-vay').dataset.daChon) $('vp-loai-vay').value = e.target.value.trim() ? 'the_chap' : 'tin_chap'; });
  $('vp-goc').addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; ve(); });
  ['vp-ls', 'vp-ngay', 'vp-dh', 'vp-tra-lai', 'vp-ghi', 'vp-tk-tien'].forEach((id) => $(id).addEventListener('input', ve));

  function ve() {
    const goc = docSo($('vp-goc')), ls = +$('vp-ls').value || 0, a = $('vp-ngay').value, b = $('vp-dh').value;
    const soThang = soThangGiua(a, b);
    if (!hd) $('vp-tk-goc').value = soThang && soThang <= 12 ? '311 — Vay ngắn hạn' : '341 — Vay dài hạn';
    $('vp-dh-gy').innerHTML = soThang ? 'Kỳ hạn ' + KD.soDem(soThang) + ' tháng · ' + (soThang <= 12 ? 'ngắn hạn' : 'dài hạn') + KD.tip((soThang <= 12 ? 'Ngắn hạn (≤ 12 tháng, TK 311).' : 'Dài hạn (TK 341).') + ' Ngày đáo hạn được tính lại từ số tháng nên có thể lệch vài ngày so với ngày chọn.', 'kd-tip--trai') : '';
    const dong = (tk, nd, no, co) => '<tr><td><span class="kt-tk">' + esc(tk || '—') + '</span></td><td>' + esc(nd) + '</td><td class="num">' + KT.tienSo(no) + '</td><td class="num">' + KT.tienSo(co) + '</td></tr>';
    const tkTen = $('vp-tk-tien').selectedOptions[0] && $('vp-tk-tien').value ? $('vp-tk-tien').selectedOptions[0].textContent : '(chưa chọn tài khoản)';
    const loanAcc = soThang && soThang <= 12 ? '311' : '341';
    if (hd) $('vp-dk').innerHTML = '<tr><td colspan="4" class="kd-muted">Sửa hợp đồng không tạo bút toán. Trả gốc, lãi, đổi lãi suất: dùng nút ⋯ ở danh sách khoản vay.</td></tr>';
    else if (!$('vp-ghi').checked) $('vp-dk').innerHTML = '<tr><td colspan="4" class="kd-muted">Không ghi bút toán — chỉ lưu hợp đồng để theo dõi lịch trả.</td></tr>';
    else $('vp-dk').innerHTML = dong(tkTen, 'Nhận tiền giải ngân', goc, 0) + dong(loanAcc, 'Nợ gốc vay', 0, goc);
    $('vp-dk-gy').innerHTML = hd ? '' : KD.tip('Ngày hạch toán = ngày giải ngân.', 'kd-tip--trai');
    if (!goc || !soThang) { $('vp-lich').innerHTML = KD.khoiRong('Nhập số tiền, ngày giải ngân và đáo hạn', 'Lịch trả gốc, lãi dự kiến sẽ hiện ở đây.'); return; }
    const pt = $('vp-tra-lai').value, deu = pt === 'tra_deu', laiCuoi = pt === 'goc_lai_cuoi_ky', khongLai = pt === 'tu_do';
    if (khongLai) { $('vp-lich').innerHTML = '<p class="kd-meta">Trả tự do — không có lịch cố định.' + KD.tip('Khi trả, dùng nút ⋯ → Trả lãi / Trả gốc ở danh sách khoản vay.', 'kd-tip--trai') + '</p>'; return; }
    const laiThang = ls / 100 / 12;
    const lich = []; let du = goc;
    if (laiCuoi) { lich.push({ ngay: b, goc: goc, lai: Math.round(goc * laiThang * soThang) }); }
    else { for (let i = 1; i <= soThang && lich.length < 60; i++) { const lai = Math.round(du * laiThang); const g = deu ? Math.round(goc / soThang) : (i === soThang ? du : 0); du -= g; lich.push({ ngay: addMonths(a, i), goc: g, lai }); } }
    const tongLai = lich.reduce((s, x) => s + x.lai, 0);
    $('vp-lich').innerHTML = '<dl class="kt-tq"><dt>Tổng lãi dự kiến</dt><dd>' + KD.tienVnd(tongLai) + '</dd><dt class="is-dam">Tổng phải trả</dt><dd>' + KD.tienVnd(goc + tongLai) + '</dd></dl>'
      + '<table class="kt-bang-nho"><thead><tr><th scope="col">Kỳ</th><th scope="col" class="num">Gốc</th><th scope="col" class="num">Lãi</th></tr></thead><tbody>'
      + lich.slice(0, 6).map((x) => '<tr><td>' + KD.ngay(x.ngay) + '</td><td class="num">' + KT.tienSo(x.goc) + '</td><td class="num">' + KT.tienSo(x.lai) + '</td></tr>').join('')
      + (lich.length > 6 ? '<tr class="is-cho"><td colspan="3">… và ' + KD.soDem(lich.length - 6) + ' kỳ nữa, kỳ cuối ' + KD.ngay(lich[lich.length - 1].ngay) + '</td></tr>' : '') + '</tbody></table>';
  }

  const baoLoi = (m) => { $('vp-loi').textContent = m; $('vp-loi').hidden = !m; };
  $('vp-luu').addEventListener('click', async () => {
    baoLoi('');
    const soThang = soThangGiua($('vp-ngay').value, $('vp-dh').value);
    const tkOpt = $('vp-tk-tien').selectedOptions[0];
    const body = {
      nguon_vay: $('vp-ben').value.trim(), so_tien_vay: docSo($('vp-goc')), ngay_vay: $('vp-ngay').value,
      ky_han_thang: hd && $('vp-dh').value === (hd.ngay_dao_han || '') ? hd.ky_han_thang : (soThang || 12), phuong_thuc_tra: $('vp-tra-lai').value,
      tai_san_the_chap: $('vp-tsdb').value.trim() || null,
      loai_vay: $('vp-loai-vay').value,
      lai_suat_nam: +$('vp-ls').value || 0,
      ghi_chu: $('vp-md').value.trim() || null,
    };
    if (!hd) {
      body.ma_khoan = $('vp-so').value.trim();
      const ghiSo = $('vp-ghi').checked;
      body.tai_khoan_giai_ngan = ghiSo && tkOpt && tkOpt.value ? tkOpt.dataset.ten : null;
      body.tai_khoan_id = ghiSo && tkOpt && tkOpt.value ? +tkOpt.value : null;
      body.auto_giai_ngan = ghiSo;
    }
    if (!hd && !body.ma_khoan) { $('vp-so').focus(); return baoLoi('Nhập số hợp đồng.'); }
    if (!body.nguon_vay) { $('vp-ben').focus(); return baoLoi('Nhập bên cho vay.'); }
    if (!body.so_tien_vay) { $('vp-goc').focus(); return baoLoi('Nhập số tiền gốc.'); }
    if ($('vp-ls').value === '') { $('vp-ls').focus(); return baoLoi('Nhập lãi suất (0 nếu không tính lãi).'); }
    if (!hd && $('vp-ghi').checked && !(tkOpt && tkOpt.value)) { $('vp-tk-tien').focus(); return baoLoi('Chọn tài khoản nhận tiền giải ngân, hoặc bỏ tick "Ghi luôn bút toán".'); }
    const nut = $('vp-luu'); nut.disabled = true;
    try { const r = await KD.api(hd ? '/api/khoan-vay/' + hd.id : '/api/khoan-vay', hd ? Object.assign(KD.JSON_POST(body), { method: 'PUT' }) : KD.JSON_POST(body));
      window.showToast && window.showToast('ok', (hd ? 'Đã lưu ' : 'Đã thêm ') + r.ma_khoan); try { location.href = '/ketoan/khoan-vay'; } catch (x) { /* khung xem trước */ } }
    catch (e) { baoLoi('Chưa lưu được: ' + e.message); } finally { nut.disabled = false; }
  });
  tai();
})();
