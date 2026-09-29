/* kt-quang-cao.js — Chi phí quảng cáo: 2 tab dùng chung ô chọn tháng.
   Tab 1 (màn cũ #page-ads): /api/external/ads trả từng dòng ngày × kênh → gộp theo ngày tại trình duyệt; CPD = chi phí / data.
   Tab 2 (màn cũ #page-cpa-ads): /api/bao-cao/cpa?thang (theo nhóm) + /cpa/per-don?thang_hoan_thanh + /cpa/cohort?from&to
   (mở khi bấm), tính lại qua POST /api/ads-phan-bo/recalc/<thang>.
   Lưu ý: màn cũ (và bản đầu màn này) gọi /per-don?thang= và /cohort?thang= — sai tên tham số nên API trả 422
   và 2 bảng đó CHƯA TỪNG hiện số; ở đây gọi đúng tham số và đổi tên field theo đúng phản hồi thật
   (quote_number, customer_name, ads_gang[], margin_after_ads; cohort: thang_chi, ads_total, by_thang_ht{}).
   Xuất Excel = CSV từ bảng đang xem (backend không có endpoint xuất). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-quang-cao')) return;
  const H = KT.H, $ = (id) => document.getElementById(id);
  const u0 = KT.url.doc();
  let tab = u0.tab === 'cpa' ? 'cpa' : 'ngay', lAd = 0, lCp = 0, lCh = 0, adThang = null, cpThang = null, chThang = null, cpDon = [];
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const cuoiThang = (m) => KD.iso(new Date(+m.slice(0, 4), +m.slice(5, 7), 0));
  const chia = (a, b) => (b ? a / b : 0);
  /* Làm tròn một dãy số lẻ về đồng sao cho Σ kết quả = làm tròn(Σ gốc) — phần dư dồn cho phần lẻ lớn nhất. */
  function chiaTron(ds, dich) {
    const tong = dich != null ? dich : Math.round(ds.reduce((a, x) => a + x, 0)), san = ds.map(Math.floor);
    let du = tong - san.reduce((a, x) => a + x, 0);
    ds.map((x, i) => [x - san[i], i]).sort((a, b) => b[0] - a[0]).forEach(([, i]) => { if (du > 0) { san[i] += 1; du -= 1; } });
    return san;
  }
  const kpiDat = (pfx, k, v, phu, title) => { const el = document.querySelector('#' + pfx + '-kpi [data-kpi="' + k + '"]'); const o = el.querySelector('[data-v]'); o.innerHTML = v; if (title) o.title = title; else o.removeAttribute('title'); el.querySelector('[data-phu]').innerHTML = phu || ''; };
  const kpiCho = (pfx, loi) => document.querySelectorAll('#' + pfx + '-kpi [data-v]').forEach((x) => { x.innerHTML = loi ? '<span class="kd-muted">—</span>' : '<span class="kd-skel kd-skel--kpi"></span>'; x.parentNode.querySelector('[data-phu]').innerHTML = ''; });
  const trang = (pfx, cuon, tt) => { $(cuon).hidden = false; $(tt).innerHTML = ''; };
  const thang = () => $('qc-thang').value;

  /* ── Ô chọn tháng: 24 tháng gần nhất (như 2 ô tháng màn cũ #page-ads / #page-cpa-ads), mặc định tháng hiện hành ── */
  (function napThang() { const h = new Date(), ds = [];
    for (let i = 0; i < 24; i++) { const d = new Date(h.getFullYear(), h.getMonth() - i, 1); const m = KD.iso(d).slice(0, 7); ds.push([m, 'Tháng ' + thangChu(m)]); }
    if (u0.thang && /^\d{4}-\d{2}$/.test(u0.thang) && !ds.some((x) => x[0] === u0.thang)) ds.push([u0.thang, 'Tháng ' + thangChu(u0.thang)]);
    H.napChon($('qc-thang'), ds, '', u0.thang && /^\d{4}-\d{2}$/.test(u0.thang) ? u0.thang : ds[0][0]); })();
  /* URL giữ tab, tháng + 2 ô lọc bảng "Ads theo từng đơn" (q = tìm, nhom = nhóm hàng) → F5 / gửi link mở đúng như đang xem. */
  function ghiUrl() { try { KT.url.ghi({ tab, thang: thang(), q: $('cd-q').value.trim(), nhom: $('cd-nhom').value }, { tab: 'ngay', thang: $('qc-thang').options[0].value, q: '', nhom: '' }); } catch (e) { /* khung xem trước */ } }
  $('cd-q').value = u0.q || '';
  if ([...$('cd-nhom').options].some((o) => o.value === u0.nhom)) $('cd-nhom').value = u0.nhom;
  function capNhatNut() {
    $('qc-recalc').hidden = tab !== 'cpa';
  }

  /* ═════════ Tab 1: chi phí theo ngày ═════════ */
  async function taiAds() {
    const l = ++lAd, m = thang(); adThang = m; kpiCho('ad'); $('ad-pham-vi').textContent = ''; trang('ad', 'ad-cuon', 'ad-tt'); $('ad-tfoot').innerHTML = ''; $('ad-tbody').innerHTML = KT.hangCho(6, 8); $('ak-noi-dung').innerHTML = KD.KHUNG_TAI;
    try {
      const d = await KD.api('/api/external/ads?' + KT.url.qs({ tu_ngay: m + '-01', den_ngay: cuoiThang(m) })); if (l !== lAd) return;
      const dong = d.data || d.items || [], ngay = {}, kenh = {};
      dong.forEach((x) => { const n = String(x.ngay).slice(0, 10), k = x.kenh || 'Khác';
        const a = ngay[n] || (ngay[n] = { ngay: n, kenhMap: {}, chi: 0, inbox: 0, data: 0 });
        /* API trả 1 dòng / (ngày × kênh × sản phẩm) → gộp theo kênh trong ngày như màn cũ (không lặp chip "Facebook" theo từng sản phẩm) */
        const kk = a.kenhMap[k] || (a.kenhMap[k] = { kenh: k, chi_phi: 0, sp: 0 }); kk.chi_phi += +x.chi_phi || 0; kk.sp += 1; a.chi += +x.chi_phi || 0; a.inbox += +x.so_inbox || 0; a.data += +x.so_data || 0;
        const b = kenh[k] || (kenh[k] = { kenh: k, chi: 0, inbox: 0, data: 0, ngay: new Set() }); b.chi += +x.chi_phi || 0; b.inbox += +x.so_inbox || 0; b.data += +x.so_data || 0; b.ngay.add(n); });
      Object.values(ngay).forEach((x) => { x.kenh = Object.values(x.kenhMap); });
      const ds = Object.values(ngay).sort((a, b) => (a.ngay < b.ngay ? 1 : -1)), kd = Object.values(kenh).sort((a, b) => b.chi - a.chi);
      const T = ds.reduce((a, x) => ({ chi: a.chi + x.chi, inbox: a.inbox + x.inbox, data: a.data + x.data }), { chi: 0, inbox: 0, data: 0 });
      kpiDat('ad', 'chi', H.tienKpi(T.chi), KD.soDem(ds.length) + ' ngày có chạy · ' + KD.soDem(kd.length) + ' kênh', KD.tienVnd(T.chi));
      kpiDat('ad', 'inbox', H.dem(T.inbox, 'tin'), T.inbox ? 'Mỗi tin ' + KD.tienVnd(Math.round(chia(T.chi, T.inbox))) : '');
      kpiDat('ad', 'data', H.dem(T.data, 'data'), T.inbox ? 'Tỷ lệ inbox ra data ' + KD.phanTram(chia(T.data, T.inbox) * 100) : '');
      kpiDat('ad', 'cpd', T.data ? H.tienKpi(Math.round(chia(T.chi, T.data))) : '<span class="kd-muted">—</span>', 'Chi phí ÷ số data', T.data ? KD.tienVnd(Math.round(chia(T.chi, T.data))) : '');
      $('ad-pham-vi').textContent = '';
      if (!ds.length) { $('ad-cuon').hidden = true; $('ad-tt').innerHTML = KD.khoiRong('Tháng ' + thangChu(m) + ' chưa có chi phí quảng cáo', 'Marketing chưa nhập số liệu ngày nào trong tháng này. Chọn tháng khác ở ô phía trên.'); $('ak-noi-dung').innerHTML = '<p class="kd-muted kt-qc-ak-rong">Chưa có kênh nào.</p>'; return; }
      $('ad-tbody').innerHTML = ds.map((x) => '<tr><td class="kt-qc-ngay">' + KD.ngay(x.ngay) + '</td>'
        + '<td><ul class="kt-qc-kenh">' + x.kenh.slice().sort((a, b) => b.chi_phi - a.chi_phi).map((k) => '<li><span class="kd-chip kd-chip--xam">' + esc(k.kenh) + '</span><span class="num">' + KD.tien(k.chi_phi) + '</span><span class="kd-meta">' + KD.soDem(k.sp) + ' sản phẩm</span></li>').join('') + '</ul></td>'
        + '<td class="num kd-strong">' + KD.tien(x.chi) + '</td><td class="num">' + KD.soDem(x.inbox) + '</td><td class="num">' + KD.soDem(x.data) + '</td><td class="num">' + (x.data ? KD.tien(Math.round(x.chi / x.data)) : '<span class="kd-muted">—</span>') + '</td></tr>').join('');
      $('ad-tfoot').innerHTML = '<tr><th scope="row" colspan="2">Cộng ' + KD.soDem(ds.length) + ' ngày</th><td class="num">' + KD.tien(T.chi) + '</td><td class="num">' + KD.soDem(T.inbox) + '</td><td class="num">' + KD.soDem(T.data) + '</td><td class="num">' + (T.data ? KD.tien(Math.round(T.chi / T.data)) : '—') + '</td></tr>';
      $('ak-noi-dung').innerHTML = '<ul class="kt-qc-ak">' + kd.map((k) => '<li><div class="kt-qc-ak__dong"><span class="kd-strong">' + esc(k.kenh) + '</span><span class="num kd-strong">' + KD.tien(k.chi) + '</span></div>'
        + '<p class="kd-meta kt-qc-ak__phu">' + KD.phanTram(chia(k.chi, T.chi) * 100) + ' tổng chi · ' + KD.soDem(k.ngay.size) + ' ngày chạy</p>'
        + '<p class="kd-meta kt-qc-ak__phu">' + KD.soDem(k.inbox) + ' inbox · ' + KD.soDem(k.data) + ' data · CPD ' + (k.data ? KD.tien(Math.round(k.chi / k.data)) : '—') + '</p></li>').join('') + '</ul>';
    } catch (e) { if (l !== lAd) return; adThang = null; kpiCho('ad', true); $('ad-cuon').hidden = true; $('ak-noi-dung').innerHTML = ''; KD.khoiLoi($('ad-tt'), 'Không tải được chi phí quảng cáo', e, taiAds); }
  }

  /* ═════════ Tab 2: phân bổ CPA ═════════ */
  const NHOM_COT = { ads_go: 'Đồ Gỗ', ads_may: 'Đồ Mây', ads_du_an: 'Dự Án' };
  async function taiCpa() {
    const l = ++lCp, m = thang(); cpThang = m; kpiCho('cp'); $('cp-pham-vi').textContent = ''; $('cn-phu').textContent = '';
    ['cn', 'cd'].forEach((p) => { trang(p, p + '-cuon', p + '-tt'); $(p + '-tfoot').innerHTML = ''; }); $('cn-tbody').innerHTML = KT.hangCho(5, 3); $('cd-tbody').innerHTML = KT.hangCho(4, 6);
    if ($('ch-khoi').open) taiCohort(); else chThang = null;
    try {
      const [t, p] = await Promise.all([KD.api('/api/bao-cao/cpa?' + KT.url.qs({ thang: m })), KD.api('/api/bao-cao/cpa/per-don?' + KT.url.qs({ thang_hoan_thanh: m }))]); if (l !== lCp) return;
      const rows = t.by_nhom || [];
      /* Quỹ từng nhóm làm tròn sao cho Σ = "Chi ads trong tháng" (thẻ) tới từng đồng */
      const quy0 = rows.map((x) => +x.ads_pool || 0), quyDich = Math.abs(quy0.reduce((a, v) => a + v, 0) - (+t.ads_total_chi || 0)) < 1 ? Math.round(+t.ads_total_chi || 0) : null;
      chiaTron(quy0, quyDich).forEach((v, i) => { rows[i].ads_pool = v; });
      const don = rows.reduce((a, x) => a + (+x.so_don || 0), 0), ht = rows.reduce((a, x) => a + (+x.so_don_da_hoan_thanh || 0), 0), tong = +t.ads_total_chi || 0, pb = +t.tong_phan_bo || 0;
      kpiDat('cp', 'tong', H.tienKpi(tong), t.recalc_luc ? 'Tính phân bổ lúc ' + KD.ngayGio(t.recalc_luc) : 'Chưa tính phân bổ', KD.tienVnd(tong));
      kpiDat('cp', 'pb', H.tienKpi(pb), Math.round(tong - pb) >= 1 ? H.pill('warning', KD.tienGon(tong - pb) + ' chưa có đơn nhận') : tong ? H.pill('success', 'Phân bổ hết') : '', KD.tienVnd(pb));
      kpiDat('cp', 'don', H.dem(don, 'đơn'), KD.soDem(ht) + '/' + KD.soDem(don) + ' đơn đã hoàn thành' + (don ? ' (' + KD.phanTram(ht / don * 100) + ')' : ''));
      kpiDat('cp', 'cpa', don ? H.tienKpi(Math.round(pb / don)) : '<span class="kd-muted">—</span>', 'Đã phân bổ ÷ số đơn', don ? KD.tienVnd(Math.round(pb / don)) : '');
      $('cp-pham-vi').textContent = '';
      const nhanPb = document.querySelector('#cp-kpi [data-kpi="pb"] .kd-kpi__label');
      if (nhanPb && !nhanPb.querySelector('.kd-tip')) nhanPb.insertAdjacentHTML('beforeend', ' ' + KD.tip('Chi ads trong tháng chia vào quỹ từng nhóm hàng rồi chia đều cho các đơn của nhóm. Nhóm không có đơn thì phần ads chưa có đơn nhận. Marketing sửa số hoặc đơn đổi nhóm → bấm "Tính lại phân bổ".'));
      $('cn-phu').textContent = rows.length ? 'Tổng quỹ ' + KD.tienVnd(rows.reduce((a, x) => a + (+x.ads_pool || 0), 0)) : '';
      if (!rows.length) { $('cn-cuon').hidden = true; $('cn-tt').innerHTML = KD.khoiRong('Tháng ' + thangChu(m) + ' chưa có phân bổ', tong ? 'Có chi phí ads nhưng chưa tính phân bổ — bấm "Tính lại phân bổ".' : 'Chưa có chi phí quảng cáo trong tháng.'); }
      else {
        $('cn-tbody').innerHTML = rows.map((x) => '<tr><td>' + esc(x.nhom_master || 'Chưa phân loại') + '</td><td class="num">' + KD.tien(x.ads_pool || 0) + '</td><td class="num">' + KD.soDem(x.so_don || 0) + '</td><td class="num">' + KT.tienSo(x.cpa_avg)
          + (x.so_don ? '' : ' <span class="pill pill--warning">Không có đơn</span>') + '</td><td>' + (x.so_don ? KD.soDem(x.so_don_da_hoan_thanh || 0) + '/' + KD.soDem(x.so_don) + ' <span class="kd-meta">(' + KD.phanTram((x.so_don_da_hoan_thanh || 0) / x.so_don * 100) + ')</span>' : '<span class="kd-muted">—</span>') + '</td></tr>').join('');
        $('cn-tfoot').innerHTML = '<tr><th scope="row">Cộng</th><td class="num">' + KD.tien(rows.reduce((a, x) => a + (+x.ads_pool || 0), 0)) + '</td><td class="num">' + KD.soDem(don) + '</td><td class="num">' + (don ? KD.tien(Math.round(pb / don)) : '—') + '</td><td>' + KD.soDem(ht) + '/' + KD.soDem(don) + '</td></tr>';
      }
      /* per-don: 1 dòng / đơn hoàn thành trong tháng; ads_gang[] = phần ads gánh theo nhóm × tháng chi → cộng theo nhóm */
      const theoNhom = (g, ten) => (g || []).filter((a) => a.nhom_master === ten).reduce((s, a) => s + (+a.so_tien || 0), 0);
      const tho = (p.rows || []).map((x) => { const go = theoNhom(x.ads_gang, 'Đồ Gỗ'), may = theoNhom(x.ads_gang, 'Đồ Mây'), da = theoNhom(x.ads_gang, 'Dự Án');
        return { ma_bg: x.quote_number, khach: x.customer_name || '', tong_don: +x.tong_don || 0, ads_go: go, ads_may: may, ads_du_an: da, ads_khac: (+x.tong_ads || 0) - go - may - da,
          thang_chi: [...new Set((x.ads_gang || []).map((a) => a.thang_chi))].sort() }; });
      /* VND nguyên: làm tròn từng cột theo phần dư lớn nhất (Σ dòng = tổng cột làm tròn), rồi Tổng ads = Σ các nhóm,
         Còn lại = doanh thu − tổng ads trên chính số hiển thị → hàng và dòng Cộng khớp từng đồng. */
      /* tổng từng cột nhóm chia từ làm tròn(Σ tổng ads) — cùng cách báo cáo KQKD chia "Quảng cáo nhóm …" → 2 màn cùng số */
      const NH = ['ads_go', 'ads_may', 'ads_du_an', 'ads_khac'], SS = (k) => tho.reduce((a, x) => a + x[k], 0);
      const dichNh = chiaTron(NH.map(SS), Math.round(NH.reduce((a, k) => a + SS(k), 0)));
      [['tong_don', null]].concat(NH.map((k, i) => [k, dichNh[i]])).forEach(([k, dich]) => { const v = chiaTron(tho.map((x) => x[k]), dich); tho.forEach((x, i) => { x[k] = v[i]; }); });
      cpDon = tho.map((x) => Object.assign(x, { tong_ads: x.ads_go + x.ads_may + x.ads_du_an + x.ads_khac })).map((x) => Object.assign(x, { con_lai: x.tong_don - x.tong_ads }))
        .sort((a, b) => b.tong_ads - a.tong_ads);
      veDon();
    } catch (e) { if (l !== lCp) return; cpThang = null; kpiCho('cp', true); ['cn', 'cd'].forEach((p) => { $(p + '-cuon').hidden = true; }); $('cd-tt').innerHTML = ''; KD.khoiLoi($('cn-tt'), 'Không tải được phân bổ quảng cáo', e, taiCpa); }
  }
  function veDon() {
    const tim = $('cd-q').value.trim(), nhom = $('cd-nhom').value;
    const ds = cpDon.filter((x) => KT.khopTim([x.ma_bg, x.khach], tim) && (!nhom || +x[nhom] > 0));
    $('cd-cuon').hidden = false; $('cd-tt').innerHTML = ''; $('cd-tfoot').innerHTML = '';
    if (!ds.length) { $('cd-cuon').hidden = true; $('cd-tt').innerHTML = cpDon.length ? KD.khoiRong('Không có đơn nào khớp bộ lọc', 'Thử bỏ ô tìm hoặc chọn "Tất cả nhóm".') : KD.khoiRong('Chưa có đơn nào nhận phân bổ tháng ' + thangChu(thang()), 'Đơn duyệt trong tháng mới được chia chi phí quảng cáo.'); return; }
    const S = (k) => ds.reduce((a, x) => a + (+x[k] || 0), 0);
    /* Dòng nhỏ dưới Tổng ads: tách theo nhóm hàng (chỉ nhóm có số) — thay 3 cột Ads Gỗ / Mây / Dự Án */
    const tach = (g, luonHien) => { const p = Object.keys(NHOM_COT).filter((k) => luonHien || +g(k)).map((k) => NHOM_COT[k] + ' ' + KD.tien(g(k))); return p.length ? '<span class="kt-khach__ma">' + p.join(' · ') + '</span>' : ''; };
    const tyLe = (a, dt) => '<span class="kt-khach__ma">ads ' + (dt ? KD.phanTram(a / dt * 100) : '—') + '</span>';
    $('cd-tbody').innerHTML = ds.map((x) => '<tr><td>' + H.ten(x.ma_bg, x.khach + (x.thang_chi.length ? ' · ads tháng ' + x.thang_chi.map(thangChu).join(', ') : '')) + '</td><td class="num">' + KD.tien(x.tong_don || 0) + '</td>'
      + '<td class="num"><b>' + KD.tien(x.tong_ads || 0) + '</b>' + tach((k) => x[k]) + '</td><td class="num">' + KD.tien(x.con_lai) + tyLe(x.tong_ads, x.tong_don) + '</td></tr>').join('');
    $('cd-tfoot').innerHTML = '<tr><th scope="row">Cộng ' + KD.soDem(ds.length) + ' đơn</th><td class="num">' + KD.tien(S('tong_don')) + '</td>'
      + '<td class="num">' + KD.tien(S('tong_ads')) + tach(S, true) + '</td><td class="num">' + KD.tien(S('con_lai')) + tyLe(S('tong_ads'), S('tong_don')) + '</td></tr>';
  }
  $('cd-q').addEventListener('input', KD.debounce(() => { ghiUrl(); veDon(); }, 200)); $('cd-nhom').addEventListener('change', () => { ghiUrl(); veDon(); });

  const lui = (m, n) => KD.iso(new Date(+m.slice(0, 4), +m.slice(5, 7) - 1 - n, 1)).slice(0, 7);
  async function taiCohort() {
    const l = ++lCh, m = thang(); chThang = m; $('ch-cuon').hidden = false; $('ch-tt').innerHTML = ''; $('ch-tbody').innerHTML = KT.hangCho(9, 3);
    try {
      /* 6 tháng chi ads gần nhất tính tới tháng chọn; ô = phần ads của tháng đó đã gắn vào đơn hoàn thành ở tháng T+n */
      const d = await KD.api('/api/bao-cao/cpa/cohort?' + KT.url.qs({ from: lui(m, 5), to: m })); if (l !== lCh) return;
      const rows = (d.rows || []).filter((x) => +x.ads_total || Object.keys(x.by_thang_ht || {}).length).reverse();
      if (!rows.length) { $('ch-cuon').hidden = true; $('ch-tt').innerHTML = KD.khoiRong('Chưa có dữ liệu theo tháng', 'Cần ít nhất một tháng đã tính phân bổ.'); return; }
      const o = (v, t) => (+v ? KD.tien(v) + '<span class="kt-khach__ma">' + KD.phanTram(chia(v, t) * 100) + '</span>' : '<span class="kd-muted">—</span>');
      $('ch-tbody').innerHTML = rows.map((x) => {
        const b = x.by_thang_ht || {}, t0 = [0, 0, 0, 0, 0, +b.chua_hoan_thanh || 0];
        Object.keys(b).forEach((k) => { if (k === 'chua_hoan_thanh') return; const n = (+k.slice(0, 4) - +x.thang_chi.slice(0, 4)) * 12 + (+k.slice(5, 7) - +x.thang_chi.slice(5, 7)); t0[Math.min(4, Math.max(0, n))] += +b[k] || 0; });
        const t = chiaTron(t0), tong = t.reduce((a, v) => a + v, 0);   // Σ 6 ô = Tổng chi của dòng, tới từng đồng
        return '<tr><td>Tháng ' + thangChu(x.thang_chi) + '</td><td class="num kd-strong" title="API: ' + KD.tienVnd(+x.ads_total || 0) + '">' + KD.tien(tong) + '</td>' + t.slice(0, 5).map((v) => '<td class="num">' + o(v, tong) + '</td>').join('')
          + '<td class="num">' + o(t[5], tong) + '</td><td class="num">' + KD.phanTram((+x.ty_le_hoan_thanh || 0) * 100) + '</td></tr>';
      }).join('');
    } catch (e) { if (l !== lCh) return; chThang = null; $('ch-cuon').hidden = true; KD.khoiLoi($('ch-tt'), 'Không tải được bảng theo tháng', e, taiCohort); }
  }
  $('ch-khoi').addEventListener('toggle', () => { if ($('ch-khoi').open && chThang !== thang()) taiCohort(); });

  /* ── Tính lại phân bổ ── */
  const dlg = $('qc-dlg');
  $('qc-recalc').addEventListener('click', () => { $('qc-dlg-nd').textContent = 'Chia lại toàn bộ chi phí quảng cáo tháng ' + thangChu(thang()) + ' vào các đơn theo số liệu Marketing và nhóm hàng hiện tại. Số phân bổ cũ của tháng này sẽ bị thay thế; các báo cáo dùng CPA (lãi theo đơn, thưởng) sẽ đổi theo.'; KD.moHopThoai(dlg); });
  $('qc-dlg-ok').addEventListener('click', async () => { const nut = $('qc-dlg-ok'); nut.disabled = true;
    try { await KD.api('/api/ads-phan-bo/recalc/' + encodeURIComponent(thang()), KD.JSON_POST({})); dlg.close(); window.showToast && window.showToast('ok', 'Đã tính lại phân bổ quảng cáo tháng ' + thangChu(thang())); taiCpa(); }
    catch (e) { KD.baoLoiHopThoai(dlg, 'Chưa tính lại được: ' + e.message); } finally { nut.disabled = false; } });

  /* ── Xuất Excel: CSV các bảng của tab đang xem ── */
  $('qc-xuat').addEventListener('click', () => {
    const bang = tab === 'cpa' ? [['cn-cuon', 'Quỹ quảng cáo theo nhóm hàng'], ['cd-cuon', 'Chi phí quảng cáo gánh trên từng đơn']].concat($('ch-khoi').open ? [['ch-cuon', 'Ads tháng nào ra đơn tháng nào']] : []) : [['ad-cuon', 'Chi phí quảng cáo theo ngày']];
    const co = bang.filter(([id]) => !$(id).hidden);
    if (!co.length) { window.showToast && window.showToast('warn', 'Chưa có số liệu để xuất'); return; }
    const t = document.createElement('table');
    co.forEach(([id, ten]) => { t.insertAdjacentHTML('beforeend', '<tr><th>' + esc(ten) + '</th></tr>'); $(id).querySelectorAll('tr').forEach((tr) => t.appendChild(tr.cloneNode(true))); t.insertAdjacentHTML('beforeend', '<tr><td></td></tr>'); });
    KT.xuatCsv(t, (tab === 'cpa' ? 'phan-bo-quang-cao_' : 'chi-phi-quang-cao_') + thang(), ['Chi phí quảng cáo — tháng ' + thangChu(thang()), 'Đơn vị tính: VND']);
  });

  /* ── Tab + tháng ── */
  function taiTab() { if (tab === 'ngay' && adThang !== thang()) taiAds(); if (tab === 'cpa' && cpThang !== thang()) taiCpa(); }
  const tabs = KD.ganTab($('qc-tabs'), (k) => { tab = k; capNhatNut(); ghiUrl(); taiTab(); });
  $('qc-thang').addEventListener('change', () => { adThang = cpThang = chThang = null; capNhatNut(); ghiUrl(); taiTab(); });
  capNhatNut(); tabs.chon(tab);
})();
