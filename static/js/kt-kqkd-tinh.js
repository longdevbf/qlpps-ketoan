/* kt-kqkd-tinh.js — cách DỰNG SỐ Kết quả kinh doanh (B02) dùng chung cho màn /ketoan/bao-cao/kqkd (kt-kqkd.js)
   và trang in /ketoan/in?mau=kqkd (kt-in.js) — 1 chỗ tính duy nhất để số in = số trên màn.
   Nguồn: GET /api/bao-cao/pl?thang=YYYY-MM (services/pl_calculator — P&L chuẩn, chỉ nhận 1 tháng).
   - Kỳ [tu, den] → mọi tháng giao với kỳ; kỳ trước = cùng số tháng liền trước.
   - Cộng dồn mọi lá số của các tháng; kỳ > 1 tháng thì thuế TNDN tính lại trên LNTT cả kỳ
     (tháng lỗ bù tháng lãi) — cùng quy tắc /api/bao-cao/pl/yearly.
   Cần KD (kd-man-hinh.js) + KT.url (kt-chung.js). */
(function () {
  'use strict';
  const THUE_SUAT_TNDN = 0.2;   // thuế suất TNDN phổ thông — trùng TAX_RATE_TNDN của pl_calculator.py

  const ym = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  function cacThang(tu, den) {
    const a = new Date(tu + 'T00:00:00'), b = new Date(den + 'T00:00:00'), ds = [];
    for (let d = new Date(a.getFullYear(), a.getMonth(), 1); d <= b; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) ds.push(ym(d));
    return ds.length ? ds : [ym(b)];
  }
  /* Các tháng của kỳ so sánh: mặc định cùng số tháng LIỀN TRƯỚC; lui = số tháng lùi (12 = cùng kỳ năm trước,
     theo KT.kySoSanh — "Năm nay" 01–09/2026 so với 01–09/2025, không phải 04–12/2025). */
  function thangTruoc(ds, lui) {
    const [y, m] = ds[0].split('-').map(Number), n = lui || ds.length, out = [];
    for (let i = 0; i < ds.length; i++) out.push(ym(new Date(y, m - 1 - n + i, 1)));
    return out;
  }
  function cong(a, b) {
    if (typeof b === 'number') return (typeof a === 'number' ? a : 0) + b;
    if (b && typeof b === 'object' && !Array.isArray(b)) { const o = Object.assign({}, a && typeof a === 'object' ? a : {});
      Object.keys(b).forEach((k) => { o[k] = cong(o[k], b[k]); }); return o; }
    return b;
  }
  /* Chia `tong` (số nguyên) theo tỉ lệ các phần lẻ — phần dư dồn cho phần lẻ lớn nhất (largest remainder),
     để các dòng con làm tròn vẫn cộng ĐÚNG bằng dòng cha hiển thị. */
  function chiaTron(obj, tong) {
    const ks = Object.keys(obj || {}); if (!ks.length) return obj;
    const o = {}; ks.forEach((k) => { o[k] = Math.floor(obj[k] || 0); });
    let du = tong - ks.reduce((a, k) => a + o[k], 0);
    ks.slice().sort((a, b) => ((obj[b] || 0) - Math.floor(obj[b] || 0)) - ((obj[a] || 0) - Math.floor(obj[a] || 0)))
      .forEach((k) => { if (du > 0) { o[k] += 1; du -= 1; } });
    if (du) o[ks[0]] += du;
    return o;
  }
  const tongLa = (o, ks) => ks.reduce((a, k) => a + (o[k] = Math.round(o[k] || 0)), 0);
  /* Tiền VND là số nguyên: làm tròn mọi LÁ rồi CỘNG LẠI các dòng tổng từ chính số đã làm tròn
     → mọi phép trừ trên bảng B02 (10=01−02, 20=10−11, 30=20+21−22−25−26, 50=30+40, 60=50−51) đúng
     trên số hiển thị, không lệch 1đ do làm tròn từng dòng riêng. */
  function chuanHoa(t, tinhThue) {
    const dt = t.doanh_thu, bh = t.cp_ban_hang, ql = t.cp_quan_ly, tc = t.cp_tai_chinh;
    tongLa(dt, ['dt_thuc_hien', 'chiet_khau', 'giam_tru']);
    t.dt_thuan = dt.dt_thuan = dt.dt_thuc_hien - dt.chiet_khau - dt.giam_tru;
    t.cogs = Math.round(t.cogs || 0); t.ln_gop = t.dt_thuan - t.cogs;
    t.dt_tai_chinh = Math.round(t.dt_tai_chinh || 0);
    tc.tong = tongLa(tc, ['lai_vay', 'phi_nh', 'khac']);
    bh.bien_phi.tong = tongLa(bh.bien_phi, ['hoa_hong', 'luong_ot', 'ads', 'van_chuyen', 'khuyen_mai', 'khac']);
    if (bh.bien_phi.ads_by_nhom) bh.bien_phi.ads_by_nhom = chiaTron(bh.bien_phi.ads_by_nhom, bh.bien_phi.ads);
    bh.dinh_phi.tong = tongLa(bh.dinh_phi, ['luong_co_ban_kd_mkt', 'thue_showroom', 'khau_hao_tscd_bh', 'phi_thuong_xuyen']);
    bh.tong = bh.bien_phi.tong + bh.dinh_phi.tong;
    ql.bien_phi.tong = tongLa(ql.bien_phi, ['vpp', 'dao_tao', 'hoi_hop_cong_tac', 'qua_bieu', 'khac']);
    ql.dinh_phi.tong = tongLa(ql.dinh_phi, ['luong_co_ban_hcns_kt_ceo', 'thue_vp', 'dien_nuoc_vp', 'internet_dien_thoai', 'khau_hao_tscd_ql', 'dich_vu_kt_luat', 'phi_khac']);
    ql.tong = ql.bien_phi.tong + ql.dinh_phi.tong;
    t.ln_thuan_hdkd = t.ln_gop + t.dt_tai_chinh - tc.tong - bh.tong - ql.tong;
    t.thu_nhap_khac = Math.round(t.thu_nhap_khac || 0); t.cp_khac = Math.round(t.cp_khac || 0);
    t.ln_truoc_thue = t.ln_thuan_hdkd + t.thu_nhap_khac - t.cp_khac;
    t.thue_tndn = tinhThue ? (t.ln_truoc_thue > 0 ? Math.round(t.ln_truoc_thue * THUE_SUAT_TNDN) : 0) : Math.round(t.thue_tndn || 0);
    t.lnst = t.ln_truoc_thue - t.thue_tndn;
    return t;
  }
  function gop(ds) {
    const t = ds.reduce((a, x) => cong(a, x), {});
    if (!t.doanh_thu) return t;
    return chuanHoa(t, ds.length > 1);   // kỳ nhiều tháng: thuế TNDN tính lại trên LNTT cả kỳ
  }
  /* Kế hoạch gọi API cho kỳ: { nay, truoc, urls } */
  function ke(tu, den, lui) {
    const nay = cacThang(tu, den), truoc = thangTruoc(nay, lui);
    return { nay, truoc, urls: nay.concat(truoc).map((t) => '/api/bao-cao/pl?' + KT.url.qs({ thang: t })) };
  }
  /* Kết quả các lần gọi (cùng thứ tự urls) → { c: kỳ này, p: kỳ trước, ky, thang, thang_truoc } */
  function tach(ds, k) {
    const n = k.nay.length;
    return { c: gop(ds.slice(0, n)), p: gop(ds.slice(n)), ky: { tu: ds[0].tu_ngay, den: ds[n - 1].den_ngay }, thang: k.nay, thang_truoc: k.truoc };
  }
  async function tai(tu, den, lui) { const k = ke(tu, den, lui); return tach(await Promise.all(k.urls.map((u) => KD.api(u))), k); }

  window.KT = Object.assign(window.KT || {}, { kqkd: { THUE_SUAT_TNDN, cacThang, thangTruoc, gop, ke, tach, tai } });
})();
