/* kt-lctt.js — Lưu chuyển tiền tệ B03-DN (khung kt-bao-cao.js) + đủ số liệu màn cũ #cashflow.
   API thật (cùng màn cũ):
   - GET /api/bao-cao/cashflow?from&to → {so_du_dau_ky, operating:{thu_kh,tra_ncc,tra_ads,tra_luong,tra_lai_vay,nop_thue_tndn,
     thu_khac,chi_khac,net}, investing:{mua_ccdc,sua_chua,thanh_ly_tscd,chi_cho_vay,thu_hoi_cho_vay,chi_gop_von,thu_hoi_gop_von,
     thu_lai,net}, financing:{nhan_von,tra_von,vay_nh,tra_no_nh,tra_goc_thue_tc,chia_co_tuc,net}, net_cashflow, so_du_cuoi_ky,
     daily, by_account} (mỗi khoản mục có items = 5 giao dịch lớn nhất). Gọi 2 lần song song: kỳ này + kỳ liền trước cùng số ngày.
     Bảng khoản mục KM bên dưới liệt kê ĐỦ mã số B03 như mẫu chính thức (dòng chưa có số hiện "—"); mã dòng tiền gắn vào
     phiếu thu/chi khai ở một chỗ: app/services/phan_loai_cf.py.
   - GET /api/bao-cao/tinh-hinh-tai-chinh?as_of=<đến ngày> · /cong-no-ngam?from&to · /cashflow-validation?from&to
     (tải riêng sau bảng chính, lỗi khối nào báo khối đó).
   Tổng thu/chi và tỷ lệ thu/chi tính từ các khoản mục đã phân loại (API không trả tong_thu/tong_chi —
   màn cũ đọc 2 field không tồn tại nên luôn hiện "Thu 0 − Chi 0"). */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-lctt')) return;
  const $ = (id) => document.getElementById(id), H = KT.H;

  /* Kỳ trước: kỳ trọn tháng → đúng các tháng liền trước (như KQKD); kỳ lẻ ngày → cùng số ngày liền trước. */
  function previousRange(tu, den) {
    const a = new Date(tu + 'T00:00:00'), b = new Date(den + 'T00:00:00');
    if (a.getDate() === 1 && new Date(b.getFullYear(), b.getMonth(), b.getDate() + 1).getDate() === 1) {
      const n = (b.getFullYear() - a.getFullYear()) * 12 + b.getMonth() - a.getMonth() + 1;
      return { tu: KD.iso(new Date(a.getFullYear(), a.getMonth() - n, 1)), den: KD.iso(new Date(a.getFullYear(), a.getMonth(), 0)) };
    }
    const dTu = new Date(tu + 'T00:00:00'), dDen = new Date(den + 'T00:00:00');
    const nDays = Math.round((dDen - dTu) / 86400000) + 1;
    const prevDen = new Date(dTu); prevDen.setDate(prevDen.getDate() - 1);
    const prevTu = new Date(prevDen); prevTu.setDate(prevTu.getDate() - (nDays - 1));
    return { tu: KD.iso(prevTu), den: KD.iso(prevDen) };
  }

  /* Khoản mục: [mã, tên, nhóm API, khoá, dấu (+ thu / − chi), tên ngắn] */
  const KM = [
    ['01', 'Tiền thu từ bán hàng, cung cấp dịch vụ', 'operating', 'thu_kh', 1, 'Thu khách hàng'],
    ['02', 'Tiền chi trả cho người cung cấp hàng hoá, dịch vụ', 'operating', 'tra_ncc', -1, 'Trả NCC'],
    ['02', 'Tiền chi trả quảng cáo, marketing', 'operating', 'tra_ads', -1, 'Trả quảng cáo'],
    ['03', 'Tiền chi trả cho người lao động', 'operating', 'tra_luong', -1, 'Trả lương'],
    ['04', 'Tiền chi trả lãi vay', 'operating', 'tra_lai_vay', -1, 'Trả lãi vay'],
    ['05', 'Tiền chi nộp thuế thu nhập doanh nghiệp', 'operating', 'nop_thue_tndn', -1, 'Nộp thuế TNDN'],
    ['06', 'Tiền thu khác từ hoạt động kinh doanh', 'operating', 'thu_khac', 1, 'Thu khác'],
    ['07', 'Tiền chi khác cho hoạt động kinh doanh', 'operating', 'chi_khac', -1, 'Chi khác'],
    ['21', 'Tiền chi mua sắm tài sản cố định, công cụ dụng cụ', 'investing', 'mua_ccdc', -1, 'Mua CCDC/TSCĐ'],
    ['21', 'Tiền chi sửa chữa lớn tài sản cố định', 'investing', 'sua_chua', -1, 'Sửa chữa lớn'],
    ['22', 'Tiền thu từ thanh lý, nhượng bán tài sản cố định', 'investing', 'thanh_ly_tscd', 1, 'Thanh lý TSCĐ'],
    ['23', 'Tiền chi cho vay, mua các công cụ nợ của đơn vị khác', 'investing', 'chi_cho_vay', -1, 'Chi cho vay'],
    ['24', 'Tiền thu hồi cho vay, bán lại các công cụ nợ của đơn vị khác', 'investing', 'thu_hoi_cho_vay', 1, 'Thu hồi cho vay'],
    ['25', 'Tiền chi đầu tư góp vốn vào đơn vị khác', 'investing', 'chi_gop_von', -1, 'Chi góp vốn'],
    ['26', 'Tiền thu hồi đầu tư góp vốn vào đơn vị khác', 'investing', 'thu_hoi_gop_von', 1, 'Thu hồi góp vốn'],
    ['27', 'Tiền thu lãi cho vay, cổ tức và lợi nhuận được chia', 'investing', 'thu_lai', 1, 'Thu lãi, cổ tức'],
    ['31', 'Tiền thu từ phát hành cổ phiếu, nhận vốn góp của chủ sở hữu', 'financing', 'nhan_von', 1, 'Nhận vốn góp'],
    ['32', 'Tiền trả lại vốn góp cho chủ sở hữu, mua lại cổ phiếu của doanh nghiệp đã phát hành', 'financing', 'tra_von', -1, 'Trả vốn góp'],
    ['33', 'Tiền thu từ đi vay', 'financing', 'vay_nh', 1, 'Vay ngân hàng'],
    ['34', 'Tiền trả nợ gốc, lãi vay', 'financing', 'tra_no_nh', -1, 'Trả nợ vay'],
    ['35', 'Tiền trả nợ gốc thuê tài chính', 'financing', 'tra_goc_thue_tc', -1, 'Trả gốc thuê TC'],
    ['36', 'Cổ tức, lợi nhuận đã trả cho chủ sở hữu', 'financing', 'chia_co_tuc', -1, 'Chia cổ tức'],
  ];
  const nhomKm = { operating: 'op', investing: 'inv', financing: 'fin' };
  const val = (d, n, k) => (d && d[n] && d[n][k] ? +d[n][k].total || 0 : 0);

  function dongTu(c, p) {
    const out = [], P = (f) => (p ? f(p) : null);
    const dong = (ma, chi_tieu, cap, a, b, them) => Object.assign({ ma, chi_tieu, cap, ky_nay: a, ky_truoc: b == null ? null : b }, them || {});
    const khoi = (ten, nhom, maNet, tenNet) => {
      out.push({ ma: '', chi_tieu: ten, cap: 'nhom' });
      KM.filter((x) => x[2] === nhom).forEach(([ma, ten2, n, k, dau], i) => {
        const id = k, items = (c[n] && c[n][k] && c[n][k].items) || [];
        // `khoa` = '<nhóm>.<khoá>' — khớp _NHAN_CF trong bao_cao_cashflow.py, để bấm vào
        // số mở popup liệt kê ĐẦY ĐỦ phiếu (có phân trang), không chỉ 5 giao dịch lớn nhất.
        out.push(dong(ma, ten2, 'muc', dau * val(c, n, k), P((x) => dau * val(x, n, k)),
          Object.assign({ khoa: n + '.' + k }, items.length ? { nhom_mo: id, gap: true, ghi_chu: KD.soDem(items.length) + ' giao dịch lớn nhất' } : {})));
        items.forEach((it) => out.push(dong('', [KD.ngay(it.ngay), it.lien_quan, it.noi_dung, it.tai_khoan].filter(Boolean).join(' · '), 'con2', dau * (+it.so_tien || 0), null, { thuoc: id })));
      });
      out.push(dong(maNet, tenNet, 'tong', c[nhom].net, P((x) => x[nhom].net), { khoa: nhom + '.net' }));
    };
    khoi('I. Lưu chuyển tiền từ hoạt động kinh doanh', 'operating', '20', 'Lưu chuyển tiền thuần từ hoạt động kinh doanh');
    khoi('II. Lưu chuyển tiền từ hoạt động đầu tư', 'investing', '30', 'Lưu chuyển tiền thuần từ hoạt động đầu tư');
    khoi('III. Lưu chuyển tiền từ hoạt động tài chính', 'financing', '40', 'Lưu chuyển tiền thuần từ hoạt động tài chính');
    out.push(dong('50', 'Lưu chuyển tiền thuần trong kỳ', 'tong', c.net_cashflow, P((x) => x.net_cashflow), { khoa: 'net_cashflow' }));
    out.push(dong('60', 'Tiền và tương đương tiền đầu kỳ', 'muc', c.so_du_dau_ky, P((x) => x.so_du_dau_ky), { khoa: 'so_du_dau_ky' }));
    out.push(dong('70', 'Tiền và tương đương tiền cuối kỳ', 'dam', c.so_du_cuoi_ky, P((x) => x.so_du_cuoi_ky), { khoa: 'so_du_cuoi_ky' }));
    return out;
  }
  function thuChi(c) {
    let thu = 0, chi = 0;
    KM.forEach(([, , n, k, dau]) => { if (dau > 0) thu += val(c, n, k); else chi += val(c, n, k); });
    return { thu, chi };
  }

  /* VND nguyên: làm tròn từng khoản mục rồi cộng lại 20/30/40/50 và 70 = 60 + 50 từ chính số đã làm tròn
     → mọi phép cộng trên bảng B03 đúng tới từng đồng. */
  function lamTron(d) {
    if (!d) return d;
    KM.forEach(([, , n, k]) => { if (d[n] && d[n][k]) d[n][k].total = Math.round(+d[n][k].total || 0); });
    ['operating', 'investing', 'financing'].forEach((n) => { d[n].net = KM.filter((x) => x[2] === n).reduce((a, [, , , k, dau]) => a + dau * val(d, n, k), 0); });
    d.net_cashflow = d.operating.net + d.investing.net + d.financing.net;
    d.so_du_dau_ky = Math.round(+d.so_du_dau_ky || 0); d.so_du_cuoi_ky = d.so_du_dau_ky + d.net_cashflow;
    (d.by_account || []).forEach((x) => { ['thu', 'chi', 'thu_noi_bo', 'chi_noi_bo', 'so_du_cuoi'].forEach((f) => { x[f] = Math.round(+x[f] || 0); }); x.net = x.thu - x.chi; });
    return d;
  }
  function chuyen(ds, k) {
    ds.forEach(lamTron);
    const [c, p] = ds;
    return { ky: { tu: c.from, den: c.to }, ky_truoc: { tu: p.from, den: p.to }, c, p, tc: thuChi(c), dong: dongTu(c, p), nguon: c.nguon || {} };
  }

  const kpiTien = (v) => ({ v: (v < 0 ? '−' : '') + KD.tienGonHtml(Math.abs(v)), title: KD.tienVnd(v) });
  const bc = KT.baoCao({
    pfx: 'lc', tenFile: 'luu-chuyen-tien-te',
    api: (k) => { const pr = k.ss || previousRange(k.tu, k.den); return ['/api/bao-cao/cashflow?' + KT.url.qs({ from: k.tu, to: k.den }), '/api/bao-cao/cashflow?' + KT.url.qs({ from: pr.tu, to: pr.den })]; },
    macDinh: { ky: 'thang_nay', tu: '', den: '' },
    inUrl: (k) => '/ketoan/in?' + KT.url.qs({ loai: 'bao_cao', mau: 'lctt', tu: k.tu, den: k.den, ky: k.ky }),
    cot: [{ key: 'ma' }, { key: 'ky_nay', num: true }, { key: 'ky_truoc', num: true }],
    lien: { '01': '131', '03': '334', '33': '341', '34': '341' },
    chuyen,
    canhBao: { man: 'lctt', thang: (k) => k.den.slice(0, 7) },
    nguonChung: { loai: 'nghiep_vu', nhan: 'Sổ quỹ', chu: 'Dòng không gắn nhãn lấy từ sổ quỹ (phiếu thu, phiếu chi), không phải sổ cái TK 111/112.' },
    chiTiet: (khoa, k, trang, cot) => {
      const kk = cot === 'ky_truoc' ? (bc.st.ss || previousRange(k.tu, k.den)) : { tu: k.tu, den: k.den };
      return '/api/bao-cao/cashflow/chi-tiet?'
        + KT.url.qs({ khoa: khoa, from: kk.tu, to: kk.den, trang: trang, so_dong: 50 });
    },
    kpi: {
      /* `canh_bao_dau_ky` chỉ có khi kỳ xem bắt đầu TRƯỚC mốc số dư đầu kỳ sớm nhất đã khai —
         khi đó "Tiền đầu kỳ" là số suy ngược, không phải số kiểm quỹ (xem _canh_bao_dau_ky
         trong bao_cao_cashflow.py). Hiện rõ ở thẻ thay vì để người xem tin một số âm vô lý. */
      dau: (d) => Object.assign(kpiTien(d.c.so_du_dau_ky), { phu: d.c.canh_bao_dau_ky
        ? H.pill('warning', 'Số suy ngược') + KD.tip(d.c.canh_bao_dau_ky)
        : 'Ngày ' + KD.ngay(d.ky.tu) + KD.tip('Tổng tiền mặt và tiền gửi ngân hàng') }),
      hdkd: (d) => Object.assign(kpiTien(d.c.operating.net), { phu: d.c.operating.net >= 0 ? H.pill('success', 'Kinh doanh tạo ra tiền') : H.pill('warning', 'Kinh doanh đang tiêu tiền') }),
      thuan: (d) => { const t = d.tc, tong = t.thu + t.chi;
        return Object.assign(kpiTien(d.c.net_cashflow), { phu: 'Thu ' + KD.tienGon(t.thu) + ' − Chi ' + KD.tienGon(t.chi) + (tong ? KD.tip('Thu/Chi = ' + (t.chi ? (t.thu / t.chi).toLocaleString('vi-VN', { maximumFractionDigits: 2 }) : '—') + ' (thu chiếm ' + KD.phanTram(t.thu / tong * 100) + ')') : '') }); },
      cuoi: (d) => Object.assign(kpiTien(d.c.so_du_cuoi_ky), { phu: 'Ngày ' + KD.ngay(d.ky.den) + ' · <a class="kd-link" href="/ketoan/bao-cao/cdkt?den=' + d.ky.den + '">Xem cân đối</a>' }),
    },
    phuDe: (d) => KD.ngay(d.ky.tu) + ' – ' + KD.ngay(d.ky.den) + ' so với ' + KD.ngay(d.ky_truoc.tu) + ' – ' + KD.ngay(d.ky_truoc.den),
    phamVi: () => 'Phân loại từng giao dịch sổ quỹ, ngân hàng theo khoản mục; chuyển tiền nội bộ giữa các tài khoản không tính.',
    sauTai: (d, k) => { veBieuDo(d.c); veTaiKhoan(d.c); gdDuLieu(d.c); taiPhu(k); },
    khiLoi: () => { $('gd-tbody').innerHTML = ''; $('tk-tbody').innerHTML = ''; },
    rong: ['Kỳ này chưa có dòng tiền nào', 'Chưa có phiếu thu, chi hay giao dịch ngân hàng được ghi sổ trong kỳ.'],
    loi: 'Không tải được báo cáo lưu chuyển tiền tệ',
  });

  /* ── Biểu đồ thu/chi theo ngày (Chart.js) ── */
  let bieuDo = null;
  const token = (ten, duPhong) => getComputedStyle(document.documentElement).getPropertyValue('--' + ten).trim() || duPhong;
  function veBieuDo(c) {
    const ds = c.daily || [], cv = $('bd-chart');
    $('bd-tt').innerHTML = ''; cv.parentElement.hidden = false;
    if (!ds.length || typeof Chart === 'undefined') { cv.parentElement.hidden = true; $('bd-tt').innerHTML = KD.khoiRong('Chưa có giao dịch trong kỳ', ''); return; }
    const chu = token('text-2', '#334166'), ke = token('border-soft', '#ebf0f7');
    if (bieuDo) bieuDo.destroy();
    bieuDo = new Chart(cv, { data: { labels: ds.map((x) => KD.ngayNgan(x.ngay)), datasets: [
      { type: 'bar', label: 'Thu', data: ds.map((x) => x.thu), backgroundColor: token('success', '#15803d'), borderRadius: 3, maxBarThickness: 14, order: 2 },
      { type: 'bar', label: 'Chi', data: ds.map((x) => x.chi), backgroundColor: token('danger', '#b91c1c'), borderRadius: 3, maxBarThickness: 14, order: 3 },
      { type: 'line', label: 'Thuần', data: ds.map((x) => x.net), borderColor: token('brand', '#2563eb'), backgroundColor: token('brand', '#2563eb'), borderWidth: 2, pointRadius: 2, tension: 0.25, order: 1 },
    ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'top', align: 'end', labels: { color: chu, boxWidth: 10, boxHeight: 10 } }, tooltip: { callbacks: { label: (x) => x.dataset.label + ': ' + KD.tienVnd(x.parsed.y) } } },
      scales: { x: { grid: { display: false }, ticks: { color: chu, maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } }, y: { grid: { color: ke }, border: { display: false }, ticks: { color: chu, callback: (v) => KD.tienGon(v) } } } } });
  }

  /* ── Dòng tiền theo tài khoản ── */
  function veTaiKhoan(c) {
    const ds = c.by_account || [], S = (k) => ds.reduce((a, x) => a + (+x[k] || 0), 0);
    const so = (v) => (v < 0 ? '<span class="kt-so--xau">' + KT.soBc(v) + '</span>' : KT.soBc(v));
    $('tk-tbody').innerHTML = ds.length ? ds.map((x) => '<tr><td>' + H.ten(x.ten_tk, x.loai === 'tien_mat' ? 'Tiền mặt' : 'Ngân hàng') + '</td><td class="num">' + KT.tienSo(x.thu) + '</td><td class="num">' + KT.tienSo(x.chi) + '</td><td class="num">' + so(x.net) + '</td><td class="num">' + so(x.so_du_cuoi) + '</td></tr>').join('')
      : '<tr><td colspan="5">' + KD.khoiRong('Chưa có tài khoản nào có giao dịch', '') + '</td></tr>';
    const nbThu = S('thu_noi_bo'), nbChi = S('chi_noi_bo');
    $('tk-tfoot').innerHTML = !ds.length ? '' : '<tr><th scope="row">Cộng</th><td class="num">' + KD.tien(S('thu')) + '</td><td class="num">' + KD.tien(S('chi')) + '</td><td class="num">' + so(S('net')) + '</td><td class="num" title="= mã 70 bảng B03">' + so(S('so_du_cuoi')) + '</td></tr>'
      + (nbThu || nbChi ? '<tr class="kd-muted"><th scope="row">Trừ chuyển nội bộ giữa các tài khoản</th><td class="num">' + KT.soBc(-nbThu) + '</td><td class="num">' + KT.soBc(-nbChi) + '</td><td class="num">' + so(nbChi - nbThu) + '</td><td></td></tr>'
        + '<tr><th scope="row">Thu, chi thật trong kỳ (= tổng các mã B03)</th><td class="num">' + KD.tien(S('thu') - nbThu) + '</td><td class="num">' + KD.tien(S('chi') - nbChi) + '</td><td class="num">' + so(S('net') - nbThu + nbChi) + '</td><td></td></tr>' : '');
  }

  /* ── Giao dịch nổi bật: top 10 theo nhóm + mới nhất (thay "Top 10" + "Nhật ký giao dịch" màn cũ) ── */
  let gd = { op: [], inv: [], fin: [], moi: [] }, gdTab = 'op';
  function gdDuLieu(c) {
    const all = [];
    KM.forEach(([, , n, k, dau, ngan]) => ((c[n] && c[n][k] && c[n][k].items) || []).forEach((it) => all.push(Object.assign({}, it, { nhom: nhomKm[n], khoan: ngan, dau }))));
    const seen = new Set(), uniq = all.filter((x) => !x.id || (!seen.has(x.nhom + x.id) && seen.add(x.nhom + x.id)));
    const top = (n) => uniq.filter((x) => x.nhom === n).sort((a, b) => b.so_tien - a.so_tien).slice(0, 10);
    gd = { op: top('op'), inv: top('inv'), fin: top('fin'), moi: uniq.slice().sort((a, b) => (b.ngay || '').localeCompare(a.ngay || '')).slice(0, 30) };
    veGd();
  }
  function veGd() {
    const q = $('gd-q').value.trim();
    const ds = gd[gdTab].filter((x) => KT.khopTim([x.noi_dung, x.lien_quan, x.tai_khoan, x.ghi_chu, x.khoan], q));
    $('gd-cuon').hidden = !ds.length; $('gd-tt').innerHTML = ds.length ? '' : KD.khoiRong(q ? 'Không có giao dịch khớp ô tìm' : 'Không có giao dịch trong nhóm này', '');
    $('gd-tbody').innerHTML = ds.map((x, i) => '<tr><td class="num kd-muted">' + (i + 1) + '</td><td>' + KD.ngay(x.ngay) + '</td><td>' + H.pill(x.dau > 0 ? 'success' : 'danger', x.khoan) + '</td>'
      + '<td>' + H.cat([x.lien_quan, x.noi_dung].filter(Boolean).join(' · ') + (x.ghi_chu ? ' — ' + x.ghi_chu : '')) + '</td><td>' + esc(x.tai_khoan || '—') + '</td>'
      + '<td class="num kd-strong ' + (x.dau > 0 ? 'kt-so--tot' : 'kt-so--xau') + '">' + (x.dau > 0 ? '+' : '−') + KD.tien(x.so_tien) + '</td></tr>').join('');
  }
  const gdTabs = KD.ganTab($('gd-tabs'), (t) => { gdTab = t; veGd(); });
  $('gd-q').addEventListener('input', KD.debounce(veGd, 200));

  /* ── 3 khối phụ: tình hình tài chính, công nợ ngầm, đối chiếu ── */
  let lPhu = 0;
  const quaHan = (n) => (n > 0 ? '<span class="kt-so--xau kd-strong">' + KD.soDem(n) + ' ngày</span>' : '<span class="kd-muted">—</span>');
  const rongHang = (n, t) => '<tr><td colspan="' + n + '">' + KD.khoiRong(t, '') + '</td></tr>';
  function veTinhHinh(d) {
    const nl = d.no_phai_tra.by_loai, pt = d.phai_thu, tk = d.summary.thanh_khoan_thuan;
    $('th-sub').textContent = 'Tại ngày ' + KD.ngay(d.as_of);
    $('th-tien').textContent = KD.tienVnd(d.tien_mat.tong);
    $('th-tien-ds').innerHTML = d.tien_mat.by_account.map((x) => '<li><span>' + esc(x.ten_tk) + '</span><b class="num' + (x.so_du < 0 ? ' kt-so--xau' : '') + '">' + KD.tien(x.so_du) + '</b></li>').join('');
    $('th-no').textContent = KD.tienVnd(d.no_phai_tra.tong);
    $('th-no-ds').innerHTML = [['Nhà cung cấp', nl.ncc.tong], ['Quảng cáo', nl.ads.tong], ['Lương', nl.luong.tong], ['Vay ngân hàng', nl.vay_nh.tong]].map((x) => '<li><span>' + x[0] + '</span><b class="num">' + KD.tien(x[1]) + '</b></li>').join('');
    $('th-tk').textContent = (tk > 0 ? '+' : '') + KD.tienVnd(tk); $('th-tk').className = 'kt-lc-th__so num ' + (tk >= 0 ? 'kt-so--tot' : 'kt-so--xau');
    $('th-tk-tip').innerHTML = KD.tip('Tiền + Phải thu − Phải trả');
    $('th-tk-ds').innerHTML = [['Tiền', d.summary.tien_co], ['+ Phải thu', d.summary.se_thu_ve], ['− Phải trả', d.summary.se_phai_tra]].map((x) => '<li><span>' + x[0] + '</span><b class="num">' + KD.tien(x[1]) + '</b></li>').join('');
    $('th-b-ncc').innerHTML = nl.ncc.items.length ? nl.ncc.items.map((r) => '<tr><td>' + esc(r.doi_tac && r.doi_tac !== 'undefined' ? r.doi_tac : '(chưa rõ)') + '</td><td class="num kd-strong">' + KD.tien(r.so_tien) + '</td><td>' + KD.ngay(r.han_thanh_toan) + '</td><td>' + quaHan(r.qua_han_ngay) + '</td><td class="num">' + KD.soDem(r.so_don) + '</td></tr>').join('') : rongHang(5, 'Chưa có công nợ nhà cung cấp');
    $('th-b-ads').innerHTML = nl.ads.items.length ? nl.ads.items.map((r) => '<tr><td>' + esc(r.kenh) + '</td><td class="num">' + KD.tien(r.phat_sinh) + '</td><td class="num">' + KD.tien(r.da_tra) + '</td><td class="num kd-strong">' + KD.tien(r.con_no) + '</td></tr>').join('') : rongHang(4, 'Không nợ quảng cáo');
    $('th-b-luong').innerHTML = nl.luong.items.length ? nl.luong.items.map((r) => '<tr><td>Tháng ' + esc(r.thang) + '</td><td class="num">' + KD.tien(r.phat_sinh) + '</td><td class="num">' + KD.tien(r.da_tra) + '</td><td class="num kd-strong">' + KD.tien(r.con_no) + '</td></tr>').join('') : rongHang(4, 'Lương đã thanh toán đủ');
    $('th-b-vay').innerHTML = nl.vay_nh.items.length ? nl.vay_nh.items.map((r) => '<tr><td class="kd-strong">' + esc(r.ma_khoan) + '</td><td>' + esc(r.nguon_vay) + '</td><td>' + esc(r.loai_vay) + '</td><td class="num kd-strong">' + KD.tien(r.du_no) + '</td><td>' + KD.ngay(r.ngay_dao_han) + '</td><td class="num">'
      + (r.ngay_con_lai < 0 ? H.pill('danger', 'Quá hạn ' + KD.soDem(-r.ngay_con_lai) + ' ngày') : r.ngay_con_lai < 30 ? H.pill('danger', KD.soDem(r.ngay_con_lai) + ' ngày') : r.ngay_con_lai < 90 ? H.pill('warning', KD.soDem(r.ngay_con_lai) + ' ngày') : KD.soDem(r.ngay_con_lai) + ' ngày') + '</td></tr>').join('') : rongHang(6, 'Không có khoản vay');
    $('th-b-pt').innerHTML = pt.items.length ? pt.items.map((r) => '<tr><td>' + esc(r.doi_tac && r.doi_tac !== 'undefined' ? r.doi_tac : '(chưa rõ)') + '</td><td class="num kd-strong">' + KD.tien(r.so_tien) + '</td><td>' + KD.ngay(r.han_thanh_toan) + '</td><td>' + quaHan(r.qua_han_ngay) + '</td><td class="num">' + KD.soDem(r.so_don) + '</td></tr>').join('') : rongHang(5, 'Không có khoản phải thu');
  }
  function veCongNo(d) {
    $('cn-cuon').hidden = false; $('cn-tt').innerHTML = '';
    $('cn-tbody').innerHTML = d.rows.map((r) => '<tr><td>' + H.ten(r.khoan, r.ghi_chu || '') + '</td><td class="num">' + KT.tienSo(r.phat_sinh) + '</td><td class="num">' + KT.tienSo(r.da_tra) + '</td><td class="num kd-strong ' + (r.con_no > 0 ? 'kt-so--xau' : r.con_no < 0 ? 'kt-so--tot' : '') + '">' + KT.soBc(r.con_no) + '</td></tr>').join('');
    $('cn-tfoot').innerHTML = '<tr><th scope="row" colspan="3">Tổng công nợ ngầm (khoản còn nợ dương)</th><td class="num">' + KD.tien(d.tong_cong_no_ngam) + '</td></tr>';
    if (d.warning) $('cn-tt').innerHTML = '<p class="kt-lc-canh">' + H.pill('warning', 'Sức ép dòng tiền') + ' ' + esc(String(d.warning).replace(/^[^\p{L}\d]+/u, '')) + '</p>';
  }
  function veDoiChieu(d) {
    const dr = d.direct, id = d.indirect, t = (v) => '<span class="num">' + KT.soBc(v) + '</span>';
    $('dx-noi-dung').hidden = false; $('dx-loi').innerHTML = '';
    $('dx-tt').innerHTML = [['Thu khách hàng', dr.thu_kh], ['− Trả nhà cung cấp', -dr.tra_ncc], ['− Trả quảng cáo', -dr.tra_ads], ['− Trả lương', -dr.tra_luong]].map((x) => '<dt>' + x[0] + '</dt><dd>' + t(x[1]) + '</dd>').join('')
      + '<dt class="is-dam">= Tiền thuần 4 khoản trên' + KD.tip('Chưa trừ chi khác (mã 07)') + '</dt><dd class="kd-strong">' + t(dr.net_operating) + '</dd>';
    $('dx-gt').innerHTML = [['Lãi/lỗ ước tính' + KD.tip('Doanh thu tiền thu − chi phí ghi sổ'), id.ln_sau_thue], ['+ Khấu hao', id.khau_hao], ['− Tăng phải thu khách', -id.bien_dong_phai_thu], ['+ Tăng phải trả NCC', id.bien_dong_phai_tra_ncc], ['+ Tăng nợ quảng cáo', id.bien_dong_phai_tra_ads], ['+ Tăng lương chưa trả', id.bien_dong_phai_tra_luong]].map((x) => '<dt>' + x[0] + '</dt><dd>' + t(x[1]) + '</dd>').join('')
      + '<dt class="is-dam">= Tiền thuần kinh doanh ước tính gián tiếp</dt><dd class="kd-strong">' + t(id.net_operating) + '</dd>';
    const mau = { ok: 'success', warning: 'warning', error: 'danger' }[d.status] || 'info';
    $('dx-tt-nhan').innerHTML = H.pill(mau, String(d.message || '').replace(/^[^\p{L}\d]+/u, ''));
    $('dx-kq').innerHTML = 'Chênh lệch hai cách tính: <b class="num">' + KD.tienVnd(d.chenh_lech) + '</b> (' + KD.phanTram(d.pct_lech) + ')';
  }
  async function taiPhu(k) {
    const l = ++lPhu, q = KT.url.qs({ from: k.tu, to: k.den });
    const khoi = (url, ve, loi) => KD.api(url).then((d) => { if (l === lPhu) ve(d); }).catch((e) => { if (l === lPhu) loi(e); });
    $('th-tt').innerHTML = ''; ['th-tien', 'th-no', 'th-tk'].forEach((x) => { $(x).innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; });
    $('cn-tbody').innerHTML = KT.hangCho(4, 4); $('cn-tfoot').innerHTML = ''; $('cn-tt').innerHTML = '';
    $('dx-tt').innerHTML = ''; $('dx-gt').innerHTML = ''; $('dx-kq').textContent = ''; $('dx-tt-nhan').textContent = '';
    khoi('/api/bao-cao/tinh-hinh-tai-chinh?' + KT.url.qs({ as_of: k.den }), veTinhHinh, (e) => { ['th-tien', 'th-no', 'th-tk'].forEach((x) => { $(x).textContent = '—'; }); KD.khoiLoi($('th-tt'), 'Không tải được tình hình tiền và công nợ', e, () => taiPhu(k)); });
    khoi('/api/bao-cao/cong-no-ngam?' + q, veCongNo, (e) => { $('cn-cuon').hidden = true; KD.khoiLoi($('cn-tt'), 'Không tải được công nợ ngầm', e, () => taiPhu(k)); });
    khoi('/api/bao-cao/cashflow-validation?' + q, veDoiChieu, (e) => { $('dx-noi-dung').hidden = true; KD.khoiLoi($('dx-loi'), 'Không tải được đối chiếu', e, () => taiPhu(k)); });
  }
  KD.ganTab($('th-tabs'));
  KD.ganTab($('pt-tabs'), (t) => { if (t === 'bd' && bieuDo) bieuDo.resize(); });

  bc.tai(); void gdTabs;
})();
