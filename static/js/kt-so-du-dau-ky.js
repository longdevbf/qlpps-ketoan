/* kt-so-du-dau-ky.js — Số dư đầu kỳ: nhập dư Nợ/Có từng tài khoản chi tiết + chi tiết công nợ 131/331/141 theo đối tượng.
   Kiểm trước khi lưu: tổng Nợ = tổng Có, mỗi tài khoản một bên, chi tiết đối tượng khớp số dư tài khoản. Khoá khi sổ đã khoá qua ngày số dư
   hoặc người xem không có quyền sửa (quyen_sua=false — chỉ CEO/admin). API thật: /api/so-du-dau-ky-gl (app/routers/so_du_dau_ky_gl.py).
   131 có hàng chục nghìn khách nên không liệt kê sẵn: thêm từng khách qua ô "Thêm đối tượng" (GET /api/so-du-dau-ky-gl/doi-tuong).
   Tiền nhập theo TK con của từng tài khoản tiền (cap=2, tk_cha=111/112 — danh sách do API trả); TK cha chỉ còn khi bản đã lưu
   có số ghi thẳng nó. Mỗi dòng chỉ mang số của đúng mã đó nên tổng Nợ/Có cộng mọi dòng không trùng. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-so-du')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TC = { no: 'Dư Nợ', co: 'Dư Có', luong_tinh: 'Lưỡng tính' };
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const sao = (x) => JSON.parse(JSON.stringify(x));
  const API = '/api/so-du-dau-ky-gl', TEN_DT = { 131: 'khách hàng', 331: 'nhà cung cấp', 141: 'nhân viên' };
  const TK_TIEN = ['111', '112'], laTkTien = (x) => TK_TIEN.includes(x.tk_cha || x.tk);   // gồm cả TK con 1111, 1121…
  let goc = null, dang = null, tkDt = '131', khoa = true, quyen = false;   // quyen = d.quyen_sua (require_ceo_thuchi của PUT)

  /* Bộ lọc + tab trên URL (?tab=dt&tk=331&tim=&loai=&co_so=1) — F5 / gửi link mở lại đúng chỗ đang xem. */
  const u0 = KT.url.doc();
  let tabDang = u0.tab === 'dt' ? 'dt' : 'tk';
  if (['131', '331', '141'].includes(u0.tk)) tkDt = u0.tk;
  $('sd-dt-tk').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tk === tkDt)));
  $('sd-tim').value = u0.tim || ''; $('sd-loai').value = u0.loai || ''; if ($('sd-loai').value !== (u0.loai || '')) $('sd-loai').value = '';
  $('sd-co-so').checked = u0.co_so === '1';
  function ghiUrl() {
    try { KT.url.ghi({ tab: tabDang, tk: tkDt, tim: $('sd-tim').value.trim(), loai: $('sd-loai').value, co_so: $('sd-co-so').checked ? '1' : '' }, { tab: 'tk', tk: '131' }); } catch (e) { /* khung xem */ }
  }
  function datLaiLoc() { $('sd-tim').value = ''; $('sd-loai').value = ''; $('sd-co-so').checked = false; veTk(); }

  const tabs = KD.ganTab($('sd-tabs'), (k) => { tabDang = k; ghiUrl(); if (dang) veDt(); });   // tab chi tiết đọc số dư TK vừa gõ ở tab kia
  const tong = () => ({ no: dang.tai_khoan.reduce((a, x) => a + x.du_no, 0), co: dang.tai_khoan.reduce((a, x) => a + x.du_co, 0) });
  const soDuTk = (tk) => dang.tai_khoan.filter((x) => x.tk.indexOf(tk) === 0).reduce((a, x) => a + x.du_no - x.du_co, 0);
  const soDuDt = (tk) => dang.doi_tuong.filter((x) => x.tk === tk).reduce((a, x) => a + x.du_no - x.du_co, 0);
  const oSo = (v, ben, i, nhan) => (khoa ? (v ? KD.tien(v) : KT.tienSo(0)) : '<input class="kd-input kt-sd-so" data-ben="' + ben + '" data-i="' + i + '" inputmode="numeric" value="' + (v ? KD.tien(v) : '') + '" placeholder="0" aria-label="' + esc(nhan) + '">');
  function veKpi() {
    const t = tong(), l = t.no - t.co, dat = (k, v, phu) => { const el = document.querySelector('#sd-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-phu]').innerHTML = phu || ''; };
    dat('no', H.tienKpi(t.no), KD.soDem(dang.tai_khoan.filter((x) => x.du_no).length) + ' tài khoản'); dat('co', H.tienKpi(t.co), KD.soDem(dang.tai_khoan.filter((x) => x.du_co).length) + ' tài khoản');
    dat('lech', H.tienKpi(Math.abs(l)), l ? H.pill('danger', l > 0 ? 'Nợ lớn hơn Có' : 'Có lớn hơn Nợ') : H.pill('success', 'Đã cân'));
    dat('ngay', '<span>' + KD.ngay(dang.ngay) + '</span>', khoa ? H.pill('muted', 'Đã khoá — chỉ xem') : H.pill('info', 'Đang mở để nhập'));
    const lech = ['131', '331', '141'].filter((k) => dang.doi_tuong.some((x) => x.tk === k && (x.du_no || x.du_co)) && soDuDt(k) !== soDuTk(k));
    // Đợt 4: hướng dẫn nhập đã chuyển vào ⓘ ở tiêu đề; dòng này chỉ hiện khi có cảnh báo lệch.
    $('sd-pham-vi').innerHTML = lech.length ? H.pill('danger', 'Chi tiết đối tượng TK ' + lech.join(', ') + ' chưa khớp số dư tài khoản') : '';
    $('sd-pham-vi').hidden = !lech.length;
    $('sd-dem-dt').textContent = lech.length ? '(' + KD.soDem(lech.length) + ' lệch)' : '';
  }
  /* TK tiền (TK con 1111, 1121… và 111/112 nếu còn): đối chiếu với tồn Sổ quỹ + mốc "Chốt số dư đầu kỳ" của đúng tài khoản đó
     tại cùng ngày (so_quy) — nhập khớp để bảng cân đối (lấy tiền từ sổ quỹ) và sổ cái/cân đối phát sinh (lấy từ journal) không vênh nhau. */
  function oSoQuy(x, i) {
    if (!laTkTien(x)) return '';
    const t = dang.tien_so_quy || {};
    if (x.so_quy == null) return '<span class="kd-muted">Sổ quỹ: chưa có mốc</span>' + KD.tip('Sổ quỹ chỉ có số từ mốc chốt số dư đầu kỳ sớm nhất' + (t.moc_som_nhat ? ' (' + KD.ngay(t.moc_som_nhat) + ')' : '') + ', sau ngày số dư này.', 'kd-tip--trai');
    const khop = x.du_no - x.du_co === x.so_quy;
    return '<span class="kt-sd-sq">Sổ quỹ: ' + KD.tien(x.so_quy) + ' ' + (khop ? H.pill('success', 'Khớp') : H.pill('warning', 'Khác')) + (!khop && !khoa ? ' <button type="button" class="kd-link" data-sq="' + i + '">Dùng số này</button>' : '') + '</span>';
  }
  function veTk() {
    const t = ($('sd-tim').value || '').trim(), loai = $('sd-loai').value, coSo = $('sd-co-so').checked;
    ghiUrl();
    const ds = dang.tai_khoan.map((x, i) => [x, i]).filter(([x]) => KT.khopTim([x.tk, x.ten], t) && (!loai || String(x.loai) === loai) && (!coSo || x.du_no || x.du_co));
    if (!ds.length) {
      $('sd-cuon').hidden = true;
      $('sd-tt-bang').innerHTML = KD.khoiRong('Không có tài khoản nào khớp bộ lọc', coSo ? 'Bỏ tích "Chỉ tài khoản có số dư" để nhập cho tài khoản mới.' : 'Thử bỏ bớt điều kiện lọc.')
        + '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>';
      $('sd-tt-bang').querySelector('[data-dat-lai]').addEventListener('click', datLaiLoc);
      return;
    }
    $('sd-cuon').hidden = false; $('sd-tt-bang').innerHTML = '';
    // TK con: mã 4 chữ số; chỉ thụt lề khi TK cha cũng hiện (bản đã lưu còn số ghi thẳng 111/112) — dòng cha đó kèm ⓘ nhắc chuyển.
    const coMa = new Set(dang.tai_khoan.map((x) => x.tk)), laCha = new Set(dang.tai_khoan.map((x) => x.tk_cha).filter(Boolean));
    const tenTk = (x) => '<span class="kt-tk">' + esc(x.tk) + '</span> ' + esc(x.ten);
    $('sd-tbody').innerHTML = ds.map(([x, i]) => { const g = goc.tai_khoan[i], sua = g.du_no !== x.du_no || g.du_co !== x.du_co;
      return '<tr' + (sua ? ' class="is-sua"' : '') + '><th scope="row">' + (x.tk_cha && coMa.has(x.tk_cha) ? '<span class="kt-cap-2">' + tenTk(x) + '</span>' : tenTk(x))
        + (laCha.has(x.tk) ? KD.tip('Số cũ ghi thẳng TK ' + x.tk + ' — nên chuyển sang các TK con bên dưới.') : '') + '</th><td>' + esc(TC[x.tinh_chat] || '—') + '</td>'
        + '<td class="num">' + oSo(x.du_no, 'du_no', i, 'Dư Nợ TK ' + x.tk) + '</td><td class="num">' + oSo(x.du_co, 'du_co', i, 'Dư Có TK ' + x.tk) + '</td>'
        + '<td>' + (x.doi_tuong ? (() => { const n = dang.doi_tuong.filter((d) => d.tk === x.doi_tuong && (d.du_no || d.du_co)).length, lech = n && soDuDt(x.doi_tuong) !== soDuTk(x.doi_tuong);
          return '<button type="button" class="kd-link" data-dt="' + x.doi_tuong + '">' + (n ? KD.soDem(n) + ' đối tượng' : 'Nhập chi tiết') + '</button> ' + (x.du_no || x.du_co || n ? (lech || (!n && (x.du_no || x.du_co)) ? H.pill('danger', 'Chưa khớp') : H.pill('success', 'Khớp')) : ''); })() : oSoQuy(x, i)) + '</td></tr>'; }).join('');
    const tt = tong(); $('sd-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng toàn bộ tài khoản</th><td class="num">' + KD.tien(tt.no) + '</td><td class="num">' + KD.tien(tt.co) + '</td><td>' + (tt.no === tt.co ? H.pill('success', 'Cân') : H.pill('danger', 'Lệch ' + KD.tien(Math.abs(tt.no - tt.co)))) + '</td></tr>';
  }
  function veDt() {
    const ds = dang.doi_tuong.map((x, i) => [x, i]).filter(([x]) => x.tk === tkDt);
    $('sd-dt-tbody').innerHTML = ds.map(([x, i]) => { const g = goc.doi_tuong[i], sua = g.du_no !== x.du_no || g.du_co !== x.du_co;
      return '<tr' + (sua ? ' class="is-sua"' : '') + '><td>' + H.ma(x.ma) + '</td><td>' + esc(x.ten) + '</td><td class="num">' + (khoa ? (x.du_no ? KD.tien(x.du_no) : KT.tienSo(0)) : '<input class="kd-input kt-sd-so" data-dt-ben="du_no" data-i="' + i + '" inputmode="numeric" value="' + (x.du_no ? KD.tien(x.du_no) : '') + '" placeholder="0" aria-label="Dư Nợ ' + esc(x.ten) + '">')
        + '</td><td class="num">' + (khoa ? (x.du_co ? KD.tien(x.du_co) : KT.tienSo(0)) : '<input class="kd-input kt-sd-so" data-dt-ben="du_co" data-i="' + i + '" inputmode="numeric" value="' + (x.du_co ? KD.tien(x.du_co) : '') + '" placeholder="0" aria-label="Dư Có ' + esc(x.ten) + '">') + '</td></tr>'; }).join('');
    if (!ds.length) $('sd-dt-tbody').innerHTML = '<tr><td colspan="4" class="kd-muted">Chưa có ' + TEN_DT[tkDt] + ' nào có số dư đầu kỳ' + (khoa ? '.' : ' — gõ tên vào ô "Thêm đối tượng" để thêm.') + '</td></tr>';
    const sDt = soDuDt(tkDt), sTk = soDuTk(tkDt), n = ds.reduce((a, [x]) => a + x.du_no, 0), c = ds.reduce((a, [x]) => a + x.du_co, 0);
    $('sd-dt-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng chi tiết · số dư TK ' + tkDt + ' là ' + (sTk >= 0 ? 'Nợ ' : 'Có ') + KD.tienVnd(Math.abs(sTk)) + ' ' + (sDt === sTk ? H.pill('success', 'Khớp') : H.pill('danger', 'Lệch ' + KD.tien(Math.abs(sDt - sTk)))) + '</th><td class="num">' + KD.tien(n) + '</td><td class="num">' + KD.tien(c) + '</td></tr>';
  }
  const doi = () => JSON.stringify(goc) !== JSON.stringify(dang);
  function capNhat() {
    const n = dang.tai_khoan.filter((x, i) => x.du_no !== goc.tai_khoan[i].du_no || x.du_co !== goc.tai_khoan[i].du_co).length + dang.doi_tuong.filter((x, i) => x.du_no !== goc.doi_tuong[i].du_no || x.du_co !== goc.doi_tuong[i].du_co).length;
    $('sd-tt-luu').textContent = khoa ? (quyen ? 'Chỉ xem — số dư đã khoá.' : 'Chỉ xem — cần quyền CEO để ghi.') : n ? 'Chưa lưu: ' + KD.soDem(n) + ' dòng thay đổi.' : 'Chưa có thay đổi.';
    $('sd-luu').disabled = khoa || !n; $('sd-huy').disabled = !n; $('sd-loi').hidden = true; veKpi();
    if (dang.tai_khoan.some((x) => x.du_no || x.du_co) && $('sd-tt').querySelector('.kd-state')) $('sd-tt').innerHTML = '';
  }
  function veTatCa() { veTk(); veDt(); capNhat(); }
  // Nhập số: một tài khoản chỉ một bên — gõ bên Nợ thì xoá bên Có và ngược lại
  document.addEventListener('input', (e) => {
    const i = e.target.closest('[data-ben], [data-dt-ben]'); if (!i) return; const n = docSo(i.value); i.value = n ? KD.tien(n) : '';
    const x = i.dataset.ben ? dang.tai_khoan[+i.dataset.i] : dang.doi_tuong[+i.dataset.i], ben = i.dataset.ben || i.dataset.dtBen, kia = ben === 'du_no' ? 'du_co' : 'du_no';
    x[ben] = n; if (n && x[kia]) { x[kia] = 0; const o = i.closest('tr').querySelector('[data-' + (i.dataset.ben ? 'ben' : 'dt-ben') + '="' + kia + '"]'); if (o) o.value = ''; }
    const g = (i.dataset.ben ? goc.tai_khoan : goc.doi_tuong)[+i.dataset.i]; i.closest('tr').classList.toggle('is-sua', g.du_no !== x.du_no || g.du_co !== x.du_co);
    capNhat(); const tt = tong();
    if (i.dataset.ben) $('sd-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng toàn bộ tài khoản</th><td class="num">' + KD.tien(tt.no) + '</td><td class="num">' + KD.tien(tt.co) + '</td><td>' + (tt.no === tt.co ? H.pill('success', 'Cân') : H.pill('danger', 'Lệch ' + KD.tien(Math.abs(tt.no - tt.co)))) + '</td></tr>';
    else { const giu = document.activeElement; const vt = giu.dataset.i + giu.dataset.dtBen; veDt(); const lai = document.querySelector('[data-i="' + giu.dataset.i + '"][data-dt-ben="' + giu.dataset.dtBen + '"]'); if (lai && vt) { lai.focus(); lai.setSelectionRange(lai.value.length, lai.value.length); } }
  });
  $('sd-tbody').addEventListener('focusout', () => setTimeout(() => { if (!$('sd-tbody').contains(document.activeElement)) veTk(); }, 0));
  $('sd-tbody').addEventListener('click', (e) => {
    const q = e.target.closest('[data-sq]');
    if (q) { const x = dang.tai_khoan[+q.dataset.sq]; x.du_no = Math.max(0, x.so_quy); x.du_co = Math.max(0, -x.so_quy); veTk(); capNhat(); return; }
    const b = e.target.closest('[data-dt]'); if (!b) return; chonTkDt(b.dataset.dt); tabs.chon('dt'); });
  function chonTkDt(k) { tkDt = k; $('sd-dt-tk').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.tk === k))); $('sd-dt-tim').value = ''; $('sd-dt-goi-y').innerHTML = ''; ghiUrl(); veDt(); }
  /* Thêm đối tượng (nhất là khách hàng 131) vào bảng chi tiết — chỉ thêm dòng 0 đồng, nhập số rồi Lưu mới ghi. */
  let goiY = [], luotTim = 0;
  const timDt = KD.debounce(async () => {
    const q = $('sd-dt-tim').value.trim(), l = ++luotTim; if (!q) { $('sd-dt-goi-y').innerHTML = ''; return; }
    try { goiY = await KD.api(API + '/doi-tuong?' + new URLSearchParams({ tk: tkDt, q })); if (l !== luotTim) return;
      const co = new Set(dang.doi_tuong.filter((x) => x.tk === tkDt).map((x) => x.id));
      $('sd-dt-goi-y').innerHTML = goiY.length ? '<ul class="kt-sd-goi-y__ds">' + goiY.map((x, i) => '<li><span>' + esc(x.ten) + (x.ma ? ' <span class="kd-muted">' + esc(x.ma) + '</span>' : '') + '</span>'
        + (co.has(x.id) ? '<span class="kd-muted">Đã có trong bảng</span>' : '<button type="button" class="kd-btn kd-btn--sm" data-them="' + i + '"><i class="bi bi-plus-lg" aria-hidden="true"></i>Thêm</button>') + '</li>').join('') + '</ul>'
        : '<p class="kd-muted">Không tìm thấy ' + TEN_DT[tkDt] + ' nào khớp "' + esc(q) + '".</p>';
    } catch (e) { if (l === luotTim) $('sd-dt-goi-y').innerHTML = '<p class="kd-form-err">Không tìm được: ' + esc(e.message) + '</p>'; }
  }, 300);
  $('sd-dt-tim').addEventListener('input', timDt);
  $('sd-dt-goi-y').addEventListener('click', (e) => { const b = e.target.closest('[data-them]'); if (!b) return; const x = goiY[+b.dataset.them];
    if (!dang.doi_tuong.some((d) => d.tk === x.tk && d.id === x.id)) { const dong = { tk: x.tk, id: x.id, ma: x.ma, ten: x.ten, du_no: 0, du_co: 0 }; dang.doi_tuong.unshift(sao(dong)); goc.doi_tuong.unshift(sao(dong)); }
    $('sd-dt-tim').value = ''; $('sd-dt-goi-y').innerHTML = ''; veDt(); capNhat();
    const o = document.querySelector('#sd-dt-tbody [data-i="0"][data-dt-ben="du_no"]'); if (o) o.focus(); });
  $('sd-dt-tk').addEventListener('click', (e) => { const b = e.target.closest('[data-tk]'); if (b) chonTkDt(b.dataset.tk); });
  ['sd-tim', 'sd-loai', 'sd-co-so'].forEach((id) => $(id).addEventListener(id === 'sd-tim' ? 'input' : 'change', KD.debounce(veTk, 150)));
  $('sd-loc').addEventListener('submit', (e) => e.preventDefault());
  $('sd-huy').addEventListener('click', () => { dang = sao(goc); veTatCa(); });
  window.addEventListener('beforeunload', (e) => { if (dang && doi()) { e.preventDefault(); e.returnValue = ''; } });
  $('sd-luu').addEventListener('click', async () => {
    const t = tong(); const loi = (m) => { $('sd-loi').textContent = m; $('sd-loi').hidden = false; };
    if (t.no !== t.co) return loi('Tổng dư Nợ khác tổng dư Có ' + KD.tienVnd(Math.abs(t.no - t.co)) + ' — kiểm lại trước khi lưu.');
    const lech = ['131', '331', '141'].find((k) => dang.doi_tuong.some((x) => x.tk === k && (x.du_no || x.du_co)) && soDuDt(k) !== soDuTk(k));
    if (lech) { chonTkDt(lech); tabs.chon('dt'); return loi('Chi tiết đối tượng TK ' + lech + ' chưa khớp số dư tài khoản.'); }
    const nut = $('sd-luu'); nut.disabled = true;
    try { await KD.api(API, Object.assign(KD.JSON_POST({ tai_khoan: dang.tai_khoan.filter((x) => x.du_no || x.du_co).map((x) => ({ tk: x.tk, du_no: x.du_no, du_co: x.du_co })), doi_tuong: dang.doi_tuong.filter((x) => x.du_no || x.du_co).map((x) => ({ tk: x.tk, id: x.id, du_no: x.du_no, du_co: x.du_co })) }), { method: 'PUT' }));
      window.showToast && window.showToast('ok', 'Đã lưu số dư đầu kỳ ngày ' + KD.ngay(dang.ngay)); goc = sao(dang); await tai(); }
    catch (e) { loi('Chưa lưu được: ' + e.message); nut.disabled = false; }
  });

  async function tai() {
    $('sd-tt').innerHTML = KD.KHUNG_TAI; $('sd-p-tk').hidden = true; $('sd-p-dt').hidden = true; $('sd-thanh').hidden = true;
    document.querySelectorAll('#sd-kpi [data-v]').forEach((x) => { x.innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; });
    try {
      const d = await KD.api(API); goc = d; dang = sao(d); quyen = !!d.quyen_sua; khoa = d.khoa || !quyen;
      $('sd-khoa').hidden = !khoa; $('sd-dt-them').hidden = khoa;
      // F3 28/09: không có quyền ghi (PUT /api/so-du-dau-ky-gl = require_ceo_thuchi) → ẩn hẳn Lưu / Huỷ thay vì để nút khoá.
      $('sd-luu').hidden = !quyen; $('sd-huy').hidden = !quyen;
      $('sd-khoa').innerHTML = '<i class="bi bi-lock" aria-hidden="true"></i> ' + (quyen && d.khoa ? 'Sổ đã khoá đến ' + KD.ngay(d.khoa_den) + ', sau ngày số dư ' + KD.ngay(d.ngay) + ' — số dư đầu kỳ chỉ xem. Muốn sửa phải <a class="kd-link" href="/ketoan/khoa-so">mở khoá sổ</a> lần lượt về trước ngày này (mọi báo cáo đã khoá sẽ thay đổi).'
        : '<b>Chỉ xem — cần quyền CEO để ghi.</b> Chỉ CEO / Admin / Trợ lý CEO được nhập, sửa số dư đầu kỳ.' + (d.khoa ? ' Sổ đang khoá đến ' + KD.ngay(d.khoa_den) + '.' : ''));
      $('sd-tt').innerHTML = ''; $('sd-thanh').hidden = false; tabs.chon(tabDang);   // giữ tab đang xem (URL / sau khi Lưu)
      if (!d.tai_khoan.some((x) => x.du_no || x.du_co)) $('sd-tt').innerHTML = KD.khoiRong('Chưa nhập số dư đầu kỳ', khoa ? (d.khoa ? 'Sổ đã khoá nên không nhập được.' : 'Chờ CEO / admin nhập số dư đầu kỳ.') : 'Nhập số ở bảng dưới rồi bấm "Lưu số dư" — ghi sổ ngày ' + KD.ngay(d.ngay_hach_toan) + '.');
      veTatCa();
    } catch (e) { document.querySelectorAll('#sd-kpi [data-v]').forEach((x) => { x.innerHTML = '<span class="kd-muted">—</span>'; }); KD.khoiLoi($('sd-tt'), 'Không tải được số dư đầu kỳ', e, tai); }
  }
  tai();
})();
