/* kt-so-quy.js (dot3b) — Sổ quỹ tiền mặt, nối API THẬT của app ketoan.
   ─────────────────────────────────────────────────────────────────────────
   GAP THẬT so với bản thiết kế / README mục 4.11 (ghi rõ để không ai tưởng nhầm là số giả):
   - KHÔNG có endpoint `/api/so-quy` kiểu tổng hợp sẵn (tồn đầu/cuối, tồn luỹ kế mỗi dòng,
     số phiếu thu/chi tách cột, phân trang server). API thật chỉ có:
       GET /api/so-quy?tu_ngay&den_ngay&loai&tai_khoan&limit&offset  → MẢNG phẳng SoQuy
       GET /api/so-quy/summary?tu_ngay&den_ngay (hoặc ?thang=) → tồn đầu/cuối THEO TỪNG TÀI KHOẢN
     → file này tự: gom MỌI quỹ đang hoạt động (TaiKhoanNH.active — tiền mặt + ngân hàng;
       mở phạm vi 02/10/2026, trước đó chỉ loai='tien_mat'), tự cộng dồn "Tồn quỹ"
       theo dòng, tự tìm-kiếm/phân trang ở trình duyệt (tồn đầu kỳ lấy từ summary theo
       đúng khoảng ngày, xem dongBoTon).
   - SoQuy không có số phiếu (so_phieu_thu/so_phieu_chi) hay TK đối ứng thật — cột "Số phiếu"
     dùng mã nội bộ SQ-<id>; cột "TK đối ứng" đổi thành "Nguồn" (lien_quan: doanh_thu/chi_phí/
     công nợ/chuyển nội bộ/nhập tay) vì đó là dữ liệu thật gần nhất có ý nghĩa tương đương.
   - Không có "kiểm kê quỹ" (đối chiếu tiền mặt thực tế) trong DB — bỏ khối này khỏi phạm vi.
   - Panel không gọi thêm API phụ (SoQuy không link sang một bút toán sổ cái riêng) — hiện
     thẳng dữ liệu của dòng sổ quỹ.
   ───────────────────────────────────────────────────────────────────────── */
