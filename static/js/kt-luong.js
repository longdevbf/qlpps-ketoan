/* kt-luong.js — Lương (chỉ xem), nối API THẬT của app ketoan.
   ─────────────────────────────────────────────────────────────────────────
   Nguồn: `GET /api/external/luong?thang=YYYY-MM` (gọi thẳng hcns.app.routers.payroll.bang_luong_thang
   cross-app, cùng process) → `{thang, data:[...], source: 'hcns_live'|'table_fallback'}`.

   Số liệu dùng ĐÚNG trường HCNS trả, không tự tính lại:
   - Thực nhận = `luong_thuc_nhan` (= tong_cong − tong_tru của HCNS, đã trừ BHXH, đoàn phí, ứng lương,
     khấu trừ tay, phạt vắng `phat_vang_tien`, phạt chậm đơn `cham_don_phat`). QA 25/09: đối chiếu
     5 tháng (05→09/2026) tự cộng các khoản = luong_thuc_nhan, 0 lệch.
   - Tổng thu nhập = `tong_cong`. Trả ngày 5 / ngày 15 = `luong_m5` / `luong_m15` (khớp công thức màn cũ
     "lương theo công + ăn trưa − BHXH − ứng − đoàn phí", 0 lệch 4 tháng).
   - Biểu đồ "Quỹ lương theo phòng ban" cộng `luong_thuc_nhan` theo phòng ban từ CHÍNH bảng này. Màn cũ
     lấy `/api/bao-cao` luong_by_pb — đọc bảng hcns.payroll RỖNG (0 dòng) nên luôn trống (bug cũ).
     "Nhân sự theo phòng ban" đếm từ chính bảng lương tháng (xem veNhanSu) để tổng = thẻ số nhân viên.
   - BHXH doanh nghiệp đóng = `/api/external/bhxh` totals.nsdld_tong (hồ sơ BHXH Đang đóng — như màn BHXH).
   - KHÔNG có thuế TNCN trong API HCNS → không hiện cột/thẻ thuế (tránh số 0 giả).
   - Không có API xuất bảng lương → nút Xuất khoá.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-luong')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const SO_THANG = 24;   // như màn cũ: 24 tháng gần nhất
  const TOP_PB = 10;
  const N = (v) => Number(v || 0);
  const thangChu = (m) => 'tháng ' + m.slice(5, 7) + '/' + m.slice(0, 4);

  const congKhac = (r) => N(r.an_trua) + N(r.trach_nhiem) + N(r.cong_tac_xuong) + N(r.truc_toi) + N(r.toi_uu_kd);
  const truKhac = (r) => N(r.doan_phi_tru) + N(r.ung_luong) + N(r.khau_tru_tay) + N(r.phat_vang_tien) + N(r.cham_don_phat);
  const thucNhan = (r) => N(r.luong_thuc_nhan);
  const soCong = (r) => N(r.so_ngay_cong).toLocaleString('vi-VN', { maximumFractionDigits: 2 });
  const CT = 'kt-lg-ct';   // cột chi tiết thu nhập — ẩn mặc định, bật bằng ô chọn
  function datTip(k, text, trai) {
    const el = document.querySelector('#lg-kpi [data-kpi="' + k + '"] .kd-kpi__label'); if (!el) return;
    let b = el.querySelector('.kd-tip'); if (!text) { if (b) b.remove(); return; }
    if (!b) { el.insertAdjacentHTML('beforeend', ' ' + KD.tip(text, trai ? 'kd-tip--trai' : '')); b = el.querySelector('.kd-tip'); }
    b.dataset.tip = text; b.setAttribute('aria-label', text);
  }
  const tienAm = (v) => (v < 0 ? '<span class="kt-so--xau">−' + KD.tien(-v) + '</span>' : KD.tien(v));

  const THANG_URL = /^\d{4}-(0[1-9]|1[0-2])$/.test(KT.url.doc().thang || '') ? KT.url.doc().thang : '';
  function cacThang() {
    const out = []; const d = new Date(); d.setDate(1);
    for (let i = 0; i < SO_THANG; i += 1) { out.push(d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0')); d.setMonth(d.getMonth() - 1); }
    if (THANG_URL && !out.includes(THANG_URL)) out.push(THANG_URL);   // link tháng cũ hơn 24 tháng vẫn mở đúng tháng đó
    return out;
  }
  const napThang = (giu) => H.napChon($('lg-thang'), cacThang().map((m) => [m, 'Tháng ' + m.slice(5, 7) + '/' + m.slice(0, 4)]), 'Tháng hiện tại', giu);
  // Nạp sẵn danh sách tháng TRƯỚC khung danh sách: khung trả giá trị URL không có trong ô chọn về mặc định, và ô phải hiện đúng tháng ngay cả khi API lỗi.
  napThang(THANG_URL);
  const PB_TRONG = '__trong';   // nhân viên chưa gắn phòng ban — biểu đồ gom là "Chưa có phòng ban", ô lọc cũng chọn được

  /* ── Biểu đồ thanh ngang theo phòng ban ── */
  function veThanh(el, ds, dinhDang, rong) {
    if (!ds.length) { el.innerHTML = KD.khoiRong(rong, ''); return; }
    const max = Math.max.apply(null, ds.map((x) => x[1])) || 1, tong = ds.reduce((s, x) => s + x[1], 0);
    el.innerHTML = ds.slice(0, TOP_PB).map(([ten, v]) => '<div class="kd-rank__o"><span class="kd-rank__ten" title="' + esc(ten) + '">' + esc(ten) + '</span>'
      + '<span class="kd-rank__thanh"><span style="width:' + Math.max(0, Math.round(v / max * 100)) + '%"></span></span>'
      + '<b class="kd-rank__so num" title="' + (tong ? KD.phanTram(v / tong * 100) : '') + '">' + dinhDang(v) + '</b></div>').join('')
      + (ds.length > TOP_PB ? '<p class="kd-meta">+ ' + KD.soDem(ds.length - TOP_PB) + ' phòng ban khác</p>' : '');
  }
  function veQuyLuong(dong) {
    const m = {}; dong.forEach((r) => { const k = r.phong_ban || 'Chưa có phòng ban'; m[k] = (m[k] || 0) + thucNhan(r); });
    const ds = Object.entries(m).sort((a, b) => b[1] - a[1]);
    veThanh($('lg-bd-luong'), ds, (v) => KD.tienGon(v), 'Chưa có dữ liệu lương tháng này');
    $('lg-bd-luong-tong').textContent = KD.tienVnd(ds.reduce((s, x) => s + x[1], 0));
  }
  /* Nhân sự theo phòng ban đếm từ CHÍNH bảng lương tháng đang xem (QA nhất quán 25/09): trước đây lấy
     /api/bao-cao nhansu_by_pb = nhân viên "Đang làm" HIỆN TẠI, không theo tháng/không theo lọc phòng ban
     → tổng biểu đồ có thể khác thẻ "N nhân viên" khi xem tháng cũ hoặc lọc phòng ban. */
  function veNhanSu(dong) {
    const m = {}; dong.forEach((r) => { const k = r.phong_ban || 'Chưa có phòng ban'; m[k] = (m[k] || 0) + 1; });
    const ds = Object.entries(m).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    veThanh($('lg-bd-ns'), ds, (v) => KD.soDem(v), 'Chưa có nhân viên trong bảng lương tháng này');
    $('lg-bd-ns-tong').textContent = KD.soDem(dong.length) + ' người';
  }
  let bhxhDn = null, dongLuong = [], dongLuongAll = new Set();
  const taiBhxhDn = () => KD.api('/api/external/bhxh?' + KT.url.qs({ trang_thai: 'Đang đóng' })).then((r) => { bhxhDn = r.data || []; datBhxhDn(); }).catch(() => { bhxhDn = false; datBhxhDn(); });
  function datBhxhDn() {
    const el = document.querySelector('#lg-kpi [data-kpi="bhxh_dn"]'); if (!el || bhxhDn === null) return;
    if (bhxhDn === false) { el.querySelector('[data-v]').innerHTML = '<span class="kd-muted">—</span>'; el.querySelector('[data-phu]').textContent = 'Không tải được'; return; }
    // Chỉ cộng người CÓ trong bảng lương đang xem (khớp ma_nv, theo cả lọc phòng ban) để cùng tập với thẻ
    // "BH người lao động đóng" (QA nhất quán 25/09: hồ sơ BHXH còn người không có lương tháng này, và tên
    // phòng ban hồ sơ BHXH có thể khác bảng lương). Hồ sơ BHXH không lưu theo tháng → ghi rõ mức hiện tại.
    const coLuong = new Set(dongLuong.map((r) => r.ma_nv)), dong = bhxhDn.filter((x) => coLuong.has(x.ma_nv)), ngoai = bhxhDn.filter((x) => !dongLuongAll.has(x.ma_nv)).length;
    const tong = dong.reduce((s, x) => s + N(x.nsdld_tong), 0);
    el.querySelector('[data-v]').innerHTML = H.tienKpi(tong); el.querySelector('[data-v]').title = KD.tienVnd(tong);
    el.querySelector('[data-phu]').innerHTML = KD.soDem(dong.length) + ' người';
    datTip('bhxh_dn', 'Người có trong bảng lương đang xem, theo mức hồ sơ BHXH hiện tại.' + (ngoai > 0 && !ds.st.phong_ban ? ' ' + KD.soDem(ngoai) + ' người đang đóng không có lương tháng này.' : ''), true);
  }

  const ds = KT.danhSach({
    pfx: 'lg', donVi: 'nhân viên', khongTrang: true, khongDem: ['thang'],
    api: (q) => '/api/external/luong?' + KT.url.qs({ thang: q.thang || undefined }),
    macDinh: { thang: '', phong_ban: '', page: 1, size: 100, sort: '' },
    dong: { id: (r) => r.ma_nv },
    chuyen: (raw, q) => {
      let dong = (raw.data || []).slice();
      if (q.phong_ban) dong = dong.filter((r) => (q.phong_ban === PB_TRONG ? !r.phong_ban : r.phong_ban === q.phong_ban));
      dong.sort((a, b) => (a.phong_ban || '').localeCompare(b.phong_ban || '') || (a.ho_ten || '').localeCompare(b.ho_ten || ''));
      const phongBan = Array.from(new Set((raw.data || []).map((r) => r.phong_ban).filter(Boolean))).sort().map((p) => [p, p])
        .concat((raw.data || []).some((r) => !r.phong_ban) ? [[PB_TRONG, 'Chưa có phòng ban']] : []);
      const S = (f) => dong.reduce((s, r) => s + f(r), 0);
      return {
        thang: raw.thang, nguon: raw.source, dong, tatCa: raw.data || [], phong_ban: phongBan,
        tong: { tong_thu_nhap: S((r) => N(r.tong_cong)), bhxh_nld: S((r) => N(r.bhxh_tru)), tru_khac: S(truKhac), thuc_nhan: S(thucNhan),
          m5: S((r) => N(r.luong_m5)), m15: S((r) => N(r.luong_m15)), so_nv: dong.length },
      };
    },
    cot: [
      { key: 'nv', nhan: 'Nhân viên · phòng ban', ve: (r) => '<span title="' + esc([r.ma_nv, r.chuc_vu].filter(Boolean).join(' · ')) + '">' + H.ten(r.ho_ten, r.ma_nv + ' · ' + (r.phong_ban || 'Chưa có phòng ban')) + '</span>' },
      { key: 'cb', nhan: 'Lương cơ bản', num: true, lop: CT, ve: (r) => KD.tien(r.luong_co_ban) },
      { key: 'cong', nhan: 'Công', num: true, title: 'Số ngày công trong tháng', ve: (r) => soCong(r) },
      { key: 'tc', nhan: 'Lương theo công', num: true, lop: CT, ve: (r) => H.tien(r.luong_theo_cong) },
      { key: 'pc', nhan: 'Phụ cấp khác', num: true, lop: CT, title: 'Ăn trưa + trách nhiệm + công tác xưởng + trực tối + tối ưu KD — chi tiết trong Phiếu lương', ve: (r) => H.tien(congKhac(r)) },
      { key: 'hh', nhan: 'Hoa hồng + OT', num: true, lop: CT, ve: (r) => H.tien(N(r.hoa_hong) + N(r.ot_ca_gay)) },
      { key: 'tong', nhan: 'Tổng thu nhập', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.tong_cong) },
      { key: 'bh', nhan: 'BH người LĐ', num: true, title: 'BHXH + BHYT + BHTN trừ lương', ve: (r) => H.tien(r.bhxh_tru) },
      { key: 'tru', nhan: 'Trừ khác', num: true, title: 'Đoàn phí + ứng lương + khấu trừ + phạt vắng/đi muộn + phạt chậm đơn — chi tiết trong Phiếu lương', ve: (r) => H.tien(truKhac(r)) },
      { key: 'tl', nhan: 'Thực nhận', num: true, cls: 'kd-strong', ve: (r) => tienAm(thucNhan(r)) },
      { key: 'm5', nhan: 'Trả ngày 5', num: true, title: 'Lương theo công + ăn trưa − BHXH − ứng lương − đoàn phí (HCNS)', ve: (r) => tienAm(N(r.luong_m5)) },
      { key: 'm15', nhan: 'Trả ngày 15', num: true, title: 'Thực nhận − phần trả ngày 5 (HCNS)', ve: (r) => tienAm(N(r.luong_m15)) },
    ],
    kpi: {
      tong_thu_nhap: (d) => ({ v: H.tienKpi(d.tong.tong_thu_nhap), title: KD.tienVnd(d.tong.tong_thu_nhap), phu: KD.soDem(d.tong.so_nv) + ' nhân viên · ' + thangChu(d.thang) }),
      bhxh_nld: (d) => ({ v: H.tienKpi(d.tong.bhxh_nld), title: KD.tienVnd(d.tong.bhxh_nld), phu: 'Trừ khác ' + KD.tienGon(d.tong.tru_khac) }),
      thuc_linh: (d) => ({ v: H.tienKpi(d.tong.thuc_nhan), title: KD.tienVnd(d.tong.thuc_nhan), phu: '' }),
      chia_dot: (d) => ({ v: H.tienKpi(d.tong.m5), title: 'Ngày 5: ' + KD.tienVnd(d.tong.m5) + ' · ngày 15: ' + KD.tienVnd(d.tong.m15), phu: 'Ngày 15: ' + (d.tong.m15 < 0 ? '−' + KD.tienGon(-d.tong.m15) : KD.tienGon(d.tong.m15)) }),
      bhxh_dn: () => ({ v: null, phu: '' }),
    },
    phamVi: () => '',
    cong: (d) => { const S = (f) => d.dong.reduce((s, r) => s + f(r), 0);
      return [{ html: 'Cộng ' + KD.soDem(d.dong.length) + ' nhân viên' },
        { html: KD.tien(S((r) => N(r.luong_co_ban))), num: true, lop: CT }, { html: '' }, { html: KD.tien(S((r) => N(r.luong_theo_cong))), num: true, lop: CT },
        { html: KD.tien(S(congKhac)), num: true, lop: CT }, { html: KD.tien(S((r) => N(r.hoa_hong) + N(r.ot_ca_gay))), num: true, lop: CT },
        { html: KD.tien(S((r) => N(r.tong_cong))), num: true }, { html: KD.tien(S((r) => N(r.bhxh_tru))), num: true },
        { html: KD.tien(S(truKhac)), num: true }, { html: tienAm(S(thucNhan)), num: true },
        { html: tienAm(S((r) => N(r.luong_m5))), num: true }, { html: tienAm(S((r) => N(r.luong_m15))), num: true }]; },
    rong: (d, coLoc) => (coLoc ? ['Phòng ban này không có nhân viên trong bảng lương', 'Chọn "Tất cả" phòng ban.'] : ['Chưa có dữ liệu lương tháng này', 'Kiểm tra kết nối module Nhân sự hoặc đổi tháng.']),
    loi: 'Không tải được bảng lương',
    sauTai: (d) => {
      const st = ds.st;
      napThang(st.thang);
      // Phòng ban đang lọc mà tháng mới không có → vẫn giữ trong ô chọn (nếu không ô hiện "Tất cả" trong khi bảng đang lọc, bảng rỗng).
      const pb = d.phong_ban.slice(); if (st.phong_ban && !pb.some(([v]) => v === st.phong_ban)) pb.push([st.phong_ban, st.phong_ban === PB_TRONG ? 'Chưa có phòng ban' : st.phong_ban]);
      if (pb.length) H.napChon($('lg-phong_ban'), pb, 'Tất cả', st.phong_ban);
      datTip('bhxh_nld', 'BHXH + BHYT + BHTN trừ lương. Trừ khác: đoàn phí, ứng lương, khấu trừ, phạt ' + KD.tienVnd(d.tong.tru_khac) + '.');
      datTip('thuc_linh', 'Tổng quỹ lương thực nhận' + (d.nguon === 'hcns_live' ? '' : ' (bảng lương dự phòng)') + ', chưa gồm thuế TNCN.');
      dongLuong = d.dong; dongLuongAll = new Set(d.tatCa.map((r) => r.ma_nv)); veQuyLuong(d.dong); veNhanSu(d.dong); datBhxhDn();
    },
    panel: {
      ve: (r) => H.dauPanel('bi-person', 'info', r.ho_ten, esc(r.ma_nv + ' · ' + (r.chuc_vu || '') + ' · ' + (r.phong_ban || '')), '')
        + H.khoi('bi-plus-circle', 'Thu nhập', H.kv([
          ['Lương cơ bản', KD.tienVnd(r.luong_co_ban)], ['Lương theo công (' + soCong(r) + ' công)', KD.tienVnd(r.luong_theo_cong)],
          ['Ăn trưa', KD.tienVnd(r.an_trua)], ['Trách nhiệm', KD.tienVnd(r.trach_nhiem)], ['Công tác xưởng', KD.tienVnd(r.cong_tac_xuong)],
          ['Hoa hồng', KD.tienVnd(r.hoa_hong)], ['OT ca gãy (' + (r.ot_so_gio || 0) + ' giờ)', KD.tienVnd(r.ot_ca_gay)],
          ['Trực tối', KD.tienVnd(r.truc_toi)], ['Tối ưu KD', KD.tienVnd(r.toi_uu_kd)],
          ['Tổng thu nhập', KD.tienVnd(r.tong_cong), true],
        ]))
        + H.khoi('bi-dash-circle', 'Khấu trừ', H.kv([
          ['BHXH, BHYT, BHTN người lao động', KD.tienVnd(r.bhxh_tru)], ['Đoàn phí', KD.tienVnd(r.doan_phi_tru)],
          ['Ứng lương' + (N(r.ung_luong_so_lan) ? ' (' + KD.soDem(r.ung_luong_so_lan) + ' lần)' : ''), KD.tienVnd(r.ung_luong)], ['Khấu trừ khác', KD.tienVnd(r.khau_tru_tay)],
          ['Phạt vắng (' + KD.soDem(N(r.vang_ca_sang) + N(r.vang_ca_chieu)) + ' ca)', KD.tienVnd(r.phat_vang_tien)],
          ['Phạt chậm đơn (SLA)', KD.tienVnd(r.cham_don_phat)],
          ['Đi muộn', KD.soDem(r.di_muon_so_lan) + ' lần' + (N(r.di_muon_tru_pct) ? ' — trừ ' + r.di_muon_tru_pct + '% hoa hồng/tối ưu (đã trừ trong thu nhập)' : '')],
          ['Thực nhận', KD.tienVnd(thucNhan(r)), true],
        ]))
        + H.khoi('bi-calendar2-check', 'Chia đợt trả', H.kv([['Trả ngày 5', KD.tienVnd(r.luong_m5)], ['Trả ngày 15', KD.tienVnd(r.luong_m15)]])),
      nut: () => '',
    },
  });
  $('lg-xuat').addEventListener('click', (e) => { e.preventDefault(); window.showToast && window.showToast('info', 'App kế toán chưa có API xuất bảng lương.'); });
  const datCt = (bat) => { $('lg-ct').checked = bat; $('lg-bang').classList.toggle('kt-lg-hien', bat); };
  $('lg-ct').addEventListener('change', (e) => datCt(e.target.checked));
  datCt(false);
  taiBhxhDn();
  ds.tai();
})();
