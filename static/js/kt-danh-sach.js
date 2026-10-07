/* ═══════════════════════════════════════════════════════════════════════════
   kt-danh-sach.js — bộ khung màn danh sách L3 dùng chung (nhóm 3–5 của Kế toán)
   Khung HTML lấy từ macro `ui.the_bang` / `ui.the_so` (_kt_macro.html), id theo tiền tố `pfx`.
   Mỗi màn chỉ khai cấu hình: API, cột, thẻ số, lọc, panel, menu → khung lo: bộ lọc trên URL, sắp xếp,
   phân trang, 4 trạng thái (khung chờ · rỗng vì lọc / rỗng thật · lỗi + Thử lại · dữ liệu), panel xem nhanh.
   Nạp SAU kd-man-hinh.js + kt-chung.js.

   KT.danhSach({
     pfx, api: (q) => url,                 q = trạng thái lọc (đã quy đổi kỳ → tu/den)
     macDinh: { page, size, sort, …khoá lọc },
     cot: [{ key, nhan, num?, sort?: 'chu'|'so', title?, ve: (r) => html, cls? }],
     kpi: { key: (d) => ({ v: html, phu: text, title? }) },
     cong?: (d) => [html ô chân bảng…],   phamVi?: (d) => text,
     rong: (d, coLoc) => [tiêu đề, lời], loi: 'Không tải được …', donVi: 'tài sản',
     dong?: { id: (r) => id, cls?: (r) => '' },
     panel?: { tai?: (r) => url, ve: (ct, r) => html, nut?: (ct, r) => html, sau?: (el, ct, r) => void },
     menu?: (r) => [KD.menu items], chiTiet?: (r) => href, sauTai?: (d) => void, khongTrang?: true,
     kyPfx?: 'tc'        dùng chung ô chọn kỳ của một tiền tố khác (nhiều bảng trên một màn, vd 3 tab Thu chi),
     url?: false         không đọc/ghi URL (màn nhiều bảng tự quản URL) — khi đó batDau?: {…} là trạng thái ban đầu,
     ghiUrl?: (st) => void   (khi url:false) gọi mỗi lần tải / đổi kỳ để màn tự ghi URL gộp nhiều bảng,
     sauDoiKy?: (doiKhoang) => void   gọi sau khi đổi kỳ (st đã cập nhật) — khối khác trên màn dùng chung kỳ,
     truocTai?: async (q) => void     chạy (và chờ) trước mỗi lần gọi API chính,
     khongDem?: ['thang']  khoá lọc là phạm vi dữ liệu, không đếm vào "đang lọc" / nút Đặt lại
     dangHien?: () => bool   bảng đang ẩn (tab khác) thì đổi kỳ chỉ đánh dấu, tới lúc hiện gọi taiNeuCan()
     nhomCot?: [[nhãn, số cột, lớp?]]  hàng tiêu đề nhóm cột phía trên (vd ĐƠN HÀNG | PHẢI THU | PHẢI TRẢ)
     cot[].lop?: 'kt-cot-pt'  lớp gắn cả th lẫn td — dùng để ẩn/hiện cả nhóm cột bằng CSS
     kyThem?: ['hom_nay','7_ngay','tat_ca']  thêm lựa chọn vào ô kỳ (napKy)
     chuyen?: (duLieuApi, q) => { dong, tong, … }  đổi dạng phản hồi API có sẵn (vd /api/products trả mảng) sang dạng khung cần
   }) → { tai, taiNeuCan, st, dsHien: () => rows, duLieu, dongPanel, khoang }
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  function danhSach(c) {
    const $ = (s) => document.getElementById(c.pfx + '-' + s);
    const $k = (s) => document.getElementById((c.kyPfx || c.pfx) + '-' + s);
    const coUrl = c.url !== false;
    const st = Object.assign({}, c.macDinh, coUrl ? KT.url.doc() : c.batDau || {});
    st.page = +st.page || 1; st.size = +st.size || +c.macDinh.size || 20;
    let luot = 0, luotP = 0, ds = [], du = null, canTai = false;
    const coKy = !!$k('ky');
    const khoaLoc = [...document.querySelectorAll('#' + c.pfx + '-loc [data-loc]')].map((e) => e.dataset.loc);
    const khoaDem = khoaLoc.filter((k) => !(c.khongDem || []).includes(k));   // ô chọn phạm vi (vd tháng lương) không tính là "đang lọc"

    /* ── Khởi tạo ô lọc từ URL ── */
    /* Giá trị lạ trên URL (vd ?trang_thai=xyz, ?size=7) → ô select trống mà st vẫn gửi giá trị đó lên API. Ô có sẵn lựa chọn
       tĩnh (> 1 option) thì trả về mặc định; ô nạp lựa chọn động sau khi tải (chỉ có "Tất cả") vẫn giữ giá trị URL. */
    const coLuaChon = (e, v) => [...e.options].some((o) => o.value === String(v));
    khoaLoc.forEach((k) => { const e = $(k); if (!e || st[k] == null) return;
      if (e.tagName === 'SELECT' && e.options.length > 1 && !coLuaChon(e, st[k])) st[k] = c.macDinh[k] || '';
      e.value = st[k]; });
    if ($('co-trang')) { if (!coLuaChon($('co-trang'), st.size)) st.size = +c.macDinh.size || 20; $('co-trang').value = String(st.size); }
    if ($('loc') && $('nut-loc')) {
      const mo = (x) => { $('loc').hidden = !x; $('nut-loc').setAttribute('aria-expanded', String(x)); };
      // KD.MAN_RONG() trả boolean — bản trước đọc .matches (undefined) nên khung lọc luôn gập, kể cả máy tính.
      mo(KD.MAN_RONG()); $('nut-loc').addEventListener('click', () => mo($('loc').hidden));
    } else if ($('loc')) $('loc').hidden = false;

    const khoang = () => (coKy ? KT.khoangSt(st) : {});
    // q.ky_goc: khoá kỳ đang chọn (vd '2026-07') cho màn cần tên kỳ / kỳ so sánh (KT.nhanKy, KT.kySoSanh).
    const q = () => Object.assign({}, st, khoang(), { ky: undefined, ky_goc: coKy ? st.ky : undefined });
    const coLoc = () => khoaDem.some((k) => st[k] && st[k] !== (c.macDinh[k] || ''));

    /* ── Đầu bảng + sắp xếp ── */
    const lopTh = (k) => [k.num && 'num', k.act && 'kd-col-act', k.lop].filter(Boolean).join(' ');
    $('thead').innerHTML = (c.nhomCot ? '<tr class="kt-nhom-cot">' + c.nhomCot.map(([nhan, span, lop]) => '<th scope="colgroup" colspan="' + span + '"' + (lop ? ' class="' + lop + '"' : '') + '>' + esc(nhan) + '</th>').join('') + '</tr>' : '')
      + '<tr>' + c.cot.map((k) => '<th scope="col"' + (lopTh(k) ? ' class="' + lopTh(k) + '"' : '') + (k.title ? ' title="' + esc(k.title) + '"' : '') + '>'
      + (k.sort ? '<button type="button" class="kd-sort" data-sort="' + k.key + '"' + (k.sort === 'chu' ? ' data-kieu="chu"' : '') + '>' + esc(k.nhan) + ' <i class="bi bi-arrow-down-up" aria-hidden="true"></i></button>' : esc(k.nhan)) + '</th>').join('') + '</tr>';
    if (c.cot.some((k) => k.sort)) KT.ganSapXep($('thead'), () => st.sort, (s) => { st.sort = s; st.page = 1; tai(); });

    /* ── Thẻ số ── */
    const kpiEl = (k) => document.querySelector('#' + c.pfx + '-kpi [data-kpi="' + k + '"]');
    function veKpi(d) {
      Object.keys(c.kpi || {}).forEach((k) => { const el = kpiEl(k); if (!el) return; const x = c.kpi[k](d) || {};
        el.querySelector('[data-v]').innerHTML = x.v == null ? '<span class="kd-muted">—</span>' : x.v; el.querySelector('[data-v]').title = x.title || '';
        el.querySelector('[data-phu]').innerHTML = x.phu || ''; });
    }
    function choKpi(loi) {
      Object.keys(c.kpi || {}).forEach((k) => { const el = kpiEl(k); if (!el) return;
        el.querySelector('[data-v]').innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; el.querySelector('[data-phu]').innerHTML = ''; });
    }

    /* ── Thân bảng ── */
    const idDong = (r) => (c.dong && c.dong.id ? c.dong.id(r) : r.id);
    function veBang(rows) {
      $('tbody').innerHTML = rows.map((r) => '<tr' + (c.panel || c.chiTiet ? ' data-id="' + esc(idDong(r)) + '" tabindex="0"' : '') + (c.dong && c.dong.cls ? ' class="' + c.dong.cls(r) + '"' : '') + '>'
        + c.cot.map((k) => { const cl = [k.num && 'num', k.act && 'kd-col-act', !k.act && k.cls, k.lop].filter(Boolean).join(' '); return '<td' + (cl ? ' class="' + cl + '"' : '') + '>'
          + (k.act ? (c.menu ? '<button type="button" class="kd-icon-btn" data-menu="' + esc(idDong(r)) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(k.nhanDong ? k.nhanDong(r) : idDong(r)) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button>' : '') : k.ve(r)) + '</td>'; }).join('') + '</tr>').join('');
    }

    // url:false (màn nhiều bảng tự quản URL) → c.ghiUrl(st) nếu có, để bộ lọc riêng từng bảng vẫn giữ khi F5.
    function ghiUrl() { if (coUrl) KT.url.ghi(st, Object.assign({ ky: 'thang_nay' }, c.macDinh, { page: 1, size: c.macDinh.size || 20 })); else if (c.ghiUrl) c.ghiUrl(st); }
    async function tai() {
      const l = ++luot; const qq = q(); canTai = false;
      ghiUrl();
      const n = khoaDem.filter((k) => st[k] && st[k] !== (c.macDinh[k] || '')).length;
      if ($('dem-loc')) { $('dem-loc').hidden = !n; $('dem-loc').textContent = n; }
      choKpi(); $('cuon').hidden = false; $('tt').innerHTML = ''; $('tfoot').innerHTML = ''; if ($('foot')) $('foot').hidden = true;
      $('tbody').innerHTML = KT.hangCho(c.cot.length, 8);
      try {
        // c.truocTai(q): nạp số phụ theo kỳ (vd tồn đầu kỳ) TRƯỚC khi gọi API chính — thay cho kiểu tải xong rồi tải lại lần 2.
        if (c.truocTai) { try { await c.truocTai(qq); } catch (e) { /* số phụ lỗi không chặn bảng */ } if (l !== luot) return; }
        const d0 = await KD.api(c.api(qq)); const d = c.chuyen ? c.chuyen(d0, qq) : d0;
        if (l !== luot) return;
        du = d; ds = d.dong || [];
        veKpi(d); if (c.phamVi && $('pham-vi')) $('pham-vi').textContent = c.phamVi(d);
        if (c.sauTai) c.sauTai(d);
        if (!ds.length) {
          $('cuon').hidden = true; const [td, loi] = c.rong(d, coLoc());
          $('tt').innerHTML = KD.khoiRong(td, loi) + (coLoc() ? '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>' : '');
          const b = $('tt').querySelector('[data-dat-lai]'); if (b) b.addEventListener('click', datLai);
          return;
        }
        veBang(ds);
        if (c.cong) { const o = c.cong(d); let cot = 0;
          // ô chân bảng nằm dưới cột thao tác (dính phải) cũng phải mang kd-col-act để không bị cột dính đè
          if (o) $('tfoot').innerHTML = '<tr>' + o.map((x, i) => { const n = x.span || 1, act = c.cot.slice(cot, cot + n).some((k) => k.act); cot += n;
            const cls = [x.num ? 'num' : '', act ? 'kd-col-act' : '', x.lop || ''].filter(Boolean).join(' ');
            return (i === 0 ? '<th scope="row"' : '<td') + (cls ? ' class="' + cls + '"' : '') + (x.span ? ' colspan="' + x.span + '"' : '') + '>' + (x.html || '') + (i === 0 ? '</th>' : '</td>'); }).join('') + '</tr>'; }
        if ($('foot') && !c.khongTrang) {
          $('foot').hidden = false;
          const tong = d.tong_dong != null ? d.tong_dong : ds.length, tr = d.trang || 1, so = d.so_trang || 1;
          const a = (tr - 1) * st.size + 1, b = Math.min(tr * st.size, tong);
          $('hien-thi').textContent = 'Hiển thị ' + KD.soDem(a) + ' - ' + KD.soDem(b) + ' / ' + KD.soDem(tong) + ' ' + (c.donVi || 'dòng');
          KD.phanTrang($('trang'), tr, so, (p) => { st.page = p; tai(); });
        }
      } catch (e) {
        if (l !== luot) return;
        choKpi(true); $('cuon').hidden = true;
        KD.khoiLoi($('tt'), c.loi, e, tai);
        if (c.khiLoi) c.khiLoi(e);
      }
    }

    /* ── Panel xem nhanh ── */
    let panel = null;
    if (c.panel && $('panel')) {
      panel = KT.ganPanel({ main: $('main'), panel: $('panel'), scrim: $('scrim'), nutDong: $('p-dong') });
      KT.ganDongBang($('tbody'), async (tr) => {
        const r = ds.find((x) => String(idDong(x)) === tr.dataset.id); if (!r) return;
        panel.mo(tr); const nd = $('p-noi-dung'), nut = $('p-nut'), l = ++luotP;
        if (c.panel.tieuDe) $('p-td').textContent = c.panel.tieuDe(r);
        nd.innerHTML = KD.KHUNG_TAI; nut.innerHTML = '';
        try {
          const ct = c.panel.tai ? await KD.api(c.panel.tai(r)) : r;
          if (l !== luotP) return;
          nd.innerHTML = c.panel.ve(ct, r); nut.innerHTML = c.panel.nut ? c.panel.nut(ct, r) : '';
          if (c.panel.sau) c.panel.sau(nd, ct, r, nut);
          // Lỗi VẼ (vd TypeError trong panel.ve) rơi vào cùng catch với lỗi API → luôn ghi console, không để bị giấu sau câu thông báo.
        } catch (e) { if (l !== luotP) return; console.error('[KT.danhSach] panel ' + c.pfx + ' lỗi:', e); KD.khoiLoi(nd, c.panel.loi || 'Không tải được chi tiết', e, () => tr.click()); }
      }, c.chiTiet ? (tr) => { const r = ds.find((x) => String(idDong(x)) === tr.dataset.id); const h = r && c.chiTiet(r); if (h) location.href = h; } : null);
    } else if (c.chiTiet) {
      KT.ganDongBang($('tbody'), (tr) => { const r = ds.find((x) => String(idDong(x)) === tr.dataset.id); const h = r && c.chiTiet(r); if (h) location.href = h; });
    }
    if (c.menu) $('tbody').addEventListener('click', (e) => { const m = e.target.closest('[data-menu]'); if (!m) return; const r = ds.find((x) => String(idDong(x)) === m.dataset.menu); if (r) KD.menu(m, c.menu(r)); });

    /* ── Sự kiện lọc ── */
    function doiLoc() { st.page = 1; if (panel) panel.dong(); if (c.dangHien && !c.dangHien()) { canTai = true; return; } tai(); }
    function datLai() { khoaDem.forEach((k) => { st[k] = c.macDinh[k] || ''; const e = $(k); if (e) e.value = st[k]; }); doiLoc(); }
    khoaLoc.forEach((k) => { const e = $(k); if (!e) return;
      if (e.type === 'search') e.addEventListener('input', KD.debounce(() => { st[k] = e.value.trim(); doiLoc(); }, 350));
      else e.addEventListener('change', () => { st[k] = e.value; doiLoc(); }); });
    if ($('dat-lai')) $('dat-lai').addEventListener('click', datLai);
    if ($('loc')) $('loc').addEventListener('submit', (e) => e.preventDefault());
    if ($('co-trang')) $('co-trang').addEventListener('change', (e) => { st.size = +e.target.value; doiLoc(); });
    // Ô kỳ dùng chung (kyPfx): màn đã nạp lựa chọn; mỗi bảng vẫn giữ st riêng và tự nghe sự kiện.
    // c.sauDoiKy(doiKhoang) — màn có khối khác dùng chung kỳ (vd tab Tối ưu của Đơn hàng) nghe tại đây, SAU khi st đã cập nhật.
    if (coKy) KT.ganKy({ sel: $k('ky'), hop: $k('khoang'), tu: $k('tu'), den: $k('den'), st, them: c.kyThem, nap: !c.kyPfx,
      doi: () => { doiLoc(); if (c.sauDoiKy) c.sauDoiKy(true); }, ghi: () => { ghiUrl(); if (c.sauDoiKy) c.sauDoiKy(false); } });
    return { tai, taiNeuCan: () => { if (canTai || !du) tai(); }, st, dsHien: () => ds, duLieu: () => du, dongPanel: () => panel && panel.dong(), khoang };
  }

  /* Tiện ích vẽ dùng chung cho cấu hình màn */
  const H = {
    tien: (v) => KT.tienSo(v),
    tienKpi: (v) => KD.tienGonHtml(v),
    dem: (v, dv) => '<span>' + KD.soDem(v) + '</span>' + (dv ? '<span class="kd-kpi__don-vi">' + esc(dv) + '</span>' : ''),
    ma: (v) => '<span class="kd-strong">' + esc(v) + '</span>',
    ten: (ten, phu) => '<span class="kt-khach__ten">' + esc(ten) + '</span>' + (phu ? '<span class="kt-khach__ma">' + esc(phu) + '</span>' : ''),
    cat: (v, hep) => '<span class="kt-cat' + (hep ? ' kt-cat--hep' : '') + '" title="' + esc(v || '') + '">' + esc(v || '—') + '</span>',
    pill: (mau, nhan, vien) => '<span class="pill pill--' + mau + (vien ? ' pill--vien' : '') + '">' + esc(nhan) + '</span>',
    kv: (ds) => '<dl class="kt-tq">' + ds.filter(Boolean).map(([t, v, dam]) => '<dt' + (dam ? ' class="is-dam"' : '') + '>' + esc(t) + '</dt><dd>' + v + '</dd>').join('') + '</dl>',
    khoi: (icon, tieuDe, noiDung) => '<section class="kd-block"><h3 class="kd-block__title"><i class="bi ' + icon + '" aria-hidden="true"></i>' + esc(tieuDe) + '</h3>' + noiDung + '</section>',
    /* Nạp lại lựa chọn của ô lọc theo dữ liệu trả về (nhân viên, phòng ban…) mà vẫn giữ giá trị đang lọc. */
    /* Giá trị đang lọc không còn trong danh sách (link cũ, dữ liệu kỳ khác) → vẫn thêm vào để ô không hiện "Tất cả" trong khi bảng đang lọc. */
    napChon: (el, ds, dau, giu) => { if (!el) return; if (giu && !ds.some(([v]) => String(v) === String(giu))) ds = ds.concat([[giu, giu]]);
      el.innerHTML = (dau ? '<option value="">' + esc(dau) + '</option>' : '') + ds.map(([v, t]) => '<option value="' + esc(v) + '">' + esc(t) + '</option>').join(''); el.value = giu || ''; },
    dauPanel: (icon, mau, ma, phu, pill) => '<div class="kd-panel__id kt-p-id"><span class="ico-tile' + (mau ? ' ico-tile--' + mau : '') + '" aria-hidden="true"><i class="bi ' + icon + '"></i></span><div><div class="kd-panel__code">' + esc(ma) + (pill || '') + '</div>' + (phu ? '<p class="kd-meta">' + phu + '</p>' : '') + '</div></div>',
  };
  window.KT = Object.assign(window.KT || {}, { danhSach, H });
})();