(function () {
  'use strict';
  if (!document.getElementById('kd-kt-so-quy')) return;
  const H = KT.H;
  // Giải thích phạm vi số liệu: ⓘ cạnh tiêu đề (không in đoạn chữ dưới hàng thẻ số).
  document.querySelector('#kd-kt-so-quy .kd-h1').insertAdjacentHTML('beforeend',
    KD.tip('Gồm MỌI quỹ đang hoạt động: tiền mặt và các tài khoản ngân hàng. Tồn đầu kỳ là số dư ngay trước ngày đầu kỳ; cột Tồn quỹ cộng dồn các giao dịch trong kỳ theo đúng phạm vi đang lọc. Lọc ô "Tài khoản" để xem riêng một quỹ.'));
  document.getElementById('sq-pham-vi').hidden = true;

  /* Nhãn nguồn (so_quy.lien_quan). Giá trị lạ (vd 'vay_8' = khoản vay #8) vẫn hiện có nghĩa. */
  const NGUON = {
    doanh_thu: 'Tự động — Doanh thu', chi_phi: 'Tự động — Chi phí',
    cong_no: 'Tự động — Công nợ', chuyen_noi_bo: 'Chuyển nội bộ', denghitt: 'Đề nghị thanh toán', tam_ung: 'Tạm ứng',
    nhap_tay: 'Nhập tay',
  };
  const nhanNguon = (v) => NGUON[v] || (/^vay_\d+$/.test(v || '') ? 'Khoản vay #' + v.slice(4) : v ? esc(v) : 'Nhập tay');

  /* ── Dòng tiền (so_quy.phan_loai_cf) = mã số báo cáo lưu chuyển tiền tệ (B03) ─────────────────────────
     Danh sách + nhãn lấy từ API GET /api/so-quy/phan-loai-cf — NGUỒN DUY NHẤT ở backend
     (app/services/phan_loai_cf.py), KHÔNG gõ cứng ở đây. Khoá 'khac' / 'noi_bo' dùng cho cả thu lẫn chi và nhãn khác
     nhau theo chiều → tra theo (loại phiếu, khoá). */
  const CHUA_CF = '__chua';   // giá trị bộ lọc "Chưa phân loại" (phan_loai_cf NULL — dòng cũ / bridge tự sinh)
  // Màu thẻ nhỏ chỉ là trình bày (giữ màu cũ của 9 khoá cũ); khoá mới: thu = lục, chi = xám xanh.
  const MAU_CF = { thu_kh: 'success', tra_ncc: 'danger', nap_ads: 'warning', tra_luong: 'info', mua_ccdc: 'info', sua_chua_lon: 'warning',
    vay_nh: 'info', tra_nh: 'info', khac: 'muted', noi_bo: 'muted' };
  let cfBang = {}, cfNap = null;   // cfBang: { 'chi:tra_ncc': {khoa, ma_so, ten, ngan, loai, nhom, nhom_ten} }
  // Chuyển nội bộ giữa 2 quỹ (POST /api/so-quy/chuyen-noi-bo) ghi phan_loai_cf='khac' + lien_quan='chuyen_noi_bo'; báo cáo LCTT coi
  // đó là nội bộ (loại ra) → thẻ nhỏ, panel và bộ lọc cũng coi như 'noi_bo' để màn khớp báo cáo (không hiện nhầm "Thu khác · 06").
  const cfDong = (r) => (/^chuyen_noi_bo$/i.test(r.lien_quan || '') ? 'noi_bo' : r.phan_loai_cf);
  const nhanNganCf = (x) => x.ngan + (x.ma_so ? ' · ' + x.ma_so : '');
  const nhanDaiCf = (x) => (x.ma_so ? x.ma_so + ' — ' : '') + x.ten;
  const timCf = (cf, loai) => cfBang[loai + ':' + cf] || cfBang['chi:' + cf] || cfBang['thu:' + cf] || null;
  // Nạp MỘT lần cả bảng nhãn (thu + chi) cho thẻ nhỏ ở bảng, bảng panel và bộ lọc. Không bao giờ reject (lỗi → bảng rỗng).
  function napBangCf() {
    cfNap = cfNap || KD.api('/api/so-quy/phan-loai-cf').then((d) => {
      cfBang = {}; (d || []).forEach((x) => { cfBang[x.loai + ':' + x.khoa] = x; }); return d || [];
    }).catch((e) => { console.warn('[so-quy] Không tải được bảng dòng tiền:', e && e.message); cfNap = null; return []; });
    return cfNap;
  }
  const cfPill = (cf, loai) => {
    if (!cf) return '';   // dòng chưa phân loại: không thẻ (muốn tìm thì lọc "Chưa phân loại")
    const x = timCf(cf, loai);
    if (!x) { console.warn('[so-quy] Dòng tiền chưa có nhãn:', cf); return ' ' + H.pill('muted', 'Chưa đặt tên'); }
    return ' ' + H.pill(MAU_CF[cf] || (loai === 'thu' ? 'success' : 'info'), nhanNganCf(x));
  };
  const dongTienDai = (cf, loai) => {
    if (!cf) return '<span class="kd-muted">Chưa phân loại</span>';
    const x = timCf(cf, loai);
    return x ? esc(nhanDaiCf(x)) : 'Chưa đặt tên';
  };
  // <optgroup> theo nhóm báo cáo (hoạt động kinh doanh / đầu tư / tài chính / chuyển nội bộ); server đã xếp theo mã số.
  function htmlNhomCf(ds2) {
    const nhom = [];
    ds2.forEach((x) => { let g = nhom.find((n) => n.k === x.nhom); if (!g) nhom.push(g = { k: x.nhom, ten: x.nhom_ten, ds: [] }); g.ds.push(x); });
    return nhom.map((g) => '<optgroup label="' + esc(g.ten) + '">' + g.ds.map((x) => '<option value="' + esc(x.value) + '">' + esc(x.text) + '</option>').join('') + '</optgroup>').join('');
  }
  // Ô lọc "Dòng tiền" ở bảng: mỗi khoá một dòng (khoá dùng cả hai chiều gộp nhãn), nhãn ngắn như thẻ nhỏ.
  let locCfXong = false;
  function napLocCf(dsCf) {
    const e = document.getElementById('sq-cf');
    if (!e || locCfXong || !dsCf.length) return;
    locCfXong = true;
    const theoKhoa = new Map();
    dsCf.forEach((x) => { const g = theoKhoa.get(x.khoa) || { value: x.khoa, nhom: x.nhom, nhom_ten: x.nhom_ten, nhan: [] }, n = nhanNganCf(x);
      if (g.nhan.indexOf(n) < 0) g.nhan.push(n); theoKhoa.set(x.khoa, g); });
    const giu = ds.st.cf || '';
    e.innerHTML = '<option value="">Tất cả</option><option value="' + CHUA_CF + '">Chưa phân loại</option>'
      + htmlNhomCf([...theoKhoa.values()].map((g) => Object.assign(g, { text: g.nhan.join(' / ') })));
    if (giu && ![...e.options].some((o) => o.value === giu)) e.insertAdjacentHTML('beforeend', '<option value="' + esc(giu) + '">' + esc(giu) + '</option>');   // link cũ / giá trị lạ: giữ để ô không hiện "Tất cả" khi bảng đang lọc
    e.value = giu;
  }

  /* ── Nghiệp vụ (so_quy.ma_dinh_khoan — phiếu lập tay từ 01/10/2026): nhãn lấy từ GET /api/so-quy/nghiep-vu (nguồn duy nhất ở
     backend). Dòng có nghiệp vụ hiện thẻ tên việc thay thẻ dòng tiền; dòng cũ / cầu nối (NULL) hiện như trước. Không bao giờ reject. */
  let nvBang = {}, nvNapBang = null;   // 'chi:tra_luong' → {khoa, ten, b03_ten, b03_ma_so, …}
  function napBangNv() {
    nvNapBang = nvNapBang || Promise.all(['thu', 'chi'].map((l) => KD.api('/api/so-quy/nghiep-vu?loai=' + l).catch((e) => {
      console.warn('[so-quy] Không tải được bảng nghiệp vụ:', e && e.message); return null; })))
      .then((ds2) => { nvBang = {}; ds2.forEach((d) => ((d && d.nghiep_vu) || []).forEach((x) => { nvBang[x.loai + ':' + x.khoa] = x; }));
        if (ds2.some((d) => !d)) nvNapBang = null; return nvBang; });
    return nvNapBang;
  }
  const tenNgan = (s) => String(s || '').replace(/\s*\([^)]*\)\s*$/, '');   // bỏ phần giải thích trong ngoặc ở cuối tên việc
  const tenNv = (r) => { const x = nvBang[r.loai + ':' + r.ma_dinh_khoan]; if (!x) console.warn('[so-quy] Nghiệp vụ chưa có nhãn:', r.ma_dinh_khoan); return x ? x.ten : 'Chưa đặt tên'; };
  const nvPill = (r) => ' ' + H.pill(r.loai === 'thu' ? 'success' : 'info', tenNgan(tenNv(r)));
  const DT_LOAI = { khach: 'Khách hàng', ncc: 'Nhà cung cấp', nv: 'Nhân viên' };

  /* ── MỌI quỹ đang hoạt động: tiền mặt + ngân hàng (TaiKhoanNH.active) — cache 1 lần ──
     ĐỔI 02/10/2026 (anh Quang: "sổ quỹ hiển thị hết toàn bộ tổng, hiện tại chỉ hiện mỗi
     sổ quỹ tiền mặt, còn những ngân hàng khác nữa"). Trước đây màn này gọi
     `?loai=tien_mat` nên chỉ lấy đúng 1 tài khoản (Tiền Mặt) rồi LỌC BỎ mọi dòng của
     ACB / BIDV / VPB — 263 phiếu, 2.690 tỷ thu chi, không nhìn thấy ở đâu trên màn này.
     Giờ lấy hết; ai muốn xem riêng một quỹ thì dùng ô lọc "Tài khoản" (#sq-tk). */
  let dsQuy = null;
  async function layQuy() {
    if (dsQuy) return dsQuy;
    try {
      const ds2 = await KD.api('/api/tai-khoan?active_only=true');
      dsQuy = (ds2 || []).map((t) => ({ ten: t.ten_tk, loai: t.loai }));
    } catch (e) { dsQuy = []; }
    return dsQuy;
  }
  const tenQuy = () => (dsQuy || []).map((t) => t.ten);
  /* Phạm vi đang xem: rỗng = tất cả quỹ; có giá trị = đúng 1 quỹ. Dùng chung cho tồn đầu
     kỳ và cho việc lọc dòng, để KPI Tồn đầu/Tồn cuối luôn cùng phạm vi với bảng. */
  const phamVi = (tk) => {
    const tat = tenQuy();
    return tk && tat.indexOf(tk) !== -1 ? [tk] : tat;
  };

  /* Nạp lựa chọn cho ô lọc "Tài khoản" — giữ nguyên giá trị đang chọn trên URL. */
  function napLocQuy() {
    const el = document.getElementById('sq-tk');
    if (!el || el.dataset.daNap) return;
    const dang = el.value;
    el.innerHTML = '<option value="">Tất cả tài khoản</option>'
      + (dsQuy || []).map((t) => '<option value="' + esc(t.ten) + '">' + esc(t.ten)
        + (t.loai === 'tien_mat' ? ' (tiền mặt)' : '') + '</option>').join('');
    if (dang) el.value = dang;
    el.dataset.daNap = '1';
  }

  /* ── Tồn đầu kỳ THẬT tại đúng ngày `ky.tu` ──────────────────────────────
     GET /api/so-quy/summary?tu_ngay&den_ngay (2026-09-25) trả số dư NGAY TRƯỚC `tu_ngay`
     theo từng tài khoản, cùng thuật toán neo SoDuDauKy với màn Ngân hàng
     (so_quy_auto.so_du_truoc_ngay) — không còn phải tự cộng phần lệch đầu tháng ở đây.
     Thu/Chi/Tồn cuối vẫn tính trực tiếp trên đúng danh sách đang lọc [tu, den].
     Tồn đầu kỳ cộng dồn MỌI quỹ đang xem (tất cả, hoặc đúng 1 quỹ nếu đang lọc) — phải
     cùng phạm vi với bảng, nếu không KPI Tồn đầu/Tồn cuối sẽ lệch với cột Tồn quỹ. */
  let tonState = { key: null, ready: false, tonDau: 0 };
  async function dongBoTon(ky) {
    const key = ky.tu + '|' + ky.den + '|' + (ky.tk || '');
    if (tonState.key === key && tonState.ready) return false;
    if (!ky.tu || !ky.den) { tonState = { key, ready: true, tonDau: 0 }; return true; }
    await layQuy();
    napLocQuy();
    const tks = phamVi(ky.tk);
    let tonDau = 0;
    try {
      const d = await KD.api('/api/so-quy/summary?' + KT.url.qs({ tu_ngay: ky.tu, den_ngay: ky.den }));
      tonDau = (d.items || []).filter((it) => tks.indexOf(it.ten_tk) !== -1).reduce((s, x) => s + Number(x.so_du_dau_thang || 0), 0);
    } catch (e) { /* fail-soft — giữ tonDau = 0 */ }
    tonState = { key, ready: true, tonDau };
    return true;
  }

  const ds = KT.danhSach({
    pfx: 'sq', donVi: 'giao dịch',
    // Không gửi `loai` lên API: lọc Thu/Chi ở trình duyệt SAU khi cộng dồn tồn quỹ, để cột "Tồn quỹ"
    // và KPI Tồn cuối vẫn đúng khi chỉ xem phiếu thu hoặc phiếu chi.
    api: (q) => '/api/so-quy?' + KT.url.qs({ tu_ngay: q.tu, den_ngay: q.den, limit: 2000 }),
    macDinh: { ky: 'thang_nay', tu: '', den: '', tim: '', loai: '', cf: '', tk: '', page: 1, size: 20, sort: '' },
    dong: { id: (r) => r.id },
    chuyen: (raw, q) => {
      // Mặc định hiện MỌI quỹ (tiền mặt + ngân hàng); chọn ô lọc "Tài khoản" thì chỉ quỹ đó.
      // Dòng không ghi tai_khoan vẫn giữ lại (dữ liệu cũ) để không âm thầm mất phiếu.
      const tks = phamVi(q.tk);
      const list = (raw || []).filter((r) => !tks.length || !r.tai_khoan || tks.indexOf(r.tai_khoan) !== -1);
      list.sort((a, b) => (a.ngay < b.ngay ? -1 : a.ngay > b.ngay ? 1 : a.id - b.id));
      let running = tonState.ready ? tonState.tonDau : 0;
      const withTon = list.map((r) => {
        running += r.loai === 'thu' ? Number(r.so_tien || 0) : -Number(r.so_tien || 0);
        return Object.assign({}, r, { ton: running });
      });
      withTon.reverse(); // mới nhất trước, khớp bố cục thiết kế
      const t = (q.tim || '').trim();
      const theoLoai = q.loai ? withTon.filter((r) => r.loai === q.loai) : withTon;
      const theoCf = q.cf ? theoLoai.filter((r) => (q.cf === CHUA_CF ? !cfDong(r) : cfDong(r) === q.cf)) : theoLoai;
      const filtered = t ? theoCf.filter((r) => KT.khopTim([r.noi_dung, r.mo_ta, r.ghi_chu, r.tai_khoan, r.nhan_vien_ten, r.ma_don, r.doi_tuong_ten], t)) : theoCf;
      const size = +q.size || 20, page = Math.max(1, +q.page || 1);
      const tong_dong = filtered.length, so_trang = Math.max(1, Math.ceil(tong_dong / size)), trang = Math.min(page, so_trang);
      // Thu/Chi luôn tính trực tiếp từ đúng danh sách đã lọc theo kỳ [tu, den] —
      // khớp 1-1 với các dòng đang hiển thị (không lấy tổng theo tháng nữa).
      const tongThu = list.reduce((s, r) => s + (r.loai === 'thu' ? Number(r.so_tien || 0) : 0), 0);
      const tongChi = list.reduce((s, r) => s + (r.loai === 'chi' ? Number(r.so_tien || 0) : 0), 0);
      const tonDau = tonState.ready ? tonState.tonDau : null;
      const tonCuoi = tonDau == null ? null : tonDau + tongThu - tongChi;
      return {
        ky: { tu: q.tu, den: q.den },
        ton_dau: tonDau,
        tong_thu: tongThu,
        tong_chi: tongChi,
        ton_cuoi: tonCuoi,
        so_phieu_thu: list.filter((r) => r.loai === 'thu').length,
        so_phieu_chi: list.filter((r) => r.loai === 'chi').length,
        // Đang lọc loại/tìm → dòng Cộng cộng đúng các dòng đang hiện (nhãn ghi rõ "đang lọc"),
        // còn thẻ KPI vẫn là cả kỳ — hai đại lượng khác nhau, nhãn khác nhau.
        co_loc: filtered.length !== list.length,
        thu_loc: filtered.reduce((s, r) => s + (r.loai === 'thu' ? Number(r.so_tien || 0) : 0), 0),
        chi_loc: filtered.reduce((s, r) => s + (r.loai === 'chi' ? Number(r.so_tien || 0) : 0), 0),
        trang, so_trang, tong_dong,
        dong: filtered.slice((trang - 1) * size, trang * size),
      };
    },
    cot: [
      { key: 'ngay', nhan: 'Ngày', ve: (r) => KD.ngay(r.ngay) },
      // Cột Tài khoản (thêm 02/10/2026 cùng lúc mở phạm vi ra mọi quỹ) — không có cột này
      // thì nhìn bảng gộp 4 quỹ không biết phiếu nào của quỹ nào.
      { key: 'tk', nhan: 'Tài khoản', ve: (r) => '<span class="kt-tk">' + esc(r.tai_khoan || '—') + '</span>' },
      // Gộp 2 cột "Số phiếu thu" / "Số phiếu chi" thành một — loại phiếu đã rõ qua cột Thu / Chi.
      { key: 'sp', nhan: 'Số phiếu', ve: (r) => H.ma('SQ-' + r.id) + '<span class="kt-khach__ma kt-sq-loai">' + (r.loai === 'thu' ? 'Phiếu thu' : 'Phiếu chi') + '</span>' },
      { key: 'dg', nhan: 'Diễn giải', ve: (r) => '<span class="kt-sq-dg" title="' + esc(r.noi_dung || r.mo_ta || '') + '">' + esc(r.noi_dung || r.mo_ta || '—') + '</span>' + (r.nhan_vien_ten ? '<span class="kt-khach__ma">' + esc(r.nhan_vien_ten) + '</span>' : r.doi_tuong_ten ? '<span class="kt-khach__ma">' + esc(r.doi_tuong_ten) + '</span>' : r.ma_don ? '<span class="kt-khach__ma">Đơn ' + esc(r.ma_don) + '</span>' : '') },
      { key: 'nguon', nhan: 'Nguồn', ve: (r) => '<span class="kt-tk">' + nhanNguon(r.lien_quan) + '</span>' + (r.ma_dinh_khoan ? nvPill(r) : cfPill(cfDong(r), r.loai)) },
      { key: 'thu', nhan: 'Thu (VND)', num: true, ve: (r) => (r.loai === 'thu' ? '<span class="kt-vao">+' + KD.tien(r.so_tien) + '</span>' : KT.tienSo(0)) },
      { key: 'chi', nhan: 'Chi (VND)', num: true, ve: (r) => (r.loai === 'chi' ? '−' + KD.tien(r.so_tien) : KT.tienSo(0)) },
      { key: 'ton', nhan: 'Tồn quỹ (VND)', num: true, cls: 'kd-strong', ve: (r) => KD.tien(r.ton) },
    ],
    kpi: {
      ton_dau: (d) => ({ v: d.ton_dau == null ? null : H.tienKpi(d.ton_dau), title: d.ton_dau == null ? '' : KD.tienVnd(d.ton_dau), phu: 'Ngày ' + KD.ngay(d.ky.tu) }),
      thu: (d) => ({ v: H.tienKpi(d.tong_thu), title: KD.tienVnd(d.tong_thu), phu: KD.soDem(d.so_phieu_thu) + ' phiếu thu' }),
      chi: (d) => ({ v: H.tienKpi(d.tong_chi), title: KD.tienVnd(d.tong_chi), phu: KD.soDem(d.so_phieu_chi) + ' phiếu chi' }),
      ton_cuoi: (d) => ({ v: d.ton_cuoi == null ? null : H.tienKpi(d.ton_cuoi), title: d.ton_cuoi == null ? '' : KD.tienVnd(d.ton_cuoi), phu: d.ton_cuoi != null && d.ton_cuoi < 0 ? H.pill('danger', 'Quỹ âm — kiểm tra lại phiếu chi') : 'Ngày ' + KD.ngay(d.ky.den) }),
    },
    cong: (d) => (d.co_loc
      ? [{ html: 'Cộng ' + KD.soDem(d.tong_dong) + ' giao dịch đang lọc' + KD.tip('Cả kỳ có ' + KD.soDem(d.so_phieu_thu + d.so_phieu_chi) + ' giao dịch — xem thẻ số phía trên.'), span: 5 }, { html: KD.tien(d.thu_loc), num: true }, { html: KD.tien(d.chi_loc), num: true }, { html: '—', num: true }]
      : [{ html: 'Cộng ' + KD.soDem(d.so_phieu_thu + d.so_phieu_chi) + ' giao dịch trong kỳ', span: 5 }, { html: KD.tien(d.tong_thu), num: true }, { html: KD.tien(d.tong_chi), num: true }, { html: d.ton_cuoi == null ? '' : KD.tien(d.ton_cuoi), num: true }]),
    rong: (d, coLoc) => (coLoc ? ['Không có giao dịch nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc hoặc đổi kỳ.'] : ['Kỳ này chưa có phiếu thu, chi nào', 'Sổ quỹ tự sinh khi ghi Doanh thu / Chi phí / Công nợ qua một trong các quỹ.']),
    loi: 'Không tải được sổ quỹ',
    // Tồn đầu kỳ nạp TRƯỚC khi gọi sổ (bản trước tải sổ → nạp tồn → tải sổ lần 2: mỗi lần đổi kỳ gọi /api/so-quy 2 lần).
    truocTai: (q) => Promise.all([dongBoTon({ tu: q.tu, den: q.den, tk: q.tk }), napBangCf().then(napLocCf), napBangNv()]),
    panel: {
      ve: (r) => H.dauPanel(r.loai === 'thu' ? 'bi-box-arrow-in-down' : 'bi-box-arrow-up', r.loai === 'thu' ? 'success' : 'danger',
        'SQ-' + r.id, KD.ngay(r.ngay) + (r.tai_khoan ? ' · ' + esc(r.tai_khoan) : ''), '')
        + '<p>' + esc(r.noi_dung || r.mo_ta || '(không có diễn giải)') + '</p>'
        + H.kv([
          [r.loai === 'thu' ? 'Số tiền thu' : 'Số tiền chi', KD.tienVnd(r.so_tien), true],
          ['Tồn quỹ luỹ kế sau dòng này', KD.tienVnd(r.ton)],
          ['Nguồn', nhanNguon(r.lien_quan)],
          r.ma_dinh_khoan ? ['Việc', esc(tenNv(r))] : null,
          ['Dòng tiền', dongTienDai(cfDong(r), r.loai)],
          r.doi_tuong_ten ? [DT_LOAI[r.doi_tuong_loai] || 'Đối tượng', esc(r.doi_tuong_ten)] : null,
          r.ky ? ['Kỳ', esc(r.ky)] : null,
          r.ref_id ? ['Mã tham chiếu', esc(r.ref_id)] : null,
          r.nhan_vien_ten ? ['Nhân viên', esc(r.nhan_vien_ten)] : null,
          r.ma_don ? ['Mã đơn liên quan', esc(r.ma_don)] : null,
          r.ghi_chu ? ['Ghi chú', esc(r.ghi_chu)] : null,
          ['Người tạo', esc(r.created_by || '—')],
        ]),
      nut: () => '',
    },
  });

  /* ── Lập phiếu thu / phiếu chi theo NGHIỆP VỤ (01/10/2026, đặc tả spec_phieu_chon_ma_dinh_khoan.md mục 3) ──────────────────
     Ô "Việc gì?" thay ô "Dòng tiền": người lập chọn tiền này là việc gì; máy chủ tự suy dòng tiền B03 (phan_loai_cf) và cặp Nợ/Có
     (app/services/nghiep_vu_so_quy.py — NGUỒN DUY NHẤT, trình duyệt không giữ luật). POST /api/so-quy kèm ma_dinh_khoan; chuyển tiền
     giữa hai quỹ đi POST /api/so-quy/chuyen-noi-bo (ghi cặp hai dòng). Vẫn KHÔNG sinh doanh thu / chi phí / công nợ / bút toán kèm theo.
     Dòng xem trước Nợ/Có ở chân hộp chỉ để nhìn lại, chưa ghi sổ kế toán. Màn cũ /app vẫn gửi phan_loai_cf như trước (API giữ đường cũ). */
  const $ = (id) => document.getElementById(id);
  const dlg = $('sq-dlg');
  const docSo = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const boDau = (s) => String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').toLowerCase();
  // ref_id 'nt-…' sinh lúc mở hộp: bấm Lưu hai lần (mạng chậm) chỉ ra một dòng. randomUUID chỉ có ở kết nối an toàn → dự phòng.
  const taoRef = () => 'nt-' + ((window.crypto && crypto.randomUUID) ? crypto.randomUUID().replace(/-/g, '')
    : Date.now().toString(36) + Math.random().toString(36).slice(2, 14));
  // Ô của từng trường (can_truong) — dùng để focus khi báo lỗi.
  const ID_O = { ma_don: 'sq-f-madon', ncc: 'sq-f-ncc-tim', nhan_vien: 'sq-f-nv', ky: 'sq-f-ky', ly_do: 'sq-f-lydo', quy_doi_ung: 'sq-f-quydu',
    noi_dung: 'sq-f-nd', so_tien: 'sq-f-tien', tai_khoan: 'sq-f-tk' };
  const FW = {};   // khung ô nhập thêm theo trường, khai sẵn trong .sq-kho (ẩn) của template
  dlg.querySelectorAll('.sq-fw').forEach((w) => { FW[w.dataset.truong] = w; });
  const kho = dlg.querySelector('.sq-kho');

  let dmQuy = [], napDm = null;
  function napDanhMuc() {
    napDm = napDm || Promise.all([
      KD.api('/api/tai-khoan?active_only=true').catch(() => []),
      KD.api('/api/external/employees?active=true').then((r) => (r && r.data) || []).catch(() => []),
    ]).then(([tks, nvs]) => {
      dmQuy = tks || [];
      $('sq-f-tk').innerHTML = dmQuy.map((t) => '<option value="' + esc(t.ten_tk) + '">' + esc(t.ten_tk) + (t.loai === 'tien_mat' ? ' (tiền mặt)' : '') + '</option>').join('');
      $('sq-f-nv').innerHTML = '<option value="">— Chọn nhân viên —</option>' + (nvs || []).filter((n) => n.id).map((n) => '<option value="' + n.id + '" data-ten="' + esc(n.ho_ten || '') + '">'
        + esc(n.ho_ten || '') + (n.phong_ban ? ' — ' + esc(n.phong_ban) : '') + (n.chuc_vu ? ' (' + esc(n.chuc_vu) + ')' : '') + '</option>').join('');
      return dmQuy;
    });
    return napDm;
  }
  // Tài khoản tiền của một quỹ: tk_ke_toan (1111, 1121…); chưa gán thì 111 tiền mặt / 112 còn lại — cùng luật với máy chủ.
  const tkQuy = (ten) => { const q = dmQuy.find((t) => t.ten_tk === ten); return q ? (q.tk_ke_toan || (q.loai === 'tien_mat' ? '111' : '112')) : ''; };

  let nvDs = null, nvChon = null, refPhieu = '', xacNhanTrung = false, kyTay = false, nccChon = null, dsNcc = null, nccNap = null;
  const laThu = () => $('sq-f-loai').value === 'thu';
  function datTieuDe() { $('sq-dlg-td').textContent = laThu() ? 'Lập phiếu thu' : 'Lập phiếu chi'; }
  // Nút chọn nhóm Phiếu chi | Phiếu thu: #sq-f-loai (input ẩn) giữ giá trị cho mã đọc; hàm này đồng bộ nút, tiêu đề, chân hộp theo nó.
  function dongBoLoai() {
    const l = $('sq-f-loai').value;
    dlg.querySelectorAll('#sq-f-loai-nut [data-loai]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.loai === l)));
    datTieuDe(); datXem();
  }
  function datNutLuu() {
    const chuyen = !!(nvChon && nvChon.cho_phep !== 'co');
    $('sq-f-luu').disabled = chuyen;   // việc lập ở màn khác: khoá Lưu, thẻ chỉ đường đã nói đi đâu
    $('sq-f-luu-chu').textContent = xacNhanTrung ? 'Vẫn lưu' : 'Lưu phiếu';
  }
  // Chân hộp: chưa chọn việc → dòng tóm tắt cũ ("Chi 1.500.000 VND từ Tiền Mặt"); đã chọn việc lập tay → xem trước Nợ / Có + dòng tiền B03.
  function datXem() {
    const x = nvChon, n = docSo($('sq-f-tien').value), quy = $('sq-f-tk').value, thu = laThu(), co = !!(x && x.cho_phep === 'co' && nvDs);
    const tt = $('sq-tomtat');
    tt.hidden = co || !n;
    tt.textContent = n ? (thu ? 'Thu ' : 'Chi ') + KD.tienVnd(n) + (quy ? (thu ? ' vào ' : ' từ ') + quy : '') : '';
    $('sq-xem').hidden = !co;
    if (!co) return;
    const quyDu = $('sq-f-quydu').value;
    const ve = (tk, ten) => (tk === 'TIEN' ? [tkQuy(quy) || '—', quy || 'Chưa chọn quỹ']
      : tk === 'TIEN_DOI_UNG' ? [tkQuy(quyDu) || '—', quyDu || 'Chưa chọn quỹ đối ứng'] : [tk, ten]);
    const [noTk, noTen] = ve(x.tk_no, x.ten_tk_no), [coTk, coTen] = ve(x.tk_co, x.ten_tk_co), tien = n ? KD.tien(n) : '—';
    $('sq-xem-no-tk').textContent = noTk; $('sq-xem-no-ten').textContent = noTen; $('sq-xem-no-tien').textContent = tien;
    $('sq-xem-co-tk').textContent = coTk; $('sq-xem-co-ten').textContent = coTen; $('sq-xem-co-tien').textContent = tien;
    $('sq-xem-no-ten').title = noTen; $('sq-xem-co-ten').title = coTen;
    $('sq-xem-b03').textContent = (x.b03_ma_so ? 'Báo cáo lưu chuyển tiền tệ: ' + x.b03_ten + ', mã ' + x.b03_ma_so
      : 'Chuyển nội bộ — không tính vào báo cáo lưu chuyển tiền tệ') + ' · theo ' + nvDs.che_do.toUpperCase() + ' · xem trước';
    $('sq-xem').title = 'Xem trước, CHƯA ghi sổ kế toán. Số tài khoản theo ' + nvDs.che_do_ten + ' (Cài đặt kế toán).';
  }
  // Nhóm "Thông tin thêm" (gập): đếm ô đang dùng đã điền → thẻ "Đã điền N ô"; tuBung = true thì bung nhóm nếu đã có ô điền sẵn.
  function datThem(tuBung) {
    const o = [...dlg.querySelectorAll('#sq-them .sq-them__than input:not([type="hidden"]):not([type="checkbox"]), #sq-them .sq-them__than select')];
    const n = o.filter((e) => e.value.trim()).length, d = $('sq-them-dem');
    d.hidden = !n; d.textContent = n ? 'Đã điền ' + n + ' ô' : '';
    if (tuBung && n) $('sq-them').open = true;
  }
  // Báo lỗi một ô: ô nằm trong nhóm đang gập thì bung nhóm trước; rồi viền đỏ + focus + thông báo ở chân hộp.
  function loiO(id, msg) {
    const o = $(id);
    if (o.closest('#sq-them')) $('sq-them').open = true;
    o.setAttribute('aria-invalid', 'true'); o.focus();
    KD.baoLoiHopThoai(dlg, msg);
  }
  function xoaLoi() { const e = dlg.querySelector('.kd-form-err'); if (e) { e.textContent = ''; e.hidden = true; } }
  // Ô nhập thêm theo việc: bắt buộc → ngay dưới ô chọn (#sq-o-chinh); tuỳ chọn → "Thông tin thêm" (#sq-o-phu); còn lại về kho (ẩn).
  function xepO(ct) {
    Object.values(FW).forEach((w) => kho.appendChild(w));
    ct.forEach((t) => {
      const w = FW[t.ten];
      if (!w) return;   // noi_dung có ô riêng
      w.querySelector('.kd-field__req').hidden = !t.bat_buoc;
      (t.bat_buoc ? $('sq-o-chinh') : $('sq-o-phu')).appendChild(w);
    });
  }
  const oDung = (ten) => !!(FW[ten] && FW[ten].parentElement !== kho);
  const kyMacDinh = (kieu) => { const d = new Date(); if (kieu === 'thang_truoc') d.setDate(0); return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0'); };
  function napQuyDu() {
    const e = $('sq-f-quydu'), giu = e.value, chinh = $('sq-f-tk').value;
    e.innerHTML = '<option value="">— Chọn quỹ —</option>' + dmQuy.filter((t) => t.ten_tk !== chinh).map((t) => '<option value="' + esc(t.ten_tk) + '">' + esc(t.ten_tk) + '</option>').join('');
    if (giu && giu !== chinh) e.value = giu;
    $('sq-quydu-nhan').textContent = laThu() ? 'Quỹ chuyển tiền đi' : 'Quỹ nhận tiền';
  }

  // Chọn một việc (ô chọn hoặc nút Hay dùng): thẻ chỉ đường / nhãn chờ xác nhận / cảnh báo mềm / ô nhập thêm / xem trước.
  function chonViec(khoa) {
    const x = khoa && nvDs ? nvDs.nghiep_vu.find((v) => v.khoa === khoa) || null : null;
    nvChon = x; xacNhanTrung = false;
    $('sq-f-viec').value = x ? x.khoa : '';
    $('sq-f-viec').removeAttribute('aria-invalid');
    $('sq-hay').querySelectorAll('[data-viec]').forEach((b) => b.setAttribute('aria-pressed', String(!!x && b.dataset.viec === x.khoa)));
    const chuyen = !!(x && x.cho_phep !== 'co');
    $('sq-viec-cho').hidden = !(x && x.cho_xac_nhan && !chuyen);
    $('sq-chi-duong').hidden = !chuyen;
    if (chuyen && x.man_rieng) {
      $('sq-chi-duong-chu').textContent = 'Việc này lập ở màn ' + x.man_rieng.ten + '. ' + x.man_rieng.ly_do;
      $('sq-chi-duong-nut').href = x.man_rieng.url;
      $('sq-chi-duong-nut').textContent = 'Mở màn ' + x.man_rieng.ten + ' →';
    }
    $('sq-goi-y').hidden = !(x && x.canh_bao && !chuyen);
    $('sq-goi-y').textContent = x && x.canh_bao ? x.canh_bao : '';
    xepO(x && !chuyen ? x.can_truong : []);
    const nd = x && x.can_truong.find((t) => t.ten === 'noi_dung');
    $('sq-nd-sao').hidden = !!x && !(nd && nd.bat_buoc);   // chưa chọn việc: giữ dấu * như cũ
    if (x && x.ky_mac_dinh && !kyTay) $('sq-f-ky').value = kyMacDinh(x.ky_mac_dinh);
    if (oDung('quy_doi_ung')) napQuyDu();
    if (oDung('ncc')) napNcc().catch(() => {});
    capNhatNcc(); datNutLuu(); datXem(); datThem(false);
    xoaLoi();
  }

  // Nạp danh sách việc theo loại phiếu đang chọn; đổi loại phiếu thì ô chọn về trống (tránh sai chiều).
  let luotNv = 0;
  async function napNghiepVu() {
    const l = ++luotNv, e = $('sq-f-viec'), dau = '<option value="">— Chọn việc —</option>';
    e.innerHTML = dau; $('sq-hay').innerHTML = ''; nvDs = null; chonViec('');
    try {
      const d = await KD.api('/api/so-quy/nghiep-vu?loai=' + encodeURIComponent($('sq-f-loai').value));
      if (l !== luotNv) return;   // người dùng đã đổi loại phiếu trong lúc chờ
      nvDs = d;
      e.innerHTML = dau + d.nhom.map((g) => '<optgroup label="' + esc(g.ten) + '">' + d.nghiep_vu.filter((x) => x.nhom === g.ten).map((x) =>
        '<option value="' + esc(x.khoa) + '"' + (x.cho_phep !== 'co' ? ' class="sq-op-mo"' : '') + '>' + esc(x.ten) + (x.cho_phep !== 'co' ? ' (làm ở màn khác)' : '') + '</option>').join('') + '</optgroup>').join('');
      $('sq-hay').innerHTML = d.hay_dung.map((h) => '<button type="button" class="kd-btn kd-btn--sm sq-hay__nut" data-viec="' + esc(h.khoa) + '" aria-pressed="false">' + esc(h.nhan) + '</button>').join('');
      $('sq-f-lydo').innerHTML = '<option value="">— Chọn lý do —</option>' + d.ly_do_hoan.map((r) => '<option value="' + esc(r.ma) + '">' + esc(r.nhan) + '</option>').join('');
      datXem();
    } catch (err) {
      if (l === luotNv) KD.baoLoiHopThoai(dlg, 'Chưa nạp được danh sách việc: ' + err.message + ' Đóng hộp thoại rồi mở lại để thử lại.');
    }
  }

  /* ── Ô tìm (mã đơn, nhà cung cấp): danh sách kết quả ngay dưới ô, tối đa 5 mục, mỗi mục 2 dòng ── */
  function moDs(o, ds, html) { ds.innerHTML = html; ds.hidden = false; o.setAttribute('aria-expanded', 'true'); }
  function dongDs(o, ds) { ds.hidden = true; ds.innerHTML = ''; o.setAttribute('aria-expanded', 'false'); }
  const mucDs = (attr, val, ten, phu) => '<button type="button" class="sq-ds__muc" role="option" ' + attr + '="' + esc(val) + '"><span class="sq-ds__ten">'
    + esc(ten) + '</span><span class="sq-ds__phu">' + phu + '</span></button>';
  const tienVnd = (v) => (v == null || v === '' ? '—' : KD.tienVnd(Number(v)));

  let luotDon = 0;
  async function timDon() {
    const o = $('sq-f-madon'), ds = $('sq-madon-ds'), q = o.value.trim(), l = ++luotDon;
    if (document.activeElement !== o) return;   // đã rời ô (Tab / bấm chỗ khác) trước khi hết 300ms chờ → không bung danh sách nữa
    $('sq-madon-tt').hidden = true;
    if (q.length < 2) return dongDs(o, ds);
    try {
      const d = await KD.api('/api/external/quotes-list?status=approved&q=' + encodeURIComponent(q));
      if (l !== luotDon || document.activeElement !== o) return;
      const r = ((d && d.data) || []).slice(0, 5);
      moDs(o, ds, r.length ? r.map((x) => mucDs('data-ma', x.ma_bg, x.ma_bg, esc(x.customer_name || 'Chưa có tên khách') + (x.tong_don ? ' · ' + esc(tienVnd(x.tong_don)) : ''))).join('')
        : '<p class="sq-ds__rong">Không có báo giá đã duyệt khớp “' + esc(q) + '”.</p>');
    } catch (e) { if (l === luotDon) moDs(o, ds, '<p class="sq-ds__rong">Chưa tìm được báo giá: ' + esc(e.message) + '</p>'); }
  }
  // Mã đơn → tên khách + đã thu / còn lại (GET /api/so-quy/theo-don). Mã chưa có báo giá: chữ đỏ + nút đổi sang "Tiền về chưa rõ".
  let luotTra = 0;
  async function traDon() {
    const m = $('sq-f-madon').value.trim(), tt = $('sq-madon-tt'), l = ++luotTra;
    if (!m) { tt.hidden = true; return; }
    try {
      const d = await KD.api('/api/so-quy/theo-don/' + encodeURIComponent(m));
      if (l !== luotTra) return;
      if (d.doc_duoc_bao_gia && !d.co_bao_gia) {
        tt.className = 'sq-tt sq-tt--loi';
        tt.innerHTML = 'Mã đơn ' + esc(d.ma_don) + ' chưa có báo giá.' + (laThu() && !(nvChon && nvChon.khoa === 'thu_khong_ro') ? ' <button type="button" class="kd-btn kd-btn--sm" data-doi-viec="thu_khong_ro">Đổi sang “Tiền về chưa rõ”</button>' : '');
      } else {
        tt.className = 'sq-tt';
        tt.innerHTML = 'Khách: <b>' + esc(d.khach || '—') + '</b> · Tổng đơn ' + esc(tienVnd(d.tong_don)) + ' · Đã thu ' + esc(tienVnd(d.da_thu))
          + (Number(d.da_hoan) ? ' · Đã hoàn ' + esc(tienVnd(d.da_hoan)) : '') + ' · Còn lại ' + esc(tienVnd(d.con_lai));
      }
      tt.hidden = false;
    } catch (e) { if (l === luotTra) { tt.className = 'sq-tt sq-tt--loi'; tt.textContent = 'Chưa tra được đơn: ' + e.message; tt.hidden = false; } }
  }
  function napNcc() {
    nccNap = nccNap || KD.api('/api/cong-no/ncc-summary?only_outstanding=false').then((d) => { dsNcc = (d && d.items) || []; return dsNcc; })
      .catch((e) => { nccNap = null; throw e; });
    return nccNap;
  }
  async function timNcc() {
    const o = $('sq-f-ncc-tim'), ds = $('sq-ncc-ds'), q = boDau(o.value.trim());
    $('sq-f-ncc').value = ''; nccChon = null; capNhatNcc();
    if (!q) return dongDs(o, ds);
    try { await napNcc(); } catch (e) { return moDs(o, ds, '<p class="sq-ds__rong">Chưa tải được danh sách nhà cung cấp: ' + esc(e.message) + '</p>'); }
    const r = dsNcc.filter((n) => boDau(n.supplier_name).includes(q) || boDau(n.supplier_code).includes(q)).slice(0, 5);
    moDs(o, ds, r.length ? r.map((n) => mucDs('data-ncc', n.supplier_id, n.supplier_name, Number(n.balance) > 0 ? 'Còn nợ thực ' + esc(tienVnd(n.balance)) : 'Không còn nợ thực')).join('')
      : '<p class="sq-ds__rong">Không có nhà cung cấp nào khớp. Nhà cung cấp mới phải thêm ở Mua hàng trước.</p>');
  }
  // Trả trước cho NCC còn nợ thực > 0: nhắc chi ở hộp Ghi nhận trả (công nợ tự giảm); vẫn cho lưu khi đánh dấu là trả trước.
  function capNhatNcc() {
    const tt = $('sq-ncc-tt'), no = nccChon ? Number(nccChon.balance || 0) : 0;
    const canh = !!(nccChon && no > 0 && nvChon && nvChon.khoa === 'tra_ncc_ngoai_cong_no');
    tt.hidden = !nccChon;
    tt.classList.toggle('sq-tt--canh-bao', canh);
    if (nccChon) {
      tt.innerHTML = canh ? 'Nhà cung cấp này còn nợ <b>' + esc(tienVnd(no)) + '</b>. Nếu đã có đề xuất, nên chi từ hộp Ghi nhận trả để công nợ tự giảm. <a href="/ketoan/cong-no-ncc">Mở Công nợ NCC →</a>'
        : (no > 0 ? 'Còn nợ thực ' + esc(tienVnd(no)) + '.' : 'Không còn nợ thực.');
    }
    $('sq-ncc-xn').hidden = !canh;
    if (!canh) $('sq-f-ncc-xn').checked = false;
  }

  async function moPhieu(loai) {
    ['sq-f-tien', 'sq-f-nd', 'sq-f-madon', 'sq-f-gc', 'sq-f-ncc-tim', 'sq-f-ncc', 'sq-f-ky', 'sq-f-lydo', 'sq-f-quydu'].forEach((id) => { $(id).value = ''; });
    $('sq-f-nv').value = ''; $('sq-f-ncc-xn').checked = false;
    ['sq-madon-tt', 'sq-ncc-tt'].forEach((id) => { $(id).hidden = true; });
    dongDs($('sq-f-madon'), $('sq-madon-ds')); dongDs($('sq-f-ncc-tim'), $('sq-ncc-ds'));
    refPhieu = taoRef(); xacNhanTrung = false; kyTay = false; nccChon = null;
    $('sq-f-loai').value = loai; dongBoLoai(); napNghiepVu();
    $('sq-them').open = false; datThem(true);   // nhóm phụ gập lại; ô nào có điền sẵn thì bung
    dlg.querySelectorAll('[aria-invalid]').forEach((o) => o.removeAttribute('aria-invalid'));
    xoaLoi();
    const k = ds.khoang(), hom = KD.iso(new Date());
    $('sq-f-ngay').value = k.den && k.den < hom ? k.den : hom;
    KD.moHopThoai(dlg);
    dlg.querySelector('.kd-dialog__body').scrollTop = 0;   // mở lại luôn bắt đầu từ đầu hộp, không giữ vị trí cuộn của lần trước
    const tks = await napDanhMuc();
    const tm = tks.find((t) => t.loai === 'tien_mat');
    if (tm && !$('sq-f-tk').dataset.daChon) $('sq-f-tk').value = tm.ten_tk;   // Sổ quỹ tiền mặt → mặc định quỹ tiền mặt
    datXem();
    $('sq-f-tien').focus();
  }
  document.querySelectorAll('#kd-kt-so-quy [data-lap]').forEach((b) => b.addEventListener('click', () => moPhieu(b.dataset.lap)));
  // Bấm nút nhóm → ghi vào #sq-f-loai rồi phát "change": một đường duy nhất để đổi loại (đổi tiêu đề, nạp lại danh sách việc).
  $('sq-f-loai-nut').addEventListener('click', (e) => {
    const b = e.target.closest('[data-loai]');
    if (!b || b.dataset.loai === $('sq-f-loai').value) return;
    $('sq-f-loai').value = b.dataset.loai;
    $('sq-f-loai').dispatchEvent(new Event('change'));
  });
  $('sq-f-loai').addEventListener('change', () => { dongBoLoai(); napNghiepVu(); });
  $('sq-f-tk').addEventListener('change', () => { $('sq-f-tk').dataset.daChon = '1'; if (oDung('quy_doi_ung')) napQuyDu(); datXem(); });
  $('sq-f-quydu').addEventListener('change', datXem);
  $('sq-f-tien').addEventListener('input', (e) => { const n = docSo(e.target.value); e.target.value = n ? KD.tien(n) : ''; datXem(); });
  $('sq-f-viec').addEventListener('change', () => chonViec($('sq-f-viec').value));
  $('sq-hay').addEventListener('click', (e) => { const b = e.target.closest('[data-viec]'); if (b) chonViec(b.dataset.viec); });
  dlg.addEventListener('click', (e) => { const b = e.target.closest('[data-doi-viec]'); if (b) { chonViec(b.dataset.doiViec); $('sq-f-viec').focus(); } });
  $('sq-f-ky').addEventListener('input', () => { kyTay = true; });
  // Ô tìm: gõ → danh sách; chọn → điền; bấm ra ngoài / Esc → đóng. Bàn phím điện thoại bật → cuộn ô đang gõ vào giữa.
  const timDonTre = KD.debounce(timDon, 300);
  $('sq-f-madon').addEventListener('input', timDonTre);
  $('sq-f-madon').addEventListener('change', traDon);
  $('sq-f-ncc-tim').addEventListener('input', timNcc);
  ['sq-f-madon', 'sq-f-ncc-tim'].forEach((id) => $(id).addEventListener('focus', (e) => setTimeout(() => e.target.scrollIntoView({ block: 'center' }), 300)));
  $('sq-madon-ds').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ma]'); if (!b) return;
    $('sq-f-madon').value = b.dataset.ma; dongDs($('sq-f-madon'), $('sq-madon-ds')); traDon(); datThem(false);
  });
  $('sq-ncc-ds').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ncc]'); if (!b) return;
    nccChon = (dsNcc || []).find((n) => String(n.supplier_id) === b.dataset.ncc) || null;
    $('sq-f-ncc').value = nccChon ? nccChon.supplier_id : ''; $('sq-f-ncc-tim').value = nccChon ? nccChon.supplier_name : '';
    $('sq-f-ncc-tim').removeAttribute('aria-invalid');
    dongDs($('sq-f-ncc-tim'), $('sq-ncc-ds')); capNhatNcc(); datThem(false);
  });
  dlg.addEventListener('click', (e) => {
    [['sq-f-madon', 'sq-madon-ds'], ['sq-f-ncc-tim', 'sq-ncc-ds']].forEach(([o, d]) => {
      if (!$(d).hidden && !$(d).contains(e.target) && e.target !== $(o)) dongDs($(o), $(d));
    });
  });
  dlg.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const mo = [['sq-f-madon', 'sq-madon-ds'], ['sq-f-ncc-tim', 'sq-ncc-ds']].find(([, d]) => !$(d).hidden);
    if (mo) { e.preventDefault(); e.stopPropagation(); dongDs($(mo[0]), $(mo[1])); $(mo[0]).focus(); }
  });
  // Nhóm vừa bung → cuộn thân hộp cho thấy hết các ô mới (hộp đã cao tối đa thì phần cuối nằm dưới mép).
  $('sq-them').addEventListener('toggle', () => { if ($('sq-them').open) $('sq-them').scrollIntoView({ block: 'nearest' }); });
  // Sửa một ô thì gỡ viền đỏ của nó; ô phụ đổi thì cập nhật số "Đã điền N ô"; đã hiện "Vẫn lưu" mà sửa ô thì về lại "Lưu phiếu".
  ['input', 'change'].forEach((ev) => $('sq-form').addEventListener(ev, (e) => {
    e.target.removeAttribute('aria-invalid');
    if (e.target.closest('#sq-them')) datThem(false);
    if (xacNhanTrung && e.target.id !== 'sq-f-viec') { xacNhanTrung = false; datNutLuu(); }
  }));

  // POST JSON và đọc lỗi CÓ CẤU TRÚC của API ({ma, thong_bao, truong, man_rieng}) — KD.api chỉ đọc chuỗi detail.
  async function guiJson(url, body) {
    let r;
    try {
      r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(body) });
    } catch (e) { return { ok: false, loi: { thong_bao: 'Không kết nối được máy chủ. Kiểm tra mạng rồi bấm Lưu lại.' } }; }
    const d = await r.json().catch(() => null);
    if (r.ok) return { ok: true, status: r.status, data: d };
    let loi = d && d.detail;
    if (!loi && d && d.error === 'validation_failed') loi = 'Dữ liệu gửi lên có ô sai định dạng — kiểm tra lại các ô vừa nhập.';
    if (Array.isArray(loi)) loi = loi.map((x) => x.msg).join('; ');
    if (typeof loi === 'string') loi = { thong_bao: loi };
    if (r.status === 401) loi = { thong_bao: 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.' };
    return { ok: false, status: r.status, loi: loi && loi.thong_bao ? loi : { thong_bao: 'Máy chủ trả lỗi ' + r.status + '. Thử lại sau ít phút.' } };
  }

  $('sq-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const x = nvChon, v = (id) => $(id).value.trim() || null, so_tien = docSo($('sq-f-tien').value);
    // Kiểm theo đúng thứ tự trên hộp (tiền → ngày → quỹ → việc → ô nhập thêm → nội dung) để lỗi đầu tiên luôn là ô trên cùng còn thiếu.
    if (!so_tien) return loiO('sq-f-tien', 'Nhập số tiền lớn hơn 0.');
    if (!$('sq-f-ngay').value) return loiO('sq-f-ngay', 'Chọn ngày.');
    if (!$('sq-f-tk').value) return loiO('sq-f-tk', 'Chọn tài khoản / quỹ.');
    if (!x) return loiO('sq-f-viec', 'Chọn việc gì cho phiếu này (ví dụ Trả nhà cung cấp, Trả lương): chạm một nút phía trên hoặc mở ô “Việc gì?”.');
    if (x.cho_phep !== 'co') return loiO('sq-f-viec', 'Việc này lập ở màn ' + (x.man_rieng ? x.man_rieng.ten : 'khác') + ' — bấm nút Mở màn trong thẻ chỉ đường.');
    const giaTri = { ma_don: v('sq-f-madon'), ncc: v('sq-f-ncc'), nhan_vien: v('sq-f-nv'), ky: v('sq-f-ky'), ly_do: v('sq-f-lydo'), quy_doi_ung: v('sq-f-quydu'), noi_dung: v('sq-f-nd') };
    const thieu = x.can_truong.find((t) => t.bat_buoc && !giaTri[t.ten]);
    if (thieu) return loiO(ID_O[thieu.ten], (thieu.ten === 'ncc' ? 'Chọn nhà cung cấp trong danh sách' : thieu.ten === 'nhan_vien' || thieu.ten === 'ly_do' || thieu.ten === 'quy_doi_ung' ? 'Chọn ' + thieu.nhan.toLowerCase() : 'Nhập ' + thieu.nhan.toLowerCase()) + ' cho việc “' + x.ten + '”.');
    if (!$('sq-ncc-xn').hidden && !$('sq-f-ncc-xn').checked) return loiO('sq-f-ncc-xn', 'Nhà cung cấp này còn nợ. Đánh dấu “Đây là khoản trả trước / ngoài công nợ”, hoặc chi từ hộp Ghi nhận trả ở Công nợ NCC.');
    const nut = $('sq-f-luu'); nut.disabled = true;
    let url = '/api/so-quy', body;
    if (x.khoa === 'chuyen_noi_bo') {
      const chinh = $('sq-f-tk').value, du = giaTri.quy_doi_ung, thu = laThu();
      url = '/api/so-quy/chuyen-noi-bo';
      body = { ngay: $('sq-f-ngay').value, tu_tai_khoan: thu ? du : chinh, den_tai_khoan: thu ? chinh : du, so_tien, noi_dung: giaTri.noi_dung, ghi_chu: v('sq-f-gc'), ref_id: refPhieu };
    } else {
      const nvO = $('sq-f-nv').selectedOptions[0];
      body = { ngay: $('sq-f-ngay').value, loai: $('sq-f-loai').value, tai_khoan: $('sq-f-tk').value, so_tien, noi_dung: giaTri.noi_dung,
        ghi_chu: v('sq-f-gc'), ma_dinh_khoan: x.khoa, ref_id: refPhieu };
      if (oDung('ma_don') && giaTri.ma_don) body.ma_don = giaTri.ma_don;
      if (oDung('ncc') && giaTri.ncc) Object.assign(body, { doi_tuong_loai: 'ncc', doi_tuong_ma: giaTri.ncc, doi_tuong_ten: nccChon ? nccChon.supplier_name : null });
      if (oDung('nhan_vien') && giaTri.nhan_vien) Object.assign(body, { nhan_vien_id: +giaTri.nhan_vien, nhan_vien_ten: (nvO && nvO.dataset.ten) || null });
      if (oDung('ky') && giaTri.ky) body.ky = giaTri.ky;
      if (oDung('ly_do') && giaTri.ly_do) body.ly_do = giaTri.ly_do;
      if (xacNhanTrung) body.xac_nhan_trung = true;
    }
    try {
      const r = await guiJson(url, body);
      if (r.ok) {
        dlg.close();
        const ma = r.data.entries ? r.data.entries.map((x2) => 'SQ-' + x2.id).join(' / ') : 'SQ-' + r.data.id;
        window.showToast && window.showToast('ok', 'Đã ghi ' + (x.khoa === 'chuyen_noi_bo' ? 'chuyển nội bộ ' : laThu() ? 'phiếu thu ' : 'phiếu chi ') + ma + ' — ' + KD.tienVnd(so_tien));
        tonState.key = null;   // phiếu lùi ngày trước kỳ làm đổi tồn đầu kỳ
        ds.tai();
        return;
      }
      const l = r.loi;
      // Nghi trùng: hiện lời nhắc, nút đổi thành "Vẫn lưu" — bấm lần nữa mới gửi kèm xac_nhan_trung.
      if (l.ma === 'nghi_trung') { xacNhanTrung = true; return KD.baoLoiHopThoai(dlg, l.thong_bao); }
      // Lỗi gắn với một ô (truong) → viền đỏ + focus ô đó; ô không đang hiện thì báo ở chân hộp.
      const t = (l.truong || []).find((k) => ID_O[k] && (!FW[k] || oDung(k)));
      if (t) return loiO(ID_O[t], l.thong_bao);
      KD.baoLoiHopThoai(dlg, 'Chưa ghi được: ' + l.thong_bao);
    } finally { datNutLuu(); }
  });
  // Mở thẳng hộp thoại khi tới từ nút "Lập phiếu thu/chi" ở màn khác: /ketoan/so-quy?lap=thu|chi
  const lap = new URLSearchParams(location.search).get('lap');
  if (lap === 'thu' || lap === 'chi') {
    const u = new URL(location.href); u.searchParams.delete('lap'); history.replaceState(null, '', u); delete ds.st.lap;
    moPhieu(lap);
  }

  ds.tai();
})();
