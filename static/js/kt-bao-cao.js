/* ═══════════════════════════════════════════════════════════════════════════
   kt-bao-cao.js — khung báo cáo tài chính theo mẫu (B01/B02/B03-DN) dùng chung.
   Khung HTML: ui.the_so (thẻ số) + ui.the_bao_cao (bảng chỉ tiêu) trong _kt_macro.html.
   KT.baoCao({
     pfx, api: (q) => url | [url, …], macDinh: { ky | den … },
       api trả MẢNG url → gọi song song, `chuyen` nhận mảng kết quả cùng thứ tự.
     cot: [{ key, nhan, num? }]         cột số: lấy r[key]; key đặc biệt 'chenh' = ky_nay − ky_truoc
     lien?: { 'mã số': 'TK' }           chỉ tiêu có link xuống Sổ cái của TK
     kpi: { key: (d) => ({ v, phu, title }) }, ghiChu?: (d) => text, sauTai?, khiLoi?
     phamVi?: (d) => text   giải thích cách lập → nút ⓘ cạnh tiêu đề bảng (không in thành đoạn chữ)
     phuDe?: (d) => text    dòng phụ ngắn dưới tiêu đề bảng (vd "Tháng 09/2026 so với 08/2026")
     rong: [tiêu đề, lời], loi: 'Không tải được …'
     chuyen?: (duLieuApi, k) => { dong, ky, ky_truoc, tom_tat, … }  đổi dạng phản hồi API có sẵn
       sang dạng khung cần — dùng khi API thật của báo cáo không trả sẵn mảng `dong` theo mã số.
     tenFile?: 'ket-qua-kinh-doanh'     tên tệp khi bấm Xuất Excel (nút #pfx-xuat)
     inUrl?: (k, d) => url              nút #pfx-in mở trang in chuẩn (/ketoan/in); không khai → window.print()
   }) → { tai, st, duLieu, khoang }
   Dòng: { ma, chi_tieu, cap: nhom|tong|muc|con|con2|dam, thuyet_minh?, ghi_chu?, …cột số,
           nhom_mo?: 'id' (dòng cha gập/mở được), gap?: true (mặc định gập), thuoc?: 'id' (dòng con của nhóm gập) }.
   Số âm trong báo cáo tài chính viết trong ngoặc đơn, theo thông lệ trình bày BCTC.
   Nút #pfx-in → in trang (window.print); nút #pfx-xuat → tải CSV (Excel mở được, UTF-8 BOM)
   từ đúng bảng đang hiển thị — không có endpoint xuất riêng ở backend.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const chuTron = (html) => { const x = document.createElement('div'); x.innerHTML = html || ''; return x.textContent.replace(/\s+/g, ' ').trim(); };
  const soBc = (v) => { if (v == null) return ''; const n = Math.round(+v || 0); return !n ? KT.tienSo(0) : n < 0 ? '(' + KD.tien(-n) + ')' : KD.tien(n); };
  const chenh = (a, b) => { if (b == null) return ''; const d = (a || 0) - (b || 0); if (!d) return KT.tienSo(0);
    const pt = b ? ' <span class="kd-meta">' + (d > 0 ? '+' : '−') + KD.phanTram(Math.abs(d / b) * 100) + '</span>' : '';
    return (d > 0 ? '+' : '−') + KD.tien(Math.abs(d)) + pt; };

  /* CSV từ bảng HTML (lấy chữ hiển thị; số trong ngoặc giữ nguyên dạng BCTC). */
  function xuatCsv(bang, tenFile, dauTrang) {
    const o = (s) => '"' + String(s == null ? '' : s).replace(/\s+/g, ' ').trim().replace(/"/g, '""') + '"';
    const dong = [...bang.querySelectorAll('tr')].filter((tr) => !tr.hidden)
      .map((tr) => [...tr.children].map((c) => o(c.innerText)).join(','));
    const noi = '﻿' + (dauTrang || []).map((x) => o(x)).join('\n') + (dauTrang && dauTrang.length ? '\n\n' : '') + dong.join('\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([noi], { type: 'text/csv;charset=utf-8' }));
    a.download = tenFile + '.csv'; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  }

  function baoCao(c) {
    const $ = (s) => document.getElementById(c.pfx + '-' + s);
    const st = Object.assign({}, c.macDinh, KT.url.doc());
    let luot = 0, du = null;
    const coKy = !!$('ky');
    const u0 = KT.url.doc();
    if (coKy && !u0.ky && u0.tu && u0.den) st.ky = 'tuy_chinh';   // link ?tu=&den= (không kèm ky) → mở đúng khoảng đó
    if (!coKy && $('den-ngay')) { $('den-ngay').value = st.den || ''; }
    /* k.ky = khoá kỳ đang chọn, k.ss = kỳ so sánh (KT.kySoSanh: tháng→tháng trước, quý→quý trước,
       năm→cùng kỳ năm trước, tuỳ chỉnh→khoảng liền trước cùng độ dài) — màn dùng để gọi API kỳ trước. */
    const khoang = () => { if (!coKy) return { den: st.den || '' };
      const k = KT.khoangSt(st); return Object.assign({}, k, { ky: st.ky, ss: KT.kySoSanh(st.ky, k) }); };
    const soCot = c.cot.length + 1;
    const kpiEl = (k) => document.querySelector('#' + c.pfx + '-kpi [data-kpi="' + k + '"]');

    function choKpi(loi) { Object.keys(c.kpi || {}).forEach((k) => { const el = kpiEl(k); if (!el) return;
      el.querySelector('[data-v]').innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; el.querySelector('[data-phu]').innerHTML = ''; }); }
    function veKpi(d) { Object.keys(c.kpi || {}).forEach((k) => { const el = kpiEl(k); if (!el) return; const x = c.kpi[k](d) || {};
      el.querySelector('[data-v]').innerHTML = x.v == null ? '<span class="kd-muted">—</span>' : x.v; el.querySelector('[data-v]').title = x.title || '';
      el.querySelector('[data-phu]').innerHTML = x.phu || ''; }); }

    /* Giải thích cách lập → ⓘ cạnh tiêu đề bảng; kỳ số liệu → dòng phụ ngắn dưới tiêu đề. */
    const td = document.getElementById(c.pfx + '-td');
    const tipTd = td ? td.appendChild(document.createElement('span')) : null;
    const phuTd = td ? td.parentElement.querySelector('.kd-meta') : null, phuGoc = phuTd ? phuTd.textContent : '';
    if ($('pham-vi')) $('pham-vi').hidden = true;
    function veTieuDe(d) {
      if (tipTd) tipTd.innerHTML = c.phamVi ? KD.tip(chuTron(c.phamVi(d))) : '';
      if (phuTd && c.phuDe) phuTd.textContent = c.phuDe(d) + ' · Đơn vị tính: VND';
    }
    function lienKet(r, k) {
      const tk = c.lien && c.lien[r.ma]; if (!tk) return esc(r.chi_tieu);
      // Báo cáo tại một ngày (CĐKT, ?den=) → sổ cái từ đầu năm của ngày đó đến đúng ngày đó (bản trước luôn "Năm nay" tính tới hôm nay).
      const den = (!coKy && (k.den || (du && du.den_ngay))) || '';
      const q = Object.assign({ tk }, coKy ? { ky: 'tuy_chinh', tu: k.tu, den: k.den } : den ? { ky: 'tuy_chinh', tu: den.slice(0, 4) + '-01-01', den } : { ky: 'nam_nay' });
      return '<a class="kt-bc__lien" href="/ketoan/so-cai?' + KT.url.qs(q) + '" title="Xem sổ cái TK ' + tk + '">' + esc(r.chi_tieu) + '</a>';
    }
    function nhanDong(r, k) {
      const ten = lienKet(r, k) + (r.ghi_chu ? KD.tip(r.ghi_chu) : '');
      if (!r.nhom_mo) return ten;
      return '<button type="button" class="kt-bc__mo" aria-expanded="' + (r.gap ? 'false' : 'true') + '" data-mo="' + esc(r.nhom_mo) + '"><i class="bi bi-chevron-down" aria-hidden="true"></i><span class="visually-hidden">Thu gọn / mở chi tiết</span></button>' + ten;
    }
    function veDong(r, k) {
      if (r.cap === 'nhom') return '<tr class="kt-bc--nhom"><th scope="rowgroup" colspan="' + soCot + '">' + esc(r.chi_tieu) + '</th></tr>';
      return '<tr class="kt-bc--' + (r.cap || 'muc') + (r.nhom_mo ? ' kt-bc--cha' : '') + '"' + (r.thuoc ? ' data-thuoc="' + esc(r.thuoc) + '"' : '') + '><th scope="row">' + nhanDong(r, k) + '</th>'
        + c.cot.map((o) => (o.key === 'ma' ? '<td class="kt-bc__ma">' + esc(r.ma) + '</td>' : o.key === 'thuyet_minh' ? '<td class="kt-bc__ma">' + esc(r.thuyet_minh || '') + '</td>'
          : '<td class="num">' + (o.key === 'chenh' ? chenh(r.ky_nay, r.ky_truoc) : soBc(r[o.key])) + '</td>')).join('') + '</tr>';
    }

    async function tai() {
      const l = ++luot, k = khoang();
      KT.url.ghi(st, Object.assign({}, c.macDinh, { ky: 'thang_nay' }));
      choKpi(); if (tipTd) tipTd.innerHTML = ''; if (phuTd) phuTd.textContent = phuGoc; $('tt').innerHTML = ''; $('cuon').hidden = false; if ($('ghi-chu')) $('ghi-chu').hidden = true;
      $('tbody').innerHTML = KT.hangCho(soCot, 12);
      try {
        const url = c.api(Object.assign({}, k));
        const d0 = Array.isArray(url) ? await Promise.all(url.map((u) => KD.api(u))) : await KD.api(url);
        if (l !== luot) return;
        const d = c.chuyen ? c.chuyen(d0, k) : d0;
        du = d;
        veKpi(d); veTieuDe(d);
        if (c.sauTai) c.sauTai(d, k);
        const coSo = (d.dong || []).some((r) => c.cot.some((o) => o.num && o.key !== 'chenh' && r[o.key]));
        if (!coSo) { $('cuon').hidden = true; $('tt').innerHTML = KD.khoiRong(c.rong[0], c.rong[1]); return; }
        $('tbody').innerHTML = d.dong.map((r) => veDong(r, d.ky || k)).join(''); apGap();
        if ($('ghi-chu') && c.ghiChu) { const g = c.ghiChu(d); $('ghi-chu').hidden = !g; $('ghi-chu').innerHTML = g || ''; }
      } catch (e) {
        if (l !== luot) return;
        choKpi(true); $('cuon').hidden = true; KD.khoiLoi($('tt'), c.loi, e, tai); if (c.khiLoi) c.khiLoi(e);
      }
    }

    /* Gập / mở nhóm chi tiết (dòng cha có nút mũi tên). data-thuoc có thể chứa nhiều id (cha, ông…)
       cách nhau dấu cách — dòng ẩn khi BẤT KỲ nhóm tổ tiên nào đang gập. */
    function apGap() {
      const gap = new Set([...$('tbody').querySelectorAll('.kt-bc__mo[aria-expanded="false"]')].map((x) => x.dataset.mo));
      $('tbody').querySelectorAll('tr[data-thuoc]').forEach((tr) => { tr.hidden = tr.dataset.thuoc.split(' ').some((id) => gap.has(id)); });
    }
    $('tbody').addEventListener('click', (e) => {
      const b = e.target.closest('.kt-bc__mo'); if (!b) return;
      b.setAttribute('aria-expanded', b.getAttribute('aria-expanded') === 'true' ? 'false' : 'true');
      apGap();
    });
    if ($('in')) $('in').addEventListener('click', () => {   // inUrl → trang in chuẩn /ketoan/in; không có → in đúng màn đang xem
      if (c.inUrl) window.open(c.inUrl(khoang(), du), '_blank', 'noopener'); else window.print();
    });
    if ($('xuat')) $('xuat').addEventListener('click', () => {
      if (!du || $('cuon').hidden) { window.showToast && window.showToast('warn', 'Chưa có số liệu để xuất'); return; }
      const td = document.getElementById(c.pfx + '-td'), k = khoang();
      const ky = coKy ? 'Kỳ ' + KD.ngay(k.tu) + ' – ' + KD.ngay(k.den) : 'Tại ngày ' + KD.ngay((du && du.den_ngay) || k.den);
      xuatCsv($('cuon').querySelector('table'), (c.tenFile || c.pfx) + '_' + (coKy ? (k.tu + '_' + k.den) : ((du && du.den_ngay) || k.den || '')), [td ? td.textContent : '', ky, 'Đơn vị tính: VND']);
    });

    if (coKy) {
      KT.ganKy({ sel: $('ky'), hop: $('khoang'), tu: $('tu'), den: $('den'), st, doi: tai,
        ghi: () => KT.url.ghi(st, Object.assign({}, c.macDinh, { ky: 'thang_nay' })) });
    } else if ($('den-ngay')) {
      $('den-ngay').addEventListener('change', (e) => { st.den = e.target.value; tai(); });
    }
    return { tai, st, duLieu: () => du, khoang };
  }

  window.KT = Object.assign(window.KT || {}, { baoCao, soBc, xuatCsv });
})();
