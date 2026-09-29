/* kt-tscd-phieu.js — Phiếu TSCĐ (L4): ghi tăng · sửa · thanh lý.
   API THẬT: app/routers/tai_san.py, prefix /api/tai-san (KHÔNG PHẢI /api/tscd như README đề xuất).

   MISMATCH so với thiết kế gốc (đã xử lý ở màn này, ghi lại để bàn giao):
   - Không có GET /api/tscd/so-moi (mã dự kiến / kỳ khoá sổ) — TSCĐCreate.ma_tscd do
     máy chủ tự sinh (TS-YYYY-NNN), không hiện trước được ở đây.
   - Model TSCĐ thật KHÔNG có tk_hao_mon / tk_cp riêng từng tài sản: TK nguyên giá tự
     suy theo `loai` (211 hữu hình / 213 vô hình — ô "Loại tài sản"), TK hao mòn LUÔN là 214, TK chi phí khấu hao suy từ `bo_phan`
     (ban_hang→641, quan_ly→642, tai_chinh→635, khac→811 — app/services/tscd_calc.py
     _BO_PHAN_TO_ACCOUNT). 3 ô "TK…" trên màn vì vậy chỉ HIỂN THỊ (readonly), không gửi lên.
   - `bo_phan` là enum bắt buộc (ban_hang|quan_ly|tai_chinh|khac) — ô chọn 4 giá trị.
   - Ghi tăng CHỈ hỗ trợ mua trả ngay từ 1 "tài khoản NH/tiền mặt" của công ty
     (`tai_khoan_id` → app/services/tscd_calc.py:mua_tscd, luôn Nợ 211|213 / Có 111|112) —
     KHÔNG có mua chịu (331), KHÔNG có VAT (1332). Ô "Chi tiền từ tài khoản" vì vậy lấy
     danh sách thật từ GET /api/tai-khoan (đây là bảng tài khoản ngân hàng/tiền mặt của
     công ty, ĐÚNG ý nghĩa cần — khác với việc `KT.oTk` dùng chung của kt-chung.js đang
     hard-code gọi cùng path này để tìm HỆ THỐNG TÀI KHOẢN KẾ TOÁN, xem ghi chú ở đầu
     app/routers/ui_ketoan_dot4.py). `ncc` là ô chữ tự do (không có danh mục NCC ở đây).
   - Ghi tăng tài sản CŨ đã khấu hao một phần (hao_mon_dau / so_thang_da) không được
     backend hỗ trợ — TSCĐCreate luôn khởi tạo hao_mon_luy_ke = 0.
   - Sửa (`PUT /api/tai-san/<id>`) chặn đổi nguyên giá/thời gian khấu hao khi đã có log
     khấu hao (409) — khoá các ô tương ứng khi `so_thang_da_kh > 0` (đếm log thật, không
     phải input tay như bản thiết kế).
   - Thanh lý (`POST /api/tai-san/<id>/thanh-ly`) chỉ nhận MỘT số tiền thực nhận
     (`gia_thanh_ly`) — không tách VAT đầu ra / chi phí thanh lý riêng như thiết kế gốc;
     2 ô đó bị ẩn. `tai_khoan_id` cũng lấy từ GET /api/tai-khoan (để trống = không nhận
     tiền — thanh lý 0 đồng / cho tặng).
   QA 25/09 (so với form cũ /app#tscd) — đã sửa:
   - Nhóm tài sản là CHỮ TỰ DO trong CSDL ("Xe vận chuyển"…) nhưng form để select 4 mã cố định → mở sửa
     tài sản thật thì select rỗng và PUT ghi đè nhom = '' → đổi thành ô chữ + gợi ý từ các nhóm đang có.
   - `loai` luôn gửi 'huu_hinh' (sửa 1 TSCĐ vô hình sẽ đổi sang 211) → thêm ô Loại. `ngay_mua` luôn = ngày
     dùng (sửa sẽ ghi đè ngày mua thật) → thêm ô Ngày mua. Thêm chi phí lắp đặt, ghi chú, NCC khi sửa.
   - Sửa tài sản đã khấu hao: PUT luôn gửi nguyen_gia/so_thang_kh → máy chủ trả 409, không sửa được gì
     (cả tên, bộ phận) → khi đã khoá thì KHÔNG gửi các trường số đó.
*/
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-tscd-phieu')) return;
  const $ = (id) => document.getElementById(id);
  const u = KT.url.doc(), cheDo = u.id ? (u.che_do === 'thanh_ly' ? 'thanh_ly' : 'sua') : 'moi';
  const docSo = (el) => Number(String(el.value || '').replace(/[^\d]/g, '')) || 0;
  const pill = (mau, nhan) => '<span class="pill pill--' + mau + '">' + esc(nhan) + '</span>';
  const BO_PHAN = [['ban_hang', 'Bán hàng', '641'], ['quan_ly', 'Quản lý', '642'], ['tai_chinh', 'Tài chính', '635'], ['khac', 'Khác', '811']];
  const timBoPhan = (ma) => BO_PHAN.find((b) => b[0] === ma) || null;
  let khoaSo = false;
  const homNay = () => KD.iso(new Date());
  let ts = null, taiKhoanDs = null;

  async function napTaiKhoan() {
    if (taiKhoanDs) return taiKhoanDs;
    try { taiKhoanDs = (await KD.api('/api/tai-khoan')).filter((t) => t.active); } catch (e) { taiKhoanDs = []; }
    return taiKhoanDs;
  }
  function veChonTk(sel, ds, chon) {
    const giu = sel.querySelector('option[value=""]');
    sel.innerHTML = (giu ? giu.outerHTML : '') + ds.map((t) => '<option value="' + t.id + '">' + esc(t.ten_tk + (t.so_tk ? ' — ' + t.so_tk : '') + (t.loai === 'tien_mat' ? ' (tiền mặt)' : '')) + '</option>').join('');
    sel.value = chon ? String(chon) : '';
  }

  async function tai() {
    $('tp-tt').innerHTML = KD.KHUNG_TAI; $('tp-than').hidden = true; $('tp-thanh').hidden = true;
    try {
      const [tkDs] = await Promise.all([napTaiKhoan(), u.id ? KD.api('/api/tai-san/' + encodeURIComponent(u.id)).then((r) => { ts = r; }) : Promise.resolve(),
        KD.api('/api/tai-san/summary?only_active=false').then((sm) => { $('tp-nhom-dl').innerHTML = (sm.by_nhom || []).filter((x) => x.key).map((x) => '<option value="' + esc(x.key) + '">').join(''); }).catch(() => {})]);
      veChonTk($('tp-tk-du'), tkDs); veChonTk($('tp-tl-tk'), tkDs);
      $('tp-tt').innerHTML = ''; $('tp-than').hidden = false; $('tp-thanh').hidden = false; dung();
    } catch (e) { $('tp-ma').textContent = '—'; KD.khoiLoi($('tp-tt'), u.id ? 'Không tải được tài sản' : 'Không mở được phiếu ghi tăng', e, tai); }
  }

  function dung() {
    const tl = cheDo === 'thanh_ly', sua = cheDo === 'sua';
    $('tp-h1').textContent = tl ? 'Thanh lý tài sản cố định' : sua ? 'Sửa tài sản cố định' : 'Ghi tăng tài sản cố định';
    $('tp-crumb').textContent = tl || sua ? ts.ma_tscd : 'Ghi tăng tài sản';
    $('tp-ico').className = 'ico-tile ico-tile--lg' + (tl ? ' ico-tile--danger' : ''); $('tp-ico').innerHTML = '<i class="bi ' + (tl ? 'bi-box-arrow-right' : sua ? 'bi-pencil-square' : 'bi-building-add') + '"></i>';
    $('tp-ma').textContent = ts ? ts.ma_tscd + ' · ' + ts.ten_tscd : 'Mã tự sinh khi lưu';
    $('tp-pill').innerHTML = ts ? (ts.trang_thai === 'da_thanh_ly' ? pill('muted', 'Đã thanh lý') : (ts.so_thang_da_kh || 0) >= ts.so_thang_kh ? pill('info', 'Đã khấu hao hết') : pill('success', 'Đang khấu hao')) : pill('muted', 'Chưa ghi sổ');
    $('tp-meta').innerHTML = ts ? '<span>Nguyên giá: <b>' + KD.tienVnd(ts.nguyen_gia) + '</b></span><span>Hao mòn luỹ kế: <b>' + KD.tienVnd(ts.hao_mon_luy_ke) + '</b></span><span>Còn lại: <b>' + KD.tienVnd(ts.gia_tri_con_lai) + '</b></span>'
      : '';
    if (tl) $('tp-h-kh').textContent = 'Giá trị tài sản';
    $('tp-the-gt').hidden = !!ts; $('tp-the-tl').hidden = !tl; $('tp-the-tt').hidden = tl;
    $('tp-luu-chu').textContent = tl ? 'Ghi sổ thanh lý' : sua ? 'Lưu thay đổi' : 'Ghi tăng tài sản';
    if (ts) {
      $('tp-ten').value = ts.ten_tscd; $('tp-nhom').value = ts.nhom || ''; $('tp-loai').value = ts.loai || 'huu_hinh'; $('tp-bp').value = ts.bo_phan || 'quan_ly';
      $('tp-ncc').value = ts.ncc || ''; $('tp-ngay-mua').value = ts.ngay_mua || ts.ngay_su_dung; $('tp-ngay').value = ts.ngay_su_dung; $('tp-gc').value = ts.ghi_chu || '';
      $('tp-ng').value = KD.tien(ts.nguyen_gia); $('tp-cpld').value = +ts.chi_phi_lap_dat ? KD.tien(ts.chi_phi_lap_dat) : ''; $('tp-thang').value = ts.so_thang_kh;
      $('tp-thang-da-o').hidden = false; $('tp-thang-da').value = String(ts.so_thang_da_kh || 0);
      khoaSo = (ts.so_thang_da_kh || 0) > 0;   // đã trích khấu hao (log thật) → khoá số làm thay đổi khấu hao đã ghi
      ['tp-ng', 'tp-cpld', 'tp-thang', 'tp-ngay'].forEach((id) => { $(id).disabled = khoaSo; });
      if (khoaSo) { $('tp-ng-gy').innerHTML = 'Đã trích ' + KD.soDem(ts.so_thang_da_kh) + ' tháng — khoá sửa' + KD.tip('Không sửa nguyên giá, thời gian khấu hao ở đây. Đánh giá lại hoặc nâng cấp thì lập chứng từ điều chỉnh.'); $('tp-ng-gy').hidden = false; }
      $('tp-tl-ngay').value = homNay();
    } else {
      $('tp-ngay').value = homNay(); $('tp-ngay-mua').value = homNay();
    }
    veTkCp(); veLq(); ve();
  }
  function veTkCp() {
    const b = timBoPhan($('tp-bp').value) || BO_PHAN.find((x) => x[0] === 'quan_ly');
    $('tp-tk-cp').value = b[2] + ' — CP ' + b[1].toLowerCase();
    $('tp-tk-ng').value = $('tp-loai').value === 'vo_hinh' ? '213 — TSCĐ vô hình' : '211 — TSCĐ hữu hình';
  }
  $('tp-bp').addEventListener('change', () => { veTkCp(); ve(); });
  $('tp-loai').addEventListener('change', () => { veTkCp(); ve(); });
  $('tp-ngay-mua').addEventListener('change', () => { if (!ts && (!$('tp-ngay').value || $('tp-ngay').value < $('tp-ngay-mua').value)) $('tp-ngay').value = $('tp-ngay-mua').value; ve(); });
  $('tp-cpld').addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; });
  ['tp-ng', 'tp-vat'].forEach((id) => $(id) && $(id).addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; ve(); }));
  ['tp-thang', 'tp-ngay', 'tp-ghi', 'tp-tk-du'].forEach((id) => $(id).addEventListener('input', ve));
  ['tp-tl-ban'].forEach((id) => $(id).addEventListener('input', (e) => { const n = docSo(e.target); e.target.value = n ? KD.tien(n) : ''; ve(); }));
  $('tp-tl-tk').addEventListener('change', ve);

  /* ── Tính khấu hao + định khoản xem trước ── */
  function ve() {
    const dong = (tk, nd, no, co) => '<tr><td><span class="kt-tk">' + esc(tk || '—') + '</span></td><td>' + esc(nd) + '</td><td class="num">' + KT.tienSo(no) + '</td><td class="num">' + KT.tienSo(co) + '</td></tr>';
    if (cheDo === 'thanh_ly') {
      const thu = docSo($('tp-tl-ban')), tkTen = $('tp-tl-tk').selectedOptions[0] ? $('tp-tl-tk').selectedOptions[0].textContent : '—';
      const conLai = ts.gia_tri_con_lai;
      let h = ts.hao_mon_luy_ke > 0 ? dong('214', 'Xoá hao mòn luỹ kế', ts.hao_mon_luy_ke, 0) : '';
      if (thu > 0) h += dong($('tp-tl-tk').value ? tkTen : '111/112', 'Thu thanh lý', thu, 0);
      h += dong(ts.account_code || '211', 'Xoá nguyên giá', 0, ts.nguyen_gia);
      const laiLo = thu - conLai;
      if (laiLo > 0) h += dong('711', 'Lãi thanh lý', 0, laiLo); else if (laiLo < 0) h += dong('811', 'Lỗ thanh lý', -laiLo, 0);
      $('tp-dk').innerHTML = h;
      $('tp-dk-gy').innerHTML = 'Lãi/lỗ thanh lý: ' + (laiLo >= 0 ? '+' : '−') + KD.tienVnd(Math.abs(laiLo)) + KD.tip('Tiền thực nhận − giá trị còn lại', 'kd-tip--trai');
      $('tp-kh').innerHTML = kv([['Nguyên giá', KD.tienVnd(ts.nguyen_gia)], ['Hao mòn luỹ kế', KD.tienVnd(ts.hao_mon_luy_ke)], ['Giá trị còn lại', KD.tienVnd(conLai), true], ['Kết quả thanh lý', '<span class="' + (laiLo >= 0 ? 'kt-so--tot' : 'kt-so--xau') + '">' + (laiLo >= 0 ? 'Lãi ' : 'Lỗ ') + KD.tienVnd(Math.abs(laiLo)) + '</span>', true]])
        + '<p class="kd-meta">Sau khi ghi sổ, tài sản thôi trích khấu hao.</p>';
      return;
    }
    const ng = docSo($('tp-ng')), th = +$('tp-thang').value || 0, da = ts ? (ts.so_thang_da_kh || 0) : 0;
    const con = Math.max(0, th - da), kh = th ? Math.round(ng / th) : 0, bd = $('tp-ngay').value;
    const ketThuc = bd && th ? (() => { const d = new Date(bd.slice(0, 7) + '-01T00:00:00'); d.setMonth(d.getMonth() + th - 1); return KD.iso(d).slice(0, 7); })() : '';   // tháng cuối = tháng bắt đầu + tổng số tháng − 1
    const b = timBoPhan($('tp-bp').value) || BO_PHAN.find((x) => x[0] === 'quan_ly');
    $('tp-kh').innerHTML = ng ? kv([['Giá trị cần khấu hao', KD.tienVnd(ng)], ['Số tháng còn lại', KD.soDem(con) + ' tháng'], ['Mức khấu hao mỗi tháng', KD.tienVnd(kh), true],
      ['Bắt đầu trích', bd ? bd.slice(5, 7) + '/' + bd.slice(0, 4) : '—'], ['Trích xong', ketThuc ? ketThuc.slice(5) + '/' + ketThuc.slice(0, 4) : '—'], ['Hạch toán hằng tháng', 'Nợ ' + b[2] + ' / Có 214']])
      + (ng && ng < 30e6 ? '<p class="kt-o-tk__canh">Nguyên giá dưới 30 triệu — thường hạch toán công cụ dụng cụ, phân bổ qua TK 242.</p>' : '')
      : KD.khoiRong('Nhập nguyên giá và thời gian', 'Mức khấu hao tháng sẽ tính ở đây.');
    if (ts) { $('tp-dk').innerHTML = '<tr><td colspan="4" class="kd-muted">Sửa thông tin không tạo bút toán.</td></tr>'; $('tp-dk-gy').textContent = ''; return; }
    if (!$('tp-ghi').checked) { $('tp-dk').innerHTML = '<tr><td colspan="4" class="kd-muted">Không ghi bút toán — chỉ thêm tài sản vào danh sách để trích khấu hao.</td></tr>'; $('tp-dk-gy').textContent = ''; return; }
    const tkChon = $('tp-tk-du').selectedOptions[0] && $('tp-tk-du').value ? $('tp-tk-du').selectedOptions[0].textContent : '(chưa chọn tài khoản)';
    $('tp-dk').innerHTML = dong($('tp-loai').value === 'vo_hinh' ? '213' : '211', 'Nguyên giá tài sản', ng, 0) + dong(tkChon, 'Chi tiền mua tài sản', 0, ng);
    $('tp-dk-gy').innerHTML = KD.tip('Ngày hạch toán = ngày đưa vào sử dụng.', 'kd-tip--trai');
  }
  const kv = (ds) => '<dl class="kt-tq">' + ds.map(([t, v, d]) => '<dt' + (d ? ' class="is-dam"' : '') + '>' + esc(t) + '</dt><dd>' + v + '</dd>').join('') + '</dl>';
  function veLq() {
    const o = [['/ketoan/tscd', 'bi-list-ul', 'Danh sách tài sản cố định', '']];
    if (ts) o.unshift(['/ketoan/tscd/chi-tiet?id=' + ts.id, 'bi-eye', 'Chi tiết tài sản này', 'Lịch khấu hao đầy đủ']);
    if (ts && cheDo !== 'thanh_ly' && ts.trang_thai !== 'da_thanh_ly') o.push(['/ketoan/tscd/phieu?id=' + ts.id + '&che_do=thanh_ly', 'bi-box-arrow-right', 'Thanh lý tài sản này', 'Ghi giảm, xoá hao mòn, ghi lãi/lỗ']);
    $('tp-lq').innerHTML = o.map((x) => '<li><a href="' + x[0] + '"><i class="bi ' + x[1] + '" aria-hidden="true"></i><span class="kd-related__ten">' + esc(x[2]) + '</span>' + (x[3] ? '<span class="kd-related__sub">' + esc(x[3]) + '</span>' : '') + '</a></li>').join('');
  }

  /* ── Lưu ── */
  const baoLoi = (m) => { $('tp-loi').textContent = m; $('tp-loi').hidden = !m; };
  $('tp-luu').addEventListener('click', async () => {
    baoLoi('');
    let url, body, opts;
    if (cheDo === 'thanh_ly') {
      body = { ngay_thanh_ly: $('tp-tl-ngay').value, gia_thanh_ly: docSo($('tp-tl-ban')), tai_khoan_id: $('tp-tl-tk').value ? +$('tp-tl-tk').value : null, ghi_chu: $('tp-tl-ly').value.trim() || null };
      if (!body.ngay_thanh_ly) { $('tp-tl-ngay').focus(); return baoLoi('Chọn ngày thanh lý.'); }
      url = '/api/tai-san/' + ts.id + '/thanh-ly'; opts = KD.JSON_POST(body);
    } else {
      if (!$('tp-ten').value.trim()) { $('tp-ten').focus(); return baoLoi('Nhập tên tài sản.'); }
      const bp = timBoPhan($('tp-bp').value);
      if (!bp) { $('tp-bp').focus(); return baoLoi('Chọn bộ phận sử dụng.'); }
      if (!khoaSo && !docSo($('tp-ng'))) { $('tp-ng').focus(); return baoLoi('Nhập nguyên giá lớn hơn 0.'); }
      if (!khoaSo && docSo($('tp-cpld')) > docSo($('tp-ng'))) { $('tp-cpld').focus(); return baoLoi('Chi phí lắp đặt không được lớn hơn nguyên giá.'); }
      if (!$('tp-thang').value || +$('tp-thang').value < 1) { $('tp-thang').focus(); return baoLoi('Nhập thời gian khấu hao (tháng).'); }
      if (!$('tp-ngay-mua').value || !$('tp-ngay').value) { $('tp-ngay-mua').focus(); return baoLoi('Nhập ngày mua và ngày đưa vào sử dụng.'); }
      if ($('tp-ngay').value < $('tp-ngay-mua').value) { $('tp-ngay').focus(); return baoLoi('Ngày đưa vào sử dụng không được trước ngày mua.'); }
      const ghiSo = !ts && $('tp-ghi').checked;
      if (ghiSo && !$('tp-tk-du').value) { $('tp-tk-du').focus(); return baoLoi('Chọn tài khoản chi tiền mua tài sản, hoặc bỏ tick "Ghi luôn bút toán".'); }
      body = { ten_tscd: $('tp-ten').value.trim(), loai: $('tp-loai').value, nhom: $('tp-nhom').value.trim() || null, ngay_mua: $('tp-ngay-mua').value,
        bo_phan: bp[0], ncc: $('tp-ncc').value.trim() || null, ghi_chu: $('tp-gc').value.trim() || null };
      // Đã khấu hao: máy chủ trả 409 nếu PUT có nguyen_gia/so_thang_kh — chỉ gửi khi còn được sửa.
      if (!khoaSo) Object.assign(body, { ngay_su_dung: $('tp-ngay').value, nguyen_gia: docSo($('tp-ng')), chi_phi_lap_dat: docSo($('tp-cpld')), so_thang_kh: +$('tp-thang').value || 0 });
      if (!ts) body.tai_khoan_id = ghiSo ? +$('tp-tk-du').value : null;
      url = ts ? '/api/tai-san/' + ts.id : '/api/tai-san'; opts = ts ? Object.assign(KD.JSON_POST(body), { method: 'PUT' }) : KD.JSON_POST(body);
    }
    const nut = $('tp-luu'); nut.disabled = true;
    try {
      const r = await KD.api(url, opts);
      window.showToast && window.showToast('ok', cheDo === 'thanh_ly' ? 'Đã ghi sổ thanh lý ' + ts.ma_tscd : (ts ? 'Đã lưu ' : 'Đã ghi tăng ') + r.ma_tscd + ' — ' + (r.ten_tscd || ''));
      try { location.href = '/ketoan/tscd/chi-tiet?id=' + (r.id || r.tscd_id || (ts && ts.id)); } catch (x) { /* khung xem trước */ }
    } catch (e) { baoLoi('Chưa lưu được: ' + e.message); } finally { nut.disabled = false; }
  });
  tai();
})();
