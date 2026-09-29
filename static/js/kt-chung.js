/* ═══════════════════════════════════════════════════════════════════════════
   kt-chung.js — phần dùng chung của các màn Kế toán mới (tiền tố kt-)
   Nạp SAU kd-man-hinh.js. Chỉ chứa thứ KD chưa có:
     · bản đồ nhãn nghiệp vụ kế toán (loại chứng từ, tuổi nợ, trạng thái phiếu)
     · kỳ kế toán (tháng/quý/năm — khác kỳ bán hàng của KD.KY)
     · mở/đóng panel xem nhanh + sắp xếp bảng — chép đúng mẫu kd-bao-gia.js:382-426 / :277-299.
       Đây là lần chép thứ ba trong hệ → ĐỀ XUẤT gộp vào KD ở qlpps-baogia rồi xoá khỏi đây.
   Không định dạng tiền/ngày ở đây: mọi số và ngày đi qua KD.tien / KD.ngay…
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function nhanTu(banDo, ten) {
    return function (key) {
      const x = banDo[key];
      if (!x) { if (key != null && key !== '') console.warn('[' + ten + '] key chưa có nhãn:', key); return { nhan: 'Chưa đặt tên', mau: 'muted' }; }
      return x;
    };
  }
  function pillTu(layNhan) {
    return function (key, nhanRieng) {
      const x = layNhan(key);
      return '<span class="pill pill--' + x.mau + (x.vien ? ' pill--vien' : '') + '">' + esc(nhanRieng || x.nhan) + '</span>';
    };
  }

  /* Loại chứng từ của bút toán (JournalEntry.loai). Key phải khớp backend — xem README mục Hợp đồng API. */
  const LOAI_CT = {
    phieu_thu: { nhan: 'Phiếu thu', ma: 'PT' }, phieu_chi: { nhan: 'Phiếu chi', ma: 'PC' },
    bao_co: { nhan: 'Báo có', ma: 'BC' }, bao_no: { nhan: 'Báo nợ', ma: 'BN' },
    ban_hang: { nhan: 'Bán hàng', ma: 'BH' }, mua_hang: { nhan: 'Mua hàng', ma: 'MH' },
    xuat_kho: { nhan: 'Xuất kho', ma: 'XK' }, luong: { nhan: 'Tiền lương', ma: 'TL' },
    khau_hao: { nhan: 'Khấu hao', ma: 'KH' }, ket_chuyen: { nhan: 'Kết chuyển', ma: 'KC' },
    bu_tru: { nhan: 'Bù trừ công nợ', ma: 'BTCN' },
    khac: { nhan: 'Nghiệp vụ khác', ma: 'NVK' },
  };
  const layLoaiCt = nhanTu(LOAI_CT, 'LOAI_CT');

  /* Nhóm tuổi nợ — nghĩa màu theo Pill README (chưa đến hạn = tốt, 1-30 = chú ý, >30 = hỏng). */
  const TUOI_NO = {
    chua_den_han: { nhan: 'Chưa đến hạn', mau: 'success' },
    qh_1_30: { nhan: 'Quá hạn 1-30', mau: 'warning' },
    qh_31_60: { nhan: 'Quá hạn 31-60', mau: 'danger' },
    qh_tren_60: { nhan: 'Quá hạn >60', mau: 'danger', vien: true },
    da_thu_du: { nhan: 'Đã thu đủ', mau: 'success' },
  };
  /* Trạng thái từng phiếu công nợ. */
  const TT_PHIEU = {
    chua_thu: { nhan: 'Chưa thu', mau: 'danger' },
    thu_mot_phan: { nhan: 'Thu một phần', mau: 'warning' },
    da_thu_du: { nhan: 'Đã thu đủ', mau: 'success' },
    qua_han: { nhan: 'Quá hạn', mau: 'danger', vien: true },
  };

  /* Kỳ kế toán → khoảng ngày ISO. Hôm nay lấy từ máy người dùng.
     Khoá kỳ: lựa chọn nhanh (thang_nay, thang_truoc, quy_nay, nam_nay, hom_nay, 7_ngay, tat_ca, tuy_chinh)
     hoặc KỲ CỤ THỂ (28/09/2026 — bản cũ có ô chọn tháng, bản mới thiếu): '2026-07' = tháng 07/2026,
     '2026-Q3' = quý 3/2026, '2026' = năm 2026 (trọn kỳ). Khoá nằm nguyên trên URL: ?ky=2026-07. */
  const KY = [
    { key: 'thang_nay', nhan: 'Tháng này' }, { key: 'thang_truoc', nhan: 'Tháng trước' },
    { key: 'quy_nay', nhan: 'Quý này' }, { key: 'nam_nay', nhan: 'Năm nay' }, { key: 'tuy_chinh', nhan: 'Tuỳ chỉnh…' },
  ];
  const KY_THEM = { hom_nay: 'Hôm nay', '7_ngay': '7 ngày qua', tat_ca: 'Tất cả thời gian' };
  const SO_THANG_CHON = 24, SO_QUY_CHON = 8, SO_NAM_CHON = 3;   // độ dài danh sách kỳ cụ thể trong ô chọn
  const RE_THANG = /^(\d{4})-(0[1-9]|1[0-2])$/, RE_QUY = /^(\d{4})-Q([1-4])$/, RE_NAM = /^(\d{4})$/;
  const RE_NGAY = /^\d{4}-\d{2}-\d{2}$/;
  const p2 = (n) => String(n).padStart(2, '0');
  const nhanThang = (k) => 'Tháng ' + k.slice(5, 7) + '/' + k.slice(0, 4);
  const nhanQuy = (k) => 'Quý ' + k.slice(6) + '/' + k.slice(0, 4);
  /* Nhóm của khoá kỳ — quyết định kỳ so sánh: thang | quy | nam | ngay | tat_ca | tuy_chinh */
  function loaiKy(key) {
    if (key === 'thang_nay' || key === 'thang_truoc' || RE_THANG.test(key || '')) return 'thang';
    if (key === 'quy_nay' || RE_QUY.test(key || '')) return 'quy';
    if (key === 'nam_nay' || RE_NAM.test(key || '')) return 'nam';
    if (key === 'hom_nay' || key === '7_ngay') return 'ngay';
    if (key === 'tat_ca' || key === 'tuy_chinh') return key;
    return '';
  }
  const kyHopLe = (key, them) => !!key && (KY.some((k) => k.key === key) || (them || []).includes(key) || /^\d{4}(-(0[1-9]|1[0-2])|-Q[1-4])?$/.test(key));
  function khoangKy(key, homNay) {
    const h = homNay || new Date(); const y = h.getFullYear(); const m = h.getMonth();
    const D = (yy, mm, dd) => KD.iso(new Date(yy, mm, dd));
    let x;
    if ((x = RE_THANG.exec(key || ''))) return { tu: D(+x[1], +x[2] - 1, 1), den: D(+x[1], +x[2], 0) };
    if ((x = RE_QUY.exec(key || ''))) { const q0 = (+x[2] - 1) * 3; return { tu: D(+x[1], q0, 1), den: D(+x[1], q0 + 3, 0) }; }
    if ((x = RE_NAM.exec(key || ''))) return { tu: D(+x[1], 0, 1), den: D(+x[1], 11, 31) };
    switch (key) {
      case 'hom_nay': return { tu: KD.iso(h), den: KD.iso(h) };
      case '7_ngay': return { tu: D(y, m, h.getDate() - 6), den: KD.iso(h) };
      case 'tat_ca': return {};
      case 'thang_truoc': return { tu: D(y, m - 1, 1), den: D(y, m, 0) };
      case 'quy_nay': { const q = Math.floor(m / 3) * 3; return { tu: D(y, q, 1), den: KD.iso(h) }; }
      case 'nam_nay': return { tu: D(y, 0, 1), den: KD.iso(h) };
      default: return { tu: D(y, m, 1), den: KD.iso(h) };
    }
  }
  /* Khoảng ngày đang xem theo trạng thái lọc {ky, tu, den} — Tuỳ chỉnh thiếu ngày thì coi như Tháng này. */
  function khoangSt(st) {
    if (st.ky === 'tuy_chinh' && RE_NGAY.test(st.tu || '') && RE_NGAY.test(st.den || '') && st.tu <= st.den) return { tu: st.tu, den: st.den };
    if (st.ky === 'tat_ca') return {};
    return khoangKy(st.ky === 'tuy_chinh' ? 'thang_nay' : st.ky);
  }
  /* Tên kỳ để hiện cho người đọc: "Tháng 07/2026", "Quý 3/2026", "Năm 2025", còn lại "01/09/2026 – 28/09/2026". */
  function nhanKy(key, k) {
    if (RE_THANG.test(key || '')) return nhanThang(key);
    if (RE_QUY.test(key || '')) return nhanQuy(key);
    if (RE_NAM.test(key || '')) return 'Năm ' + key;
    k = k || khoangKy(key);
    return k.tu && k.den ? KD.ngay(k.tu) + ' – ' + KD.ngay(k.den) : 'Tất cả thời gian';
  }

  /* Kỳ so sánh (28/09/2026): tháng → tháng trước · quý → quý trước · năm → CÙNG KỲ năm trước (bản trước
     lùi 9 tháng: "Năm nay" 01/01–28/09/2026 so với 01/04–28/12/2025) · tuỳ chỉnh/ngày → khoảng liền trước
     cùng độ dài (trọn tháng thì lùi đúng số tháng, lẻ ngày thì lùi đúng số ngày).
     Lùi theo tháng giữ vị trí ngày: ngày cuối tháng ↦ ngày cuối tháng, ngày giữa tháng kẹp theo độ dài tháng
     (01–28/09 → 01–28/08; T2 nhuận 29/02 → 28/02). → { tu, den, nhan, thang? } (thang = số tháng đã lùi). */
  const ngayCuoi = (y, m0) => new Date(y, m0 + 1, 0).getDate();
  const tach = (iso) => iso.split('-').map(Number);
  function luiThang(k, n) {
    const doi = (iso) => { const [y, m, d] = tach(iso); const t = new Date(y, m - 1 - n, 1), c = ngayCuoi(t.getFullYear(), t.getMonth());
      return KD.iso(new Date(t.getFullYear(), t.getMonth(), d === ngayCuoi(y, m - 1) ? c : Math.min(d, c))); };
    return { tu: doi(k.tu), den: doi(k.den), thang: n };
  }
  function luiNgay(k) {
    const [y1, m1, d1] = tach(k.tu), [y2, m2, d2] = tach(k.den);
    const n = Math.round((new Date(y2, m2 - 1, d2) - new Date(y1, m1 - 1, d1)) / 86400000) + 1;
    return { tu: KD.iso(new Date(y1, m1 - 1, d1 - n)), den: KD.iso(new Date(y1, m1 - 1, d1 - 1)) };
  }
  function kySoSanh(key, k) {
    k = k || khoangKy(key);
    if (!k || !k.tu || !k.den) return null;
    const l = loaiKy(key);
    if (l === 'thang') return Object.assign(luiThang(k, 1), { nhan: 'tháng trước' });
    if (l === 'quy') return Object.assign(luiThang(k, 3), { nhan: 'quý trước' });
    if (l === 'nam') return Object.assign(luiThang(k, 12), { nhan: 'cùng kỳ năm trước' });
    const [y1, m1, d1] = tach(k.tu), [y2, m2, d2] = tach(k.den);
    if (d1 === 1 && d2 === ngayCuoi(y2, m2 - 1)) {   // trọn tháng → lùi đúng số tháng
      const n = (y2 * 12 + m2) - (y1 * 12 + m1) + 1;
      return Object.assign(luiThang(k, n), { nhan: n === 1 ? 'tháng trước' : n + ' tháng liền trước' });
    }
    return Object.assign(luiNgay(k), { nhan: 'kỳ liền trước' });
  }

  /* Nạp ô chọn kỳ: lựa chọn nhanh · Tuỳ chỉnh · nhóm "Chọn tháng" (24 tháng gần nhất) · "Chọn quý" (8 quý) · "Chọn năm" (3 năm).
     them: ['hom_nay','7_ngay','tat_ca'] — lựa chọn thêm riêng từng màn, chèn trước "Tuỳ chỉnh".
     Khoá kỳ cụ thể ngoài danh sách (link cũ, vd ?ky=2023-05) vẫn được thêm vào nhóm của nó.
     → khoá kỳ hợp lệ đang chọn (khoá lạ trên URL → 'thang_nay'). */
  function napKy(select, chon, them) {
    them = (them || []).filter((k) => KY_THEM[k]);
    if (!kyHopLe(chon, them)) chon = 'thang_nay';
    const o = (key, nhan) => '<option value="' + key + '"' + (key === chon ? ' selected' : '') + '>' + nhan + '</option>';
    const nhom = (nhan, ds, ten, re) => { if (re.test(chon) && !ds.includes(chon)) { ds.push(chon); ds.sort().reverse(); }
      return '<optgroup label="' + nhan + '">' + ds.map((k) => o(k, ten(k))).join('') + '</optgroup>'; };
    const h = new Date(), y = h.getFullYear(), m = h.getMonth(), q = Math.floor(m / 3);
    const thang = [], quy = [], nam = [];
    for (let i = 0; i < SO_THANG_CHON; i++) { const t = new Date(y, m - i, 1); thang.push(t.getFullYear() + '-' + p2(t.getMonth() + 1)); }
    for (let i = 0; i < SO_QUY_CHON; i++) { const t = new Date(y, (q - i) * 3, 1); quy.push(t.getFullYear() + '-Q' + (Math.floor(t.getMonth() / 3) + 1)); }
    for (let i = 0; i < SO_NAM_CHON; i++) nam.push(String(y - i));
    const ds = KY.slice(0, -1).concat(them.map((k) => ({ key: k, nhan: KY_THEM[k] })), KY.slice(-1));
    select.innerHTML = ds.map((k) => o(k.key, k.nhan)).join('')
      + nhom('Chọn tháng', thang, nhanThang, RE_THANG) + nhom('Chọn quý', quy, nhanQuy, RE_QUY) + nhom('Chọn năm', nam, (k) => 'Năm ' + k, RE_NAM);
    select.value = chon;
    return chon;
  }

  /* Gắn ô chọn kỳ (select + khung 2 ô ngày) vào trạng thái lọc st {ky, tu, den} — một chỗ cho mọi màn:
     · chọn "Tuỳ chỉnh…" → 2 ô ngày ĐIỀN SẴN khoảng đang xem (trước đây để trống, trông như hỏng);
     · đổi ngày → chờ 400 ms rồi mới tải (đổi liền 2 ô chỉ tải 1 lần), từ > đến thì báo đỏ, không tải;
     · đổi sang kỳ khác → xoá tu/den.
     o = { sel, hop, tu, den: phần tử; st; them?; nap?: false (ô dùng chung đã nạp ở chỗ khác);
           doi: () => void — khoảng số liệu đổi, cần tải lại;
           ghi?: () => void — khoảng giữ nguyên (sang Tuỳ chỉnh cùng khoảng), chỉ cần ghi URL }
     → { khoang: () => {tu, den}, veNgay } */
  function ganKy(o) {
    const st = o.st;
    st.ky = o.nap === false ? (kyHopLe(st.ky, o.them) ? st.ky : 'thang_nay') : napKy(o.sel, st.ky, o.them);
    if (st.ky === 'tuy_chinh') { const k = khoangSt(st); st.tu = k.tu; st.den = k.den; }   // ?ky=tuy_chinh thiếu/sai ngày → điền Tháng này
    const khoang = () => khoangSt(st);
    function veNgay() {
      o.hop.hidden = st.ky !== 'tuy_chinh';
      if (st.ky === 'tuy_chinh') { o.tu.value = st.tu || ''; o.den.value = st.den || ''; }
      [o.tu, o.den].forEach((i) => i.removeAttribute('aria-invalid')); o.hop.removeAttribute('title');
    }
    veNgay();
    o.sel.addEventListener('change', () => {
      const cu = khoang();
      st.ky = o.sel.value;
      if (st.ky === 'tuy_chinh') {
        const k = cu.tu && cu.den ? cu : khoangKy('thang_nay');
        st.tu = k.tu; st.den = k.den; veNgay();
        if (k === cu && o.ghi) o.ghi(); else o.doi();
      } else { st.tu = ''; st.den = ''; veNgay(); o.doi(); }
    });
    const doiNgay = KD.debounce(() => {
      const a = o.tu.value, b = o.den.value, sai = !!(a && b && a > b);
      [o.tu, o.den].forEach((i) => i.setAttribute('aria-invalid', String(sai)));
      if (sai) { o.hop.title = 'Từ ngày phải trước hoặc bằng Đến ngày'; if (window.showToast) window.showToast('warn', 'Từ ngày phải trước hoặc bằng Đến ngày — chưa đổi số liệu.'); }
      else o.hop.removeAttribute('title');
      if (!a || !b || sai || (a === st.tu && b === st.den)) return;
      st.tu = a; st.den = b; o.doi();
    }, 400);
    [o.tu, o.den].forEach((i) => i.addEventListener('change', doiNgay));
    return { khoang, veNgay };
  }

  /* Trạng thái bộ lọc trên URL (lọc, trang, sắp xếp). */
  const url = {
    doc: () => { try { const o = Object.fromEntries(new URLSearchParams(location.search)); delete o.xem; return o; } catch (e) { return {}; } },
    ghi(st, macDinh) {
      const q = new URLSearchParams();
      // v = '' khác mặc định (vd ô "Tất cả" = '' trong khi mặc định là "Chờ tôi duyệt") vẫn ghi `k=` — bản trước bỏ qua nên F5 quay về mặc định.
      Object.keys(st).forEach((k) => { const v = st[k], md = String((macDinh || {})[k] ?? ''); if (v != null && String(v) !== md && (v !== '' || md !== '')) q.set(k, v); });
      // Trong iframe sandbox/blob, replaceState có thể ném SecurityError — URL không cập nhật nhưng màn vẫn chạy.
      try { history.replaceState(null, '', location.pathname + (q.toString() ? '?' + q : '') + location.hash); } catch (e) { /* bỏ qua */ }
    },
    qs(st) { const q = new URLSearchParams(); Object.keys(st).forEach((k) => { if (st[k] !== '' && st[k] != null) q.set(k, st[k]); }); return q.toString(); },
  };

  /* Panel xem nhanh (L3) — mẫu kd-bao-gia.js:382-426. */
  function ganPanel(opt) {
    // dong: một <tr> hoặc mảng <tr> (một bút toán nhiều dòng tô chọn cả nhóm; focus trả về dòng đầu).
    const main = opt.main; const panel = opt.panel; const scrim = opt.scrim;
    let truocDo = null; let dangChon = [];
    const ds = (d) => (!d ? [] : Array.isArray(d) ? d : [d]);
    function mo(dong) {
      const moi = ds(dong);
      if (!panel.hidden && moi[0] && moi[0] === dangChon[0]) return;
      if (panel.hidden) truocDo = document.activeElement;
      dangChon.forEach((r) => r.classList.remove('is-selected'));
      dangChon = moi; dangChon.forEach((r) => r.classList.add('is-selected'));
      main.classList.add('has-panel'); panel.hidden = false; if (scrim) scrim.hidden = false;
      // Popup dùng lại một vùng cuộn: mở bản ghi khác phải bắt đầu từ đầu, không giữ vị trí cuộn của lần xem trước.
      const cuon = panel.querySelector('.kd-panel__scroll'); if (cuon) cuon.scrollTop = 0;
      opt.nutDong.focus({ preventScroll: true });
    }
    function dong() {
      if (panel.hidden) return;
      panel.hidden = true; if (scrim) scrim.hidden = true; main.classList.remove('has-panel');
      dangChon.forEach((r) => r.classList.remove('is-selected'));
      const ve = (dangChon[0] && document.contains(dangChon[0])) ? dangChon[0] : truocDo; dangChon = [];
      if (ve && document.contains(ve)) ve.focus({ preventScroll: true });
    }
    opt.nutDong.addEventListener('click', dong);
    if (scrim) scrim.addEventListener('click', dong);
    // Panel giờ là popup giữa màn có nền mờ (kd-man-hinh.css, 28/09/2026) → khai là hộp thoại, giữ Tab trong popup.
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true');
    document.addEventListener('keydown', (e) => {
      if ((e.key !== 'Escape' && e.key !== 'Tab') || panel.hidden) return;
      if (document.querySelector('.kd-menu') || document.querySelector('dialog[open]')) return;
      if (e.key === 'Escape') { dong(); return; }
      const ds = [...panel.querySelectorAll('a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled && x.getClientRects().length);
      if (!ds.length) return;
      const dau = ds[0], cuoi = ds[ds.length - 1], o = document.activeElement;
      if (e.shiftKey && (o === dau || !panel.contains(o))) { e.preventDefault(); cuoi.focus(); }
      else if (!e.shiftKey && (o === cuoi || !panel.contains(o))) { e.preventDefault(); dau.focus(); }
    });
    return { mo, dong, dangMo: () => !panel.hidden };
  }

  /* Dòng bảng bấm được: bấm/Enter/Space mở panel, bấm đúp sang trang chi tiết. */
  function ganDongBang(tbody, onMo, onChiTiet) {
    const lay = (e) => { const tr = e.target.closest('tr[data-id]'); return tr && !e.target.closest('button, a, input') ? tr : null; };
    tbody.addEventListener('click', (e) => { const tr = lay(e); if (tr) onMo(tr); });
    tbody.addEventListener('dblclick', (e) => { const tr = lay(e); if (tr && onChiTiet) onChiTiet(tr); });
    tbody.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr[data-id]')) { e.preventDefault(); onMo(e.target); }
    });
  }

  /* Sắp xếp — mẫu kd-bao-gia.js:277-299. aria-sort CHỈ trên <th> (50-khong-chep.md). */
  const tachSort = (v) => { v = v || ''; const i = v.lastIndexOf('_'); return i < 0 ? [v, ''] : [v.slice(0, i), v.slice(i + 1)]; };
  function ganSapXep(thead, layTrangThai, doi) {
    function ve() {
      const [cot, chieu] = tachSort(layTrangThai());
      thead.querySelectorAll('.kd-sort').forEach((b) => {
        const th = b.closest('th'); const on = b.dataset.sort === cot;
        if (on) th.setAttribute('aria-sort', chieu === 'asc' ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
        const i = b.querySelector('.bi'); i.className = 'bi ' + (on ? (chieu === 'asc' ? 'bi-sort-up' : 'bi-sort-down') : 'bi-arrow-down-up');
      });
    }
    thead.addEventListener('click', (e) => {
      const b = e.target.closest('.kd-sort'); if (!b) return;
      const [cot, chieu] = tachSort(layTrangThai());
      const dauTien = b.dataset.kieu === 'chu' ? 'asc' : 'desc';
      const moi = b.dataset.sort === cot ? (chieu === 'asc' ? 'desc' : 'asc') : dauTien;
      doi(b.dataset.sort + '_' + moi); ve();
    });
    ve();
    return { ve };
  }

  /* Hàng khung chờ cho tbody (tối đa 8 hàng). */
  function hangCho(soCot, soHang) {
    let h = '';
    for (let i = 0; i < (soHang || 8); i++) { h += '<tr aria-hidden="true">'; for (let j = 0; j < soCot; j++) h += '<td><span class="kd-skel kd-skel--o"></span></td>'; h += '</tr>'; }
    return h;
  }

  /* ── Tìm kiếm KHÔNG phân biệt dấu + hoa/thường (anh Quang 28/09): gõ "chien" / "CHIẾN" ra "Chiến Phương".
     Cùng tinh thần ketoan.bo_dau() phía server (app/services/tim_kiem.py): tách dấu (NFD) rồi bỏ, đ/Đ (+ ð/Ð gõ nhầm) → d,
     chữ thường. KT.khopTim(chuỗi | [các trường], từ khoá) — từ khoá rỗng = khớp; mảng thì nối các trường bằng dấu cách. */
  function boDau(s) {
    return String(s == null ? '' : s).normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[đĐðÐ]/g, 'd').toLowerCase();
  }
  function khopTim(chuoi, tuKhoa) {
    const t = boDau(tuKhoa).trim();
    return !t || boDau(Array.isArray(chuoi) ? chuoi.filter((x) => x != null && x !== '').join(' ') : chuoi).indexOf(t) >= 0;
  }

  /* ── Ô chọn tài khoản kế toán có tìm kiếm (combobox ARIA 1.2) ─────────────────────────────
     Dùng: KT.oTk(inputEl, { loc?: (tk) => bool, goiY?: (tk) => 'câu cảnh báo'|'' , khiChon?: (tk|null) => void })
     inputEl nằm trong .kt-o-tk; danh sách <ul role="listbox"> được tạo ngay sau input. Gõ mã hoặc tên → lọc;
     ↑/↓ chọn, Enter nhận, Esc đóng. Giá trị đã chọn ở input.dataset.ma (rỗng = chưa chọn hợp lệ).
     Danh mục = KT.dmTk() (GET /api/journal/accounts, xem napDmTk bên dưới); TK con (1111, 1121…) hiện thụt dưới TK cha. */
  /* Đọc số tiền bằng chữ (VND) cho phiếu thu/chi — "Một trăm linh năm triệu đồng chẵn". Bản in chính thức nên lấy từ máy chủ. */
  const CS = ['không', 'một', 'hai', 'ba', 'bốn', 'năm', 'sáu', 'bảy', 'tám', 'chín'];
  function doc3(n, day) {
    const tr = Math.floor(n / 100), ch = Math.floor((n % 100) / 10), dv = n % 10, o = [];
    if (day || tr) o.push(CS[tr] + ' trăm');
    if (ch === 0 && dv && (day || tr)) o.push('linh');
    if (ch === 1) o.push('mười'); else if (ch > 1) o.push(CS[ch] + ' mươi');
    if (dv) o.push(ch > 1 && dv === 1 ? 'mốt' : ch >= 1 && dv === 5 ? 'lăm' : ch > 1 && dv === 4 ? 'tư' : CS[dv]);
    return o.join(' ');
  }
  function bangChu(v) {
    let n = Math.round(Math.abs(+v || 0)); if (!n) return 'Không đồng.';
    const DV = ['', ' nghìn', ' triệu', ' tỷ'], nhom = [];
    while (n > 0) { nhom.push(n % 1000); n = Math.floor(n / 1000); }
    const o = []; for (let i = nhom.length - 1; i >= 0; i--) { const g = nhom[i]; if (!g) { if (i % 3 === 0 && i > 0 && o.length) o.push('tỷ'); continue; }
      o.push(doc3(g, i < nhom.length - 1) + DV[i % 3 === 0 && i > 0 ? 3 : i % 3]); }
    const c = o.join(' ').replace(/\s+/g, ' ').trim();
    return c.charAt(0).toUpperCase() + c.slice(1) + ' đồng' + (Math.round(Math.abs(+v)) % 1000 === 0 ? ' chẵn' : '') + '.';
  }

  /* 2026-09-25: /api/tai-khoan là TK ngân hàng/tiền mặt (tai_khoan_nh.py), KHÔNG PHẢI danh mục
     tài khoản kế toán — dùng nhầm sẽ vỡ combobox này ở mọi màn. Danh mục tài khoản thật nằm ở
     GET /api/journal/accounts ({code,name}): các TK cấp 1 TT200 + (28/09/2026) TK con của từng tài khoản
     tiền (mã 4–6 chữ số dưới 111/112, tên = tên tài khoản tiền). API không trả cấp → cha = mã dài nhất
     trong danh mục là tiền tố của mã (cùng cách services/journal.py:tk_cha_cua). Ánh xạ sang
     {ma,ten,cap,cha,so_tk_con,dang_dung} ngay tại đây để không phải sửa từng màn dùng KT.oTk.
     so_tk_con để false cả với 111/112: bút toán cũ ghi thẳng TK cha vẫn giữ, nên TK cha vẫn chọn được.
     KT.dmTk() = danh mục này (tải một lần mỗi trang). */
  let dmTk = null;
  function ganCap(ds) {
    const co = new Set(ds.map((t) => t.ma));
    ds.forEach((t) => {
      for (let n = t.ma.length - 1; n >= 3 && !t.cha; n--) if (co.has(t.ma.slice(0, n))) t.cha = t.ma.slice(0, n);
      t.cha = t.cha || null; t.cap = t.cha ? 2 : 1;
    });
    return ds.sort((a, b) => (a.ma < b.ma ? -1 : a.ma > b.ma ? 1 : 0));   // thứ tự chuỗi: TK con đứng ngay sau TK cha
  }
  const napDmTk = () => (dmTk = dmTk || KD.api('/api/journal/accounts')
    .then((all) => ganCap(all.map((t) => ({ ma: String(t.code), ten: t.name, so_tk_con: false, dang_dung: true }))))
    .catch((e) => { dmTk = null; throw e; }));
  let soOTk = 0;
  function oTk(inp, o) {
    o = o || {}; const id = inp.id || ('kt-o-tk-' + (++soOTk)); inp.id = id;
    const ul = document.createElement('ul'); ul.className = 'kt-o-tk__ds'; ul.id = id + '-ds'; ul.setAttribute('role', 'listbox'); ul.hidden = true;
    inp.insertAdjacentElement('afterend', ul);
    inp.setAttribute('role', 'combobox'); inp.setAttribute('aria-autocomplete', 'list'); inp.setAttribute('aria-expanded', 'false'); inp.setAttribute('aria-controls', ul.id);
    inp.autocomplete = 'off';
    let ds = [], hien = [], dang = -1;
    const nhan = (t) => t.ma + ' — ' + t.ten;
    function dong() { ul.hidden = true; inp.setAttribute('aria-expanded', 'false'); inp.removeAttribute('aria-activedescendant'); dang = -1; }
    function ve() {
      const q = boDau(inp.value.trim());
      hien = ds.filter((t) => !q || t.ma.indexOf(q) === 0 || boDau(t.ten).indexOf(q) >= 0 || boDau(nhan(t)) === q).slice(0, 40);
      ul.innerHTML = hien.length ? hien.map((t, i) => '<li role="option" id="' + id + '-o' + i + '" data-i="' + i + '" aria-selected="' + (i === dang) + '">'
        + '<span class="kt-tk' + (t.cap === 2 ? ' kt-cap-2' : '') + '">' + esc(t.ma) + '</span><span class="kt-o-tk__ten">' + esc(t.ten) + '</span></li>').join('')
        : '<li class="kt-o-tk__rong" role="presentation">Không có tài khoản chi tiết nào khớp "' + esc(inp.value.trim()) + '"</li>';
      ul.hidden = false; inp.setAttribute('aria-expanded', 'true');
      if (dang >= 0) inp.setAttribute('aria-activedescendant', id + '-o' + dang); else inp.removeAttribute('aria-activedescendant');
    }
    function chon(t) { inp.value = t ? nhan(t) : ''; inp.dataset.ma = t ? t.ma : ''; dong(); if (o.khiChon) o.khiChon(t || null); }
    async function mo() { try { const all = await napDmTk(); ds = all.filter((t) => !t.so_tk_con && t.dang_dung && (!o.loc || o.loc(t))); ve(); }
      catch (e) { ul.innerHTML = '<li class="kt-o-tk__rong" role="presentation">Không tải được danh mục tài khoản — ' + esc(e.message) + '</li>'; ul.hidden = false; } }
    inp.addEventListener('focus', mo);
    inp.addEventListener('input', () => { inp.dataset.ma = ''; dang = -1; if (o.khiChon) o.khiChon(null); if (ds.length) ve(); else mo(); });
    inp.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); if (ul.hidden) return mo(); if (!hien.length) return;
        dang = (dang + (e.key === 'ArrowDown' ? 1 : -1) + hien.length) % hien.length; ve(); const li = document.getElementById(id + '-o' + dang); if (li) li.scrollIntoView({ block: 'nearest' }); }
      else if (e.key === 'Enter' && (!ul.hidden || !inp.dataset.ma)) { e.preventDefault();
        if (dang >= 0 && !ul.hidden) return chon(hien[dang]);
        // gõ nhanh rồi Enter khi danh mục còn đang tải: chờ tải xong rồi nhận mã gõ đúng (hoặc gợi ý duy nhất)
        Promise.resolve(ds.length ? null : mo()).then(() => { const q = inp.value.trim(); const t = ds.find((x) => x.ma === q) || (hien.length === 1 ? hien[0] : null); if (t) chon(t); }); }
      else if (e.key === 'Escape' && !ul.hidden) { e.preventDefault(); e.stopPropagation(); dong(); }
    });
    ul.addEventListener('mousedown', (e) => { const li = e.target.closest('[data-i]'); if (li) { e.preventDefault(); chon(hien[+li.dataset.i]); } });
    inp.addEventListener('blur', () => setTimeout(() => { dong(); if (!inp.dataset.ma) { const t = ds.find((x) => x.ma === inp.value.trim()); if (t) chon(t); } }, 120));
    return { dat: async (ma) => { if (!ma) return chon(null); try { const all = await napDmTk(); chon(all.find((t) => t.ma === ma) || null); } catch (e) { inp.value = ma; inp.dataset.ma = ma; } },
      lay: () => inp.dataset.ma || '', lamMoi: () => { dmTk = null; ds = []; },
      /* Trước khi lưu: người dùng gõ đúng mã mà chưa chọn trong danh sách → nhận luôn. */
      xacNhan: async () => { if (inp.dataset.ma || !inp.value.trim()) return inp.dataset.ma || '';
        try { const all = await napDmTk(); const q = inp.value.trim(); const t = all.find((x) => !x.so_tk_con && x.dang_dung && (!o.loc || o.loc(x)) && (x.ma === q || nhan(x) === q)); if (t) chon(t); } catch (e) { /* để ô báo lỗi ở bước kiểm */ }
        return inp.dataset.ma || ''; } };
  }

  window.KT = {
    loaiCt: layLoaiCt, LOAI_CT,
    pillTuoiNo: pillTu(nhanTu(TUOI_NO, 'TUOI_NO')),
    pillPhieu: pillTu(nhanTu(TT_PHIEU, 'TT_PHIEU')),
    KY, khoangKy, khoangSt, napKy, ganKy, kySoSanh, nhanKy, loaiKy, kyHopLe, url, ganPanel, ganDongBang, ganSapXep, hangCho, oTk, bangChu, dmTk: napDmTk,
    boDau, khopTim,
    /* Chữ cho ô tiền trống/bằng 0 trong cột Nợ/Có: để trống cho dễ đọc sổ, nhưng trình đọc màn hình vẫn nghe "không". */
    tienSo(v) { const n = KD.so(v); return !n ? '<span class="kd-muted" aria-label="không">—</span>' : KD.tien(n); },
    /* Link mở một chứng từ trên Sổ kế toán (lọc đúng ngày + số chứng từ). */
    urlCt(so, ngay) { return '/ketoan/so-cai?ky=tuy_chinh&tu=' + ngay + '&den=' + ngay + '&tim=' + encodeURIComponent(so); },
    linkCt(so, ngay) { return so ? '<a class="kt-ma" href="' + KT.urlCt(so, ngay) + '">' + esc(so) + '</a>' : '<span class="kd-muted">—</span>'; },
  };
})();
