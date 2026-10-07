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
    function urlSoCai(r, k) {
      const tk = c.lien && c.lien[r.ma]; if (!tk) return null;
      const den = (!coKy && (k.den || (du && du.den_ngay))) || '';
      const q = Object.assign({ tk }, coKy ? { ky: 'tuy_chinh', tu: k.tu, den: k.den } : den ? { ky: 'tuy_chinh', tu: den.slice(0, 4) + '-01-01', den } : { ky: 'nam_nay' });
      return '/ketoan/so-cai?' + KT.url.qs(q);
    }
    function lienKet(r, k) {
      /* Dòng có chi tiết → bấm TÊN cũng mở popup chứng từ. Trước đây tên luôn link sang
         Sổ cái, nhưng sổ kép mới ghi ~8% nghiệp vụ (TK 331/411/421/334 KHÔNG có dòng nào)
         nên bấm vào hay rơi vào trang trống — người dùng tưởng báo cáo hỏng. Link Sổ cái
         chuyển xuống chân popup, nơi nó vẫn dùng được với các TK thật sự có bút toán. */
      if (c.chiTiet && r.khoa) {
        return '<button type="button" class="kt-bc__ten" data-khoa="' + esc(r.khoa) + '" data-ma="' + esc(r.ma || '')
          + '" title="Xem các chứng từ làm nên con số này">' + esc(r.chi_tieu) + '</button>';
      }
      const tk = c.lien && c.lien[r.ma]; if (!tk) return esc(r.chi_tieu);
      // Báo cáo tại một ngày (CĐKT, ?den=) → sổ cái từ đầu năm của ngày đó đến đúng ngày đó (bản trước luôn "Năm nay" tính tới hôm nay).
      const den = (!coKy && (k.den || (du && du.den_ngay))) || '';
      const q = Object.assign({ tk }, coKy ? { ky: 'tuy_chinh', tu: k.tu, den: k.den } : den ? { ky: 'tuy_chinh', tu: den.slice(0, 4) + '-01-01', den } : { ky: 'nam_nay' });
      return '<a class="kt-bc__lien" href="/ketoan/so-cai?' + KT.url.qs(q) + '" title="Xem sổ cái TK ' + tk + '">' + esc(r.chi_tieu) + '</a>';
      /* eslint-disable-next-line no-unreachable */
    }
    function nhanDong(r, k) {
      const ten = lienKet(r, k) + (r.ghi_chu ? KD.tip(r.ghi_chu) : '');
      if (!r.nhom_mo) return ten;
      return '<button type="button" class="kt-bc__mo" aria-expanded="' + (r.gap ? 'false' : 'true') + '" data-mo="' + esc(r.nhom_mo) + '"><i class="bi bi-chevron-down" aria-hidden="true"></i><span class="visually-hidden">Thu gọn / mở chi tiết</span></button>' + ten;
    }
    /* MỌI cột số đều bấm được khi dòng có `khoa`:
         · cột kỳ này    → chứng từ của kỳ đang xem
         · cột kỳ trước  → chứng từ của CHÍNH kỳ so sánh (cùng dòng, khác khoảng ngày).
           Bản đầu bỏ sót cột này vì nghĩ nó "không có chứng từ riêng" — sai, kỳ trước
           có chứng từ thật y như kỳ này.
         · cột chênh lệch → hiện phép trừ "kỳ này − kỳ trước", dựng tại chỗ, không gọi API.
       `data-cot` cho biết bấm cột nào, để lấy đúng khoảng ngày.
       Số 0 vẫn bấm được: "vì sao bằng 0" cũng là câu hỏi cần trả lời. */
    function soMoDuoc(r, key) {
      const html = key === 'chenh' ? chenh(r.ky_nay, r.ky_truoc) : soBc(r[key]);
      if (!c.chiTiet || !r.khoa) return html;
      if (key === 'chenh' ? r.ky_truoc == null : r[key] == null) return html;
      return '<button type="button" class="kt-bc__so" data-khoa="' + esc(r.khoa)
        + '" data-cot="' + esc(key) + '" title="Xem các chứng từ làm nên con số này">'
        + html + '</button>';
    }

    function veDong(r, k) {
      if (r.cap === 'nhom') return '<tr class="kt-bc--nhom"><th scope="rowgroup" colspan="' + soCot + '">' + esc(r.chi_tieu) + '</th></tr>';
      return '<tr class="kt-bc--' + (r.cap || 'muc') + (r.nhom_mo ? ' kt-bc--cha' : '') + '"' + (r.thuoc ? ' data-thuoc="' + esc(r.thuoc) + '"' : '') + '><th scope="row">' + nhanDong(r, k) + '</th>'
        + c.cot.map((o) => (o.key === 'ma' ? '<td class="kt-bc__ma">' + esc(r.ma) + '</td>' : o.key === 'thuyet_minh' ? '<td class="kt-bc__ma">' + esc(r.thuyet_minh || '') + '</td>'
          : '<td class="num">' + soMoDuoc(r, o.key) + '</td>')).join('') + '</tr>';
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

    /* ── Popup "nguồn gốc con số" ──────────────────────────────────────────
       `c.chiTiet(khoa, khoang, trang)` → URL API. API trả {nhan, nguon, giai_thich,
       tong, so_dong, trang, so_trang, cot[], dong[], dieu_chinh[], phan[]?}.
       Tổng do API trả LUÔN bằng số trên dòng (bất biến giữ ở backend) nên ở đây
       chỉ việc hiển thị, không tự cộng lại. */
    let khoaDangXem = null, trangDangXem = 1, maDangXem = '', cotDangXem = 'ky_nay', dongDangXem = null;
    if (c.chiTiet && $('panel')) {
      const dongPanel = KT.ganPanel({
        main: $('main'), panel: $('panel'), scrim: $('scrim'), nutDong: $('p-dong'),
      });
      const soCot = (v, kieu) => (kieu === 'tien' ? KD.tien(v) : kieu === 'ngay' ? KD.ngay(v) : esc(v == null ? '' : String(v)));
      function veBang(d) {
        if (!d.cot || !d.cot.length || !d.dong || !d.dong.length) {
          return '<p class="kd-meta">' + (d.ghi_chu ? esc(d.ghi_chu) : 'Không có chứng từ nào trong kỳ.') + '</p>';
        }
        return '<div class="kd-table-scroll"><table class="kd-table kt-bang kt-bc-ct">'
          + '<thead><tr>' + d.cot.map((o) => '<th scope="col"' + (o.kieu === 'tien' ? ' class="num"' : '') + '>' + esc(o.nhan) + '</th>').join('') + '</tr></thead>'
          + '<tbody>' + d.dong.map((r) => '<tr>' + d.cot.map((o) => '<td' + (o.kieu === 'tien' ? ' class="num"' : '') + '>' + soCot(r[o.key], o.kieu) + '</td>').join('') + '</tr>').join('') + '</tbody>'
          + '</table></div>';
      }
      function veTrang(d, ky) {
        if (!d.so_trang || d.so_trang <= 1) return '';
        const dk = ky ? ' data-ky="' + ky + '"' : '';
        return '<nav class="kt-bc-ct__trang" aria-label="Phân trang chi tiết">'
          + '<button type="button" class="kd-btn kd-btn--nho"' + dk + ' data-trang="' + Math.max(1, d.trang - 1) + '"' + (d.trang <= 1 ? ' disabled' : '') + '>Trước</button>'
          + '<span class="kd-meta">Trang ' + KD.soDem(d.trang) + ' / ' + KD.soDem(d.so_trang) + ' · ' + KD.soDem(d.so_dong) + ' dòng</span>'
          + '<button type="button" class="kd-btn kd-btn--nho"' + dk + ' data-trang="' + Math.min(d.so_trang, d.trang + 1) + '"' + (d.trang >= d.so_trang ? ' disabled' : '') + '>Sau</button>'
          + '</nav>';
      }
      function veChiTiet(d) {
        $('p-td').textContent = (d.nhan || 'Chi tiết')
          + (cotDangXem !== (c.cotChiTiet || 'ky_nay') ? ' — kỳ trước' : '');
        const dc = (d.dieu_chinh || []).length
          ? '<ul class="kt-bc-ct__dc">' + d.dieu_chinh.map((x) => '<li><span>' + esc(x.nhan) + '</span><b class="num">' + KD.tien(x.so_tien) + '</b></li>').join('') + '</ul>'
          : '';
        /* Có `phan` thì vẫn giữ bảng chính ở trên (dòng tổng = bảng công thức), rồi mới
           tới từng khối chứng từ — người xem cần cả "vì sao ra số này" lẫn "chứng từ đâu". */
        const khoi = (d.phan || []).map((p) => '<section class="kt-bc-ct__phan"><h3>' + esc(p.nhan)
            + '<span class="kd-meta"> · ' + esc(p.nguon) + '</span></h3>'
            + '<p class="kt-bc-ct__tong num">' + KD.tienVnd(p.tong) + '</p>'
            + (p.ghi_chu ? '<p class="kd-meta kt-bc-ct__canh">' + esc(p.ghi_chu) + '</p>' : '')
            + veBang(p) + veTrang(p) + '</section>').join('');
        const than = ((d.dong && d.dong.length) ? veBang(d) + veTrang(d) : (khoi ? '' : veBang(d)))
          + khoi;
        $('p-noi-dung').innerHTML =
          '<p class="kt-bc-ct__nguon"><i class="bi bi-database" aria-hidden="true"></i> ' + esc(d.nguon || '') + '</p>'
          + (d.giai_thich ? '<p class="kd-meta">' + esc(d.giai_thich) + '</p>' : '')
          + '<p class="kt-bc-ct__tong num" title="Đúng bằng số trên dòng báo cáo">' + KD.tienVnd(d.tong) + '</p>'
          + (d.tong_dong != null && Math.abs(d.tong_dong - d.tong) > 0.5
              ? '<p class="kd-meta kt-bc-ct__canh"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> Cộng các chứng từ dưới đây ra ' + KD.tienVnd(d.tong_dong) + '.</p>' : '')
          + (d.ghi_chu ? '<p class="kd-meta kt-bc-ct__canh"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> ' + esc(d.ghi_chu) + '</p>' : '')
          + dc + than;
        /* Link Sổ cái để ở chân popup — chỉ hiện khi dòng này có gắn tài khoản kế toán. */
        const url = urlSoCai({ ma: maDangXem }, khoang());
        $('p-nut').innerHTML = url
          ? '<a class="kd-btn" href="' + url + '"><i class="bi bi-journal-text" aria-hidden="true"></i>Xem sổ cái TK ' + esc(c.lien[maDangXem]) + '</a>'
          : '';
      }
      /* Cột Chênh lệch: hiện phép trừ Ở TRÊN rồi nạp CHỨNG TỪ CỦA CẢ HAI KỲ ở dưới.
         Bản đầu chỉ hiện mỗi phép tính — đúng về số nhưng vô dụng: người xem muốn biết
         chênh 917 triệu là do đơn nào, chứ không phải xem lại hai con số đã thấy. */
      const trangChenh = { ky_nay: 1, ky_truoc: 1 };
      async function veChenh(doiKy) {
        const r = dongDangXem; if (!r) return;
        const a = +r.ky_nay || 0, t = +r.ky_truoc || 0;
        if (!doiKy) { trangChenh.ky_nay = 1; trangChenh.ky_truoc = 1; }
        $('p-td').textContent = (r.chi_tieu || 'Chênh lệch') + ' — chênh lệch';
        $('p-nut').innerHTML = '';
        const dauTrang =
          '<p class="kt-bc-ct__nguon"><i class="bi bi-calculator" aria-hidden="true"></i> Chênh lệch = kỳ này − kỳ trước</p>'
          + '<p class="kt-bc-ct__tong num">' + KD.tienVnd(a - t) + '</p>'
          + '<div class="kd-table-scroll"><table class="kd-table kt-bang kt-bc-ct"><tbody>'
          + '<tr><td>+ Kỳ này</td><td class="num">' + KD.tien(a) + '</td></tr>'
          + '<tr><td>− Kỳ trước</td><td class="num">' + KD.tien(t) + '</td></tr>'
          + '</tbody></table></div>';
        $('p-noi-dung').innerHTML = dauTrang + '<p class="kd-meta">Đang tải chứng từ hai kỳ…</p>';
        const lay = async (ky) => {
          try { return await KD.api(c.chiTiet(r.khoa, khoang(), trangChenh[ky], ky)); }
          catch (e) { return null; }
        };
        const [dn, dt] = await Promise.all([lay('ky_nay'), lay('ky_truoc')]);
        const phan = (d, ky, ten) => (!d ? '<section class="kt-bc-ct__phan"><h3>' + ten
            + '</h3><p class="kd-meta">Không tải được chứng từ kỳ này.</p></section>'
          : '<section class="kt-bc-ct__phan" data-ky="' + ky + '"><h3>' + ten
            + '<span class="kd-meta"> · ' + esc(d.nguon || '') + '</span></h3>'
            + '<p class="kt-bc-ct__tong num">' + KD.tienVnd(d.tong) + '</p>'
            + (d.ghi_chu ? '<p class="kd-meta kt-bc-ct__canh">' + esc(d.ghi_chu) + '</p>' : '')
            + veBang(d) + veTrang(d, ky) + '</section>');
        $('p-noi-dung').innerHTML = dauTrang
          + phan(dn, 'ky_nay', 'Chứng từ kỳ này')
          + phan(dt, 'ky_truoc', 'Chứng từ kỳ trước');
      }
      async function taiChiTiet(khoa, trang) {
        khoaDangXem = khoa; trangDangXem = trang || 1;
        $('p-noi-dung').innerHTML = KD.khoiCho ? KD.khoiCho() : '<p class="kd-meta">Đang tải…</p>';
        try {
          veChiTiet(await KD.api(c.chiTiet(khoa, khoang(), trangDangXem, cotDangXem)));
        } catch (err) {
          KD.khoiLoi($('p-noi-dung'), 'Không tải được chi tiết', err, () => taiChiTiet(khoa, trangDangXem));
        }
      }
      $('tbody').addEventListener('click', (e) => {
        const b = e.target.closest('.kt-bc__so, .kt-bc__ten'); if (!b) return;
        const tr = b.closest('tr');
        maDangXem = b.dataset.ma || ((tr && tr.querySelector('.kt-bc__ma')) || {}).textContent || '';
        cotDangXem = b.dataset.cot || (c.cotChiTiet || 'ky_nay');
        dongDangXem = ((du && du.dong) || []).find((x) => x.khoa === b.dataset.khoa) || null;
        dongPanel.mo(tr);
        if (cotDangXem === 'chenh') { veChenh(); return; }
        taiChiTiet(b.dataset.khoa, 1);
      });
      $('p-noi-dung').addEventListener('click', (e) => {
        const b = e.target.closest('[data-trang]'); if (!b || b.disabled) return;
        if (b.dataset.ky) { trangChenh[b.dataset.ky] = Number(b.dataset.trang) || 1; veChenh(true); return; }
        taiChiTiet(khoaDangXem, Number(b.dataset.trang) || 1);
      });
    }
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
