/* kt-quy.js — Quản lý quỹ nội bộ. Giữ nghiệp vụ màn cũ #page-quan-ly-quy:
   cây quỹ theo tháng (thanh_tien = công thức nguồn, so_du = cộng giao dịch), nạp / chi (không cho chi quá số dư: allow_negative=false),
   lịch sử + huỷ giao dịch, quản trị (can_admin): chỉnh %, thêm / sửa / xoá quỹ (xoá kéo theo quỹ con). Quỹ Công Đoàn đọc từ HCNS — chỉ xem.
   QA 25/09: Quỹ Công Đoàn — API trả thanh_tien = so_du = so_du_luy_ke HCNS (số LUỸ KẾ, không phải số trích tháng) → hiện ở cột
   Số dư, KHÔNG cộng vào "Trích theo công thức"/chân cột Trích tháng (bản trước cộng 7,35tr vào tổng trích tháng dù dòng hiện "—").
   Màn cũ hiện 7,35tr ở cột "Thành tiền tháng" và số dư 0 — sai nghĩa, giữ bản mới.
   Lịch sử giao dịch: thêm dòng Số dư / Tổng nạp / Tổng chi toàn quỹ như màn cũ (API /giao-dich trả sẵn, không theo bộ lọc). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-quy-nb')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const u0 = KT.url.doc();
  let du = null, phang = [], luot = 0, tkNap = null;
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const docPct = (v) => { const s = String(v || '').trim().replace(',', '.'); return s === '' ? NaN : Number(s); };
  const pct = (v) => KD.phanTram(v).replace(/,0%$/, '%');   // 2% · 0,5% (một chữ số lẻ)
  const laHcns = (q) => q.nguon_compute === 'hcns_cong_doan';
  const NGUON = {
    manual: (q) => H.pill('muted', 'Nạp tay'),
    doanh_thu_pct: (q) => H.pill('brand', pct(q.ty_le_pct) + ' doanh thu'),
    parent_pct: (q) => H.pill('info', pct(q.ty_le_pct) + ' quỹ cha'),
    hcns_cong_doan: () => H.pill('warning', 'Từ HCNS'),
  };
  const kpiDat = (k, v, phu, title) => { const el = document.querySelector('#qy-kpi [data-kpi="' + k + '"]'); const o = el.querySelector('[data-v]'); o.innerHTML = v; if (title) o.title = title; else o.removeAttribute('title'); el.querySelector('[data-phu]').innerHTML = phu || ''; };
  const kpiCho = (loi) => document.querySelectorAll('#qy-kpi [data-v]').forEach((x) => { x.innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; x.parentNode.querySelector('[data-phu]').innerHTML = ''; });
  const timQuy = (id) => phang.find((x) => String(x.id) === String(id));

  /* Ô tháng: tháng hiện hành + 36 tháng trước (màn cũ dùng ô tháng chung 36 tháng trước); tháng trên URL ngoài khoảng vẫn được thêm vào. */
  const SO_THANG = 37;
  (function napThang() { const h = new Date(), ds = [];
    for (let i = 0; i < SO_THANG; i++) { const m = KD.iso(new Date(h.getFullYear(), h.getMonth() - i, 1)).slice(0, 7); ds.push([m, 'Tháng ' + thangChu(m)]); }
    const chon = u0.thang && /^\d{4}-\d{2}$/.test(u0.thang) ? u0.thang : ds[0][0]; if (!ds.some((x) => x[0] === chon)) ds.push([chon, 'Tháng ' + thangChu(chon)]);
    H.napChon($('qy-thang'), ds, '', chon); })();

  /* Số trích có số lẻ (vd 14.553.446,56) → làm tròn riêng từng quỹ con thì tổng các quỹ con lệch quỹ cha 1đ
     (QA nhất quán 25/09, T08/2026: 9.896.344 + 3.201.758 + 727.672 + 727.672 = 14.553.446 ≠ cha 14.553.447).
     Làm tròn quỹ gốc; nhóm quỹ con chia đủ 100% thì phân phần dư theo phần lẻ lớn nhất để cộng đúng bằng cha. */
  function lamTronTrich(ds, cha) {
    ds.forEach((x) => { x.thanh_tien = Math.round(+x.thanh_tien || 0); });
    const con = ds.filter((x) => x.nguon_compute === 'parent_pct');
    if (cha && con.length && Math.abs(con.reduce((a, x) => a + (+x.ty_le_pct || 0), 0) - 100) < 0.001) {
      const that = con.map((x) => (+cha.thanh_tien || 0) * (+x.ty_le_pct || 0) / 100), san = that.map(Math.floor);
      let du2 = (+cha.thanh_tien || 0) - san.reduce((a, v) => a + v, 0);
      that.map((v, i) => [v - san[i], i]).sort((a2, b2) => b2[0] - a2[0]).forEach(([, i]) => { if (du2 > 0) { san[i] += 1; du2 -= 1; } });
      con.forEach((x, i) => { x.thanh_tien = san[i]; });
    }
    ds.forEach((x) => lamTronTrich(x.children || [], x));
  }

  /* ═════════ Cây quỹ ═════════ */
  async function tai() {
    const l = ++luot; du = null; kpiCho(); $('qy-pham-vi').textContent = ''; $('qy-td-phu').textContent = ''; $('qy-cuon').hidden = false; $('qy-tt').innerHTML = ''; $('qy-tfoot').innerHTML = ''; $('qy-tbody').innerHTML = KT.hangCho(6, 6);
    try { KT.url.ghi({ thang: $('qy-thang').value }, { thang: $('qy-thang').options[0].value }); } catch (e) { /* khung xem trước */ }
    try {
      const d = await KD.api('/api/quy/tree?' + KT.url.qs({ thang: $('qy-thang').value })); if (l !== luot) return; du = d;
      lamTronTrich(d.tree || [], null);
      phang = []; const di = (ds, cap, cha) => ds.forEach((x) => { phang.push(Object.assign({}, x, { cap, cha })); di(x.children || [], cap + 1, x); }); di(d.tree || [], 0, null);
      $('qy-them').hidden = !d.can_admin;
      const goc = d.tree || [], trich = goc.filter((x) => !laHcns(x)).reduce((a, x) => a + (+x.thanh_tien || 0), 0), soDu = phang.reduce((a, x) => a + (+x.so_du || 0), 0), am = phang.filter((x) => +x.so_du < 0);
      kpiDat('dt', H.tienKpi(d.doanh_thu_thang || 0), 'Tháng ' + thangChu($('qy-thang').value) + KD.tip('Bảng doanh thu kế toán, chưa gồm đơn hoàn thành chưa ghi sổ — là cơ sở trích quỹ.'), KD.tienVnd(d.doanh_thu_thang || 0));
      kpiDat('trich', H.tienKpi(trich), goc.filter((x) => x.nguon_compute === 'doanh_thu_pct').length ? 'Quỹ gốc lấy % doanh thu' : 'Chưa có quỹ trích theo doanh thu', KD.tienVnd(trich));
      kpiDat('so_du', H.tienKpi(soDu), am.length ? H.pill('danger', KD.soDem(am.length) + ' quỹ âm') : 'Gồm cả quỹ con', KD.tienVnd(soDu));
      kpiDat('so_quy', H.dem(phang.length, 'quỹ'), KD.soDem(goc.length) + ' quỹ gốc · ' + KD.soDem(phang.length - goc.length) + ' quỹ con');
      if (!phang.length) { $('qy-cuon').hidden = true; $('qy-tt').innerHTML = KD.khoiRong('Chưa có quỹ nào', d.can_admin ? 'Bấm "Thêm quỹ" để tạo quỹ đầu tiên, vd quỹ dự phòng trích 2% doanh thu.' : 'Người quản trị chưa tạo quỹ nào.'); return; }
      $('qy-td-phu').textContent = KD.soDem(phang.length) + ' quỹ';
      ve();
    } catch (e) { if (l !== luot) return; kpiCho(true); $('qy-cuon').hidden = true; KD.khoiLoi($('qy-tt'), 'Không tải được danh sách quỹ', e, tai); }
  }
  function ve() {
    $('qy-tbody').innerHTML = phang.map((q) => {
      const con = (q.children || []).filter((c) => c.nguon_compute === 'parent_pct'), tongCon = con.reduce((a, c) => a + (+c.ty_le_pct || 0), 0);
      const canh = con.length && Math.abs(tongCon - 100) > 0.001 ? ' ' + H.pill(tongCon > 100 ? 'danger' : 'warning', 'Quỹ con chia ' + pct(tongCon)) : '';
      const gd = laHcns(q) ? '<span class="kd-muted">Chỉ xem</span>'
        : '<span class="kd-act"><button type="button" class="kd-btn kd-btn--sm" data-nap="' + q.id + '"><i class="bi bi-plus-circle" aria-hidden="true"></i>Nạp</button><button type="button" class="kd-btn kd-btn--sm" data-chi="' + q.id + '"><i class="bi bi-dash-circle" aria-hidden="true"></i>Chi</button></span>';
      return '<tr class="kt-quy-cap' + Math.min(q.cap, 3) + '"><td><div class="kt-quy-ten">' + (q.cap ? '<span class="kt-quy-nhanh" aria-hidden="true"></span>' : '') + '<div><span class="kt-khach__ten' + (q.cap ? '' : ' kd-strong') + '">' + esc(q.ten_quy) + '</span>'
        + (q.ghi_chu ? '<span class="kt-khach__ma">' + esc(q.ghi_chu) + '</span>' : '') + '</div></div></td>'
        + '<td>' + (NGUON[q.nguon_compute] || NGUON.manual)(q) + canh + '</td>'
        + '<td class="num">' + (q.nguon_compute === 'manual' || laHcns(q) ? '<span class="kd-muted">—</span>' : KD.tien(q.thanh_tien || 0)) + '</td>'
        + '<td class="num' + (+q.so_du < 0 ? ' kt-quy-am' : ' kd-strong') + '">' + KD.tien(q.so_du || 0) + '</td>'
        + '<td>' + gd + '</td>'
        + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu="' + q.id + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(q.ten_quy) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>';
    }).join('');
    const goc = du.tree || [];
    $('qy-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng ' + KD.soDem(phang.length) + ' quỹ</th><td class="num">' + KD.tip('Chỉ cộng quỹ gốc — quỹ con là phần chia của quỹ cha; không gồm Quỹ Công Đoàn (số luỹ kế HCNS).') + KD.tien(goc.filter((x) => !laHcns(x)).reduce((a, x) => a + (+x.thanh_tien || 0), 0)) + '</td><td class="num">' + KD.tien(phang.reduce((a, x) => a + (+x.so_du || 0), 0)) + '</td><td colspan="2"></td></tr>';
  }
  $('qy-tbody').addEventListener('click', (e) => {
    const b = e.target.closest('button'); if (!b) return; const q = timQuy(b.dataset.nap || b.dataset.chi || b.dataset.menu); if (!q) return;
    if (b.dataset.nap) return moGd(q, 'thu'); if (b.dataset.chi) return moGd(q, 'chi');
    const ad = du.can_admin && !laHcns(q), coPct = ['doanh_thu_pct', 'parent_pct'].includes(q.nguon_compute);
    KD.menu(b, [
      { nhan: 'Lịch sử giao dịch', icon: 'bi-clock-history', onClick: () => moLs(q) },
      ad && coPct ? { nhan: 'Chỉnh tỷ lệ %', icon: 'bi-percent', onClick: () => moPct(q) } : null,
      ad ? { nhan: 'Sửa quỹ', icon: 'bi-pencil', onClick: () => moQuy(q) } : null,
      ad ? '-' : null,
      ad ? { nhan: 'Xoá quỹ', icon: 'bi-trash', danger: true, onClick: () => moXoa(q) } : null,
    ].filter(Boolean));
  });
  $('qy-thang').addEventListener('change', tai);

  /* ═════════ Nạp / chi ═════════ */
  const dGd = $('qy-dlg-gd'); let gdQuy = null, gdLoai = 'thu';
  async function napTk() {
    if (tkNap) return; const sel = $('qy-gd-tk');
    try { const r = await KD.api('/api/tai-khoan?active_only=true'); tkNap = Array.isArray(r) ? r : (r.items || []);
      const giu = sel.value; sel.innerHTML = '<option value="">— Không đối ứng —</option>' + tkNap.map((t) => '<option value="' + esc(t.id) + '">' + esc(t.ten_tk || t.ten_nh || ('Tài khoản ' + t.id)) + '</option>').join(''); sel.value = giu; }
    catch (e) { sel.innerHTML = '<option value="">— Không tải được danh sách tài khoản —</option>'; }
  }
  function veGyTien() { if (!gdQuy) return; const t = docSo($('qy-gd-tien').value), sd = +gdQuy.so_du || 0;
    $('qy-gd-tien-gy').textContent = gdLoai === 'chi' ? (t > sd ? 'Vượt số dư ' + KD.tienVnd(sd) + ' — không chi được quá số dư.' : t ? 'Số dư còn lại ' + KD.tienVnd(sd - t) + '.' : 'Số dư hiện có ' + KD.tienVnd(sd) + '.') : (t ? 'Số dư sau khi nạp ' + KD.tienVnd(sd + t) + '.' : '');
    $('qy-gd-tien-gy').classList.toggle('kt-quy-canh', gdLoai === 'chi' && t > sd); }
  function moGd(q, loai) {
    gdQuy = q; gdLoai = loai; const nap = loai === 'thu';
    $('qy-gd-td').textContent = (nap ? 'Nạp tiền vào ' : 'Chi tiền từ ') + q.ten_quy;
    $('qy-gd-tt').innerHTML = '<dt>Số dư hiện tại</dt><dd>' + KD.tienVnd(q.so_du || 0) + '</dd>' + (!nap || q.nguon_compute === 'manual' ? '' : '<dt>Trích theo công thức tháng ' + thangChu($('qy-thang').value) + '</dt><dd>' + KD.tienVnd(q.thanh_tien || 0) + '</dd>');
    $('qy-gd-ngay').value = KD.iso(new Date()); $('qy-gd-tien').value = nap && q.nguon_compute !== 'manual' && +q.thanh_tien > 0 ? KD.tien(q.thanh_tien) : '';
    $('qy-gd-nd').value = nap && q.nguon_compute !== 'manual' ? 'Trích ' + q.ten_quy.replace(/^Quỹ /i, 'quỹ ') + ' tháng ' + thangChu($('qy-thang').value) : '';
    $('qy-gd-nd').placeholder = nap ? 'Vd: Trích quỹ tháng 09' : 'Vd: Chi bảo hành đơn NV001-0415'; $('qy-gd-gc').value = ''; $('qy-gd-tk').value = '';
    $('qy-gd-ok').innerHTML = '<i class="bi ' + (nap ? 'bi-plus-circle' : 'bi-dash-circle') + '" aria-hidden="true"></i>' + (nap ? 'Nạp tiền' : 'Chi tiền');
    veGyTien(); napTk(); KD.moHopThoai(dGd); $('qy-gd-tien').focus();
  }
  $('qy-gd-tien').addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; veGyTien(); });
  $('qy-gd-form').addEventListener('submit', async (e) => {
    e.preventDefault(); const t = docSo($('qy-gd-tien').value), nd = $('qy-gd-nd').value.trim(), ngay = $('qy-gd-ngay').value;
    if (!ngay) { $('qy-gd-ngay').focus(); return KD.baoLoiHopThoai(dGd, 'Chọn ngày giao dịch.'); }
    if (!t) { $('qy-gd-tien').focus(); return KD.baoLoiHopThoai(dGd, 'Nhập số tiền lớn hơn 0.'); }
    if (!nd) { $('qy-gd-nd').focus(); return KD.baoLoiHopThoai(dGd, 'Nhập nội dung giao dịch.'); }
    if (gdLoai === 'chi' && t > (+gdQuy.so_du || 0)) { $('qy-gd-tien').focus(); return KD.baoLoiHopThoai(dGd, 'Số tiền chi vượt số dư quỹ (' + KD.tienVnd(gdQuy.so_du || 0) + ').'); }
    const body = { ngay, so_tien: t, noi_dung: nd, tai_khoan_id: $('qy-gd-tk').value ? +$('qy-gd-tk').value : null, ghi_chu: $('qy-gd-gc').value.trim() || null };
    if (gdLoai === 'chi') body.allow_negative = false;
    const nut = $('qy-gd-ok'); nut.disabled = true;
    try { await KD.api('/api/quy-dn/' + gdQuy.id + (gdLoai === 'thu' ? '/nap' : '/chi'), KD.JSON_POST(body)); dGd.close();
      window.showToast && window.showToast('ok', (gdLoai === 'thu' ? 'Đã nạp ' : 'Đã chi ') + KD.tienVnd(t) + (gdLoai === 'thu' ? ' vào ' : ' từ ') + gdQuy.ten_quy); tai(); }
    catch (err) { KD.baoLoiHopThoai(dGd, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ═════════ Lịch sử giao dịch ═════════ */
  const dLs = $('qy-dlg-ls'); let lsQuy = null, lsLoai = '', lsLuot = 0, lsCanAdmin = false, lsDs = [];
  function moLs(q) { lsQuy = q; lsLoai = ''; $('qy-ls-tong').innerHTML = ''; $('qy-ls-td').textContent = 'Lịch sử giao dịch — ' + q.ten_quy; $('qy-ls-tu').value = ''; $('qy-ls-den').value = '';
    $('qy-ls-loai').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.loai === ''))); KD.moHopThoai(dLs); taiLs(); }
  async function taiLs() {
    const l = ++lsLuot; $('qy-ls-cuon').hidden = false; $('qy-ls-tt').innerHTML = ''; $('qy-ls-tfoot').innerHTML = ''; $('qy-ls-tbody').innerHTML = KT.hangCho(5, 4);
    try {
      let tu = $('qy-ls-tu').value, den = $('qy-ls-den').value; if (tu && den && tu > den) [tu, den] = [den, tu];   // nhập ngược (từ > đến) → vẫn lọc đúng khoảng thay vì ra rỗng
      const d = await KD.api('/api/quy-dn/' + lsQuy.id + '/giao-dich?' + KT.url.qs({ from_date: tu, to_date: den, loai: lsLoai })); if (l !== lsLuot) return;
      const ds = d.items || [], coLoc = !!(lsLoai || $('qy-ls-tu').value || $('qy-ls-den').value); lsCanAdmin = !!d.can_admin && !laHcns(lsQuy);
      $('qy-ls-tong').innerHTML = '<dt>Số dư quỹ</dt><dd>' + KD.tienVnd(d.so_du || 0) + '</dd><dt>Tổng nạp (mọi thời gian)</dt><dd>' + KD.tienVnd(d.tong_thu || 0) + '</dd><dt>Tổng chi (mọi thời gian)</dt><dd>' + KD.tienVnd(d.tong_chi || 0) + '</dd>';
      if (!ds.length) { $('qy-ls-cuon').hidden = true; $('qy-ls-tt').innerHTML = coLoc ? KD.khoiRong('Không có giao dịch nào khớp bộ lọc', 'Thử chọn "Tất cả" hoặc bỏ khoảng ngày.') : KD.khoiRong('Quỹ chưa có giao dịch nào', 'Nạp tiền vào quỹ để bắt đầu.'); return; }
      $('qy-ls-tbody').innerHTML = ds.map((g) => '<tr><td>' + KD.ngay(g.ngay) + '</td><td>' + H.ten(g.noi_dung || '—', [g.source_type && g.source_type !== 'manual' ? 'Tự động từ ' + g.source_type : '', g.created_by ? 'Người lập: ' + g.created_by : '', g.ghi_chu || ''].filter(Boolean).join(' · ')) + '</td>'
        + '<td class="num">' + (g.loai === 'thu' ? KD.tien(g.so_tien) : '') + '</td><td class="num">' + (g.loai === 'chi' ? KD.tien(g.so_tien) : '') + '</td>'
        + '<td class="kd-col-act">' + (lsCanAdmin && (!g.source_type || g.source_type === 'manual') ? '<button type="button" class="kd-icon-btn" data-huy="' + g.id + '" aria-label="Huỷ giao dịch ngày ' + KD.ngay(g.ngay) + '"><i class="bi bi-x-circle" aria-hidden="true"></i></button>' : '') + '</td></tr>').join('');
      const nap = ds.filter((g) => g.loai === 'thu').reduce((a, g) => a + (+g.so_tien || 0), 0), chi = ds.filter((g) => g.loai === 'chi').reduce((a, g) => a + (+g.so_tien || 0), 0);
      $('qy-ls-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng ' + KD.soDem(ds.length) + ' giao dịch · chênh lệch ' + KD.tienVnd(nap - chi) + '</th><td class="num">' + KD.tien(nap) + '</td><td class="num">' + KD.tien(chi) + '</td><td></td></tr>';
      lsDs = ds;
    } catch (e) { if (l !== lsLuot) return; $('qy-ls-cuon').hidden = true; KD.khoiLoi($('qy-ls-tt'), 'Không tải được lịch sử giao dịch', e, taiLs); }
  }
  $('qy-ls-loai').addEventListener('click', (e) => { const b = e.target.closest('[data-loai]'); if (!b) return; lsLoai = b.dataset.loai; $('qy-ls-loai').querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); taiLs(); });
  ['qy-ls-tu', 'qy-ls-den'].forEach((id) => $(id).addEventListener('change', taiLs));
  $('qy-ls-tbody').addEventListener('click', (e) => { const b = e.target.closest('[data-huy]'); if (!b) return; const g = lsDs.find((x) => String(x.id) === b.dataset.huy); if (!g) return;
    xacNhan('Huỷ giao dịch?', 'Huỷ ' + (g.loai === 'thu' ? 'khoản nạp ' : 'khoản chi ') + KD.tienVnd(g.so_tien) + ' ngày ' + KD.ngay(g.ngay) + ' ("' + (g.noi_dung || '') + '"). Số dư quỹ sẽ tính lại; không hoàn tác được.', 'Huỷ giao dịch',
      async () => { await KD.api('/api/quy-dn/giao-dich/' + g.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); window.showToast && window.showToast('ok', 'Đã huỷ giao dịch ' + KD.tienVnd(g.so_tien)); taiLs(); tai(); }); });

  /* ═════════ Quản trị: chỉnh %, thêm / sửa / xoá ═════════ */
  const dPct = $('qy-dlg-pct'); let pctQuy = null;
  function anhEmConLai(q) { return q.cha ? (q.cha.children || []).filter((c) => c.id !== q.id && c.nguon_compute === 'parent_pct').reduce((a, c) => a + (+c.ty_le_pct || 0), 0) : 0; }
  function veGyPct() { const p = docPct($('qy-p-pct').value), q = pctQuy; if (!q) return;
    const coSo = q.nguon_compute === 'doanh_thu_pct' ? +du.doanh_thu_thang || 0 : q.cha ? +q.cha.thanh_tien || 0 : 0;
    $('qy-p-gy').textContent = Number.isNaN(p) ? '' : 'Trích tháng ' + thangChu($('qy-thang').value) + ' sẽ là ' + KD.tienVnd(Math.round(coSo * p / 100)) + (q.nguon_compute === 'parent_pct' ? ' · các quỹ cùng cấp đang chiếm ' + pct(anhEmConLai(q)) + ', cộng lại ' + pct(anhEmConLai(q) + p) : '') + '.'; }
  function moPct(q) { pctQuy = q; $('qy-p-td').textContent = 'Chỉnh tỷ lệ — ' + q.ten_quy;
    $('qy-p-tt').innerHTML = '<dt>Nguồn</dt><dd>' + (q.nguon_compute === 'doanh_thu_pct' ? '% doanh thu tháng' : '% của ' + esc(q.cha ? q.cha.ten_quy : 'quỹ cha')) + '</dd><dt>Tỷ lệ hiện tại</dt><dd>' + pct(q.ty_le_pct) + '</dd>';
    $('qy-p-pct').value = String(q.ty_le_pct).replace('.', ','); veGyPct(); KD.moHopThoai(dPct); $('qy-p-pct').select(); }
  $('qy-p-pct').addEventListener('input', veGyPct);
  $('qy-p-form').addEventListener('submit', async (e) => { e.preventDefault(); const p = docPct($('qy-p-pct').value);
    if (Number.isNaN(p) || p < 0 || p > 100) { $('qy-p-pct').focus(); return KD.baoLoiHopThoai(dPct, 'Nhập tỷ lệ từ 0 đến 100 (dùng dấu phẩy cho số lẻ, vd 0,5).'); }
    if (pctQuy.nguon_compute === 'parent_pct' && anhEmConLai(pctQuy) + p > 100) { $('qy-p-pct').focus(); return KD.baoLoiHopThoai(dPct, 'Tổng tỷ lệ các quỹ con của "' + pctQuy.cha.ten_quy + '" sẽ vượt 100%.'); }
    const nut = $('qy-p-ok'); nut.disabled = true;
    try { await KD.api('/api/quy/' + pctQuy.id + '/config', Object.assign(KD.JSON_POST({ ty_le_pct: p }), { method: 'PUT' })); dPct.close(); window.showToast && window.showToast('ok', 'Đã đổi tỷ lệ ' + pctQuy.ten_quy + ' thành ' + pct(p)); tai(); }
    catch (err) { KD.baoLoiHopThoai(dPct, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; } });

  const dQuy = $('qy-dlg-quy'); let suaQuy = null;
  const conChau = (q) => { const s = new Set([q.id]); let doi = true; while (doi) { doi = false; phang.forEach((x) => { if (x.cha && s.has(x.cha.id) && !s.has(x.id)) { s.add(x.id); doi = true; } }); } return s; };
  function veNguon() { const n = $('qy-q-nguon').value, coPct = n !== 'manual'; $('qy-q-pct-o').hidden = !coPct;
    $('qy-q-pct-gy').textContent = n === 'doanh_thu_pct' ? 'Phần trăm doanh thu tháng, vd 0,5 = 0,5% doanh thu.' : n === 'parent_pct' ? 'Phần trăm số trích của quỹ cha — các quỹ con cộng lại không quá 100%.' : ''; }
  function moQuy(q) {
    suaQuy = q; $('qy-q-td').textContent = q ? 'Sửa quỹ' : 'Thêm quỹ'; const bo = q ? conChau(q) : new Set();
    $('qy-q-cha').innerHTML = '<option value="">— Quỹ gốc (không có quỹ cha) —</option>' + phang.filter((x) => !bo.has(x.id) && !laHcns(x)).map((x) => '<option value="' + x.id + '">' + '— '.repeat(x.cap) + esc(x.ten_quy) + '</option>').join('');
    $('qy-q-ten').value = q ? q.ten_quy : ''; $('qy-q-cha').value = q && q.parent_id ? String(q.parent_id) : ''; $('qy-q-nguon').value = q ? q.nguon_compute : 'manual';
    $('qy-q-pct').value = q && q.ty_le_pct ? String(q.ty_le_pct).replace('.', ',') : ''; $('qy-q-tt').value = q ? q.thu_tu || '' : ''; $('qy-q-gc').value = q ? q.ghi_chu || '' : '';
    veNguon(); KD.moHopThoai(dQuy); $('qy-q-ten').focus(); }
  $('qy-q-nguon').addEventListener('change', veNguon);
  $('qy-them').addEventListener('click', () => moQuy(null));
  $('qy-q-form').addEventListener('submit', async (e) => {
    e.preventDefault(); const ten = $('qy-q-ten').value.trim(), nguon = $('qy-q-nguon').value, cha = $('qy-q-cha').value ? +$('qy-q-cha').value : null, p = nguon === 'manual' ? 0 : docPct($('qy-q-pct').value);
    if (!ten) { $('qy-q-ten').focus(); return KD.baoLoiHopThoai(dQuy, 'Nhập tên quỹ.'); }
    if (nguon === 'parent_pct' && !cha) { $('qy-q-cha').focus(); return KD.baoLoiHopThoai(dQuy, 'Nguồn "% của quỹ cha" cần chọn quỹ cha.'); }
    if (nguon !== 'manual' && (Number.isNaN(p) || p <= 0 || p > 100)) { $('qy-q-pct').focus(); return KD.baoLoiHopThoai(dQuy, 'Nhập tỷ lệ lớn hơn 0 và không quá 100.'); }
    const body = { ten_quy: ten, parent_id: cha, nguon_compute: nguon, ty_le_pct: p, thu_tu: +$('qy-q-tt').value || 0, ghi_chu: $('qy-q-gc').value.trim() || null, active: true };
    const nut = $('qy-q-ok'); nut.disabled = true;
    try { if (suaQuy) await KD.api('/api/quy/' + suaQuy.id, Object.assign(KD.JSON_POST(body), { method: 'PUT' })); else await KD.api('/api/quy', KD.JSON_POST(body));
      dQuy.close(); window.showToast && window.showToast('ok', (suaQuy ? 'Đã cập nhật ' : 'Đã thêm ') + ten); tai(); }
    catch (err) { KD.baoLoiHopThoai(dQuy, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  function moXoa(q) { const con = conChau(q).size - 1;
    xacNhan('Xoá ' + q.ten_quy + '?', 'Xoá quỹ' + (con ? ' cùng ' + KD.soDem(con) + ' quỹ con' : '') + '. Quỹ còn số dư thì máy chủ sẽ từ chối — chi hết hoặc chuyển số dư trước. Lịch sử giao dịch vẫn được giữ.', 'Xoá quỹ',
      async () => { await KD.api('/api/quy/' + q.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); window.showToast && window.showToast('ok', 'Đã xoá ' + q.ten_quy); tai(); }); }

  /* Hộp xác nhận dùng chung */
  const dXn = $('qy-dlg-xn'); let xnLam = null;
  function xacNhan(td, nd, nut, lam) { $('qy-xn-td').textContent = td; $('qy-xn-nd').textContent = nd; $('qy-xn-nut').textContent = nut; xnLam = lam; KD.moHopThoai(dXn); }
  $('qy-xn-ok').addEventListener('click', async () => { const b = $('qy-xn-ok'); b.disabled = true;
    try { await xnLam(); dXn.close(); } catch (e) { KD.baoLoiHopThoai(dXn, 'Chưa thực hiện được: ' + e.message); } finally { b.disabled = false; } });

  tai();
})();
