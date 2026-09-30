/* ═══════════════════════════════════════════════════════════════════════════
   kt-tong-quan.js — màn Tổng quan kế toán (đợt 1, nối API THẬT)

   README của gói giao diện (mục 4.1) đề xuất MỘT endpoint gộp sẵn
   `GET /api/ketoan/tong-quan?tu=&den=` — endpoint đó KHÔNG tồn tại trong
   backend thật. Backend thật (app/routers/bao_cao.py, journal.py, cong_no.py,
   kt_duyet.py) chia số liệu thành nhiều endpoint nhỏ, nên màn này gọi SONG
   SONG nhiều API rồi tự ráp lại đúng hình dạng mà các hàm vẽ (vốn giữ nguyên
   từ bản thiết kế) đang cần. Chỗ nào không có API thật tương đương, code có
   ghi chú "GHI CHÚ" ngay tại chỗ và KHÔNG bịa số — chỉ để trống/ẩn phần đó.

   Nguồn thật đang dùng:
     · GET /api/bao-cao/pl?thang=YYYY-MM qua KT.kqkd (kt-kqkd-tinh.js — CÙNG cách dựng số màn KQKD)
                                                         → Doanh thu thuần, Giá vốn + chi phí, LN gộp, LN trước thuế,
       cơ cấu chi phí, biểu đồ doanh thu thuần 12 tháng, % so kỳ trước. KQKD là SỐ CHUẨN DUY NHẤT cho doanh
       thu/chi phí/lợi nhuận (anh Quang duyệt 28/09/2026). Bản trước lấy "Doanh thu" = tiền thu + giá trị đơn
       MUA hàng từ NCC (công thức Dashboard cũ) và không trừ giá vốn → T9/2026 báo LÃI trong khi KQKD LỖ.
     · GET /api/bao-cao/tong-quan?tu_ngay&den_ngay     → tiền thu từ khách (+ tách cọc/thanh toán, theo loại),
       số đơn duyệt, VAT đầu ra, Data/Inbox MKT, nhân sự, công nợ phát sinh, doanh số theo NV, ADS theo kênh.
       /tong-quan cho kỳ trước → % trên thẻ Tiền thu từ khách.
     · GET /api/orders/pending-revenue                  → "Việc cần xử lý": đơn hoàn thành chưa ghi DT
     · /tong-quan.phai_thu_mo (đã loại thu hộ ĐVVC trùng) → phải thu, tuổi nợ, top nợ, quá hạn
     · GET /api/cong-no/ncc-module                       → tổng phải trả ròng, đến hạn NCC (= màn Công nợ NCC)
     · GET /api/journal?from&to&limit                   → bút toán gần đây
     · GET /api/so-quy/summary?tu_ngay&den_ngay          → tồn quỹ đến đúng ngày cuối kỳ (= Sổ quỹ + Ngân hàng)
     · /api/duyet-chi/queue/me + /api/de-nghi-tt + /api/ncc-de-xuat + /api/profile
                                                         → "Lệnh cần phê duyệt" = "Chờ tôi duyệt" màn Duyệt chi
     · GET /api/kt-duyet/list                            → xác nhận cọc chờ KT (mục trong "Việc cần xử lý")

   Vì số liệu đến từ NHIỀU nguồn độc lập (khác bản mock — vốn giả định một
   nguồn duy nhất), lỗi một nguồn không còn làm sập cả trang: mỗi khối tự vẽ
   lỗi cục bộ (Promise.allSettled), không dùng khối lỗi toàn trang nữa.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = $('kd-kt-tong-quan');
  if (!trang) return;

  const st = Object.assign({ ky: 'thang_nay', tu: '', den: '' }, KT.url.doc());
  let luot = 0; let bieuDo = null; let ssHt = null;   // ssHt: kỳ so sánh của lần tải gần nhất (nhãn "so tháng trước"…)

  const khoang = () => KT.khoangSt(st);
  /* Kỳ so sánh cho % trên thẻ KPI — KT.kySoSanh (kt-chung.js, dùng chung KQKD/LCTT): tháng → tháng trước
     (01–28/09 → 01–28/08), quý → quý trước, năm → CÙNG KỲ năm trước (01/01–28/09/2026 → 01/01–28/09/2025;
     bản trước lùi 9 tháng ra 01/04–28/12/2025), tuỳ chỉnh → khoảng liền trước cùng độ dài. */
  function themNgay(iso, n) { const d = new Date(iso); d.setDate(d.getDate() + n); return KD.iso(d); }

  /* ── Tồn quỹ đến ngày cuối kỳ (BUG FIX 2026-09-25) ──
     Bản trước lấy Tồn quỹ = SUM(no)-SUM(co) của TK 111/112 trong /api/journal/balance-summary
     (sổ nhật ký NỢ-CÓ "Phase 2" — app/routers/journal.py). Sổ đó CHỈ ghi nhận vay/trả vay,
     khấu hao và hoàn thành đơn hàng (source_type: tao_khoan_vay/tra_no_vay/khau_hao/
     vc_hoan_thanh) — KHÔNG ghi nhận thu doanh thu, chi phí phát sinh hay thu/trả công nợ, nên
     hoàn toàn KHÔNG PHẢI sổ quỹ đầy đủ. Kết quả: ra số âm vô lý (vd -230,3 triệu) vì chỉ thấy
     phần "trả nợ vay" mà không thấy các khoản thu bù vào ngân hàng.
     Sổ quỹ THẬT (đầy đủ, tự đồng bộ từ Doanh Thu/Chi Phí/Công Nợ — services/so_quy_auto.py) là
     bảng SoQuy, đã có sẵn endpoint tổng hợp /api/so-quy/summary?thang=YYYY-MM (tồn đầu/cuối mỗi
     TK, tôn trọng snapshot SoDuDauKy) — CÙNG nguồn cột "Tồn quỹ" của Sổ quỹ (kt-so-quy.js) nên
     số ở Tổng quan sẽ khớp màn Sổ quỹ. Hạn chế còn lại: /summary chỉ nhận theo THÁNG nên khi
     "đến ngày" (ky.den) không phải ngày cuối tháng, số lấy là tồn đến HẾT THÁNG chứa ky.den chứ
     không phải chính xác đến ky.den (chấp nhận được — ky.den mặc định luôn là hôm nay nên sổ
     quỹ chưa có giao dịch sau đó; chỉ lệch khi lọc "tuỳ chỉnh" một ngày cuối kỳ ở giữa tháng). */
  /* Cập nhật đợt 3: /summary nay nhận tu_ngay&den_ngay → lấy tồn ĐÚNG đến ky.den (cùng lời gọi màn Sổ quỹ
     và Ngân hàng dùng), tách Tiền mặt / Ngân hàng để đối chiếu thẳng với "Tồn cuối" của hai màn đó. */
  async function tonQuyDenNgay(ky) {
    const d = await KD.api('/api/so-quy/summary?' + KT.url.qs({ tu_ngay: ky.tu, den_ngay: ky.den }));
    const tach = { tien_mat: 0, ngan_hang: 0 };
    ((d && d.items) || []).forEach((it) => { tach[it.loai === 'tien_mat' ? 'tien_mat' : 'ngan_hang'] += KD.so(it.so_du_cuoi) || 0; });
    return { tong: KD.so(d && d.tong && d.tong.so_du_cuoi), ...tach };
  }

  /* Hạn thu mặc định khi khoản phải thu KHÔNG có han_thanh_toan (DB thật: 0/65 khoản có hạn) =
     ngày phát sinh + 30 ngày — đúng ngưỡng "Công nợ quá 30 ngày" của Dashboard cũ (chốt 08/08/2026).
     Bản trước coi "không có hạn" = "chưa đến hạn" nên cả 997tr nợ đều hiện "Chưa đến hạn", "Nợ khách
     quá hạn = 0" trong khi màn cũ báo 40 khoản quá 30 ngày. */
  const HAN_NO_MAC_DINH = 30;
  function hanThu(rec) { return rec.han_thanh_toan || (rec.ngay ? themNgay(rec.ngay, HAN_NO_MAC_DINH) : null); }

  /* Nhóm tuổi nợ theo hạn thu so với một ngày mốc. */
  function nhomTuoi(hanThanhToan, conLai, moc) {
    if (!(conLai > 0)) return 'da_thu_du';
    if (!hanThanhToan || hanThanhToan >= moc) return 'chua_den_han';
    const soNgay = Math.round((new Date(moc) - new Date(hanThanhToan)) / 86400000);
    if (soNgay <= 30) return 'qh_1_30';
    if (soNgay <= 60) return 'qh_31_60';
    return 'qh_tren_60';
  }

  /* Nhãn source_type của JournalEntry (models/journal_entry.py) — khác từ vựng LOAI_CT của
     kt-chung.js (vốn viết cho backend mock). Không đăng ký vào KT.LOAI_CT vì đó là file dùng chung
     nhiều màn; khai bản đồ riêng ở đây, thiếu key thì vẫn hiện chữ (source_type) thay vì cảnh báo đỏ. */
  const NHAN_NGUON = {
    gop_von: 'Góp vốn', rut_von: 'Rút vốn', chia_co_tuc: 'Chia cổ tức', trich_quy: 'Trích quỹ',
    chi_phi_phat_sinh: 'Chi phí phát sinh', chi_phi_co_dinh: 'Chi phí cố định',
    nhap_kho_manual: 'Nhập kho', xuat_kho_manual: 'Xuất kho', tao_khoan_vay: 'Tạo khoản vay',
    tra_no_vay: 'Trả nợ vay', tk_nh_thu: 'Ngân hàng báo có', tk_nh_chi: 'Ngân hàng báo nợ', other: 'Khác',
    khau_hao: 'Khấu hao TSCĐ', vc_hoan_thanh: 'Hoàn thành đơn hàng', tam_ung: 'Tạm ứng', tam_ung_quyet_toan: 'Quyết toán tạm ứng',
  };
  function nhanNguon(st_) {
    if (!st_) return 'Khác';
    if (NHAN_NGUON[st_]) return NHAN_NGUON[st_];
    if (st_.indexOf('reversal_of_') === 0) return 'Đảo bút toán';
    return st_;
  }

  /* ── Khung chờ ── */
  function veCho() {
    trang.querySelectorAll('[data-v]').forEach((el) => { el.innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; el.classList.remove('kt-so--xau'); el.removeAttribute('title'); });
    trang.querySelectorAll('[data-d]').forEach((el) => { el.hidden = true; });
    trang.querySelectorAll('[data-phu]').forEach((el) => { el.textContent = ''; el.hidden = true; });
    trang.querySelectorAll('[data-tip-o]').forEach((el) => { el.innerHTML = ''; });
    $('tq-chart-hop').hidden = true; $('tq-chart-tt').innerHTML = KD.KHUNG_TAI;
    $('tq-tuoi').innerHTML = KD.KHUNG_TAI;
    $('tq-bt').innerHTML = ''; $('tq-bt').hidden = true; $('tq-bt-tt').innerHTML = KD.KHUNG_TAI;
    $('tq-top').innerHTML = KD.KHUNG_TAI; $('tq-nv').innerHTML = KD.KHUNG_TAI; $('tq-cp').innerHTML = KD.KHUNG_TAI;
    $('tq-dt').innerHTML = KD.KHUNG_TAI; $('tq-ads').innerHTML = KD.KHUNG_TAI; $('tq-loi').hidden = true;
    $('tq-duyet').innerHTML = ''; $('tq-duyet-tt').innerHTML = KD.KHUNG_TAI; $('tq-duyet-tong').hidden = true; $('tq-duyet-dem').hidden = true;
  }

  /* ── Thẻ KPI: số + tối đa 1 dòng phụ ngắn (so kỳ trước, hoặc k.phu); phần tách chi tiết → ⓘ (k.tip).
     Số âm viết "−" + trị tuyệt đối như thẻ màn KQKD; title = số đủ đồng để đối chiếu. k.xau: tô đỏ khi âm.
     k.ss = { nhan, chu }: kỳ so sánh riêng của thẻ (thẻ KQKD so TRỌN tháng) — mặc định kỳ so sánh của trang. ── */
  function veKpi(kpi) {
    trang.querySelectorAll('#tq-kpi [data-kpi]').forEach((the) => {
      const k = kpi[the.dataset.kpi];
      const v = the.querySelector('[data-v]');
      if (!k) { v.innerHTML = '<span class="kd-muted">—</span>'; v.removeAttribute('title'); return; }
      v.innerHTML = soKpi(k.gia_tri); v.title = KD.tienVnd(k.gia_tri);
      v.classList.toggle('kt-so--xau', !!k.xau && k.gia_tri < 0);
      the.querySelector('[data-tip-o]').innerHTML = KD.tip(k.tip, the.dataset.tipLop);
      const phuLn = the.querySelector('[data-phu]');
      phuLn.textContent = k.phu || ''; phuLn.hidden = !k.phu;
      const d = the.querySelector('[data-d]');
      if (k.truoc != null) {
        const pct = k.truoc ? ((k.gia_tri - k.truoc) / Math.abs(k.truoc)) * 100 : 0;
        const huong = pct > 0 ? 'up' : pct < 0 ? 'down' : '';
        const ss = k.ss || (ssHt ? { nhan: ssHt.nhan, chu: KD.ngay(ssHt.tu) + ' – ' + KD.ngay(ssHt.den) } : null);
        const nhanSs = ss ? ss.nhan : 'kỳ trước', khoangSs = ss ? ' (' + ss.chu + ')' : '';
        // Kỳ so sánh = 0 (vd cùng kỳ 2025, trước khi có dữ liệu) → không có % để so, KHÔNG in "0%" như không đổi.
        const khongSo = !k.truoc && !!k.gia_tri;
        const cau = khongSo ? 'Kỳ so sánh — ' + nhanSs + khoangSs + ' — chưa có số liệu'
          : (pct > 0 ? 'Tăng ' : pct < 0 ? 'Giảm ' : 'Không đổi ') + KD.phanTram(Math.abs(pct)) + ' so với ' + nhanSs + khoangSs;
        d.dataset.huong = khongSo ? '' : huong;
        d.setAttribute('aria-label', cau);
        d.innerHTML = khongSo ? '<span>—</span><span class="kd-kpi__since">' + esc(nhanSs) + ' chưa có số</span>'
          : (huong ? '<i class="bi bi-arrow-' + huong + '" aria-hidden="true"></i>' : '') + '<span>' + KD.phanTram(Math.abs(pct)) + '</span>'
          + '<span class="kd-kpi__since">so ' + esc(nhanSs) + '</span>';
        d.title = cau;
        d.hidden = false;
      } else { d.hidden = true; }
    });
  }
  /* Thẻ "Chỉ số khác": mỗi dòng { v: html số, tip: ghi chú trong ⓘ }. Thiếu dữ liệu → "—". */
  function veChiSo(bs) {
    trang.querySelectorAll('#tq-chiso [data-kpi]').forEach((o) => {
      const x = bs[o.dataset.kpi];
      o.querySelector('[data-v]').innerHTML = x ? x.v : '<span class="kd-muted">—</span>';
      o.querySelector('[data-tip-o]').innerHTML = x ? KD.tip(x.tip) : '';
    });
  }
  const dem = (n, dv) => '<span>' + KD.soDem(n) + '</span>' + (dv ? '<span class="kd-kpi__don-vi">' + dv + '</span>' : '');
  /* Tiền trong thẻ: số âm "−" + trị tuyệt đối — cùng cách viết thẻ màn KQKD (kt-kqkd.js tienKpi). */
  const soKpi = (v) => (v < 0 ? '−' : '') + KD.tienGonHtml(Math.abs(v));
  const tienGonDau = (v) => (v < 0 ? '−' : '') + KD.tienGon(Math.abs(v));
  const phanTramDau = (v) => (v < 0 ? '−' : '') + KD.phanTram(Math.abs(v));

  /* ── Số KQKD (B02-DN) — SỐ CHUẨN DUY NHẤT cho doanh thu, chi phí, lợi nhuận (anh Quang duyệt 28/09/2026) ──
     Dựng số bằng CHÍNH KT.kqkd của màn KQKD (kt-kqkd-tinh.js): gọi /api/bao-cao/pl từng tháng giao với kỳ,
     cộng dồn + làm tròn lá (gop), kỳ trước = KT.kqkd.ke(tu, den, kySoSanh.thang) — như kt-kqkd.js
     (ke(k.tu, k.den, k.ss.thang)) ⇒ số trên thẻ = số màn KQKD cùng kỳ tới từng đồng. /pl chỉ tính TRỌN THÁNG
     (vd "Tháng này" 01–28/09 ⇒ KQKD tháng 09) — dòng kỳ ở đầu trang ghi rõ các tháng KQKD đang dùng. */
  const PL_TTL = 30000;   // = _PL_TTL cache /pl phía máy chủ (bao_cao_pnl.py): đổi kỳ trong 30s không gọi lại tháng đã có
  const plDaTai = new Map();
  function layPl(url) {
    const c = plDaTai.get(url);
    if (c && Date.now() - c.luc < PL_TTL) return c.hua;
    const hua = KD.api(url);
    plDaTai.set(url, { luc: Date.now(), hua });
    hua.catch(() => plDaTai.delete(url));
    return hua;
  }
  const urlPl = (thang) => '/api/bao-cao/pl?' + KT.url.qs({ thang });   // cùng dạng url KT.kqkd.ke → dùng chung plDaTai
  const thangChu = (m) => m.slice(5, 7) + '/' + m.slice(0, 4);
  const nhanThangKq = (ds) => 'tháng ' + (ds.length === 1 ? thangChu(ds[0]) : thangChu(ds[0]) + ' – ' + thangChu(ds[ds.length - 1]));
  /* Giá vốn + chi phí của KQKD: dòng 11 + 22 + 25 + 26 + 32 ⇒ LNTT (50) = DT thuần + DT tài chính + thu nhập khác − số này. */
  const tongCpKq = (x) => x.cogs + x.cp_tai_chinh.tong + x.cp_ban_hang.tong + x.cp_quan_ly.tong + x.cp_khac;
  const SO_THANG_BIEU_DO = 12;
  function thangBieuDo(den) {
    const [y, m] = den.split('-').map(Number);
    return KT.kqkd.cacThang(KD.iso(new Date(y, m - SO_THANG_BIEU_DO, 1)), den);
  }

  /* ── Biểu đồ "Doanh thu thuần theo tháng" — mỗi cột = Doanh thu thuần KQKD của tháng đó (KT.kqkd.gop 1 tháng
     = đúng số màn KQKD khi xem tháng ấy). Bản trước vẽ cột chồng "Đã ghi sổ KT" + "Đơn mua hàng" (giá mua NCC).
     Cột thuộc kỳ đang xem tô đậm, ngoài kỳ tô nhạt. ── */
  function token(ten, duPhong) { return getComputedStyle(document.documentElement).getPropertyValue('--' + ten).trim() || duPhong; }
  function veThang(ds, ky, kq) {
    const hop = $('tq-chart-hop'), tt = $('tq-chart-tt'), meta = $('tq-thang-meta');
    const trongKy = (t) => kq.thang.includes(t.thang);
    const duKy = kq.thang.every((m) => ds.some((t) => t.thang === m));   // kỳ > 12 tháng: biểu đồ chỉ có phần cuối
    meta.textContent = '12 tháng đến ' + thangChu(ky.den.slice(0, 7));
    $('tq-thang-tip').innerHTML = KD.tip('Doanh thu thuần theo báo cáo KQKD (dòng 10: đơn hoàn thành, chưa VAT, trừ hoàn tiền) — cột mỗi tháng = KQKD tháng đó. '
      + (duKy ? 'Cột đậm là ' + nhanThangKq(kq.thang) + ' của kỳ đang xem, cộng ' + KD.tienGon(kq.c.dt_thuan) + ' = thẻ Doanh thu thuần.'
        : 'Kỳ đang xem dài hơn 12 tháng — cột đậm chỉ là phần kỳ nằm trong biểu đồ; thẻ Doanh thu thuần cộng đủ ' + nhanThangKq(kq.thang) + '.'));
    if (!ds.some((t) => t.dt_thuan)) { hop.hidden = true; tt.innerHTML = KD.khoiRong('Chưa có doanh thu trong 12 tháng gần nhất', 'Biểu đồ sẽ hiện khi có đơn hàng hoàn thành.'); return; }
    if (typeof Chart === 'undefined') { hop.hidden = true; tt.innerHTML = KD.khoiRong('Không vẽ được biểu đồ', 'Trang chưa nạp Chart.js.'); return; }
    hop.hidden = false; tt.innerHTML = '';   // bỏ khung chờ (vệt xám dưới biểu đồ)
    const nhan = ds.map((t) => thangChu(t.thang));
    const chu = token('text-2', '#334166'), ke = token('border-soft', '#ebf0f7');
    const mau = token('brand-graph', '#3b82f6');
    const nhat = /^#[0-9a-f]{6}$/i.test(mau) ? mau + '59' : mau;   // ngoài kỳ: alpha ~35% (token là hex 6 số)
    const cfg = {
      data: {
        labels: nhan,
        datasets: [
          { type: 'bar', label: 'Doanh thu thuần', data: ds.map((t) => t.dt_thuan), backgroundColor: ds.map((t) => (trongKy(t) ? mau : nhat)),
            maxBarThickness: 22, borderRadius: { topLeft: 4, topRight: 4 } },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (c) => 'Doanh thu thuần: ' + KD.tienVnd(c.parsed.y) } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { color: chu } },
          y: { grid: { color: ke }, border: { display: false }, ticks: { color: chu, callback: (v) => KD.tienGon(v) } },
        },
      },
    };
    const cv = $('tq-chart'); cv.parentElement.style.height = '260px';
    if (bieuDo) bieuDo.destroy();
    bieuDo = new Chart(cv, cfg);
  }

  /* ── Tuổi nợ (từ /api/cong-no?loai=phai_thu, mọi thời điểm — không riêng trong kỳ) ── */
  const NHOM_TUOI = { chua_den_han: 'success', qh_1_30: 'warning', qh_31_60: 'danger', qh_tren_60: 'danger' };
  function veTuoi(ds) {
    const el = $('tq-tuoi'); const tong = ds.reduce((a, x) => a + x.gia_tri, 0);
    if (!tong) { el.innerHTML = KD.khoiRong('Không có khách nào còn nợ', 'Mọi khoản phải thu đã ghi sổ đều đã được thu đủ.'); return; }
    const max = Math.max(...ds.map((x) => x.gia_tri));
    el.innerHTML = ds.map((x) => '<div class="kt-tuoi__o">' + KT.pillTuoiNo(x.nhom)
      + '<span class="kt-tuoi__thanh kt-tuoi__thanh--' + (NHOM_TUOI[x.nhom] || 'success') + '"><span style="width:' + (max ? Math.round((x.gia_tri / max) * 100) : 0) + '%"></span></span>'
      + '<b class="kt-tuoi__so num" title="' + KD.tienVnd(x.gia_tri) + '">' + KD.tienGon(x.gia_tri) + '</b></div>').join('')
      + '<p class="kt-tuoi__tong">Tổng còn phải thu<b class="num">' + KD.tienVnd(tong) + '</b></p>';
  }

  /* ── Bút toán gần đây (JournalEntrySummary — không có sẵn dòng Nợ/Có ở đây, xem chi tiết ở Sổ kế toán) ── */
  function veBt(ds, ky) {
    const ul = $('tq-bt'), tt = $('tq-bt-tt');
    if (!ds.length) { ul.innerHTML = ''; ul.hidden = true; tt.innerHTML = KD.khoiRong('Chưa có bút toán nào trong kỳ', 'Bút toán được ghi khi có nghiệp vụ phát sinh (chi phí, lương, ngân hàng…) hoặc khi bấm "Tạo bút toán".'); return; }
    ul.hidden = false; tt.innerHTML = '';
    ul.innerHTML = ds.map((b) => '<li><span class="kt-cat kt-cat--dong" title="' + esc(b.mo_ta || '') + '">' + esc(b.mo_ta || nhanNguon(b.source_type)) + '</span>'
      + '<b class="num">' + KD.tienVnd(b.tong_tien) + '</b>'
      + '<span class="kd-lines__sub"><a class="kt-ma" href="/ketoan/so-cai?tim=' + encodeURIComponent(b.ma_but_toan) + '&ky=tuy_chinh&tu=' + ky.tu + '&den=' + ky.den + '">' + esc(b.ma_but_toan) + '</a> · '
      + esc(nhanNguon(b.source_type)) + ' · ' + KD.ngay(b.ngay) + '</span></li>').join('');
  }

  /* ── Khách nợ nhiều nhất (gộp theo doi_tac từ /api/cong-no?loai=phai_thu) ── */
  const SO_DONG_XEP_HANG = 8;
  function veTop(tatCa) {
    const el = $('tq-top');
    if (!tatCa.length) { el.innerHTML = KD.khoiRong('Không có khách nào còn nợ', 'Mọi khoản phải thu trong sổ đã được thu đủ.'); return; }
    const ds = tatCa.slice(0, SO_DONG_XEP_HANG);
    const max = ds[0].con_lai, tongTop = ds.reduce((a, k) => a + k.con_lai, 0), tong = tatCa.reduce((a, k) => a + k.con_lai, 0);
    el.innerHTML = ds.map((k, i) => '<div class="kd-rank__o"><span class="kd-rank__hang num">' + (i + 1) + '</span>'
      + '<span class="kd-avatar kd-avatar--sm" aria-hidden="true">' + esc(initials(k.ten)) + '</span>'
      + '<a class="kd-rank__ten kt-ten-link" href="/ketoan/cong-no-kh?tim=' + encodeURIComponent(k.ten) + '" title="' + esc(k.ten) + '">' + esc(k.ten) + '</a>'
      + '<span class="kd-rank__thanh"><span style="width:' + Math.round((k.con_lai / max) * 100) + '%"></span></span>'
      + '<b class="kd-rank__so num" title="' + KD.tienVnd(k.con_lai) + '">' + KD.tienGon(k.con_lai) + '</b></div>').join('')
      + (tatCa.length > ds.length
        ? '<p class="kt-tuoi__tong kt-tuoi__tong--phu">' + KD.soDem(ds.length) + ' khách đầu<b class="num">' + KD.tienVnd(tongTop) + '</b></p>'
          + '<p class="kt-tuoi__tong kt-tuoi__tong--phu kt-tuoi__tong--lien">' + KD.soDem(tatCa.length - ds.length) + ' khách khác<b class="num">' + KD.tienVnd(tong - tongTop) + '</b></p>'
          + '<p class="kt-tuoi__tong kt-tuoi__tong--lien"><span>Tổng ' + KD.soDem(tatCa.length) + ' khách' + KD.tip('Bằng thẻ Phải thu.') + '</span><b class="num">' + KD.tienVnd(tong) + '</b></p>'
        : '<p class="kt-tuoi__tong">Cộng<b class="num">' + KD.tienVnd(tongTop) + '</b></p>');
  }

  /* Hạn trả NCC là TEXT tự do (YYYY-MM-DD hoặc DD/MM/YYYY) — cùng cách đọc của kt-cong-no.js parseNgayLinhHoat. */
  function parseNgay(s) {
    if (!s) return null;
    s = String(s).trim();
    let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
    m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
    return null;
  }

  /* ── Danh sách thanh ngang theo loại (chi phí / doanh thu / ADS): tên | thanh | số | %.
     ds: [{ ten, so_tien, phu? }]. API trả tiền Decimal dạng CHUỖI → luôn qua KD.so trước khi cộng
     (bản trước cộng chuỗi nên "Cộng chi phí phát sinh" và cột % ra "—"). ── */
  function veLoai(el, ds, rong, chanTong, ghiChu) {
    ds = ds.map((x) => Object.assign({}, x, { so_tien: KD.so(x.so_tien) || 0 })).filter((x) => x.so_tien);
    if (!ds.length) { el.innerHTML = KD.khoiRong(rong[0], rong[1]); return; }
    const tong = ds.reduce((a, x) => a + x.so_tien, 0), max = Math.max(...ds.map((x) => x.so_tien));
    el.innerHTML = ds.map((x) => '<div class="kt-loai__o"><span class="kt-loai__ten"><span title="' + esc(x.ten) + '">' + esc(x.ten) + '</span>'
      + (x.phu ? '<small>' + esc(x.phu) + '</small>' : '') + '</span>'
      + '<span class="kt-tuoi__thanh"><span style="width:' + Math.max(1, Math.round((x.so_tien / max) * 100)) + '%"></span></span>'
      + '<b class="kt-tuoi__so num" title="' + KD.tienVnd(x.so_tien) + '">' + KD.tienGon(x.so_tien) + '</b>'
      + '<span class="kt-loai__pct num">' + KD.phanTram(tong ? (x.so_tien / tong) * 100 : 0) + '</span></div>').join('')
      + '<p class="kt-tuoi__tong"><span>' + esc(chanTong) + KD.tip(ghiChu) + '</span><b class="num">' + KD.tienVnd(tong) + '</b></p>';
  }

  /* ── Thẻ "Tiền thu từ khách": tiền THỰC THU trong kỳ (phiếu thu cọc + thanh toán, gồm VAT) = thẻ "Doanh thu đã ghi
     nhận" màn Thu chi — để CEO theo dõi dòng tiền; KHÁC doanh thu kế toán (KQKD ghi nhận khi đơn hoàn thành). ── */
  function kpiTienThu(tq, th) {
    if (!tq) return { tien_thu: null };
    const ht = tq.tien_thu_theo_hinh_thuc || {};
    return { tien_thu: {
      gia_tri: KD.so(tq.tien_thu_khach), truoc: th ? KD.so(th.tien_thu_khach) : null,
      phu: 'Gồm cọc ' + KD.tienGon(ht.dat_coc || 0),
      tip: 'Tiền thực thu từ khách trong kỳ: đặt cọc ' + KD.tienGon(ht.dat_coc || 0) + ' + thanh toán ' + KD.tienGon(ht.thanh_toan || 0)
        + (KD.so(ht.khac) ? ' + hình thức khác ' + KD.tienVnd(ht.khac) : '') + ', gồm VAT'
        + ' — bằng "Doanh thu đã ghi nhận" màn Thu chi. Đây là dòng tiền, KHÔNG phải doanh thu kế toán: cọc của đơn chưa giao cũng tính ở đây, còn Doanh thu thuần (KQKD) chỉ tính đơn đã hoàn thành, chưa VAT.',
    } };
  }

  /* ── 4 thẻ KQKD (nhãn theo dòng B02) — kq = KT.kqkd.tach: { c: kỳ này, p: kỳ so sánh, thang, thang_truoc } ── */
  function kpiKqkd(kq, kyTr) {
    if (!kq) return { dt_thuan: null, chi_phi: null, ln_gop: null, loi_nhuan_truoc_thue: null };
    const c = kq.c, p = kq.p, ss = { nhan: kyTr.nhan, chu: nhanThangKq(kq.thang_truoc) };
    const bien = (a) => (c.dt_thuan ? phanTramDau((a / c.dt_thuan) * 100) : '—');
    const nguon = ' Số báo cáo Kết quả kinh doanh ' + nhanThangKq(kq.thang) + '.';
    const lnKhac = c.dt_tai_chinh || c.thu_nhap_khac
      ? ' + doanh thu tài chính ' + KD.tienGon(c.dt_tai_chinh) + ' + thu nhập khác ' + KD.tienGon(c.thu_nhap_khac) : '';
    return {
      dt_thuan: { gia_tri: c.dt_thuan, truoc: p.dt_thuan, ss,
        phu: KD.soDem((c.metadata && c.metadata.so_don_hoan_thanh_trong_ky) || 0) + ' đơn hoàn thành',
        tip: 'Dòng 10 — giá trị đơn hoàn thành trong kỳ, chưa VAT, trừ hoàn tiền khách.' + nguon },
      chi_phi: { gia_tri: tongCpKq(c), truoc: tongCpKq(p), ss,
        phu: 'Giá vốn ' + tienGonDau(c.cogs),
        tip: 'Giá vốn (dòng 11) ' + tienGonDau(c.cogs) + ' + chi phí tài chính (22) ' + tienGonDau(c.cp_tai_chinh.tong) + ' + bán hàng (25) ' + tienGonDau(c.cp_ban_hang.tong)
          + ' + quản lý DN (26) ' + tienGonDau(c.cp_quan_ly.tong) + ' + chi phí khác (32) ' + tienGonDau(c.cp_khac) + '.' + nguon },
      ln_gop: { gia_tri: c.ln_gop, truoc: p.ln_gop, ss, xau: true,
        phu: 'Biên gộp ' + bien(c.ln_gop),
        tip: 'Dòng 20 = Doanh thu thuần − giá vốn hàng bán.' + nguon },
      loi_nhuan_truoc_thue: { gia_tri: c.ln_truoc_thue, truoc: p.ln_truoc_thue, ss, xau: true,
        phu: 'Biên lợi nhuận ' + bien(c.ln_truoc_thue),
        tip: 'Dòng 50 = Doanh thu thuần' + lnKhac + ' − giá vốn + chi phí; chưa trừ thuế TNDN.' + nguon },
    };
  }

  /* ── Cơ cấu chi phí: các dòng chi phí của KQKD (B02) — cộng = thẻ Giá vốn + chi phí. Bản trước vẽ chi phí
     phát sinh theo loại (sổ chi, không có giá vốn) ghi "Cộng biến phí" — khác định nghĩa thẻ Chi phí. ── */
  function veCoCauCp(kq) {
    const c = kq.c, bh = c.cp_ban_hang, ql = c.cp_quan_ly, tc = c.cp_tai_chinh;
    const dinhPhi = (x) => 'Định phí ' + tienGonDau(x.dinh_phi.tong);   // phần còn lại là biến phí
    veLoai($('tq-cp'), [
      { ten: 'Giá vốn hàng bán', so_tien: c.cogs },
      { ten: 'Chi phí bán hàng', so_tien: bh.tong, phu: dinhPhi(bh) },
      { ten: 'Chi phí quản lý DN', so_tien: ql.tong, phu: dinhPhi(ql) },
      { ten: 'Chi phí tài chính', so_tien: tc.tong, phu: tc.lai_vay ? 'Lãi vay ' + tienGonDau(tc.lai_vay) : '' },
      { ten: 'Chi phí khác', so_tien: c.cp_khac },
    ], ['Chưa có chi phí trong kỳ', 'Chi phí hiện khi có đơn hoàn thành, chi phí ghi sổ hoặc định phí phân bổ.'],
    'Cộng giá vốn + chi phí', 'Bằng thẻ Giá vốn + chi phí — báo cáo Kết quả kinh doanh ' + nhanThangKq(kq.thang) + '.');
  }

  /* ── Doanh số theo nhân viên — dt_by_nv của Dashboard cũ: SUM(quotes.tong_chua_thue) báo giá
     approved theo ngày duyệt. Bản trước gọi /api/bao-cao/per-nv — SQL đó đọc cột quotes.nv_kd
     KHÔNG tồn tại nên luôn trả {} ("Chưa có báo giá nào được duyệt" dù tháng 9 có 22 đơn). ── */
  function veNv(tatCa) {
    const el = $('tq-nv');
    if (!tatCa.length) { el.innerHTML = KD.khoiRong('Chưa có báo giá nào được duyệt trong kỳ', 'Doanh số hiện khi có báo giá được duyệt.'); return; }
    const ds = tatCa.slice(0, SO_DONG_XEP_HANG), max = ds[0].doanh_so;
    el.innerHTML = ds.map((n, i) => '<div class="kd-rank__o"><span class="kd-rank__hang num">' + (i + 1) + '</span>'
      + '<span class="kd-avatar kd-avatar--sm" aria-hidden="true">' + esc(initials(n.ten)) + '</span>'
      + '<span class="kd-rank__ten" title="' + esc(n.ten) + '">' + esc(n.ten) + '</span>'
      + '<span class="kd-rank__thanh"><span style="width:' + Math.round((n.doanh_so / max) * 100) + '%"></span></span>'
      + '<b class="kd-rank__so num" title="' + KD.tienVnd(n.doanh_so) + '">' + KD.tienGon(n.doanh_so) + '</b></div>').join('')
      + '<p class="kt-tuoi__tong">Tổng báo giá duyệt' + (tatCa.length > ds.length ? ' (' + KD.soDem(tatCa.length) + ' NV)' : '')
      + '<b class="num">' + KD.tienVnd(tatCa.reduce((a, n) => a + n.doanh_so, 0)) + '</b></p>';
  }

  /* ── Việc cần xử lý (khối đầu Dashboard cũ): đơn Hoàn thành chưa ghi doanh thu + công nợ phải thu
     quá 30 ngày. Rỗng → ẩn nguyên khối. (Mục "Nhân sự biến động" của bản cũ KHÔNG đưa sang: nó so
     tong_nv của 2 tháng, mà tong_nv đếm nhân viên "Đang làm" HIỆN TẠI, không theo tháng → 2 số luôn
     bằng nhau, mục đó không bao giờ hiện được.) ── */
  /* Đợt 3: thêm mục "Xác nhận cọc chờ Kế toán" (/api/kt-duyet/list, duyet_status kt_pending) — trước nằm ở khối
     "Lệnh cần phê duyệt" dù link khối đó mở màn Duyệt chi (đề xuất chi), hai khái niệm khác nhau nên số không khớp. */
  /* Một dòng danh sách việc/duyệt: tiêu đề | số tiền, dưới là 1 nhãn trạng thái. Chi tiết phụ → title (rê chuột). */
  function dongViec(tieuDe, tien, pill, chiTiet, href) {
    const t = chiTiet ? ' title="' + esc(chiTiet) + '"' : '';
    const ten = href ? '<a class="kt-dong__ten kt-ten-link" href="' + href + '"' + t + '>' + esc(tieuDe) + '</a>'
      : '<span class="kt-dong__ten"' + t + '>' + esc(tieuDe) + '</span>';
    return '<li class="kt-dong">' + ten + '<b class="num kt-dong__tien">' + KD.tienVnd(tien) + '</b><span class="kt-dong__tt">' + pill + '</span></li>';
  }
  function veViec(donChuaGhi, noQuaHan, cocCho) {
    const ds = [];
    (donChuaGhi || []).slice(0, 5).forEach((it) => ds.push(dongViec((it.ma_don || '') + ' · ' + (it.customer_name || it.ten_don || ''), it.tong_don,
      '<span class="pill pill--warning">Chưa ghi doanh thu</span>', 'Hoàn thành, chưa ghi doanh thu · ' + KD.ngay((it.updated_at || '').slice(0, 10)))));
    if (donChuaGhi && donChuaGhi.length > 5) ds.push('<li class="kt-viec__them"><span class="kd-lines__sub">… và ' + KD.soDem(donChuaGhi.length - 5) + ' đơn khác chưa ghi doanh thu</span></li>');
    if (noQuaHan && noQuaHan.so) ds.push(dongViec('Nợ khách quá hạn', noQuaHan.tien, '<span class="pill pill--danger">' + KD.soDem(noQuaHan.so) + ' khoản quá hạn</span>',
      'Bằng dòng "Nợ khách quá hạn" ở Chỉ số khác', '/ketoan/cong-no-kh?tinh_trang=qua_han'));
    if (cocCho && cocCho.length) ds.push(dongViec('Xác nhận cọc chờ Kế toán', cocCho.reduce((a, x) => a + x.so_tien, 0),
      '<span class="pill pill--warning">' + KD.soDem(cocCho.length) + ' đơn chờ xác nhận</span>', cocCho.map((x) => x.ma + ' — ' + x.khach).join(' · '), '/kt-duyet'));
    $('tq-viec-hop').hidden = !ds.length;
    $('tq-viec-dem').textContent = ds.length ? KD.soDem((donChuaGhi || []).length + (noQuaHan && noQuaHan.so ? 1 : 0) + ((cocCho || []).length ? 1 : 0)) : '';
    $('tq-viec').innerHTML = ds.join('');
  }

  function pillCho(ngay) {
    if (ngay >= 5) return '<span class="pill pill--danger">Chờ ' + KD.soDem(ngay) + ' ngày</span>';
    if (ngay >= 2) return '<span class="pill pill--warning">Chờ ' + KD.soDem(ngay) + ' ngày</span>';
    return '<span class="pill pill--info">' + (ngay ? 'Chờ 1 ngày' : 'Gửi hôm nay') + '</span>';
  }
  function veDuyet(cd) {
    const ul = $('tq-duyet'), tt = $('tq-duyet-tt'), tong = $('tq-duyet-tong'), dem = $('tq-duyet-dem');
    tt.innerHTML = '';
    if (!cd || !cd.tong_so) {
      ul.innerHTML = ''; ul.hidden = true; tong.hidden = true; dem.hidden = true;
      tt.innerHTML = KD.khoiRong('Không có lệnh nào chờ bạn duyệt', 'Không có đề xuất chi, đề nghị thanh toán hay đề xuất trả NCC nào đang chờ bạn.'); return;
    }
    dem.hidden = false; dem.textContent = cd.tong_so;
    tong.hidden = false; tong.innerHTML = 'Tổng chờ duyệt<b class="num">' + KD.tienVnd(cd.tong_tien) + '</b>';
    ul.hidden = false;
    ul.innerHTML = cd.ds.slice(0, 4).map((x) => dongViec(x.noi_dung, x.so_tien, pillCho(x.cho_ngay),
      x.ma + ' · ' + x.nguoi_de_nghi + (x.bo_phan ? ' · ' + x.bo_phan : ''), '/ketoan/kt-duyet?tim=' + encodeURIComponent(x.ma))).join('')
      + (cd.tong_so > 4 ? '<li class="kt-duyet__them"><a class="kd-link kd-link--sm" href="/ketoan/kt-duyet">Xem thêm ' + KD.soDem(cd.tong_so - 4) + ' lệnh</a></li>' : '');
  }

  /* ── "Chờ tôi duyệt" — CÙNG quy tắc thẻ "Chờ tôi duyệt" của màn Duyệt chi (kt-duyet.js: taiPhu/tuDx/tuHaiCap):
     · Đề xuất chi: /api/duyet-chi/queue/me, trạng thái còn chờ (không từ chối / xong / 'duyet' dữ liệu cũ).
     · Đề nghị TT (/api/de-nghi-tt) + Trả NCC (/api/ncc-de-xuat): trang_thai 'cho_duyet' khi vai trò ∈ KT_ROLES.
     Bản trước lấy /api/kt-duyet/list (xác nhận cọc báo giá) — khối đó link sang Duyệt chi nhưng đếm thứ khác
     (1 lệnh · 29,4tr vs Duyệt chi "Chờ tôi duyệt" 4 · 11,2tr ngày 25/09/2026). ── */
  const KT_ROLES = ['manager', 'admin'];
  function choToiDuyet(q, dntt, ncc, vaiTro) {
    const conCho = (r) => !(r.approval_level === 'rejected' || r.trang_thai === 'tu_choi' || r.approval_level === 'done'
      || r.trang_thai === 'da_duyet' || r.trang_thai === 'duyet');
    const ds = (q || []).filter(conCho).map((r) => ({
      ma: 'DX' + String(r.id).padStart(4, '0'), so_tien: KD.so(r.so_tien) || 0, gui: r.created_at,
      noi_dung: r.tieu_de || 'Đề xuất chi', nguoi_de_nghi: r.ho_ten || r.username || '—', bo_phan: r.phong_ban || '',
    }));
    if (KT_ROLES.includes(vaiTro)) {
      (dntt || []).filter((r) => r.trang_thai === 'cho_duyet').forEach((r) => ds.push({ ma: r.id, so_tien: KD.so(r.so_tien) || 0, gui: r.created_at,
        noi_dung: 'Thanh toán ĐVVC ' + (r.don_vi_vc || '') + (r.ma_don ? ' · ' + r.ma_don : ''), nguoi_de_nghi: r.nguoi_tao_ten || r.nguoi_tao || '—', bo_phan: 'Sale Admin' }));
      (ncc || []).filter((r) => r.trang_thai === 'cho_duyet').forEach((r) => ds.push({ ma: r.id, so_tien: KD.so(r.so_tien) || 0, gui: r.created_at,
        noi_dung: 'Trả nợ NCC ' + (r.ncc_name || r.ncc_id || ''), nguoi_de_nghi: r.nguoi_tao_ten || r.nv_mua_hang_ten || r.nguoi_tao || '—', bo_phan: 'Mua Hàng' }));
    }
    ds.sort((a, b) => String(a.gui || '').localeCompare(String(b.gui || '')));   // chờ lâu nhất lên đầu
    const homNay = Date.now();
    ds.forEach((x) => { x.cho_ngay = x.gui ? Math.max(0, Math.floor((homNay - new Date(x.gui).getTime()) / 86400000)) : 0; });
    return { tong_so: ds.length, tong_tien: ds.reduce((a, x) => a + x.so_tien, 0), ds };
  }

  /* ── Tải toàn màn: nhiều nguồn song song, mỗi khối tự chịu lỗi riêng ── */
  async function tai() {
    const l = ++luot; const ky = khoang(); const kyTr = KT.kySoSanh(st.ky, ky); ssHt = kyTr;
    const tenKy = KT.nhanKy(st.ky, ky), khoangChu = KD.ngay(ky.tu) + ' – ' + KD.ngay(ky.den);
    // Kế hoạch gọi KQKD của kỳ: đúng các tháng + kỳ so sánh như màn KQKD (ke(tu, den, ss.thang)).
    const keKq = KT.kqkd.ke(ky.tu, ky.den, kyTr.thang), thangBd = thangBieuDo(ky.den);
    $('tq-ky-chu').innerHTML = 'Số liệu ' + (tenKy === khoangChu ? khoangChu : esc(tenKy) + ' (' + khoangChu + ')') + ' · KQKD ' + nhanThangKq(keKq.nay)
      + KD.tip('Tiền thu, công nợ, chỉ số vận hành: theo ngày hạch toán trong kỳ; % so với ' + kyTr.nhan + ': ' + KD.ngay(kyTr.tu) + ' – ' + KD.ngay(kyTr.den) + '. '
        + 'Doanh thu thuần, giá vốn + chi phí, lợi nhuận: số báo cáo Kết quả kinh doanh (KQKD) — tính trọn ' + nhanThangKq(keKq.nay)
        + ', so với ' + nhanThangKq(keKq.truoc) + '.');
    $('tq-body').hidden = false; $('tq-loi').hidden = true;
    $('tq-kqkd-link').href = '/ketoan/bao-cao/kqkd?' + KT.url.qs(st.ky === 'tuy_chinh' ? { ky: st.ky, tu: st.tu, den: st.den } : { ky: st.ky });
    veCho();

    const goi = {
      tongQuan: KD.api('/api/bao-cao/tong-quan?' + KT.url.qs({ tu_ngay: ky.tu, den_ngay: ky.den })),
      // Kỳ so sánh cho % thẻ Tiền thu từ khách.
      tongHopTruoc: KD.api('/api/bao-cao/tong-quan?' + KT.url.qs({ tu_ngay: kyTr.tu, den_ngay: kyTr.den })),
      kqkd: Promise.all(keKq.urls.map(layPl)).then((ds) => KT.kqkd.tach(ds, keKq)),
      kqkdThang: Promise.all(thangBd.map((t) => layPl(urlPl(t))))
        .then((ds) => ds.map((pl, i) => ({ thang: thangBd[i], dt_thuan: KT.kqkd.gop([pl]).dt_thuan }))),
      // Phải trả: CÙNG nguồn màn Công nợ NCC (ncc-module, ròng theo NCC) — xem GHI CHÚ ở khối KPI.
      phaiTra: KD.api('/api/cong-no/ncc-module'),
      journal: KD.api('/api/journal?' + KT.url.qs({ from: ky.tu, to: ky.den, limit: 8, offset: 0 })),
      soDu: tonQuyDenNgay(ky),
      queueMe: KD.api('/api/duyet-chi/queue/me'),
      dntt: KD.api('/api/de-nghi-tt?limit=500'),
      ncc: KD.api('/api/ncc-de-xuat?limit=500'),
      profile: KD.api('/api/profile'),
      coc: KD.api('/api/kt-duyet/list'),
      donChuaGhi: KD.api('/api/orders/pending-revenue'),
    };
    const ten = Object.keys(goi);
    const ket = await Promise.allSettled(ten.map((k) => goi[k]));
    if (l !== luot) return;
    const r = {}; ten.forEach((k, i) => { r[k] = ket[i].status === 'fulfilled' ? ket[i].value : null; });
    const loiCuaGio = (k) => { const x = ket[ten.indexOf(k)]; return x.status === 'rejected' ? x.reason : null; };

    /* KPI 8 thẻ — hàng 1 dòng tiền & công nợ (phải thu, phải trả, tồn quỹ, tiền thu từ khách); hàng 2 số KQKD
       (doanh thu thuần, giá vốn + chi phí, LN gộp, LN trước thuế — nhãn theo dòng B02). */
    const homNay = KD.iso(new Date());
    const conLaiCua = (rec) => KD.so(rec.con_lai != null ? rec.con_lai : (rec.so_tien - rec.da_tra));
    const tongConLai = (ds) => (ds || []).reduce((a, x) => a + Math.max(0, conLaiCua(x)), 0);
    const tq = r.tongQuan, th = r.tongHopTruoc, kq = r.kqkd;
    /* Phải thu còn nợ lấy từ /tong-quan.phai_thu_mo — máy chủ đã loại dòng "thu hộ qua ĐVVC"
       (ref_source saleadmin_vc_phai_thu) vốn TRÙNG phải thu của chính đơn báo giá; cùng định nghĩa
       với màn Công nợ KH (971.261.114, không phải 997.095.513 như khi cộng cả dòng trùng). */
    r.phaiThu = tq ? tq.phai_thu_mo : null;
    /* Phải trả — GHI CHÚ đợt 3: bản trước cộng con_lai > 0 TỪNG DÒNG /api/cong-no?loai=phai_tra = 1.625.293.200,
       trong khi màn Công nợ NCC (ncc-module, ròng theo NCC) báo "Còn phải trả" 827.348.200: 797.945.000 là phần
       trả dư ghi trên các dòng khác của CÙNG NCC (con_lai âm) bị bỏ qua khi kẹp từng dòng về 0. Nay lấy đúng số
       ròng của màn Công nợ NCC (mặc định "Tất cả").
       GHI CHÚ 29/09/2026: dùng con_lai_thuc (CHỈ đơn nhóm thực/cần kiểm), KHÔNG dùng con_lai (mọi đơn kể
       cả dự kiến) — quyết định người dùng: "còn nợ/phải trả" không cộng nợ dự kiến. Xem cong_no_ncc.py.
       BƯỚC 3 30/09/2026: đổi sang stats.con_lai_thuc_duong (Σ chỉ NCC còn nợ dương — không bị 1 NCC
       trả trước kéo âm cả tổng, mỗi NCC là quan hệ độc lập) — CÙNG SỐ với thẻ "Còn phải trả" ở
       Công nợ NCC (kt-cong-no.js::veKpi). Dùng field backend tính sẵn thay vì tự reduce items. */
    const nccItems = r.phaiTra ? (r.phaiTra.items || []) : null;
    const phaiTraRong = r.phaiTra && r.phaiTra.stats ? (KD.so(r.phaiTra.stats.con_lai_thuc_duong) || 0) : null;
    const soDu = r.soDu;
    const soKhachNo = r.phaiThu ? new Set(r.phaiThu.filter((x) => conLaiCua(x) > 0).map((x) => x.doi_tac)).size : 0;
    const kpi = {
      phai_thu: r.phaiThu ? { gia_tri: tongConLai(r.phaiThu), phu: KD.soDem(soKhachNo) + ' khách còn nợ', tip: 'Còn phải thu hiện tại, tính mọi thời điểm.' } : null,
      phai_tra: nccItems ? { gia_tri: phaiTraRong, phu: 'Ròng theo NCC', tip: 'Còn phải trả ròng hiện tại — bằng màn Công nợ NCC.' } : null,
      ton_quy: soDu ? { gia_tri: soDu.tong, phu: 'Đến ' + KD.ngay(ky.den), tip: 'Tiền mặt ' + KD.tienGon(soDu.tien_mat) + ' · Ngân hàng ' + KD.tienGon(soDu.ngan_hang) + '.' } : null,
      ...kpiTienThu(tq, th),
      ...kpiKqkd(kq, kyTr),
    };
    veKpi(kpi);

    /* Dải 1: đơn duyệt · nợ quá hạn · đến hạn NCC · công nợ phát sinh */
    const dai1 = {};
    if (tq) {
      dai1.so_don = { v: dem(tq.so_don, 'đơn'), tip: 'Báo giá được duyệt trong kỳ (theo ngày duyệt).' };
      const cn = tq.cong_no_by_loai || {};
      dai1.cong_no_ps = { v: KD.tienGonHtml(tq.tong_cong_no), tip: 'Trong kỳ: phải thu ' + KD.tienGon(cn.phai_thu || 0) + ' · phải trả ' + KD.tienGon(cn.phai_tra || 0) + '.' };
    }
    let noQuaHan = null;
    if (r.phaiThu) {
      const qh = r.phaiThu.filter((x) => conLaiCua(x) > 0 && hanThu(x) && hanThu(x) < homNay);
      const khach = new Set(qh.map((x) => x.doi_tac));
      noQuaHan = { so: qh.length, tien: qh.reduce((a, x) => a + conLaiCua(x), 0) };
      dai1.no_qua_han = {
        v: KD.tienGonHtml(noQuaHan.tien),
        tip: (qh.length ? KD.soDem(qh.length) + ' khoản · ' + KD.soDem(khach.size) + ' khách (hiện tại). ' : 'Không có khách nào quá hạn. ') + 'Khoản chưa đặt hạn: tính quá hạn sau 30 ngày từ ngày phát sinh.',
      };
    }
    /* Đến hạn trả NCC 7 ngày — CÙNG quy tắc cột "Đến hạn 7 ngày" màn Công nợ NCC (kt-cong-no.js chuyenNCC): chỉ
       khoản con_lai > 0 CÓ han_thanh_toan, hạn trong [hôm nay, +7 ngày]. Bản trước tự gán hạn = phát sinh + 30
       cho khoản chưa có hạn (0/269 khoản NCC có hạn) → 16,9tr ở Tổng quan nhưng 0 ở màn Công nợ NCC. */
    if (nccItems) {
      const hn = new Date(homNay + 'T00:00:00');
      let tien = 0, so = 0, coHan = 0, conNo = 0;
      nccItems.forEach((it) => (it.don_list || []).forEach((p) => {
        if (!((KD.so(p.con_lai) || 0) > 0)) return;
        conNo++;
        const han = parseNgay(p.han_thanh_toan); if (!han) return;
        coHan++;
        const n = Math.round((han - hn) / 86400000);
        if (n >= 0 && n <= 7) { tien += KD.so(p.con_lai); so++; }
      }));
      dai1.den_han_ncc_7_ngay = {
        v: KD.tienGonHtml(tien),
        tip: (so ? KD.soDem(so) + ' khoản đến hạn' : 'Không có khoản nào sắp đến hạn') + '. ' + KD.soDem(coHan) + '/' + KD.soDem(conNo) + ' khoản còn nợ có đặt hạn trả.',
      };
    }
    /* + ADS thực chi · VAT đầu ra · Data/Inbox MKT · nhân sự → một thẻ "Chỉ số khác trong kỳ" */
    veChiSo(Object.assign(dai1, tq ? {
      tong_ads: { v: KD.tienGonHtml(tq.tong_ads), tip: 'Tiền quảng cáo chi trong kỳ theo bảng ADS của Marketing (bằng khối "Chi phí ADS theo kênh"). '
        + 'Khác dòng "Quảng cáo, marketing" trong chi phí bán hàng của KQKD' + (kq ? ' (' + KD.tienGon(kq.c.cp_ban_hang.bien_phi.ads) + ')' : '') + '.' },
      vat_dau_ra: { v: '<span>' + KD.tien(tq.vat_dau_ra) + '</span><span class="kd-kpi__don-vi">VND</span>', tip: 'Thuế GTGT của đơn duyệt trong kỳ.' },
      so_data_mkt: { v: dem(tq.so_data_mkt, 'data'), tip: 'Data khách marketing thu về.' },
      so_inbox_mkt: { v: dem(tq.so_inbox_mkt, 'inbox'), tip: 'Tin nhắn marketing nhận được.' },
      tong_nv: { v: dem(tq.tong_nv, 'người'), tip: 'Nhân viên đang làm (hiện tại).' },
    } : {}));
    if (!tq) { $('tq-loi').hidden = false; KD.khoiLoi($('tq-loi'), 'Không tải được số liệu tổng hợp', loiCuaGio('tongQuan'), tai); }

    /* Việc cần xử lý */
    const cocCho = (r.coc || []).filter((x) => x.duyet_status === 'kt_pending')
      .map((x) => ({ ma: x.quote_number || ('BG-' + x.id), khach: x.customer_name || 'khách chưa rõ', so_tien: KD.so(x.coc_so_tien != null ? x.coc_so_tien : x.tong_don) || 0 }));
    veViec(r.donChuaGhi && r.donChuaGhi.items, noQuaHan, cocCho);

    /* Biểu đồ Doanh thu thuần theo tháng — KQKD từng tháng (cùng định nghĩa thẻ Doanh thu thuần) */
    if (kq && r.kqkdThang) veThang(r.kqkdThang, ky, kq);
    else { $('tq-chart-hop').hidden = true; KD.khoiLoi($('tq-chart-tt'), 'Không tải được doanh thu thuần theo tháng', loiCuaGio(kq ? 'kqkdThang' : 'kqkd'), tai); }

    /* Tuổi nợ + top nợ (mọi thời điểm, không riêng trong kỳ) — hạn mặc định ngày phát sinh + 30 */
    if (r.phaiThu) {
      const nhom = { chua_den_han: 0, qh_1_30: 0, qh_31_60: 0, qh_tren_60: 0 };
      r.phaiThu.forEach((x) => { const cl = conLaiCua(x); if (cl <= 0) return; nhom[nhomTuoi(hanThu(x), cl, homNay)] += cl; });
      veTuoi(Object.keys(nhom).map((k) => ({ nhom: k, gia_tri: nhom[k] })));

      const theoKhach = {};
      r.phaiThu.forEach((x) => { const cl = Math.max(0, conLaiCua(x)); if (!cl) return; theoKhach[x.doi_tac] = (theoKhach[x.doi_tac] || 0) + cl; });
      const top = Object.keys(theoKhach).map((ten_) => ({ ten: ten_, con_lai: theoKhach[ten_] })).sort((a, b) => b.con_lai - a.con_lai);
      veTop(top);
    } else {
      KD.khoiLoi($('tq-tuoi'), 'Không tải được tuổi nợ', loiCuaGio('tongQuan'), tai);
      KD.khoiLoi($('tq-top'), 'Không tải được khách nợ', loiCuaGio('tongQuan'), tai);
    }

    /* Cơ cấu chi phí — các dòng chi phí của KQKD, cộng = thẻ Giá vốn + chi phí */
    if (kq) veCoCauCp(kq);
    else KD.khoiLoi($('tq-cp'), 'Không tải được cơ cấu chi phí', loiCuaGio('kqkd'), tai);

    /* Doanh số NV · Tiền thu theo loại · ADS theo kênh — từ /tong-quan */
    if (tq) {
      veNv((tq.dt_by_nv || []).map((p) => ({ ten: p[0], doanh_so: KD.so(p[1]) || 0 })).filter((n) => n.doanh_so));
      veLoai($('tq-dt'), (tq.dt_by_loai || []).map((p) => ({ ten: p[0], so_tien: p[1] })),
        ['Chưa thu tiền khách nào trong kỳ', 'Tiền thu hiện khi kế toán ghi nhận phiếu thu cọc / thanh toán.'], 'Cộng tiền thu',
        'Bằng thẻ Tiền thu từ khách (phiếu thu theo loại doanh thu, gồm cọc và VAT).');
      veLoai($('tq-ads'), (tq.ads_by_kenh || []).map((p) => ({ ten: p[0], so_tien: p[1] })),
        ['Chưa có chi phí quảng cáo trong kỳ', 'Số liệu lấy từ bảng chi phí ADS của Marketing.'], 'Cộng chi phí ADS', 'Bằng dòng "Chi ADS thực tế".');
    } else {
      ['tq-nv', 'tq-dt', 'tq-ads'].forEach((id) => KD.khoiLoi($(id), 'Không tải được số liệu', loiCuaGio('tongQuan'), tai));
    }

    /* Bút toán gần đây */
    if (r.journal) veBt(r.journal.slice(0, 8), ky); else KD.khoiLoi($('tq-bt-tt'), 'Không tải được bút toán gần đây', loiCuaGio('journal'), tai);

    /* Lệnh chờ duyệt = "Chờ tôi duyệt" của màn Duyệt chi */
    if (r.queueMe || r.dntt || r.ncc) {
      veDuyet(choToiDuyet(r.queueMe, r.dntt, r.ncc, ((r.profile && r.profile.role) || '').toLowerCase()));
    } else KD.khoiLoi($('tq-duyet-tt'), 'Không tải được danh sách chờ duyệt', loiCuaGio('queueMe'), tai);
  }

  // Ô kỳ dùng chung: nhanh / Tuỳ chỉnh (điền sẵn ngày) / Chọn tháng · quý · năm cụ thể — URL ?ky=2026-07 giữ đúng kỳ khi F5.
  KT.ganKy({ sel: $('tq-ky'), hop: $('tq-khoang'), tu: $('tq-tu'), den: $('tq-den'), st,
    doi: () => { KT.url.ghi(st, { ky: 'thang_nay' }); tai(); }, ghi: () => KT.url.ghi(st, { ky: 'thang_nay' }) });
  tai();
})();
