/* ═══════════════════════════════════════════════════════════════════════════
   kt-can-doi.js — Bảng cân đối phát sinh (nối API THẬT).

   Nguồn: GET /api/journal/can-doi-phat-sinh?tu_ngay&den_ngay (app/services/journal.py:
   trial_balance) — dư đầu kỳ, phát sinh Nợ/Có THẬT (tổng gộp, không phải chênh lệch ròng)
   và dư cuối kỳ của MỌI tài khoản kể cả 511/632/635/641/642/711/811/821, chỉ tính bút toán
   'da_post'. Dòng Cộng vì vậy phải cân Nợ = Có ở cả 3 cặp cột — thẻ "Kết quả kiểm tra" kiểm thật.

   QA 25/09/2026 — bản trước ghép từ 2 lần /api/journal/balance-summary: (1) "phát sinh" chỉ là
   chênh lệch ròng cuối − đầu kỳ, (2) tự chép danh sách TK nên thiếu 141/242/3334/3335 và bỏ
   trống 8 TK doanh thu/chi phí (dù API có trả) → dòng Cộng lệch, thẻ kiểm tra "Không kiểm được",
   (3) nút Xuất Excel chỉ báo "chưa có chức năng".
   Không có màn tương ứng ở giao diện cũ (SPA /app không có sổ cái / cân đối phát sinh).

   Bấm/Enter một dòng → /ketoan/so-cai?tk=<ma>&ky=tuy_chinh&tu=&den= (sổ cái đúng TK + kỳ).

   Mức hiển thị (28/09/2026): mỗi tài khoản tiền có TK con (1111, 1121… — API trả dòng `cap`=2 kèm
   `tk_cha`). "Cấp 1" = chỉ dòng cap 1; "Chi tiết" = thêm dòng TK con ngay dưới TK cha, thụt lề.
   Dòng TK cha ĐÃ GỒM số của TK con → dòng Cộng + thẻ kiểm tra chỉ cộng cap 1 (xem dongCong).
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = $('kd-kt-can-doi');
  if (!trang) return;

  /* Đợt 1 (07/10/2026): MẶC ĐỊNH HIỆN ĐỦ mọi tài khoản trong danh mục, kể cả mã chưa có bút toán (số 0) —
     trước đây mặc định ẩn nên mã chưa hạch toán biến mất, không ai biết là thiếu. Vẫn bật ẩn được bằng ô lọc. */
  const MAC_DINH = { ky: 'thang_nay', tu: '', den: '', cap: '1', an_trong: '0', tim: '' };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  if (st.cap !== 'chi_tiet') st.cap = '1';
  const COT = ['dau_no', 'dau_co', 'ps_no', 'ps_co', 'cuoi_no', 'cuoi_co'];
  const TINH_CHAT = { no: 'Dư Nợ', co: 'Dư Có' };
  const LECH_TOI_DA = 1; // VND — sai số làm tròn chấp nhận được
  let luot = 0; let kyHt = null; let dongHt = [];

  $('cd-tim').value = st.tim; $('cd-an').checked = st.an_trong !== '0';
  function veCap() { $('cd-cap').querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.cap === st.cap))); }
  veCap();

  const khoang = () => KT.khoangSt(st);

  const tienO = (v) => '<span>' + KD.tien(v) + '</span><span class="kd-kpi__don-vi">VND</span>';
  const O = {}; trang.querySelectorAll('#cd-strip [data-o]').forEach((o) => { O[o.dataset.o] = o; });
  function veO(k, gt, phu) { O[k].querySelector('[data-v]').innerHTML = gt; O[k].querySelector('[data-phu]').innerHTML = phu || ''; }

  function veStrip(tg) {
    const cap = (n, c) => 'Nợ ' + KD.tien(n) + ' · Có ' + KD.tien(c);
    veO('dau', tienO(tg.dau_no), cap(tg.dau_no, tg.dau_co));
    veO('ps', tienO(tg.ps_no), cap(tg.ps_no, tg.ps_co));
    veO('cuoi', tienO(tg.cuoi_no), cap(tg.cuoi_no, tg.cuoi_co));
    const lech = Math.max(Math.abs(tg.dau_no - tg.dau_co), Math.abs(tg.ps_no - tg.ps_co), Math.abs(tg.cuoi_no - tg.cuoi_co));
    const can = lech <= LECH_TOI_DA;
    O.can.querySelector('[data-icon]').className = 'ico-tile ico-tile--sm ico-tile--' + (can ? 'success' : 'danger');
    O.can.querySelector('[data-icon]').innerHTML = '<i class="bi ' + (can ? 'bi-check2-circle' : 'bi-exclamation-triangle') + '"></i>';
    veO('can', '<span>' + (can ? 'Cân đối' : 'Lệch ' + KD.tien(lech)) + '</span>',
      can ? '<span class="pill pill--success">Nợ = Có ở cả 3 cặp cột</span>'
        : '<span class="pill pill--danger">Tổng Nợ ≠ Tổng Có — cần kiểm tra bút toán</span>');
  }

  function lienKet(ma) { return '/ketoan/so-cai?tk=' + encodeURIComponent(ma) + '&ky=tuy_chinh&tu=' + kyHt.tu + '&den=' + kyHt.den; }

  const laCon = (r) => r.cap === 2;
  // so_dong = số dòng định khoản của TK từ trước tới cuối kỳ (API trial_balance) — 0 nghĩa là chưa từng hạch toán.
  const chuaHachToan = (r) => !laCon(r) && !r.so_dong;
  // Mức "Cấp 1" bỏ dòng TK con; lọc tìm + ẩn dòng trống áp như nhau cho cả hai cấp.
  function locVaSap(dong) {
    let ds = dong.filter((r) => (st.cap === 'chi_tiet' || !laCon(r)) && KT.khopTim([r.ma, r.ten], st.tim));
    if (st.an_trong === '1') ds = ds.filter((r) => COT.some((k) => r[k]));
    return ds;
  }
  /* Dòng TK con xếp ngay dưới TK cha (không dựa vào thứ tự máy chủ trả); con không thấy cha thì để cuối. */
  function xepCon(dong) {
    const con = {}; dong.filter(laCon).forEach((r) => { (con[r.tk_cha] = con[r.tk_cha] || []).push(r); });
    const out = [];
    dong.filter((r) => !laCon(r)).forEach((r) => { out.push(r); (con[r.ma] || []).forEach((c) => out.push(c)); delete con[r.ma]; });
    Object.keys(con).forEach((k) => { out.push(...con[k]); });
    return out;
  }
  /* Các dòng được cộng: dòng cap 1 + dòng TK con đang hiện mà TK cha KHÔNG hiện (vd tìm "ACB" chỉ ra 1121)
     — dòng cha đã gồm số của con nên cộng cả hai là cộng trùng. */
  function dongCong(ds) {
    const cha = new Set(ds.filter((r) => !laCon(r)).map((r) => r.ma));
    return ds.filter((r) => !laCon(r) || !cha.has(r.tk_cha));
  }

  /* Dòng Cộng + thẻ kiểm tra luôn tính trên TOÀN BỘ tài khoản cấp 1 (ẩn dòng trống / mức Chi tiết không đổi tổng);
     khi đang TÌM thì cộng theo các dòng đang hiện (dongCong — không cộng trùng TK con) và ghi rõ ở nhãn. */
  function veBang(dong) {
    const hien = locVaSap(dong);
    const tinhTong = (ds) => { const t = {}; COT.forEach((k) => { t[k] = ds.reduce((a, r) => a + r[k], 0); }); return t; };
    const tongCap1 = tinhTong(dong.filter((r) => !laCon(r)));
    veStrip(tongCap1);
    if (!hien.length) {
      $('cd-tbody').innerHTML = ''; $('cd-tfoot').innerHTML = ''; $('cd-cuon').hidden = true;
      // Đang ở "Cấp 1" mà từ khoá chỉ khớp TK con (vd tên ngân hàng) → chỉ đường sang "Chi tiết".
      const coCon = st.tim && st.cap !== 'chi_tiet' && dong.some((r) => laCon(r) && KT.khopTim([r.ma, r.ten], st.tim) && (st.an_trong !== '1' || COT.some((k) => r[k])));
      $('cd-tt').innerHTML = st.tim
        ? KD.khoiRong('Không có tài khoản nào khớp "' + st.tim + '"', coCon ? 'Có tài khoản con khớp — bấm "Chi tiết" ở Mức hiển thị để xem.' : 'Thử tìm theo số hiệu (VD: 131) hoặc bỏ bớt chữ.') + '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>'
        : KD.khoiRong('Chưa có số dư hay phát sinh nào trong kỳ', 'Bảng hiện khi có số dư đầu kỳ hoặc bút toán được ghi sổ trong khoảng ngày đã chọn.');
      const b = $('cd-tt').querySelector('[data-dat-lai]'); if (b) b.addEventListener('click', datLai);
      return;
    }
    $('cd-cuon').hidden = false; $('cd-tt').innerHTML = '';
    $('cd-tbody').innerHTML = hien.map((r) => { const con = laCon(r);
      return '<tr class="kt-cap' + (con ? 2 : 1) + '" data-href="' + lienKet(r.ma) + '" tabindex="-1">'
        + '<td>' + (con ? '<span class="kt-cap-2">' : '') + '<a class="kt-tk-link" href="' + lienKet(r.ma) + '" aria-label="Mở sổ cái tài khoản ' + esc(r.ma) + ' ' + esc(r.ten) + '">' + esc(r.ma) + '</a>' + (con ? '</span>' : '') + '</td>'
        + '<td>' + esc(r.ten) + (chuaHachToan(r) ? ' <span class="pill pill--warning kt-cd-chua">Chưa có bút toán</span>' : '')
        + '<span class="kt-dk__phu">' + (con ? 'TK con của ' + esc(r.tk_cha) : esc(TINH_CHAT[r.tinh_chat] || '')) + '</span></td>'
        + COT.map((k) => '<td class="num">' + KT.tienSo(r[k]) + '</td>').join('') + '</tr>'; }).join('');
    const tong = st.tim ? tinhTong(dongCong(hien)) : tongCap1;
    const c = (a, b) => '<td class="num">' + KD.tien(a) + '</td><td class="num">' + KD.tien(b) + '</td>';
    $('cd-tfoot').innerHTML = '<tr><th scope="row" colspan="2">' + (st.tim ? 'Cộng các tài khoản đang lọc' : st.cap === 'chi_tiet' ? 'Cộng tất cả tài khoản cấp 1' : 'Cộng tất cả tài khoản') + '</th>'
      + c(tong.dau_no, tong.dau_co) + c(tong.ps_no, tong.ps_co) + c(tong.cuoi_no, tong.cuoi_co) + '</tr>';
  }

  async function tai() {
    const l = ++luot; kyHt = khoang();
    KT.url.ghi(st, MAC_DINH);
    // Đợt 4: dòng phạm vi chỉ còn "Kỳ …" + ⓘ; ghi chú cuối bảng cũng chuyển vào ⓘ này (xem veGhiChu).
    const ghiChu = 'Chỉ bút toán đã ghi sổ, gồm cả tài khoản doanh thu / chi phí chưa kết chuyển. Dư Nợ / Dư Có là số dư ròng (Nợ − Có) đặt về bên lớn hơn — kể cả TK lưỡng tính 131, 331. TK con (mức Chi tiết, thụt vào) đã gồm trong TK cha nên dòng Cộng chỉ cộng TK cấp 1.';
    const veGhiChu = (them) => { $('cd-pham-vi').innerHTML = 'Kỳ ' + KD.ngay(kyHt.tu) + ' – ' + KD.ngay(kyHt.den) + KD.tip(ghiChu + (them || '')); };
    veGhiChu();
    $('cd-cap-bang').textContent = 'Bảng cân đối phát sinh kỳ ' + KD.ngay(kyHt.tu) + ' – ' + KD.ngay(kyHt.den);
    $('cd-cuon').hidden = false; $('cd-tt').innerHTML = ''; $('cd-tfoot').innerHTML = '';
    $('cd-tbody').innerHTML = KT.hangCho(8, 10);
    Object.values(O).forEach((o) => { o.querySelector('[data-v]').innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; o.querySelector('[data-phu]').innerHTML = ''; });
    try {
      const d = await KD.api('/api/journal/can-doi-phat-sinh?' + KT.url.qs({ tu_ngay: kyHt.tu, den_ngay: kyHt.den }));
      if (l !== luot) return;
      dongHt = xepCon((d.tai_khoan || []).map((r) => { const x = Object.assign({}, r); COT.forEach((k) => { x[k] = KD.so(r[k]) || 0; }); return x; }));
      const le = dongHt.some((r) => COT.some((k) => Math.abs(r[k] % 1) > 1e-9));
      $('cd-ghi-chu').hidden = true;
      veGhiChu(le ? ' Có bút toán lẻ dưới 1 đồng (vd khấu hao 25.094.346,25) — số hiển thị làm tròn nên cộng tay có thể lệch 1 đ.' : '');
      const cap1 = dongHt.filter((r) => !laCon(r)), chua = cap1.filter(chuaHachToan).length;
      if (chua) $('cd-pham-vi').insertAdjacentHTML('beforeend', ' · <b>' + KD.soDem(chua) + '/' + KD.soDem(cap1.length) + ' tài khoản chưa có bút toán nào</b>');
      veBang(dongHt);
    } catch (e) {
      if (l !== luot) return;
      $('cd-cuon').hidden = true;
      Object.values(O).forEach((o) => { o.querySelector('[data-v]').innerHTML = '<span class="kd-muted">—</span>'; });
      KD.khoiLoi($('cd-tt'), 'Không tải được bảng cân đối phát sinh', e, tai);
    }
  }

  /* Xuất CSV (UTF-8 có BOM — Excel mở thẳng, không lỗi dấu) đúng các dòng đang hiện. Có dòng TK con thì thêm
     cột "TK cấp trên" để người cộng tay trên Excel không cộng trùng (dòng cha đã gồm số của con). */
  function xuatCsv() {
    const hien = locVaSap(dongHt);
    if (!hien.length) { if (window.showToast) window.showToast('info', 'Không có dòng nào để xuất'); return; }
    const o = (v) => '"' + String(v == null ? '' : v).split('"').join('""') + '"';
    const coCon = hien.some(laCon);
    const dau = ['Số hiệu', 'Tên tài khoản'].concat(coCon ? ['TK cấp trên'] : [], ['Dư đầu kỳ Nợ', 'Dư đầu kỳ Có', 'Phát sinh Nợ', 'Phát sinh Có', 'Dư cuối kỳ Nợ', 'Dư cuối kỳ Có']);
    const dong = hien.map((r) => [r.ma, r.ten].concat(coCon ? [r.tk_cha || ''] : [], COT.map((k) => Math.round(r[k]))));
    const csv = '﻿' + [dau].concat(dong).map((x) => x.map(o).join(',')).join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
    a.download = 'can-doi-phat-sinh_' + kyHt.tu + '_' + kyHt.den + '.csv';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // Cả dòng bấm được (vùng bấm lớn), nhưng phần tử tương tác thật là <a> ở ô số hiệu — bàn phím Tab vào link, Enter mở.
  $('cd-tbody').addEventListener('click', (e) => { if (e.target.closest('a')) return; const tr = e.target.closest('tr[data-href]'); if (tr) location.href = tr.dataset.href; });

  function veLai() { KT.url.ghi(st, MAC_DINH); veBang(dongHt); }
  function datLai() { Object.assign(st, { cap: '1', an_trong: '0', tim: '' }); $('cd-tim').value = ''; $('cd-an').checked = false; veCap(); veLai(); }
  // Ô kỳ dùng chung (kt-chung.js): Tuỳ chỉnh điền sẵn ngày, chọn tháng/quý/năm cụ thể, URL ?ky=2026-07.
  KT.ganKy({ sel: $('cd-ky'), hop: $('cd-khoang'), tu: $('cd-tu'), den: $('cd-den'), st, doi: tai, ghi: () => KT.url.ghi(st, MAC_DINH) });
  // "Chi tiết" = thêm dòng TK con của tài khoản tiền (1111, 1121…) dưới TK cha. 3334/3335 máy chủ trả là cấp 1 (không có TK "333").
  $('cd-cap').addEventListener('click', (e) => {
    const b = e.target.closest('button[data-cap]'); if (!b || b.dataset.cap === st.cap) return;
    st.cap = b.dataset.cap; veCap(); veLai();
  });
  $('cd-an').addEventListener('change', (e) => { st.an_trong = e.target.checked ? '1' : '0'; veLai(); });
  $('cd-tim').addEventListener('input', KD.debounce(() => { st.tim = $('cd-tim').value.trim(); veLai(); }, 250));
  $('cd-dat-lai').addEventListener('click', datLai);
  $('cd-loc').addEventListener('submit', (e) => e.preventDefault());
  $('cd-in').addEventListener('click', () => window.print());
  $('cd-xuat').addEventListener('click', xuatCsv);
  tai();
})();
