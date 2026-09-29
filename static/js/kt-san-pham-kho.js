/* kt-san-pham-kho.js — các tab "Kho kế toán" của màn Sản phẩm, thay trang cũ /products (M1: Danh mục · Sản phẩm · Tồn kho ·
   Biến động · Cảnh báo · BOM giá vốn). Giữ nguyên nghiệp vụ + API của trang cũ:
     ketoan.product (/api/product)  ·  ketoan.product_category (/api/product-category)  ·  inventory_balance (/api/inventory/balance)
     inventory_movement (/api/inventory/movement, /kiem-ke)  ·  /api/inventory/canh-bao  ·  bom_master (/api/bom, /margin-report)
   Tab đang mở giữ trên URL (#kho, #bom…) — không đụng tham số lọc của tab Danh mục dùng chung (kt-san-pham.js). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-san-pham')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const TABS = ['chung', 'kho', 'nhom', 'bien_dong', 'canh_bao', 'bom'];
  const LOAI = { nhap: ['success', 'Nhập'], xuat: ['warning', 'Xuất'], dieu_chinh: ['info', 'Điều chỉnh'] };
  const NGUON = { muahang: 'Mua hàng', saleadmin: 'Đơn hàng (Sale Admin)', manual: 'Kế toán lập', kiem_ke: 'Kiểm kê' };
  const soLuong = (v) => { const n = Number(v); return Number.isFinite(n) ? new Intl.NumberFormat('vi-VN', { maximumFractionDigits: 2 }).format(n) : '—'; };
  const docTien = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  // Số lẻ kiểu VN: "1,5" = 1.5; "1.000" = 1000; "1.5" (một dấu chấm, ≤ 2 số lẻ) vẫn hiểu là 1.5
  const docSoLe = (v) => { let t = String(v == null ? '' : v).trim(); if (t === '') return null;
    t = t.includes(',') ? t.replace(/\./g, '').replace(',', '.') : /^-?\d+\.\d{1,2}$/.test(t) ? t : t.replace(/\./g, ''); return Number(t); };
  const homNay = () => { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); };
  const bao = (loai, nd) => window.showToast && window.showToast(loai, nd);
  const oTien = (el) => el.addEventListener('input', () => { const n = docTien(el.value); el.value = n ? KD.tien(n) : ''; });
  const JSON_ = (m, b) => Object.assign(KD.JSON_POST(b || {}), { method: m });
  const XOA = { method: 'DELETE', headers: { Accept: 'application/json' } };
  let NHOM = [], CAY = [], SP = [];   // nhóm phẳng · cây nhóm · sản phẩm kế toán (đang dùng) cho ô chọn

  /* ── Tab cấp trang + bộ lọc các tab kho giữ trên HASH: #<tab>?kk_q=…&mv_sp=…&bom_nhom=…
     (phần ?… trước dấu # là của tab Danh mục dùng chung — KT.danhSach tự ghi; hai bên không đè nhau).
     Bản trước bộ lọc các tab kho không lên URL → F5 / gửi link mất lọc. ── */
  const [hTab, hLoc] = location.hash.slice(1).split('?');
  let tab = TABS.includes(hTab) ? hTab : 'chung';
  const LOC = { kk_q: 'kk-q', kk_nhom: 'kk-nhom', kk_active: 'kk-active', mv_sp: 'mv-sp', mv_loai: 'mv-loai', mv_tu: 'mv-tu', mv_den: 'mv-den', bom_nhom: 'bom-nhom', bom_active: 'bom-active' };
  const LOC_MAC_DINH = { kk_active: 'true', bom_active: 'true' };
  const LOC_NAP_SAU = ['kk-nhom', 'bom-nhom', 'mv-sp'];   // ô chọn nạp lựa chọn từ API sau
  function ghiHash() {
    const p = new URLSearchParams();
    Object.keys(LOC).forEach((k) => { const v = $(LOC[k]).value; if (v !== (LOC_MAC_DINH[k] || '')) p.set(k, v); });
    const h = (tab === 'chung' ? '' : tab) + (p.toString() ? '?' + p : '');
    try { history.replaceState(null, '', location.pathname + location.search + (h ? '#' + h : '')); } catch (e) { /* khung xem trước */ }
  }
  function datLaiLoc(tien, taiLai) { Object.keys(LOC).filter((k) => k.startsWith(tien + '_')).forEach((k) => { $(LOC[k]).value = LOC_MAC_DINH[k] || ''; }); taiLai(); }
  (function docHash() {
    const p = new URLSearchParams(hLoc || '');
    Object.keys(LOC).forEach((k) => { if (!p.has(k)) return; const el = $(LOC[k]), v = p.get(k);
      if (el.type === 'date' && !/^\d{4}-\d{2}-\d{2}$/.test(v)) return;
      const coSan = el.tagName !== 'SELECT' || [...el.options].some((o) => o.value === v);
      if (!coSan && !LOC_NAP_SAU.includes(el.id)) return;
      if (!coSan) el.add(new Option('Đang tải…', v));   // giữ giá trị tới lúc nạp xong danh sách (napNhom / napSp giữ el.value)
      el.value = v; });
  })();
  const daTai = {};
  const tabs = KD.ganTab($('sp-tabs'), (k) => {
    tab = k; $('sp-cong-cu').hidden = k !== 'chung';
    ghiHash();
    if (!daTai[k] && TAI[k]) { daTai[k] = true; TAI[k](); }
  });

  /* ── Dữ liệu dùng chung giữa các tab ── */
  async function napNhom(ep) {
    if (NHOM.length && !ep) return;
    [CAY, NHOM] = await Promise.all([KD.api('/api/product-category/tree'), KD.api('/api/product-category')]);
    const ds = phang(CAY).map((n) => [String(n.id), '  '.repeat(n.sau) + n.ten_nhom]);
    H.napChon($('kk-nhom'), ds, 'Tất cả nhóm', $('kk-nhom').value);
    H.napChon($('bom-nhom'), ds, 'Tất cả nhóm', $('bom-nhom').value);
    H.napChon($('kk-sp-nhom'), ds, '', '');
    H.napChon($('kk-bom-nhom'), ds, '', '');
  }
  const phang = (cay, sau) => (cay || []).reduce((a, n) => a.concat([Object.assign({}, n, { sau: sau || 0 })], phang(n.children, (sau || 0) + 1)), []);
  async function napSp(ep) {
    if (SP.length && !ep) return;
    SP = ((await KD.api('/api/product?page=1&size=500')).items || []);
    const ds = SP.map((p) => [String(p.id), p.ma_sp + ' — ' + p.ten_sp]);
    H.napChon($('mv-sp'), ds, 'Tất cả sản phẩm', $('mv-sp').value);
    H.napChon($('kk-mv-sp'), ds, '', ''); H.napChon($('kk-kk-sp'), ds, '', '');
  }
  const tonHint = (sel, out) => { const p = SP.find((x) => String(x.id) === sel.value); out.textContent = p ? 'Tồn sổ sách hiện tại: ' + soLuong(p.so_luong_ton) + ' ' + (p.dvt || '') + ' · giá vốn bình quân ' + KD.tienVnd(p.gia_von_bq) : ''; };

  /* ── Tab Kho kế toán (tồn theo nhóm) ── */
  const kpi = (pfx, k, v, phu, title) => { const el = document.querySelector('#' + pfx + '-kpi [data-kpi="' + k + '"]'); if (!el) return; el.querySelector('[data-v]').innerHTML = v; el.querySelector('[data-v]').title = title || ''; el.querySelector('[data-phu]').innerHTML = phu || ''; };
  let luotKho = 0, KHO = [];
  /* QA nhất quán 25/09: 4 SP (BẬP-BÊNH-MÂY, KỆ-TIVI, SOFA, ĐỆM-ĐÔN) có Giá trị tồn ≠ Tồn × Giá vốn BQ vì luồng
     hoàn thành đơn (external.py) trừ số lượng tồn nhưng KHÔNG trừ giá trị tồn. Không tự sửa số ở đây (thẻ/Cân đối
     dùng cùng giá trị sổ) — đánh dấu dòng lệch để kế toán thấy; lệch do làm tròn giá BQ (≤ 1đ × SL) bỏ qua. */
  const lechGt = (p, ton) => { const ch = (+p.gia_tri_ton || 0) - ton * (+p.gia_von_bq || 0);
    return Math.abs(ch) > Math.max(1, Math.abs(ton)) ? '<span class="kt-khach__ma kt-so--xau">lệch ' + (ch > 0 ? '+' : '−') + KD.tien(Math.abs(Math.round(ch))) + KD.tip('Tồn × giá vốn BQ = ' + KD.tienVnd(Math.round(ton * (+p.gia_von_bq || 0))) + ' — giá trị sổ lệch ' + KD.tienVnd(Math.round(ch)) + ' (xuất bán chưa trừ giá trị tồn).', 'kd-tip--trai') + '</span>' : ''; };
  async function taiKho() {
    const l = ++luotKho;
    $('kk-cuon').hidden = false; $('kk-tt').innerHTML = ''; $('kk-tfoot').innerHTML = ''; $('kk-tbody').innerHTML = KT.hangCho(8, 8);
    ['so_sp', 'tong_sl', 'gia_tri'].forEach((k) => kpi('kk', k, '<span class="kd-skel kd-skel--kpi"></span>'));
    try {
      await napNhom(); if (l !== luotKho) return;
      // Đọc ô lọc SAU khi nạp nhóm: nhóm trên link đã bị xoá thì ô về "Tất cả" và dữ liệu cũng không lọc theo nó.
      const q = $('kk-q').value.trim(), nhom = $('kk-nhom').value, tatCa = $('kk-active').value === 'false';
      ghiHash();
      const [cay, ds] = await Promise.all([KD.api('/api/inventory/balance' + (q ? '?q=' + encodeURIComponent(q) : '')),
        KD.api('/api/product?' + KT.url.qs({ page: 1, size: 500, q, category_id: nhom, active_only: tatCa ? 'false' : 'true' }))]);
      if (l !== luotKho) return;
      const theoId = {}; phang(cay).forEach((n) => (n.products || []).forEach((p) => { theoId[p.product_id] = p; }));
      KHO = (ds.items || []).map((p) => Object.assign({}, p, { gia_tri_ton: theoId[p.id] ? +theoId[p.id].gia_tri_ton : (+p.so_luong_ton || 0) * (+p.gia_von_bq || 0) }));
      // Thẻ số theo đúng trang cũ: cộng dồn cây /api/inventory/balance (chỉ SP đang dùng, đã lọc theo ô tìm) + tổng SP /api/product.
      // Đang lọc nhóm thì chỉ cộng SP của ĐÚNG nhóm đó (khớp /api/product?category_id=, không gồm nhóm con) — bản trước thẻ đứng yên khi lọc nhóm.
      let tsl = 0, tgt = 0;
      if (nhom) { const nut = phang(cay).find((n) => String(n.category_id) === nhom); ((nut && nut.products) || []).forEach((p) => { tsl += +p.so_luong_ton || 0; tgt += +p.gia_tri_ton || 0; }); }
      else cay.forEach((n) => { tsl += +n.tong_sl || 0; tgt += +n.tong_gia_tri || 0; });
      // Không lọc gì thì tổng SP đang dùng = ds.total vừa tải → khỏi gọi thêm /api/product?size=1.
      const soSp = !q && !nhom && !tatCa ? ds.total || 0 : (await KD.api('/api/product?page=1&size=1')).total || 0; if (l !== luotKho) return;
      kpi('kk', 'so_sp', H.dem(soSp, 'sản phẩm'), 'Đang dùng · ' + KD.soDem(NHOM.length) + ' nhóm');
      kpi('kk', 'tong_sl', '<span>' + soLuong(tsl) + '</span>', 'Mọi đơn vị tính' + (q || nhom ? ' (theo bộ lọc)' : ''));
      kpi('kk', 'gia_tri', H.tienKpi(tgt), 'Tồn × giá vốn BQ' + KD.tip('Giá trị tồn = số lượng tồn × giá vốn bình quân gia quyền. Sản phẩm đã có biến động kho thì chỉ ngừng dùng, không xoá được.', 'kd-tip--trai'), KD.tienVnd(tgt));
      $('kk-dem').textContent = KD.soDem(KHO.length) + ' sản phẩm' + (ds.total > KHO.length ? ' (hiện ' + KD.soDem(KHO.length) + ' / ' + KD.soDem(ds.total) + ')' : '');
      if (!KHO.length) { $('kk-cuon').hidden = true; $('kk-tt').innerHTML = KD.khoiRong(q || nhom ? 'Không có sản phẩm khớp bộ lọc' : 'Chưa có sản phẩm kế toán', q || nhom ? 'Thử bỏ bớt điều kiện lọc.' : 'Sản phẩm tự tạo khi Mua hàng nhập PO, hoặc bấm "Thêm sản phẩm kế toán".'); return; }
      const nhomTheoId = {}; NHOM.forEach((c) => { nhomTheoId[c.id] = c; });
      const nhomSp = {}; KHO.forEach((p) => { (nhomSp[p.category_id] = nhomSp[p.category_id] || []).push(p); });
      const thuTu = phang(CAY).map((n) => n.id).filter((id) => nhomSp[id]).concat(Object.keys(nhomSp).map(Number).filter((id) => !phang(CAY).some((n) => n.id === id)));
      $('kk-tbody').innerHTML = thuTu.map((cid) => { const g = nhomSp[cid], c = nhomTheoId[cid] || {};
        const sl = g.reduce((a, p) => a + (+p.so_luong_ton || 0), 0), gt = g.reduce((a, p) => a + p.gia_tri_ton, 0);
        return '<tr class="kt-kk-nhom-dong"><th scope="rowgroup" colspan="2">' + (c.ma_nhom ? '<span class="kd-chip kd-chip--xam">' + esc(c.ma_nhom) + '</span> ' : '') + esc(c.ten_nhom || 'Chưa phân nhóm') + ' <span class="kd-meta">· ' + KD.soDem(g.length) + ' sản phẩm</span></th><td class="num">' + soLuong(sl) + '</td><td></td><td class="num">' + KD.tien(gt) + '</td><td colspan="2"></td><td class="kd-col-act"></td></tr>'
          + g.map((p) => { const ton = +p.so_luong_ton || 0;
            return '<tr data-id="' + p.id + '"><td>' + H.ten(p.ten_sp || p.ma_sp, p.ma_sp) + '</td><td>' + esc(p.dvt || '—') + '</td>'
              + '<td class="num">' + H.pill(ton <= 0 ? 'danger' : ton < 5 ? 'warning' : 'success', soLuong(ton)) + '</td><td class="num">' + KD.tien(p.gia_von_bq) + '</td><td class="num">' + KD.tien(p.gia_tri_ton) + lechGt(p, ton) + '</td>'
              + '<td class="num">' + (+p.gia_ban_mac_dinh > 0 ? KD.tien(p.gia_ban_mac_dinh) : '<span class="kd-muted">Chưa đặt</span>') + '</td><td>' + (p.active ? H.pill('success', 'Đang dùng') : H.pill('muted', 'Ngừng dùng')) + '</td>'
              + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu-kk="' + p.id + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(p.ma_sp) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>'; }).join(''); }).join('');
      const csl = KHO.reduce((a, p) => a + (+p.so_luong_ton || 0), 0), cgt = KHO.reduce((a, p) => a + p.gia_tri_ton, 0);
      $('kk-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng ' + KD.soDem(KHO.length) + ' sản phẩm đang hiện</th><td class="num">' + soLuong(csl) + '</td><td></td><td class="num">' + KD.tien(cgt) + '</td><td colspan="2"></td><td class="kd-col-act"></td></tr>';
    } catch (e) { if (l !== luotKho) return; $('kk-cuon').hidden = true; ['so_sp', 'tong_sl', 'gia_tri'].forEach((k) => kpi('kk', k, '<span class="kd-muted">—</span>')); KD.khoiLoi($('kk-tt'), 'Không tải được kho kế toán', e, taiKho); }
  }
  $('kk-q').addEventListener('input', KD.debounce(taiKho, 350));
  ['kk-nhom', 'kk-active'].forEach((id) => $(id).addEventListener('change', taiKho));
  $('kk-dat-lai').addEventListener('click', () => datLaiLoc('kk', taiKho));
  $('kk-loc').addEventListener('submit', (e) => e.preventDefault());
  $('kk-tbody').addEventListener('click', (e) => { const b = e.target.closest('[data-menu-kk]'); if (!b) return; const p = KHO.find((x) => String(x.id) === b.dataset.menuKk); if (!p) return;
    KD.menu(b, [{ nhan: 'Sửa sản phẩm kế toán', icon: 'bi-pencil', onClick: () => moSp(p) },
      { nhan: 'Lập phiếu kho', icon: 'bi-box-arrow-in-down', onClick: () => moMv(p.id) }, { nhan: 'Kiểm kê', icon: 'bi-clipboard-check', onClick: () => moKk(p.id) },
      { nhan: 'Xem biến động', icon: 'bi-clock-history', onClick: () => { $('mv-sp').value = String(p.id); daTai.bien_dong = true; tabs.chon('bien_dong'); taiMv(); } },
      '-', { nhan: 'Xoá', icon: 'bi-trash', danger: true, onClick: () => hoiXoa('Xoá sản phẩm kế toán ' + p.ma_sp + '?', 'Chỉ xoá được khi chưa có biến động kho. Sản phẩm đã nhập / xuất thì chọn Sửa → bỏ tích "Đang dùng".', async () => { await KD.api('/api/product/' + p.id, XOA); SP = []; taiKho(); }) }]); });

  /* Thêm / sửa sản phẩm kế toán */
  const dlgSp = $('kk-dlg-sp'); let spSua = null; oTien($('kk-sp-gia'));
  async function moSp(p) {
    try { await napNhom(); } catch (e) { return bao('err', 'Không tải được nhóm hàng: ' + e.message); }
    spSua = p || null; $('kk-form-sp').reset(); $('kk-sp-td').textContent = p ? 'Sửa sản phẩm kế toán ' + p.ma_sp : 'Thêm sản phẩm kế toán';
    $('kk-sp-ma').value = p ? p.ma_sp : ''; $('kk-sp-ten').value = p ? p.ten_sp : ''; $('kk-sp-dvt').value = p ? p.dvt || '' : 'cái';
    $('kk-sp-nhom').value = p ? String(p.category_id) : ($('kk-nhom').value || (phang(CAY)[0] ? String(phang(CAY)[0].id) : ''));
    $('kk-sp-gia').value = p && +p.gia_ban_mac_dinh > 0 ? KD.tien(p.gia_ban_mac_dinh) : ''; $('kk-sp-active').checked = p ? !!p.active : true;
    KD.moHopThoai(dlgSp); $(p ? 'kk-sp-ten' : 'kk-sp-ma').focus();
  }
  $('kk-them').addEventListener('click', () => moSp(null));
  $('kk-form-sp').addEventListener('submit', async (e) => {
    e.preventDefault(); const ma = $('kk-sp-ma').value.trim(), ten = $('kk-sp-ten').value.trim(), cat = +$('kk-sp-nhom').value;
    if (!ma) { $('kk-sp-ma').focus(); return KD.baoLoiHopThoai(dlgSp, 'Nhập mã sản phẩm.'); }
    if (!ten) { $('kk-sp-ten').focus(); return KD.baoLoiHopThoai(dlgSp, 'Nhập tên sản phẩm.'); }
    if (!cat) return KD.baoLoiHopThoai(dlgSp, 'Chọn nhóm hàng kế toán — tạo nhóm ở tab Nhóm hàng kế toán nếu chưa có.');
    const body = { ma_sp: ma, ten_sp: ten, category_id: cat, dvt: $('kk-sp-dvt').value.trim() || 'cái', gia_ban_mac_dinh: docTien($('kk-sp-gia').value), active: $('kk-sp-active').checked };
    const nut = $('kk-sp-ok'); nut.disabled = true;
    try { if (spSua) await KD.api('/api/product/' + spSua.id, JSON_('PUT', body)); else await KD.api('/api/product', KD.JSON_POST(body));
      dlgSp.close(); bao('ok', (spSua ? 'Đã cập nhật ' : 'Đã thêm ') + ma); SP = []; taiKho(); }
    catch (err) { KD.baoLoiHopThoai(dlgSp, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Tab Nhóm hàng kế toán ── */
  async function taiNhom() {
    $('kn-cuon').hidden = false; $('kn-tt').innerHTML = ''; $('kn-tbody').innerHTML = KT.hangCho(5, 4);
    try {
      await napNhom(true); const ds = phang(CAY);
      if (!ds.length) { $('kn-cuon').hidden = true; $('kn-tt').innerHTML = KD.khoiRong('Chưa có nhóm hàng kế toán', 'Bấm "Thêm nhóm" để tạo nhóm đầu tiên.'); return; }
      $('kn-tbody').innerHTML = ds.map((n) => '<tr><td><span class="kd-chip kd-chip--xam">' + esc(n.ma_nhom) + '</span></td><td><span class="kt-kn-ten" style="--sau:' + n.sau + '">' + (n.sau ? '<i class="bi bi-arrow-return-right kd-muted" aria-hidden="true"></i> ' : '') + esc(n.ten_nhom) + '</span></td>'
        + '<td class="num">' + KD.soDem(n.product_count || 0) + '</td><td class="num">' + KD.soDem(n.display_order || 0) + '</td>'
        + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu-kn="' + n.id + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với nhóm ' + esc(n.ten_nhom) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>').join('');
    } catch (e) { $('kn-cuon').hidden = true; KD.khoiLoi($('kn-tt'), 'Không tải được nhóm hàng kế toán', e, taiNhom); }
  }
  $('kn-tbody').addEventListener('click', (e) => { const b = e.target.closest('[data-menu-kn]'); if (!b) return; const n = NHOM.find((x) => String(x.id) === b.dataset.menuKn); if (!n) return;
    const dem = (phang(CAY).find((x) => x.id === n.id) || {}).product_count || 0;
    KD.menu(b, [{ nhan: 'Sửa nhóm', icon: 'bi-pencil', onClick: () => moNhom(n) }, '-',
      { nhan: 'Xoá nhóm', icon: 'bi-trash', danger: true, onClick: () => hoiXoa('Xoá nhóm ' + n.ten_nhom + '?', dem ? 'Nhóm đang có ' + KD.soDem(dem) + ' sản phẩm — máy chủ sẽ từ chối; chuyển sản phẩm sang nhóm khác trước.' : 'Xoá hẳn nhóm khỏi danh mục, không hoàn tác được.', async () => { await KD.api('/api/product-category/' + n.id, XOA); taiNhom(); }) }]); });
  const dlgNhom = $('kk-dlg-nhom'); let nhomSua = null;
  async function moNhom(n) {
    try { await napNhom(); } catch (e) { return bao('err', e.message); }
    nhomSua = n || null; $('kk-form-nhom').reset(); $('kk-nhom-td').textContent = n ? 'Sửa nhóm ' + n.ten_nhom : 'Thêm nhóm hàng kế toán';
    H.napChon($('kk-nhom-cha'), phang(CAY).filter((x) => !n || x.id !== n.id).map((x) => [String(x.id), '  '.repeat(x.sau) + x.ten_nhom]), '— Không có (nhóm gốc) —', n && n.parent_id ? String(n.parent_id) : '');
    $('kk-nhom-ma').value = n ? n.ma_nhom : ''; $('kk-nhom-ten').value = n ? n.ten_nhom : ''; $('kk-nhom-tt').value = n ? n.display_order || 0 : 0;
    KD.moHopThoai(dlgNhom); $(n ? 'kk-nhom-ten' : 'kk-nhom-ma').focus();
  }
  $('kn-them').addEventListener('click', () => moNhom(null));
  $('kk-form-nhom').addEventListener('submit', async (e) => {
    e.preventDefault(); const ma = $('kk-nhom-ma').value.trim(), ten = $('kk-nhom-ten').value.trim();
    if (!ma) { $('kk-nhom-ma').focus(); return KD.baoLoiHopThoai(dlgNhom, 'Nhập mã nhóm.'); }
    if (!ten) { $('kk-nhom-ten').focus(); return KD.baoLoiHopThoai(dlgNhom, 'Nhập tên nhóm.'); }
    const body = { ma_nhom: ma, ten_nhom: ten, parent_id: +$('kk-nhom-cha').value || null, display_order: parseInt($('kk-nhom-tt').value || '0', 10) || 0, active: true };
    const nut = $('kk-nhom-ok'); nut.disabled = true;
    try { if (nhomSua) await KD.api('/api/product-category/' + nhomSua.id, JSON_('PUT', body)); else await KD.api('/api/product-category', KD.JSON_POST(body));
      dlgNhom.close(); bao('ok', (nhomSua ? 'Đã cập nhật nhóm ' : 'Đã thêm nhóm ') + ten); taiNhom(); }
    catch (err) { KD.baoLoiHopThoai(dlgNhom, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Tab Biến động kho ── */
  let luotMv = 0;
  async function taiMv() {
    const l = ++luotMv; $('mv-cuon').hidden = false; $('mv-tt').innerHTML = ''; $('mv-tbody').innerHTML = KT.hangCho(7, 8);
    ['nhap', 'xuat', 'dieu_chinh'].forEach((k) => kpi('mv', k, '<span class="kd-skel kd-skel--kpi"></span>'));
    try {
      await napSp(); if (l !== luotMv) return;
      const tu = $('mv-tu').value, den = $('mv-den').value;
      ghiHash();
      if (tu && den && tu > den) {   // khoảng ngày ngược → máy chủ trả rỗng, dễ tưởng "không có biến động"
        ['nhap', 'xuat', 'dieu_chinh'].forEach((k) => kpi('mv', k, '<span class="kd-muted">—</span>')); $('mv-dem').textContent = ''; $('mv-pham-vi').textContent = '';
        $('mv-cuon').hidden = true; $('mv-tt').innerHTML = KD.khoiRong('Khoảng ngày chưa hợp lệ', 'Từ ngày phải trước hoặc bằng đến ngày.'); return;
      }
      const rows = await KD.api('/api/inventory/movement?' + KT.url.qs({ product_id: $('mv-sp').value, loai: $('mv-loai').value, from: tu, to: den, limit: 1000 }));
      if (l !== luotMv) return;
      ['nhap', 'xuat', 'dieu_chinh'].forEach((k) => { const g = rows.filter((m) => m.loai === k);
        kpi('mv', k, H.dem(g.length, 'phiếu'), g.length ? 'SL ' + soLuong(g.reduce((a, m) => a + (+m.so_luong || 0), 0)) + ' · ' + KD.tienVnd(g.reduce((a, m) => a + (+m.thanh_tien || 0), 0)) : ''); });
      $('mv-pham-vi').textContent = rows.length >= 1000 ? 'Hiện 1.000 phiếu mới nhất — lọc theo sản phẩm hoặc ngày để xem đủ.' : '';
      $('mv-dem').innerHTML = KD.soDem(rows.length) + ' phiếu' + KD.tip('Phiếu xuất do đơn hàng hoàn thành tự sinh (nguồn Đơn hàng); phiếu nhập từ PO của Mua hàng.', 'kd-tip--trai');
      if (!rows.length) { $('mv-cuon').hidden = true; $('mv-tt').innerHTML = KD.khoiRong('Chưa có biến động kho', 'Đổi bộ lọc hoặc lập phiếu kho.'); return; }
      $('mv-tbody').innerHTML = rows.map((m) => { const lo = LOAI[m.loai] || ['muted', m.loai];
        return '<tr><td>' + KD.ngay(m.ngay) + '</td><td><span class="kt-khach__ten">' + esc(m.ten_sp || '') + '</span><span class="kt-khach__ma">' + esc(m.ma_sp || '') + '</span>' + (m.ghi_chu ? '<span class="kt-khach__ma kt-cat" title="' + esc(m.ghi_chu) + '"><i class="bi bi-sticky" aria-hidden="true"></i> ' + esc(m.ghi_chu) + '</span>' : '') + '</td><td>' + H.pill(lo[0], lo[1]) + '</td>'
          + '<td class="num">' + soLuong(m.so_luong) + '</td><td class="num">' + KD.tien(m.don_gia) + '</td><td class="num">' + KD.tien(m.thanh_tien) + '</td>'
          + '<td>' + esc(NGUON[m.source_app] || m.source_app || '—') + (m.source_doc_id ? '<span class="kt-khach__ma">' + esc(m.source_doc_id) + '</span>' : '') + '</td></tr>'; }).join('');
    } catch (e) { if (l !== luotMv) return; $('mv-cuon').hidden = true; ['nhap', 'xuat', 'dieu_chinh'].forEach((k) => kpi('mv', k, '<span class="kd-muted">—</span>')); KD.khoiLoi($('mv-tt'), 'Không tải được biến động kho', e, taiMv); }
  }
  ['mv-sp', 'mv-loai', 'mv-tu', 'mv-den'].forEach((id) => $(id).addEventListener('change', taiMv));
  $('mv-dat-lai').addEventListener('click', () => datLaiLoc('mv', taiMv));
  $('mv-loc').addEventListener('submit', (e) => e.preventDefault());
  const dlgMv = $('kk-dlg-mv'); oTien($('kk-mv-dg'));
  $('kk-mv-sp').addEventListener('change', () => tonHint($('kk-mv-sp'), $('kk-mv-ton')));
  $('kk-mv-loai').addEventListener('change', () => { $('kk-mv-dg').disabled = $('kk-mv-loai').value !== 'nhap'; if ($('kk-mv-dg').disabled) $('kk-mv-dg').value = ''; });
  async function moMv(pid) {
    try { await napSp(); } catch (e) { return bao('err', e.message); }
    $('kk-form-mv').reset(); $('kk-mv-ngay').value = homNay(); $('kk-mv-dg').disabled = false;
    $('kk-mv-sp').value = pid ? String(pid) : ($('mv-sp').value || (SP[0] ? String(SP[0].id) : '')); tonHint($('kk-mv-sp'), $('kk-mv-ton'));
    KD.moHopThoai(dlgMv); $('kk-mv-sl').focus();
  }
  $('mv-them').addEventListener('click', () => moMv(null));
  $('kk-form-mv').addEventListener('submit', async (e) => {
    e.preventDefault(); const sl = docSoLe($('kk-mv-sl').value), loai = $('kk-mv-loai').value;
    if (!$('kk-mv-ngay').value) return KD.baoLoiHopThoai(dlgMv, 'Chọn ngày.');
    if (!$('kk-mv-sp').value) return KD.baoLoiHopThoai(dlgMv, 'Chọn sản phẩm.');
    if (sl == null || !Number.isFinite(sl) || sl === 0 || (loai !== 'dieu_chinh' && sl < 0)) { $('kk-mv-sl').focus(); return KD.baoLoiHopThoai(dlgMv, loai === 'dieu_chinh' ? 'Nhập số lượng điều chỉnh khác 0 (âm để giảm tồn).' : 'Nhập số lượng lớn hơn 0.'); }
    const body = { ngay: $('kk-mv-ngay').value, product_id: +$('kk-mv-sp').value, loai, so_luong: sl, don_gia: loai === 'nhap' ? docTien($('kk-mv-dg').value) : 0, ghi_chu: $('kk-mv-gc').value.trim() || null, source_app: 'manual' };
    const nut = $('kk-mv-ok'); nut.disabled = true;
    try { await KD.api('/api/inventory/movement', KD.JSON_POST(body)); dlgMv.close(); bao('ok', 'Đã lưu phiếu ' + (LOAI[loai] || [0, loai])[1].toLowerCase()); SP = []; daTai.kho = false; if (tab === 'bien_dong') taiMv(); else if (tab === 'kho') { daTai.kho = true; taiKho(); } }
    catch (err) { KD.baoLoiHopThoai(dlgMv, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  /* Kiểm kê */
  const dlgKk = $('kk-dlg-kk');
  $('kk-kk-sp').addEventListener('change', () => tonHint($('kk-kk-sp'), $('kk-kk-ton')));
  async function moKk(pid) {
    try { await napSp(); } catch (e) { return bao('err', e.message); }
    $('kk-form-kk').reset(); $('kk-kk-ngay').value = homNay();
    $('kk-kk-sp').value = pid ? String(pid) : ($('mv-sp').value || (SP[0] ? String(SP[0].id) : '')); tonHint($('kk-kk-sp'), $('kk-kk-ton'));
    KD.moHopThoai(dlgKk); $('kk-kk-tt').focus();
  }
  $('mv-kiem-ke').addEventListener('click', () => moKk(null));
  $('kk-form-kk').addEventListener('submit', async (e) => {
    e.preventDefault(); const tt = docSoLe($('kk-kk-tt').value);
    if (!$('kk-kk-ngay').value) return KD.baoLoiHopThoai(dlgKk, 'Chọn ngày kiểm kê.');
    if (!$('kk-kk-sp').value) return KD.baoLoiHopThoai(dlgKk, 'Chọn sản phẩm.');
    if (tt == null || !Number.isFinite(tt) || tt < 0) { $('kk-kk-tt').focus(); return KD.baoLoiHopThoai(dlgKk, 'Nhập tồn thực tế (0 trở lên).'); }
    const nut = $('kk-kk-ok'); nut.disabled = true;
    try { const kq = await KD.api('/api/inventory/kiem-ke', KD.JSON_POST({ ngay: $('kk-kk-ngay').value, product_id: +$('kk-kk-sp').value, ton_thuc_te: tt, ghi_chu: $('kk-kk-gc').value.trim() || null }));
      dlgKk.close(); bao('ok', 'Đã chốt kiểm kê' + (kq && kq.chenh_lech != null ? ' — chênh lệch ' + soLuong(kq.chenh_lech) : '')); SP = []; daTai.kho = false; if (tab === 'bien_dong') taiMv(); else if (tab === 'kho') { daTai.kho = true; taiKho(); } }
    catch (err) { KD.baoLoiHopThoai(dlgKk, 'Chưa chốt được: ' + err.message); } finally { nut.disabled = false; }
  });

  /* ── Tab Cảnh báo tồn ── */
  let cbTaiSan = null;
  async function taiCb() {
    $('cb-cuon').hidden = false; $('cb-tt').innerHTML = ''; $('cb-tbody').innerHTML = KT.hangCho(5, 4);
    try {
      // Lần đầu mở tab dùng lại kết quả đã tải sẵn để đếm trên nhãn tab (bản trước gọi /api/inventory/canh-bao 2 lần).
      const cho = cbTaiSan; cbTaiSan = null;
      const rows = await (cho || KD.api('/api/inventory/canh-bao')); $('cb-dem-tab').textContent = rows.length ? '(' + KD.soDem(rows.length) + ')' : '';
      if (!rows.length) { $('cb-cuon').hidden = true; $('cb-tt').innerHTML = KD.khoiRong('Tất cả tồn kho đang trong ngưỡng', 'Chỉ sản phẩm đã đặt ngưỡng tối thiểu / tối đa mới được theo dõi.'); return; }
      $('cb-tbody').innerHTML = rows.map((r) => '<tr><td>' + H.ten(r.ten_sp || r.ma_sp, r.ma_sp) + '</td><td class="num">' + soLuong(r.so_luong_ton) + '</td><td class="num">' + soLuong(r.ton_min) + '</td><td class="num">' + soLuong(r.ton_max) + '</td>'
        + '<td>' + (r.loai_canh_bao === 'duoi_min' ? H.pill('danger', 'Dưới tối thiểu') : r.loai_canh_bao === 'tren_max' ? H.pill('warning', 'Vượt tối đa') : H.pill('muted', r.loai_canh_bao || '—')) + '</td></tr>').join('');
    } catch (e) { $('cb-cuon').hidden = true; KD.khoiLoi($('cb-tt'), 'Không tải được cảnh báo tồn', e, taiCb); }
  }

  /* ── Tab BOM giá vốn ── */
  let BOM = [], luotBom = 0;
  async function taiBom() {
    const l = ++luotBom;   // đổi lọc nhanh: kết quả lần trước về sau không được đè lần mới
    $('bom-cuon').hidden = false; $('bom-tt').innerHTML = ''; $('bom-tbody').innerHTML = KT.hangCho(7, 4);
    try {
      await napNhom(); if (l !== luotBom) return;
      ghiHash();
      const qs = KT.url.qs({ category_id: $('bom-nhom').value, active: $('bom-active').value });
      const kq = await KD.api('/api/bom' + (qs ? '?' + qs : '')); if (l !== luotBom) return;
      BOM = kq;
      if (!BOM.length) { $('bom-cuon').hidden = true; $('bom-tt').innerHTML = KD.khoiRong('Chưa có BOM nào' + ($('bom-nhom').value || $('bom-active').value ? ' khớp bộ lọc' : ''), 'Bấm "Thêm BOM" để khai báo định mức nguyên vật liệu cho một nhóm sản phẩm.'); return; }
      $('bom-tbody').innerHTML = BOM.map((b) => '<tr><td>' + H.ten(b.ten_bom || b.ma_bom, b.ma_bom) + '</td><td>' + (b.ten_nhom ? '<span class="kd-chip kd-chip--xam">' + esc(b.ten_nhom) + '</span>' : '—') + '</td>'
        + '<td>' + KD.ngay(b.effective_from) + ' → ' + (b.effective_to ? KD.ngay(b.effective_to) : 'nay') + '</td><td class="num">' + KD.soDem(b.so_items) + '</td><td class="num"><b>' + KD.tien(b.tong_gia_von) + '</b></td>'
        + '<td>' + (b.active ? H.pill('success', 'Đang áp dụng') : H.pill('muted', 'Đã ngừng')) + '</td><td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu-bom="' + b.id + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(b.ma_bom) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td></tr>').join('');
    } catch (e) { if (l !== luotBom) return; $('bom-cuon').hidden = true; KD.khoiLoi($('bom-tt'), 'Không tải được BOM', e, taiBom); }
  }
  ['bom-nhom', 'bom-active'].forEach((id) => $(id).addEventListener('change', taiBom));
  $('bom-dat-lai').addEventListener('click', () => datLaiLoc('bom', taiBom));
  $('bom-loc').addEventListener('submit', (e) => e.preventDefault());
  $('bom-tbody').addEventListener('click', (e) => { const b = e.target.closest('[data-menu-bom]'); if (!b) return; const x = BOM.find((y) => String(y.id) === b.dataset.menuBom); if (!x) return;
    KD.menu(b, [{ nhan: 'Sửa BOM', icon: 'bi-pencil', onClick: () => moBom(x.id) },
      { nhan: 'Tạo phiên bản mới', icon: 'bi-files', onClick: () => hoiXoa('Tạo phiên bản mới từ ' + x.ma_bom + '?', 'Bản hiện tại sẽ đóng hiệu lực đến hôm qua; bản mới chép nguyên danh sách nguyên vật liệu để sửa giá.', async () => { await KD.api('/api/bom/' + x.id + '/clone', KD.JSON_POST({})); taiBom(); }, 'Tạo phiên bản') },
      '-', { nhan: 'Ngừng áp dụng', icon: 'bi-trash', danger: true, onClick: () => hoiXoa('Ngừng áp dụng ' + x.ma_bom + '?', 'BOM chuyển sang "Đã ngừng" (không xoá dữ liệu), không còn dùng để tính biên lãi.', async () => { await KD.api('/api/bom/' + x.id, XOA); taiBom(); }, null) }]); });
  const dlgBom = $('kk-dlg-bom'); let bomSua = null;
  const dongNvl = (it) => '<tr><td><input class="kd-input" data-nvl="ten_nvl" maxlength="255" value="' + esc(it.ten_nvl || '') + '" placeholder="Vd: Gỗ sồi" aria-label="Tên nguyên vật liệu"></td><td><input class="kd-input kt-bom-dvt" data-nvl="dvt" maxlength="32" value="' + esc(it.dvt || '') + '" placeholder="m³" aria-label="Đơn vị tính"></td>'
    + '<td><input class="kd-input num kt-bom-so" data-nvl="so_luong" inputmode="decimal" value="' + (it.so_luong ? String(+it.so_luong).replace('.', ',') : '') + '" aria-label="Số lượng"></td><td><input class="kd-input num kt-bom-so" data-nvl="don_gia" inputmode="numeric" value="' + (+it.don_gia ? KD.tien(it.don_gia) : '') + '" aria-label="Đơn giá"></td>'
    + '<td class="num" data-tt>0</td><td><button type="button" class="kd-icon-btn" data-xoa-nvl aria-label="Xoá dòng"><i class="bi bi-x-lg" aria-hidden="true"></i></button></td></tr>';
  const docNvl = () => [...$('kk-bom-nvl').querySelectorAll('tr')].map((tr) => ({ ten_nvl: tr.querySelector('[data-nvl=ten_nvl]').value.trim(), dvt: tr.querySelector('[data-nvl=dvt]').value.trim() || null, so_luong: docSoLe(tr.querySelector('[data-nvl=so_luong]').value) || 0, don_gia: docTien(tr.querySelector('[data-nvl=don_gia]').value), tr }));
  function tinhBom() { let t = 0; docNvl().forEach((x) => { const v = Math.round(x.so_luong * x.don_gia); t += v; x.tr.querySelector('[data-tt]').textContent = KD.tien(v); }); $('kk-bom-tong').textContent = KD.tien(t); }
  $('kk-bom-nvl').addEventListener('input', (e) => { if (e.target.matches('[data-nvl=don_gia]')) { const n = docTien(e.target.value); e.target.value = n ? KD.tien(n) : ''; } tinhBom(); });
  $('kk-bom-nvl').addEventListener('click', (e) => { const b = e.target.closest('[data-xoa-nvl]'); if (!b) return; b.closest('tr').remove(); if (!$('kk-bom-nvl').children.length) $('kk-bom-nvl').innerHTML = dongNvl({}); tinhBom(); });
  $('kk-bom-them-nvl').addEventListener('click', () => { $('kk-bom-nvl').insertAdjacentHTML('beforeend', dongNvl({})); $('kk-bom-nvl').lastElementChild.querySelector('input').focus(); });
  async function moBom(id) {
    try { await napNhom(); bomSua = id ? await KD.api('/api/bom/' + id) : null; } catch (e) { return bao('err', 'Không mở được BOM: ' + e.message); }
    const b = bomSua || {}; $('kk-form-bom').reset(); $('kk-bom-td').textContent = bomSua ? 'Sửa BOM ' + b.ma_bom : 'Thêm BOM';
    $('kk-bom-ma').value = b.ma_bom || ''; $('kk-bom-ten').value = b.ten_bom || ''; $('kk-bom-nhom').value = b.category_id ? String(b.category_id) : ($('bom-nhom').value || (phang(CAY)[0] ? String(phang(CAY)[0].id) : ''));
    $('kk-bom-tu').value = b.effective_from || homNay(); $('kk-bom-den').value = b.effective_to || ''; $('kk-bom-gc').value = b.ghi_chu || '';
    $('kk-bom-nvl').innerHTML = ((b.items || []).length ? b.items : [{}]).map(dongNvl).join(''); tinhBom();
    KD.moHopThoai(dlgBom); $('kk-bom-ten').focus();
  }
  $('bom-them').addEventListener('click', () => moBom(null));
  $('kk-form-bom').addEventListener('submit', async (e) => {
    e.preventDefault(); const ten = $('kk-bom-ten').value.trim(), cat = +$('kk-bom-nhom').value;
    if (!ten) { $('kk-bom-ten').focus(); return KD.baoLoiHopThoai(dlgBom, 'Nhập tên BOM.'); }
    if (!cat) return KD.baoLoiHopThoai(dlgBom, 'Chọn nhóm sản phẩm áp dụng.');
    if ($('kk-bom-den').value && $('kk-bom-tu').value && $('kk-bom-den').value < $('kk-bom-tu').value) return KD.baoLoiHopThoai(dlgBom, 'Ngày hết hiệu lực phải sau ngày bắt đầu.');
    const ds = docNvl(), items = ds.filter((x) => x.ten_nvl && x.so_luong > 0 && x.don_gia > 0).map(({ tr, ...x }) => x);
    if (!items.length) return KD.baoLoiHopThoai(dlgBom, 'Cần ít nhất một nguyên vật liệu có tên, số lượng và đơn giá lớn hơn 0.');
    if (items.length < ds.filter((x) => x.ten_nvl || x.so_luong || x.don_gia).length) return KD.baoLoiHopThoai(dlgBom, 'Có dòng nguyên vật liệu thiếu tên, số lượng hoặc đơn giá — điền đủ hoặc xoá dòng đó.');
    const body = { ma_bom: $('kk-bom-ma').value.trim() || null, ten_bom: ten, category_id: cat, effective_from: $('kk-bom-tu').value || null, effective_to: $('kk-bom-den').value || null, ghi_chu: $('kk-bom-gc').value.trim() || null, items };
    const nut = $('kk-bom-ok'); nut.disabled = true;
    try { if (bomSua) await KD.api('/api/bom/' + bomSua.id, JSON_('PUT', body)); else await KD.api('/api/bom', KD.JSON_POST(body)); dlgBom.close(); bao('ok', bomSua ? 'Đã cập nhật BOM' : 'Đã thêm BOM'); taiBom(); }
    catch (err) { KD.baoLoiHopThoai(dlgBom, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  /* Biên lãi theo nhóm */
  const dlgMg = $('kk-dlg-margin');
  $('bom-margin').addEventListener('click', () => { const d = new Date(); $('kk-mg-tu').value = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-01'; $('kk-mg-den').value = homNay();
    $('kk-mg-kq').innerHTML = KD.khoiRong('Chọn khoảng ngày rồi bấm Xem', 'So giá vốn BOM đang áp dụng với giá bán bình quân của phiếu xuất trong kỳ.'); KD.moHopThoai(dlgMg); });
  $('kk-form-margin').addEventListener('submit', async (e) => {
    e.preventDefault(); const tu = $('kk-mg-tu').value, den = $('kk-mg-den').value;
    if (!tu || !den) return KD.baoLoiHopThoai(dlgMg, 'Chọn đủ từ ngày và đến ngày.');
    if (tu > den) return KD.baoLoiHopThoai(dlgMg, 'Từ ngày phải trước đến ngày.');
    $('kk-mg-kq').innerHTML = KD.KHUNG_TAI;
    try { const rows = await KD.api('/api/bom/margin-report?' + KT.url.qs({ from: tu, to: den }));
      $('kk-mg-kq').innerHTML = !rows.length ? KD.khoiRong('Chưa có BOM đang áp dụng trong kỳ', 'Khai báo BOM cho nhóm sản phẩm để xem biên lãi.')
        : '<div class="kd-table-scroll"><table class="kd-table kt-bang"><caption class="visually-hidden">Biên lãi theo nhóm</caption><thead><tr><th scope="col">Nhóm</th><th scope="col">BOM</th><th scope="col" class="num">Giá vốn BOM (VND)</th><th scope="col" class="num">Giá bán BQ (VND)</th><th scope="col" class="num">SL xuất</th><th scope="col" class="num">Biên lãi</th></tr></thead><tbody>'
          + rows.map((r) => '<tr><td>' + (r.ma_nhom ? '<span class="kd-chip kd-chip--xam">' + esc(r.ma_nhom) + '</span> ' : '') + esc(r.ten_nhom || '') + '</td><td>' + esc(r.ma_bom || '—') + '</td><td class="num">' + KD.tien(r.bom_gia_von) + '</td><td class="num">' + KD.tien(r.gia_ban_bq) + '</td><td class="num">' + soLuong(r.so_luong_xuat) + '</td>'
            + '<td class="num">' + (r.margin_pct == null ? '<span class="kd-muted">—</span>' : H.pill(+r.margin_pct >= 30 ? 'success' : +r.margin_pct >= 15 ? 'warning' : 'danger', KD.phanTram(r.margin_pct))) + '</td></tr>').join('') + '</tbody></table></div>'; }
    catch (err) { KD.khoiLoi($('kk-mg-kq'), 'Không chạy được báo cáo biên lãi', err, () => $('kk-form-margin').requestSubmit()); }
  });

  /* ── Hộp xác nhận dùng chung ── */
  const dlgX = $('kk-dlg-xoa'); let viecX = null;
  function hoiXoa(td, nd, viec, nhanNut) { viecX = viec; $('kk-xoa-td').textContent = td; $('kk-xoa-nd').textContent = nd;
    $('kk-xoa-ok').innerHTML = nhanNut ? esc(nhanNut) : '<i class="bi bi-trash" aria-hidden="true"></i>Xoá'; $('kk-xoa-ok').className = 'kd-btn ' + (nhanNut ? 'kd-btn--primary' : 'kd-btn--danger');
    KD.moHopThoai(dlgX); dlgX.querySelector('[data-dong]').focus(); }
  $('kk-xoa-ok').addEventListener('click', async () => { const nut = $('kk-xoa-ok'); nut.disabled = true;
    try { await viecX(); dlgX.close(); bao('ok', 'Đã thực hiện'); } catch (e) { KD.baoLoiHopThoai(dlgX, 'Chưa thực hiện được: ' + e.message); } finally { nut.disabled = false; } });

  const TAI = { kho: taiKho, nhom: taiNhom, bien_dong: taiMv, canh_bao: taiCb, bom: taiBom };
  cbTaiSan = KD.api('/api/inventory/canh-bao');
  cbTaiSan.then((r) => { $('cb-dem-tab').textContent = r.length ? '(' + KD.soDem(r.length) + ')' : ''; }).catch(() => { cbTaiSan = null; });
  if (tab !== 'chung') tabs.chon(tab);
})();
