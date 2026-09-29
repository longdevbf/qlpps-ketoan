/* kt-thue-tncn-tndn.js — Thuế TNCN từ lương (tháng) + thuế TNDN tạm tính (quý). API thật: app/routers/thue.py.
   TNCN: số của bảng TNCN HCNS nếu HR đã lập, chưa có thì tạm tính từ bảng lương live bằng cấu hình + hàm tính thuế của HR
   (giảm trừ, biểu lũy tiến, khoán 10% — đều lấy từ máy chủ, trong quy_dinh).
   TNDN: lợi nhuận từ báo cáo KQKD (pl_calculator), thuế suất = hằng số báo cáo KQKD dùng; tạm nộp 4 quý ≥ 80% số quyết toán. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-thue-tn')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const SO_QUY = 12, SO_THANG = 24, nay = new Date();
  const u0 = KT.url.doc();
  /* Quý: 12 quý gần nhất (3 năm); quý trên URL đúng dạng mà ngoài khoảng vẫn thêm vào để mở đúng link. */
  const cacQuy = Array.from({ length: SO_QUY }, (_, i) => { const d = new Date(nay.getFullYear(), nay.getMonth() - 3 * i, 1); return 'Q' + (Math.floor(d.getMonth() / 3) + 1) + '-' + d.getFullYear(); });
  if (/^Q[1-4]-\d{4}$/.test(u0.quy || '') && !cacQuy.includes(u0.quy)) cacQuy.push(u0.quy);
  $('tn-quy').innerHTML = cacQuy.map((q) => '<option value="' + q + '">Quý ' + q[1] + '/' + q.slice(3) + '</option>').join('');
  /* Tháng TNCN: máy chủ trả 12 tháng gần nhất (+ tháng HR đã lập) → cộng thêm 24 tháng gần nhất tại trình duyệt (API nhận mọi tháng hợp lệ). */
  const THANG_URL = /^\d{4}-(0[1-9]|1[0-2])$/.test(u0.thang || '') ? u0.thang : '';
  const cacThang = (tuMay) => { const s = new Set(tuMay || []);
    for (let i = 0; i < SO_THANG; i++) { const d = new Date(nay.getFullYear(), nay.getMonth() - i, 1); s.add(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')); }
    if (THANG_URL) s.add(THANG_URL);
    return [...s].sort().reverse(); };
  let tab = u0.tab === 'tndn' ? 'tndn' : 'tncn', tc = null, td = null, dcDang = [], lTc = 0, lTd = 0;
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4), quyChu = (q) => 'quý ' + q[1] + '/' + q.slice(3);
  const kpiDat = (pfx, k, v, phu) => { const el = document.querySelector('#' + pfx + '-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-phu]').innerHTML = phu || ''; };
  const kpiCho = (pfx, loi) => document.querySelectorAll('#' + pfx + '-kpi [data-v]').forEach((x) => { x.innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; x.parentNode.querySelector('[data-phu]').innerHTML = ''; });
  /* Tháng luôn ghi lên URL (mặc định rỗng): trước đây coi tháng đầu danh sách (tháng hiện hành) là mặc định nên chọn tháng hiện hành
     rồi F5 thì máy chủ trả tháng TRƯỚC (mặc định của API TNCN) — lệch với ô đã chọn. */
  function ghiUrl() { try { KT.url.ghi({ tab, thang: $('tn-thang').value, quy: $('tn-quy').value }, { tab: 'tncn', thang: '', quy: cacQuy[0] }); } catch (e) { /* khung xem trước */ } }
  function nutGhi() {
    const d = tab === 'tncn' ? tc : td, b = $('tn-ghi');
    b.title = '';
    if (!d) { b.disabled = true; $('tn-ghi-chu').textContent = tab === 'tncn' ? 'Ghi sổ thuế TNCN' : 'Ghi sổ tạm nộp TNDN'; return; }
    if (tab === 'tncn') { $('tn-ghi-chu').textContent = (d.so_sach.da_ghi ? 'Đã ghi sổ TNCN tháng ' : d.khoa ? 'Đã khoá sổ tháng ' : 'Ghi sổ TNCN tháng ') + thangChu(d.thang); b.disabled = d.so_sach.da_ghi || d.khoa || !d.tong.thue || !d.ket_thuc;
      if (!d.ket_thuc && !d.so_sach.da_ghi) b.title = 'Tháng chưa kết thúc — lương còn thay đổi'; }
    else { $('tn-ghi-chu').textContent = (d.da_ghi ? 'Đã ghi sổ tạm nộp ' : 'Ghi sổ tạm nộp ') + quyChu(d.quy); b.disabled = d.da_ghi || !d.thue || dcDoi() || !d.ket_thuc;
      if (!d.da_ghi) b.title = !d.ket_thuc ? 'Quý chưa kết thúc — số liệu còn tạm tính' : !d.thue ? 'Quý này không phát sinh thuế TNDN' : ''; }
  }

  /* ═════════ TNCN ═════════ */
  async function taiTncn() {
    const l = ++lTc; tc = null; nutGhi(); kpiCho('tc'); $('tc-pham-vi').textContent = ''; $('tc-pham-vi').hidden = true; $('tc-tip').innerHTML = ''; $('tc-cuon').hidden = false; $('tc-tt').innerHTML = ''; $('tc-tfoot').innerHTML = ''; $('tc-tbody').innerHTML = KT.hangCho(7, 6);
    try {
      const d = await KD.api('/api/thue-tncn?' + KT.url.qs({ thang: $('tn-thang').value })); if (l !== lTc) return; tc = d;
      if ($('tn-thang').options.length === 0 || $('tn-thang').dataset.nap !== '1') { $('tn-thang').dataset.nap = '1'; H.napChon($('tn-thang'), cacThang((d.cac_thang || []).concat([d.thang])).map((m) => [m, 'Tháng ' + thangChu(m)]), '', d.thang); }
      const q = d.quy_dinh, t = d.tong;
      $('tc-qd').innerHTML = 'Giảm trừ bản thân ' + KD.tien(q.giam_tru_ban_than) + ' · mỗi người phụ thuộc ' + KD.tien(q.giam_tru_npt)
        + KD.tip('Biểu lũy tiến ' + KD.soDem(q.bieu.length) + ' bậc: ' + q.bieu.map(([den, ts], i) => (den == null ? 'trên ' + KD.tienGon(q.bieu[i - 1][0]) : 'đến ' + KD.tienGon(den)) + ' ' + ts + '%').join(', ')
          + '. Hợp đồng ngoài ' + q.loai_hd_luy_tien.join('/') + ' khấu trừ ' + q.flat_pct + '% khi thu nhập từ ' + KD.tienGon(q.flat_min) + '. ' + q.can_cu + '.');
      kpiDat('tc', 'tn', H.tienKpi(t.tong_thu_nhap), KD.soDem(t.so_nv) + ' nhân viên · trừ bảo hiểm ' + KD.tienGon(t.bh));
      kpiDat('tc', 'nguoi', H.dem(t.so_nv_nop, 'người'), 'Còn ' + KD.soDem(t.so_nv - t.so_nv_nop) + ' người dưới mức giảm trừ');
      kpiDat('tc', 'thue', H.tienKpi(t.thue), d.so_sach.da_ghi ? H.pill('success', 'Đã ghi sổ ' + d.so_sach.but_toan.so_ct) : t.thue ? H.pill('warning', 'Chưa ghi Nợ 334 / Có 3335') : '');
      kpiDat('tc', 'han', '<span>' + KD.ngay(d.han_nop) + '</span>', 'Thuế tháng ' + thangChu(d.thang) + (d.ky_ke_khai === 'quy' ? KD.tip('Đơn vị khai theo quý — hạn nộp theo quý', 'kd-tip--trai') : ''));
      $('tc-tip').innerHTML = KD.tip((d.nguon === 'hr_tncn' ? 'Số lấy từ bảng thuế TNCN HCNS đã lập.'
        : 'Tạm tính từ bảng lương ' + (d.trang_thai_luong === 'da_chot' ? 'đã chốt' : 'chưa chốt') + ' (HCNS chưa lập bảng thuế TNCN).')
        + ' Chưa tách thu nhập miễn thuế (ăn trưa, làm thêm giờ).'
        + (d.so_sach.ps_3335 !== t.thue ? ' Sổ cái TK 3335 tháng này: ' + KD.tienVnd(d.so_sach.ps_3335) + '.' : ' Khớp sổ cái TK 3335.'));
      /* Tháng đã khoá sổ mà chưa ghi thuế → cảnh báo cần xử lý, hiện thành nhãn */
      const canhBao = d.khoa && !d.so_sach.da_ghi && t.thue;
      $('tc-pham-vi').hidden = !canhBao;
      $('tc-pham-vi').innerHTML = canhBao ? H.pill('warning', 'Tháng đã khoá sổ mà chưa ghi thuế TNCN') + KD.tip('Mở khoá sổ tháng này để ghi, hoặc ghi vào tháng đang mở.') : '';
      $('tn-xuat').href = '/api/thue-tncn/xuat?' + KT.url.qs({ thang: d.thang });
      if (!d.dong.length) { $('tc-cuon').hidden = true; $('tc-tt').innerHTML = KD.khoiRong('Tháng ' + thangChu(d.thang) + ' chưa có bảng lương đã chốt', 'Thuế TNCN tính khi HR chốt lương. Chọn tháng khác ở ô phía trên.'); nutGhi(); return; }
      $('tc-tbody').innerHTML = d.dong.map((x) => '<tr><td>' + H.ten(x.ten, x.ma_nv + ' · ' + x.phong_ban) + '</td><td class="num">' + KD.tien(x.tong_thu_nhap) + '</td><td class="num">' + KD.tien(x.bh) + '</td><td class="num">' + KD.tien(x.giam_tru) + (x.so_npt ? '<span class="kt-tn-phu">' + KD.soDem(x.so_npt) + ' người phụ thuộc</span>' : '') + '</td>'
        + '<td class="num">' + KT.tienSo(x.tn_tinh_thue) + '</td><td class="num">' + (x.bac ? KD.soDem(x.bac) : x.thue ? '<span title="Hợp đồng không thuộc diện lũy tiến — khấu trừ ' + d.quy_dinh.flat_pct + '% trên thu nhập">' + d.quy_dinh.flat_pct + '%</span>' : '—') + '</td><td class="num kd-strong">' + KT.tienSo(x.thue) + '</td></tr>').join('');
      $('tc-tfoot').innerHTML = '<tr><th scope="row">Cộng ' + KD.soDem(t.so_nv) + ' nhân viên</th><td class="num">' + KD.tien(t.tong_thu_nhap) + '</td><td class="num">' + KD.tien(t.bh) + '</td><td></td><td class="num">' + KD.tien(t.tn_tinh_thue) + '</td><td></td><td class="num">' + KD.tien(t.thue) + '</td></tr>';
      nutGhi(); ghiUrl();
    } catch (e) { if (l !== lTc) return; kpiCho('tc', true); $('tc-cuon').hidden = true; KD.khoiLoi($('tc-tt'), 'Không tải được bảng thuế TNCN', e, taiTncn); }
  }

  /* ═════════ TNDN ═════════ */
  const dcDoi = () => !!td && JSON.stringify(td.dieu_chinh.map((x) => [x.loai, x.noi_dung, x.so_tien])) !== JSON.stringify(dcDang.map((x) => [x.loai, x.noi_dung, x.so_tien]));
  function veDc() {
    const khoa = td.da_ghi;
    $('td-dc').innerHTML = dcDang.length ? dcDang.map((x, i) => '<tr><td>' + (khoa ? (x.loai === 'tang' ? 'Tăng' : 'Giảm') : '<select class="kd-input kt-tn-loai" data-dc="loai" data-i="' + i + '" aria-label="Loại điều chỉnh"><option value="tang"' + (x.loai === 'tang' ? ' selected' : '') + '>Tăng</option><option value="giam"' + (x.loai === 'giam' ? ' selected' : '') + '>Giảm</option></select>') + '</td>'
      + '<td>' + (khoa ? esc(x.noi_dung) : '<input class="kd-input" data-dc="noi_dung" data-i="' + i + '" value="' + esc(x.noi_dung) + '" maxlength="200" placeholder="Vd: chi phí không có hoá đơn hợp lệ" aria-label="Nội dung điều chỉnh">') + '</td>'
      + '<td class="num">' + (khoa ? KD.tien(x.so_tien) : '<input class="kd-input kt-tn-so" data-dc="so_tien" data-i="' + i + '" inputmode="numeric" value="' + (x.so_tien ? KD.tien(x.so_tien) : '') + '" aria-label="Số tiền điều chỉnh">') + '</td>'
      + '<td>' + (khoa ? '' : '<button type="button" class="kd-icon-btn" data-dc-xoa="' + i + '" aria-label="Xoá khoản điều chỉnh"><i class="bi bi-x-lg" aria-hidden="true"></i></button>') + '</td></tr>').join('')
      : '<tr><td colspan="4" class="kd-muted">Chưa có khoản điều chỉnh — thu nhập tính thuế bằng lợi nhuận kế toán.</td></tr>';
    $('td-dc-them').hidden = khoa; $('td-dc-luu').hidden = khoa; capNhatDc();
  }
  function capNhatDc() { const doi = dcDoi(); $('td-dc-luu').disabled = !doi; $('td-dc-tt').textContent = td.da_ghi ? 'Quý đã ghi sổ — điều chỉnh chỉ xem.' : doi ? 'Có thay đổi chưa lưu — lưu để tính lại thuế.' : '';
    const tang = dcDang.filter((x) => x.loai === 'tang').reduce((a, x) => a + x.so_tien, 0), giam = dcDang.filter((x) => x.loai === 'giam').reduce((a, x) => a + x.so_tien, 0);
    $('td-dc-chan').textContent = 'Lợi nhuận ' + KD.tienVnd(td.loi_nhuan) + ' + tăng ' + KD.tienVnd(tang) + ' − giảm ' + KD.tienVnd(giam) + ' = thu nhập tính thuế ' + KD.tienVnd(Math.max(0, td.loi_nhuan + tang - giam)) + (doi ? ' (chưa lưu)' : '') + '.'; nutGhi(); }
  function veTd(d) {
    const lk = d.luy_ke, can = Math.round(lk.thue_uoc * lk.ty_le_toi_thieu);
    kpiDat('td', 'ln', H.tienKpi(d.loi_nhuan), 'Doanh thu ' + KD.tienGon(d.doanh_thu) + ' − chi phí ' + KD.tienGon(d.chi_phi));
    kpiDat('td', 'tntt', H.tienKpi(d.tn_tinh_thue), 'Điều chỉnh +' + KD.tienGon(d.tang) + ' / −' + KD.tienGon(d.giam));
    kpiDat('td', 'thue', H.tienKpi(d.thue), 'Thuế suất ' + d.thue_suat + '% · hạn ' + KD.ngay(d.han_nop) + (d.da_ghi ? ' · ' + H.pill('success', 'Đã ghi ' + d.but_toan.so_ct) : ''));
    kpiDat('td', 'luy_ke', H.tienKpi(lk.tam_nop), lk.thue_uoc ? (lk.tam_nop >= can ? H.pill('success', 'Đạt 80% ước quyết toán') : H.pill('warning', 'Chưa đạt 80%') + ' cần ≥ ' + KD.tienGon(can))
      : lk.tam_nop ? 'Ước cả năm (số liệu đến nay) không phát sinh thuế' : 'Chưa phát sinh thuế');
    /* Kỳ + trạng thái quý: 1 dòng ngắn; giải thích thuế suất → ⓘ. Chênh thuế suất ưu đãi là việc cần kiểm → nhãn vàng. */
    const lechTs = d.thue_suat_luat != null && d.thue_suat_luat !== d.thue_suat;
    $('td-pham-vi').innerHTML = 'Kỳ ' + KD.ngay(d.khoang.tu) + ' – ' + KD.ngay(d.khoang.den) + ' ' + (d.ket_thuc ? '' : H.pill('warning', 'Quý chưa kết thúc — số tạm tính'))
      + (lechTs ? ' ' + H.pill('warning', 'Kiểm tra thuế suất ưu đãi ' + d.thue_suat_luat + '%') : '')
      + KD.tip('Thuế suất ' + d.thue_suat + '% theo báo cáo kết quả kinh doanh.' + (d.thue_suat_luat == null ? ' Chưa có doanh thu năm ' + (+d.quy.slice(3) - 1) + ' để đối chiếu thuế suất ưu đãi.'
        : lechTs ? ' Doanh thu năm trước ' + KD.tienGon(d.doanh_thu_nam_truoc) + ' thuộc mức ' + d.thue_suat_luat + '% theo Luật Thuế TNDN 2025.' : ''));
    $('td-kq-phu').textContent = 'Tháng ' + d.cac_thang.map(thangChu).join(', ');
    const nhom = (ben, nhan) => '<tr class="kt-tn-nhom"><th scope="rowgroup" colspan="2">' + nhan + '</th></tr>' + d.chi_tiet.filter((x) => x.ben === ben).map((x) => '<tr><td><span class="kt-tk">' + esc(x.tk) + '</span> ' + esc(x.ten) + '</td><td class="num">' + KT.tienSo(x.so_tien) + '</td></tr>').join('');
    $('td-kq').innerHTML = nhom('doanh_thu', 'Doanh thu và thu nhập') + nhom('chi_phi', 'Chi phí');
    $('td-kq-chan').innerHTML = '<tr><th scope="row">Lợi nhuận kế toán trước thuế</th><td class="num ' + (d.loi_nhuan < 0 ? 'kt-so--xau' : '') + '">' + (d.loi_nhuan < 0 ? '−' + KD.tien(-d.loi_nhuan) : KD.tien(d.loi_nhuan)) + '</td></tr>';
    $('td-cq').innerHTML = d.cac_quy.map((c) => '<li class="' + (c.quy === d.quy ? 'is-nay' : '') + '"><span>Quý ' + c.quy[1] + '/' + c.quy.slice(3) + '</span>' + (c.chua_toi ? H.pill('muted', 'Chưa tới') : c.da_ghi ? H.pill('success', 'Đã ghi sổ') : c.qua_han ? H.pill('danger', 'Quá hạn, chưa ghi') : c.thue ? H.pill('warning', 'Chưa ghi sổ') : H.pill('muted', 'Không phát sinh'))
      + '<small>' + (c.thue != null ? 'Tạm tính ' + KD.tienVnd(c.thue) + ' · ' : '') + 'hạn nộp ' + KD.ngay(c.han) + '</small></li>').join('');
    $('td-qd-tip').innerHTML = KD.tip(d.can_cu + '.', 'kd-tip--trai');
    $('td-qd').innerHTML = '<p class="kd-meta">Thuế suất theo doanh thu năm' + KD.tip('Luật Thuế TNDN 2025 — để đối chiếu', 'kd-tip--trai') + '</p><table class="kt-bang-nho kt-tn-bieu"><tbody>'
      + d.bieu.map(([tran, ts], i) => '<tr><td>' + (tran == null ? 'Trên ' + KD.tienGon(d.bieu[i - 1][0]) : (i ? 'Trên ' + KD.tienGon(d.bieu[i - 1][0]) + ' đến ' : 'Đến ') + KD.tienGon(tran)) + '</td><td class="num">' + ts + '%</td></tr>').join('') + '</tbody></table>';
    dcDang = d.dieu_chinh.map((x) => Object.assign({}, x)); veDc();
  }
  async function taiTndn() {
    const l = ++lTd; td = null; nutGhi(); kpiCho('td'); $('td-pham-vi').textContent = ''; $('td-qd-tip').innerHTML = ''; $('td-than').hidden = true; $('td-tt').innerHTML = KD.KHUNG_TAI;
    try { const d = await KD.api('/api/thue-tndn?' + KT.url.qs({ quy: $('tn-quy').value })); if (l !== lTd) return; td = d; $('td-tt').innerHTML = '';
      if (!d.doanh_thu && !d.chi_phi) { kpiCho('td', true); $('td-tt').innerHTML = KD.khoiRong('Quý ' + d.quy[1] + '/' + d.quy.slice(3) + ' chưa có doanh thu, chi phí', 'Chọn quý khác ở ô phía trên.'); nutGhi(); return; }
      $('td-than').hidden = false; veTd(d); ghiUrl(); }
    catch (e) { if (l !== lTd) return; kpiCho('td', true); KD.khoiLoi($('td-tt'), 'Không tải được số liệu thuế TNDN', e, taiTndn); }
  }
  $('td-dc').addEventListener('input', (e) => { const i = e.target.closest('[data-dc]'); if (!i) return; const x = dcDang[+i.dataset.i];
    if (i.dataset.dc === 'so_tien') { const n = Number(i.value.replace(/[^\d]/g, '')) || 0; i.value = n ? KD.tien(n) : ''; x.so_tien = n; } else x[i.dataset.dc] = i.value; capNhatDc(); });
  $('td-dc').addEventListener('change', (e) => { const i = e.target.closest('select[data-dc]'); if (i) { dcDang[+i.dataset.i].loai = i.value; capNhatDc(); } });
  $('td-dc').addEventListener('click', (e) => { const b = e.target.closest('[data-dc-xoa]'); if (b) { dcDang.splice(+b.dataset.dcXoa, 1); veDc(); } });
  $('td-dc-them').addEventListener('click', () => { dcDang.push({ loai: 'tang', noi_dung: '', so_tien: 0 }); veDc(); $('td-dc').querySelector('tr:last-child [data-dc="noi_dung"]').focus(); });
  $('td-dc-luu').addEventListener('click', async () => { const nut = $('td-dc-luu'); nut.disabled = true;
    try { await KD.api('/api/thue-tndn/dieu-chinh', Object.assign(KD.JSON_POST({ quy: td.quy, dong: dcDang.map((x) => ({ loai: x.loai, noi_dung: (x.noi_dung || '').trim(), so_tien: x.so_tien })) }), { method: 'PUT' }));
      window.showToast && window.showToast('ok', 'Đã lưu điều chỉnh — tính lại thuế tạm nộp'); taiTndn(); }
    catch (e) { $('td-dc-tt').textContent = 'Chưa lưu được: ' + e.message; nut.disabled = false; } });

  /* ═════════ Ghi sổ (nút chính dùng chung 2 tab) ═════════ */
  const dlg = $('tn-dlg');
  $('tn-ghi').addEventListener('click', () => {
    const dk = (tk, ten, no, co) => '<tr><td><span class="kt-tk">' + tk + '</span><span class="kt-dk__phu">' + ten + '</span></td><td class="num">' + (no ? KD.tien(no) : KT.tienSo(0)) + '</td><td class="num">' + (co ? KD.tien(co) : KT.tienSo(0)) + '</td></tr>';
    if (tab === 'tncn') { $('tn-dlg-td').textContent = 'Ghi sổ thuế TNCN tháng ' + thangChu(tc.thang) + '?'; $('tn-dlg-nd').textContent = 'Khấu trừ ' + KD.tienVnd(tc.tong.thue) + ' thuế TNCN của ' + KD.soDem(tc.tong.so_nv_nop) + ' nhân viên vào lương phải trả. Mỗi tháng ghi một lần.'; $('tn-dlg-dk').innerHTML = dk('334', 'Phải trả người lao động', tc.tong.thue, 0) + dk('3335', 'Thuế thu nhập cá nhân', 0, tc.tong.thue); }
    else { $('tn-dlg-td').textContent = 'Ghi sổ tạm nộp TNDN ' + quyChu(td.quy) + '?'; $('tn-dlg-nd').textContent = 'Ghi nhận chi phí thuế TNDN tạm tính ' + KD.tienVnd(td.thue) + ' (' + td.thue_suat + '% × ' + KD.tienVnd(td.tn_tinh_thue) + '). Nộp tiền trước ' + KD.ngay(td.han_nop) + ' bằng phiếu chi / báo nợ Nợ 3334.'; $('tn-dlg-dk').innerHTML = dk('8211', 'Chi phí thuế TNDN hiện hành', td.thue, 0) + dk('3334', 'Thuế thu nhập doanh nghiệp', 0, td.thue); }
    KD.moHopThoai(dlg); $('tn-dlg-ok').focus();
  });
  $('tn-dlg-ok').addEventListener('click', async () => { const nut = $('tn-dlg-ok'); nut.disabled = true;
    try { const r = tab === 'tncn' ? await KD.api('/api/thue-tncn/ghi-so', KD.JSON_POST({ thang: tc.thang })) : await KD.api('/api/thue-tndn/ghi-so', KD.JSON_POST({ quy: td.quy }));
      dlg.close(); window.showToast && window.showToast('ok', 'Đã ghi sổ ' + r.so_ct + ' — ' + KD.tienVnd(r.so_tien)); tab === 'tncn' ? taiTncn() : taiTndn(); }
    catch (e) { KD.baoLoiHopThoai(dlg, 'Chưa ghi sổ được: ' + e.message); } finally { nut.disabled = false; } });

  const tabs = KD.ganTab($('tn-tabs'), (k) => { tab = k; $('tn-thang-o').hidden = k !== 'tncn'; $('tn-quy-o').hidden = k !== 'tndn'; $('tn-xuat').hidden = k !== 'tncn'; nutGhi(); ghiUrl();
    if (k === 'tncn' && !tc) taiTncn(); if (k === 'tndn' && !td) taiTndn(); });
  $('tn-thang').addEventListener('change', taiTncn); $('tn-quy').addEventListener('change', taiTndn);
  if (u0.quy && cacQuy.includes(u0.quy)) $('tn-quy').value = u0.quy;
  if (THANG_URL) { $('tn-thang').innerHTML = '<option value="' + esc(THANG_URL) + '">Tháng ' + esc(thangChu(THANG_URL)) + '</option>'; }
  window.addEventListener('beforeunload', (e) => { if (dcDoi()) { e.preventDefault(); e.returnValue = ''; } });
  tabs.chon(tab);
})();
