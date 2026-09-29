/* kt-thuoc-tinh.js — Thuộc tính sản phẩm, master-detail 3 bước. Giữ nghiệp vụ màn cũ #page-thuoc-tinh:
   7 thuộc tính cố định (phân khúc & phong cách có hệ số giá), thuộc tính tuỳ chỉnh (đổi tên / xoá), giá trị theo "Mặc định nhóm" hoặc riêng từng sản phẩm
   (chép / bổ sung từ mặc định), sửa tại chỗ (Enter lưu, Esc huỷ), bật/tắt, xoá; lựa chọn cộng thêm (addon) theo sản phẩm. */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-thuoc-tinh')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const NHOM_GOC = ['Đồ Gỗ', 'Đồ Mây', 'Dự Án'];
  const CO_DINH = [
    { key: 'phan_khuc', nhan: 'Phân khúc', he: true, gy: 'Bản Tiêu Chuẩn / Plus / Hàng Trạm — hệ số nhân giá cơ bản' },
    { key: 'phong_cach', nhan: 'Phong cách', he: true, gy: 'Hiện đại / Indochine / Boho… — hệ số phong cách' },
    { key: 'vat_lieu', nhan: 'Vật liệu', gy: 'Gỗ sồi / Plywood / Kính / Mây / Cói… — ô tích khi báo giá' },
    { key: 'mau_go', nhan: 'Màu gỗ', gy: 'Màu sơn, nhuộm cho gỗ — danh sách chọn' },
    { key: 'mau_vai', nhan: 'Màu vải', gy: 'Màu, mã vải bọc — gợi ý khi nhập' },
    { key: 'mau_da', nhan: 'Màu da', gy: 'Màu da bọc — gợi ý khi nhập' },
    { key: 'loai_son', nhan: 'Loại sơn', gy: 'Mã sơn (07, Inchem…) — danh sách chọn' },
  ];
  const CACH = [['flat', 'Cộng thẳng'], ['per_m2', 'Nhân theo m² (dài × rộng)'], ['per_m_dai', 'Nhân theo mét dài']];
  const u0 = KT.url.doc();
  let TT = [], SPS = [], ADDON = [], nhom = u0.nhom || 'Đồ Gỗ', spId = u0.sp ? +u0.sp : null, nhomThem = [], luot = 0;
  const JSON_ = (m, b) => Object.assign(KD.JSON_POST(b || {}), { method: m });

  const dsNhom = () => [...new Set(NHOM_GOC.concat(TT.map((x) => x.nhom_master).filter(Boolean), nhomThem, [nhom]))];
  function veTabs() {
    $('tt-tabs').innerHTML = dsNhom().map((g, i) => '<button type="button" role="tab" id="tt-tab-' + i + '" data-nhom="' + esc(g) + '" aria-controls="tt-phai" aria-selected="' + (g === nhom) + '"' + (g === nhom ? '' : ' tabindex="-1"') + '>' + esc(g) + ' <span class="kd-muted">(' + KD.soDem(TT.filter((x) => x.nhom_master === g).length) + ')</span></button>').join('');
    const on = $('tt-tabs').querySelector('[aria-selected="true"]'); if (on) $('tt-phai').setAttribute('aria-labelledby', on.id);
  }
  $('tt-tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-nhom]'); if (b && b.dataset.nhom !== nhom) chonNhom(b.dataset.nhom); });
  $('tt-tabs').addEventListener('keydown', (e) => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return; const t = [...$('tt-tabs').querySelectorAll('[role="tab"]')], i = t.indexOf(document.activeElement);
    const j = e.key === 'Home' ? 0 : e.key === 'End' ? t.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + t.length) % t.length; e.preventDefault(); chonNhom(t[j].dataset.nhom).then(() => $('tt-tabs').querySelectorAll('[role="tab"]')[j].focus()); });

  /* ── Tải ── */
  async function tai() {
    const l = ++luot; $('tt-khung').hidden = true; $('tt-tt').innerHTML = KD.KHUNG_TAI; khungKpi();
    try {
      const [tt, sps] = await Promise.all([KD.api('/api/product-attributes'), KD.api('/api/products?' + KT.url.qs({ active_only: 'true', nhom_master: nhom }))]);
      if (l !== luot) return; TT = tt || []; SPS = sps || [];
      // Giữ nghiệp vụ màn cũ: nhóm (tự thêm) chưa có sản phẩm theo nhóm master thì tìm theo nhóm hàng cùng tên
      if (!SPS.length) { SPS = (await KD.api('/api/products?' + KT.url.qs({ active_only: 'true', nhom_hang: nhom }))) || []; if (l !== luot) return; }
      if (spId && !SPS.some((x) => x.id === spId)) spId = null;
      ADDON = spId ? ((await KD.api('/api/products/' + spId)).addons || []) : [];
      if (l !== luot) return;
      $('tt-tt').innerHTML = ''; $('tt-khung').hidden = false; veTatCa();
    } catch (e) { if (l !== luot) return; khungKpi(true); KD.khoiLoi($('tt-tt'), 'Không tải được thuộc tính sản phẩm', e, tai); }
  }
  async function chonNhom(g) { nhom = g; spId = null; ghiUrl(); veTabs(); await tai(); }
  async function chonSp(id) { spId = id; ghiUrl(); try { ADDON = id ? ((await KD.api('/api/products/' + id)).addons || []) : []; } catch (e) { ADDON = []; window.showToast && window.showToast('err', 'Không tải được lựa chọn cộng thêm: ' + e.message); } veTatCa(); }
  // Ô tìm sản phẩm (Bước 2) cũng giữ trên URL (?tim=) — F5 / gửi link không mất lọc.
  function ghiUrl() { try { KT.url.ghi({ nhom, sp: spId || '', tim: $('tt-sp-tim').value.trim() }, { nhom: 'Đồ Gỗ', sp: '', tim: '' }); } catch (e) { /* khung xem trước */ } }

  /* ── Thẻ số ── */
  function khungKpi(loi) { document.querySelectorAll('#tt-kpi [data-v]').forEach((x) => { x.innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; }); document.querySelectorAll('#tt-kpi [data-phu]').forEach((x) => { x.innerHTML = ''; }); $('tt-pham-vi').textContent = ''; }
  function veKpi() {
    const cuaNhom = TT.filter((x) => x.nhom_master === nhom), mac = cuaNhom.filter((x) => x.product_id == null), idSpNhom = new Set(SPS.map((p) => p.id)),
      // chỉ đếm SP thuộc nhóm đang xem — có dòng thuộc tính gắn nhầm nhóm (vd SP Đồ Mây mang thuộc tính Đồ Gỗ)
      rieng = new Set(cuaNhom.filter((x) => x.product_id != null && idSpNhom.has(x.product_id)).map((x) => x.product_id));
    const trong = CO_DINH.filter((m) => !mac.some((x) => x.attr_key === m.key));
    const dat = (k, v, phu) => { const el = document.querySelector('#tt-kpi [data-kpi="' + k + '"]'); el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-phu]').innerHTML = phu || ''; };
    dat('gia_tri', H.dem(cuaNhom.length, 'giá trị'), KD.soDem(mac.length) + ' mặc định · ' + KD.soDem(cuaNhom.length - mac.length) + ' riêng');
    dat('san_pham', H.dem(SPS.length, 'sản phẩm'), 'Đang bán, nhóm ' + esc(nhom));
    dat('rieng', H.dem(rieng.size, 'sản phẩm'), 'Còn lại dùng mặc định nhóm');
    dat('trong', H.dem(trong.length, 'thuộc tính'), trong.length ? H.pill('warning', 'Báo giá thiếu lựa chọn') + KD.tip('Còn trống: ' + trong.map((m) => m.nhan).join(', ') + '.', 'kd-tip--trai') : H.pill('success', 'Đủ 7 thuộc tính'));
  }

  /* ── Bước 2: danh sách sản phẩm ── */
  function veDsSp() {
    const t = ($('tt-sp-tim').value || '').trim(), dem = {}; TT.forEach((x) => { if (x.product_id != null && x.nhom_master === nhom) dem[x.product_id] = (dem[x.product_id] || 0) + 1; });
    const sp = SPS.filter((p) => KT.khopTim([p.ten_sp, p.ma_sp], t));
    $('tt-sp-ds').innerHTML = '<li><button type="button" class="kt-tt-sp kt-tt-sp--mac" data-sp=""' + (spId == null ? ' aria-current="true"' : '') + '><span><span class="kt-tt-sp__ten">Mặc định nhóm</span><span class="kt-tt-sp__ma">Áp cho sản phẩm chưa khai báo riêng</span></span>' + H.pill('brand', KD.soDem(TT.filter((x) => x.nhom_master === nhom && x.product_id == null).length)) + '</button></li>'
      + (sp.length ? sp.map((p) => '<li><button type="button" class="kt-tt-sp" data-sp="' + p.id + '"' + (spId === p.id ? ' aria-current="true"' : '') + '><span><span class="kt-tt-sp__ten" title="' + esc(p.ten_sp) + '">' + esc(p.ten_sp || p.label || p.ma_sp) + '</span><span class="kt-tt-sp__ma">' + esc(p.ma_sp || '—') + '</span></span>'
        + (dem[p.id] ? H.pill('success', KD.soDem(dem[p.id]) + ' riêng') : '<span class="kd-meta">Dùng mặc định</span>') + '</button></li>').join('')
        : '<li>' + KD.khoiRong(t ? 'Không có sản phẩm khớp' : 'Nhóm ' + nhom + ' chưa có sản phẩm', t ? '' : 'Thêm ở màn Sản phẩm, chọn nhóm master là ' + nhom + '.') + '</li>');
  }
  $('tt-sp-tim').value = u0.tim || '';
  $('tt-sp-tim').addEventListener('input', KD.debounce(() => { veDsSp(); ghiUrl(); }, 200));
  $('tt-sp-ds').addEventListener('click', (e) => { const b = e.target.closest('[data-sp]'); if (!b) return; const id = b.dataset.sp ? +b.dataset.sp : null; if (id !== spId) chonSp(id); });

  /* ── Bước 3: các thẻ thuộc tính ── */
  const dongCua = () => TT.filter((x) => x.nhom_master === nhom && (spId == null ? x.product_id == null : x.product_id === spId));
  function veNgu(rows) {
    const sp = SPS.find((p) => p.id === spId);
    $('tt-ngu-td').textContent = spId == null ? 'Mặc định nhóm ' + nhom : (sp ? sp.ten_sp : 'Sản phẩm #' + spId);
    $('tt-ngu-phu').textContent = (sp ? sp.ma_sp + ' · ' : '') + KD.soDem(rows.length) + ' giá trị' + (spId != null && !rows.length ? ' — sản phẩm đang dùng toàn bộ mặc định nhóm' : '');
    $('tt-ngu-nut').innerHTML = spId == null ? '' : (rows.length ? '<button type="button" class="kd-btn kd-btn--sm" data-chep="0" title="Thêm các giá trị mặc định chưa có ở sản phẩm này">Bổ sung từ mặc định</button><button type="button" class="kd-btn kd-btn--sm" data-chep="1" title="Xoá hết giá trị riêng rồi chép lại từ mặc định">Chép lại từ đầu</button>'
      : '<button type="button" class="kd-btn kd-btn--sm" data-chep="0">Chép từ mặc định nhóm để sửa riêng</button>');
  }
  const the = (m, rows, tuyChinh) => { const n = rows.length;
    return '<section class="kd-card kt-tt-the" aria-labelledby="tt-k-' + esc(m.key) + '" data-key="' + esc(m.key) + '"><div class="kd-box__head"><div><h3 class="kd-box__title" id="tt-k-' + esc(m.key) + '">' + esc(m.nhan) + KD.tip((m.gy || 'Thuộc tính tuỳ chỉnh — app Báo giá không tự hiện') + '. Mã: ' + m.key) + '</h3>'
      + '<div class="kt-tt-chip">' + (m.he ? '<span class="kd-chip kd-chip--xam">Có hệ số giá</span>' : '')
      + H.pill(n ? 'success' : 'warning', n ? KD.soDem(n) + ' giá trị' : 'Chưa có giá trị') + '</div></div>'
      + (tuyChinh ? '<div class="kt-dh-xl"><button type="button" class="kd-btn kd-btn--sm" data-doi-key="' + esc(m.key) + '">Đổi tên</button><button type="button" class="kd-icon-btn" data-xoa-key="' + esc(m.key) + '" aria-label="Xoá thuộc tính ' + esc(m.nhan) + '"><i class="bi bi-trash" aria-hidden="true"></i></button></div>' : '') + '</div>'
      + (n ? '<div class="kd-table-scroll"><table class="kd-table kt-bang kt-tt-bang"><caption class="visually-hidden">Giá trị ' + esc(m.nhan) + '</caption><thead><tr><th scope="col" class="num">#</th><th scope="col">Giá trị</th>' + (m.he ? '<th scope="col" class="num">Hệ số ×</th>' : '') + '<th scope="col">Bật</th><th scope="col"><span class="visually-hidden">Xoá</span></th></tr></thead><tbody>'
        + rows.slice().sort((a, b) => (a.thu_tu - b.thu_tu) || (a.id - b.id)).map((r, i) => '<tr data-id="' + r.id + '"' + (r.active ? '' : ' class="is-tat"') + '><td class="num">' + (i + 1) + '</td><td><input class="kd-input" data-sua="attr_value" value="' + esc(r.attr_value) + '" data-cu="' + esc(r.attr_value) + '" aria-label="Giá trị ' + esc(m.nhan) + ' ' + (i + 1) + '"></td>'
          + (m.he ? '<td class="num"><input class="kd-input kt-tt-he" data-sua="coeff" inputmode="decimal" value="' + (r.coeff != null ? String(r.coeff).replace('.', ',') : '') + '" data-cu="' + (r.coeff != null ? String(r.coeff).replace('.', ',') : '') + '" placeholder="1,00" aria-label="Hệ số của ' + esc(r.attr_value) + '"></td>' : '')
          + '<td><label class="kt-check"><input type="checkbox" data-bat' + (r.active ? ' checked' : '') + '> ' + (r.active ? 'Bật' : 'Tắt') + '</label></td><td><button type="button" class="kd-icon-btn" data-xoa-gt aria-label="Xoá ' + esc(r.attr_value) + '"><i class="bi bi-x-lg" aria-hidden="true"></i></button></td></tr>').join('')
        + '</tbody></table></div>' : '<p class="kd-meta kt-tt-them">Chưa có giá trị' + (spId != null ? ' riêng — sản phẩm đang dùng mặc định nhóm' : '') + '. Thêm bên dưới.</p>')
      + '<div class="kt-tt-them"><input class="kd-input" data-moi placeholder="Giá trị mới" aria-label="Giá trị mới cho ' + esc(m.nhan) + '">' + (m.he ? '<input class="kd-input kt-tt-he" data-moi-he inputmode="decimal" placeholder="Hệ số, vd 1,2" aria-label="Hệ số giá trị mới">' : '') + '<button type="button" class="kd-btn kd-btn--sm" data-them>Thêm</button></div></section>'; };
  const theAddon = () => '<section class="kd-card kt-tt-the" aria-labelledby="tt-k-addon" data-addon><div class="kd-box__head"><div><h3 class="kd-box__title" id="tt-k-addon">Lựa chọn cộng thêm' + KD.tip('Tuỳ chọn tính thêm tiền khi báo giá (tay vịn rời, bánh xe, mặt kính…) — riêng từng sản phẩm.') + '</h3>'
    + '<div class="kt-tt-chip">' + H.pill(ADDON.length ? 'success' : 'warning', ADDON.length ? KD.soDem(ADDON.length) + ' lựa chọn' : 'Chưa có lựa chọn') + '</div></div></div>'
    + (ADDON.length ? '<div class="kd-table-scroll"><table class="kd-table kt-bang kt-tt-bang"><caption class="visually-hidden">Lựa chọn cộng thêm</caption><thead><tr><th scope="col">Tên lựa chọn</th><th scope="col" class="num">Giá (VND)</th><th scope="col">Cách tính</th><th scope="col"><span class="visually-hidden">Xoá</span></th></tr></thead><tbody>'
      + ADDON.slice().sort((a, b) => (a.thu_tu - b.thu_tu) || (a.id - b.id)).map((a) => '<tr data-addon-id="' + a.id + '"><td><input class="kd-input" data-a="ten_addon" value="' + esc(a.ten_addon) + '" data-cu="' + esc(a.ten_addon) + '" aria-label="Tên lựa chọn"></td><td class="num"><input class="kd-input kt-tt-he" data-a="gia_addon" inputmode="numeric" value="' + KD.tien(a.gia_addon || 0) + '" data-cu="' + KD.tien(a.gia_addon || 0) + '" aria-label="Giá lựa chọn ' + esc(a.ten_addon) + '"></td>'
        + '<td><select class="kd-input" data-a="cach_tinh" aria-label="Cách tính ' + esc(a.ten_addon) + '">' + CACH.map(([v, t]) => '<option value="' + v + '"' + ((a.cach_tinh || 'flat') === v ? ' selected' : '') + '>' + t + '</option>').join('') + '</select></td><td><button type="button" class="kd-icon-btn" data-xoa-addon aria-label="Xoá ' + esc(a.ten_addon) + '"><i class="bi bi-x-lg" aria-hidden="true"></i></button></td></tr>').join('') + '</tbody></table></div>' : '')
    + '<div class="kt-tt-them"><input class="kd-input" data-moi-addon placeholder="Tên lựa chọn mới" aria-label="Tên lựa chọn mới"><input class="kd-input kt-tt-he" data-moi-gia inputmode="numeric" placeholder="Giá" aria-label="Giá lựa chọn mới"><select class="kd-input" data-moi-cach aria-label="Cách tính">' + CACH.map(([v, t]) => '<option value="' + v + '">' + t + '</option>').join('') + '</select><button type="button" class="kd-btn kd-btn--sm" data-them-addon>Thêm</button></div></section>';
  function veTatCa() {
    veTabs(); veKpi(); veDsSp();
    const rows = dongCua(), theoKey = {}; rows.forEach((r) => { (theoKey[r.attr_key] = theoKey[r.attr_key] || []).push(r); });
    veNgu(rows);
    $('tt-the').innerHTML = CO_DINH.map((m) => the(m, theoKey[m.key] || [])).join('') + (spId != null ? theAddon() : '');
    const khac = [...new Set(TT.filter((x) => x.nhom_master === nhom && !CO_DINH.some((m) => m.key === x.attr_key)).map((x) => x.attr_key))].sort();
    $('tt-tuy-chinh').innerHTML = khac.length ? '<p class="kt-tt-buoc">Thuộc tính tuỳ chỉnh (' + KD.soDem(khac.length) + ')</p><div class="kt-tt-luoi">' + khac.map((k) => the({ key: k, nhan: k }, theoKey[k] || [], true)).join('') + '</div>' : '';
  }

  /* ── Sửa tại chỗ ── */
  const vung = $('tt-phai');
  const soHe = (v) => { const t = String(v || '').trim().replace(',', '.'); return t === '' ? null : Number(t); };
  async function luu(input, url, body, sau) {
    input.classList.remove('is-ok', 'is-loi'); input.classList.add('is-luu');
    try { const kq = await KD.api(url, JSON_('PUT', body)); input.classList.replace('is-luu', 'is-ok'); input.dataset.cu = input.value; setTimeout(() => input.classList.remove('is-ok'), 900); if (sau) sau(kq); }
    catch (e) { input.classList.replace('is-luu', 'is-loi'); window.showToast && window.showToast('err', 'Chưa lưu được: ' + e.message); }
  }
  vung.addEventListener('keydown', (e) => { const i = e.target.closest('[data-sua], [data-a]'); if (i && e.key === 'Enter') { e.preventDefault(); i.blur(); } else if (i && e.key === 'Escape') { i.value = i.dataset.cu; i.blur(); }
    if (e.key === 'Enter' && e.target.matches('[data-moi], [data-moi-he]')) { e.preventDefault(); e.target.closest('.kt-tt-the').querySelector('[data-them]').click(); }
    if (e.key === 'Enter' && e.target.matches('[data-moi-addon], [data-moi-gia]')) { e.preventDefault(); vung.querySelector('[data-them-addon]').click(); } });
  vung.addEventListener('focusout', (e) => {
    const i = e.target.closest('[data-sua]'); if (i && i.value !== i.dataset.cu) { const id = +i.closest('tr').dataset.id, r = TT.find((x) => x.id === id);
      if (i.dataset.sua === 'attr_value') { if (!i.value.trim()) { i.value = i.dataset.cu; return window.showToast && window.showToast('err', 'Giá trị không được để trống'); } luu(i, '/api/product-attributes/' + id, { attr_value: i.value.trim() }, () => { r.attr_value = i.value.trim(); }); }
      else { const h = soHe(i.value); if (h != null && !(h >= 0)) { i.value = i.dataset.cu; return window.showToast && window.showToast('err', 'Hệ số không hợp lệ'); } luu(i, '/api/product-attributes/' + id, { coeff: h }, () => { r.coeff = h; }); } }
    const a = e.target.closest('input[data-a]'); if (a && a.value !== a.dataset.cu) { const id = +a.closest('tr').dataset.addonId, x = ADDON.find((y) => y.id === id), f = a.dataset.a;
      const v = f === 'gia_addon' ? Number(a.value.replace(/[^\d]/g, '')) || 0 : a.value.trim(); if (f === 'ten_addon' && !v) { a.value = a.dataset.cu; return; }
      if (f === 'gia_addon') a.value = KD.tien(v); luu(a, '/api/products/' + spId + '/addons/' + id, { [f]: v }, () => { x[f] = v; }); }
  });
  vung.addEventListener('change', async (e) => {
    const c = e.target.closest('[data-bat]'); if (c) { const id = +c.closest('tr').dataset.id, r = TT.find((x) => x.id === id);
      try { await KD.api('/api/product-attributes/' + id, JSON_('PUT', { active: c.checked })); r.active = c.checked; c.closest('tr').classList.toggle('is-tat', !c.checked); c.parentNode.lastChild.textContent = c.checked ? ' Bật' : ' Tắt'; }
      catch (err) { c.checked = !c.checked; window.showToast && window.showToast('err', 'Chưa đổi được: ' + err.message); } }
    const s = e.target.closest('select[data-a]'); if (s) { const id = +s.closest('tr').dataset.addonId, x = ADDON.find((y) => y.id === id); luu(s, '/api/products/' + spId + '/addons/' + id, { cach_tinh: s.value }, () => { x.cach_tinh = s.value; }); }
  });
  vung.addEventListener('input', (e) => { if (e.target.matches('[data-moi-gia], input[data-a="gia_addon"]')) { const n = Number(e.target.value.replace(/[^\d]/g, '')) || 0; e.target.value = n ? KD.tien(n) : ''; } });
  vung.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-them]'); if (t) { const card = t.closest('.kt-tt-the'), key = card.dataset.key, i = card.querySelector('[data-moi]'), v = i.value.trim(), hi = card.querySelector('[data-moi-he]');
      if (!v) return i.focus(); const h = hi ? soHe(hi.value) : null; if (hi && hi.value && !(h >= 0)) return hi.focus();
      t.disabled = true; try { const x = await KD.api('/api/product-attributes', KD.JSON_POST({ nhom_master: nhom, product_id: spId, attr_key: key, attr_value: v, coeff: h })); TT.push(x); veTatCa(); const moi = vung.querySelector('.kt-tt-the[data-key="' + CSS.escape(key) + '"] [data-moi]'); if (moi) moi.focus(); }
      catch (err) { window.showToast && window.showToast('err', 'Chưa thêm được: ' + err.message); t.disabled = false; } return; }
    const ta = e.target.closest('[data-them-addon]'); if (ta) { const i = vung.querySelector('[data-moi-addon]'), v = i.value.trim(); if (!v) return i.focus();
      ta.disabled = true; try { const x = await KD.api('/api/products/' + spId + '/addons', KD.JSON_POST({ ten_addon: v, gia_addon: Number(vung.querySelector('[data-moi-gia]').value.replace(/[^\d]/g, '')) || 0, cach_tinh: vung.querySelector('[data-moi-cach]').value })); ADDON.push(x); veTatCa(); vung.querySelector('[data-moi-addon]').focus(); }
      catch (err) { window.showToast && window.showToast('err', 'Chưa thêm được: ' + err.message); ta.disabled = false; } return; }
    const xg = e.target.closest('[data-xoa-gt]'); if (xg) { const r = TT.find((x) => x.id === +xg.closest('tr').dataset.id); return hoiXoa('Xoá giá trị "' + r.attr_value + '"?', 'Báo giá mới sẽ không còn lựa chọn này. Báo giá cũ giữ nguyên. Muốn ẩn tạm thì bỏ tích "Bật".', async () => { await KD.api('/api/product-attributes/' + r.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); TT.splice(TT.indexOf(r), 1); }); }
    const xa = e.target.closest('[data-xoa-addon]'); if (xa) { const a = ADDON.find((x) => x.id === +xa.closest('tr').dataset.addonId); return hoiXoa('Xoá lựa chọn "' + a.ten_addon + '"?', 'Lựa chọn này sẽ không còn khi báo giá sản phẩm.', async () => { await KD.api('/api/products/' + spId + '/addons/' + a.id, { method: 'DELETE', headers: { Accept: 'application/json' } }); ADDON.splice(ADDON.indexOf(a), 1); }); }
    const xk = e.target.closest('[data-xoa-key]'); if (xk) { const k = xk.dataset.xoaKey; return hoiXoa('Xoá thuộc tính "' + k + '"?', 'Xoá toàn bộ ' + KD.soDem(TT.filter((x) => x.nhom_master === nhom && x.attr_key === k).length) + ' giá trị của thuộc tính này trong nhóm ' + nhom + ' (cả mặc định lẫn riêng từng sản phẩm).', async () => { await KD.api('/api/product-attributes/key?' + KT.url.qs({ nhom_master: nhom, attr_key: k }), { method: 'DELETE', headers: { Accept: 'application/json' } }); TT = TT.filter((x) => !(x.nhom_master === nhom && x.attr_key === k)); }); }
    const dk = e.target.closest('[data-doi-key]'); if (dk) { doiKey = dk.dataset.doiKey; $('tt-doi-td').textContent = 'Đổi tên thuộc tính "' + doiKey + '"'; $('tt-doi-ten').value = doiKey; KD.moHopThoai($('tt-dlg-doi')); $('tt-doi-ten').select(); return; }
    const cp = e.target.closest('[data-chep]'); if (cp) { const de = cp.dataset.chep === '1'; if (de) return hoiXoa('Chép lại từ mặc định nhóm?', 'Xoá hết giá trị riêng của sản phẩm này rồi chép lại toàn bộ từ mặc định nhóm ' + nhom + '.', () => chep(true), 'Chép lại'); chep(false); }
  }, true);
  async function chep(de) { try { const kq = await KD.api('/api/product-attributes/copy-defaults', KD.JSON_POST({ nhom_master: nhom, product_id: spId, overwrite: de })); TT = await KD.api('/api/product-attributes'); veTatCa(); window.showToast && window.showToast('ok', 'Đã chép ' + KD.soDem(kq.copied || 0) + ' giá trị từ mặc định nhóm'); }
    catch (e) { window.showToast && window.showToast('err', 'Chưa chép được: ' + e.message); } }

  /* ── Hộp thoại ── */
  const dlgX = $('tt-dlg-xoa'); let viecXoa = null;
  function hoiXoa(td, nd, viec, nhanNut) { viecXoa = viec; $('tt-xoa-td').textContent = td; $('tt-xoa-nd').textContent = nd; $('tt-xoa-ok').innerHTML = nhanNut ? nhanNut : '<i class="bi bi-trash" aria-hidden="true"></i>Xoá'; $('tt-xoa-ok').className = 'kd-btn ' + (nhanNut ? 'kd-btn--primary' : 'kd-btn--danger'); KD.moHopThoai(dlgX); dlgX.querySelector('[data-dong]').focus(); }
  $('tt-xoa-ok').addEventListener('click', async () => { const nut = $('tt-xoa-ok'); nut.disabled = true; try { await viecXoa(); dlgX.close(); veTatCa(); } catch (e) { KD.baoLoiHopThoai(dlgX, 'Chưa thực hiện được: ' + e.message); } finally { nut.disabled = false; } });
  let doiKey = null;
  $('tt-form-doi').addEventListener('submit', async (e) => { e.preventDefault(); const moi = $('tt-doi-ten').value.trim(), d = $('tt-dlg-doi');
    if (!moi) return KD.baoLoiHopThoai(d, 'Nhập tên mới.'); if (moi === doiKey) return d.close();
    if (CO_DINH.some((m) => m.key === moi) || TT.some((x) => x.nhom_master === nhom && x.attr_key === moi)) return KD.baoLoiHopThoai(d, 'Nhóm ' + nhom + ' đã có thuộc tính "' + moi + '".');
    try { await KD.api('/api/product-attributes/key/rename', KD.JSON_POST({ nhom_master: nhom, old_key: doiKey, new_key: moi })); TT.forEach((x) => { if (x.nhom_master === nhom && x.attr_key === doiKey) x.attr_key = moi; }); d.close(); veTatCa(); }
    catch (err) { KD.baoLoiHopThoai(d, 'Chưa đổi được: ' + err.message); } });
  $('tt-them-nhom').addEventListener('click', () => { $('tt-form-nhom').reset(); KD.moHopThoai($('tt-dlg-nhom')); $('tt-nhom-ten').focus(); });
  $('tt-form-nhom').addEventListener('submit', (e) => { e.preventDefault(); const t = $('tt-nhom-ten').value.trim(); if (!t) return KD.baoLoiHopThoai($('tt-dlg-nhom'), 'Nhập tên nhóm.');
    if (dsNhom().some((g) => g.toLowerCase() === t.toLowerCase())) return KD.baoLoiHopThoai($('tt-dlg-nhom'), 'Đã có nhóm "' + t + '".');
    nhomThem.push(t); $('tt-dlg-nhom').close(); chonNhom(t); });
  $('tt-them-key').addEventListener('click', () => { $('tt-form-key').reset(); $('tt-key-ngu').textContent = 'Thêm vào ' + (spId == null ? 'mặc định nhóm ' + nhom : 'riêng sản phẩm ' + (SPS.find((p) => p.id === spId) || {}).ten_sp) + '.'; KD.moHopThoai($('tt-dlg-key')); $('tt-key-ten').focus(); });
  $('tt-form-key').addEventListener('submit', async (e) => { e.preventDefault(); const d = $('tt-dlg-key'), ten = $('tt-key-ten').value.trim(), gt = $('tt-key-gt').value.split('\n').map((x) => x.trim()).filter(Boolean);
    if (!ten) return KD.baoLoiHopThoai(d, 'Nhập tên thuộc tính.');
    if (CO_DINH.some((m) => m.key === ten || m.nhan.toLowerCase() === ten.toLowerCase())) return KD.baoLoiHopThoai(d, '"' + ten + '" là thuộc tính cố định — thêm giá trị trực tiếp ở thẻ của nó.');
    const nut = $('tt-key-ok'); nut.disabled = true;
    try { if (gt.length) { const moi = await KD.api('/api/product-attributes/bulk', KD.JSON_POST({ nhom_master: nhom, product_id: spId, attr_key: ten, values: gt })); TT = TT.concat(moi || []); }
      else nhomThem.push(nhom);
      d.close(); veTatCa(); window.showToast && window.showToast('ok', gt.length ? 'Đã thêm thuộc tính "' + ten + '" với ' + KD.soDem(gt.length) + ' giá trị' : 'Thuộc tính chỉ được lưu khi có giá trị — hãy thêm ít nhất một giá trị');
      if (!gt.length) { $('tt-tuy-chinh').insertAdjacentHTML('beforeend', '<div class="kt-tt-luoi">' + the({ key: ten, nhan: ten }, [], true) + '</div>'); vung.querySelector('.kt-tt-the[data-key="' + CSS.escape(ten) + '"] [data-moi]').focus(); } }
    catch (err) { KD.baoLoiHopThoai(d, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; } });

  veTabs(); tai();
})();
