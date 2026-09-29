/* ═══════════════════════════════════════════════════════════════════════════
   kt-cong-no.js — Công nợ Tổng hợp, DÙNG CHUNG cho 2 màn (chọn theo data-ben trên <main>):
     · data-ben="kh"  → Công nợ khách hàng    · GET /api/bao-cao/cong-no       · TK 131
     · data-ben="ncc" → Công nợ nhà cung cấp  · GET /api/cong-no/ncc-module    · TK 331
   Tham số chung: ?tim&tinh_trang&nv&den_ngay&page&size&sort. Chữ khác nhau giữa 2 bên nằm trong CFG bên dưới.

   ĐỢT 2 — ghi chú riêng bên NCC (data-ben="ncc"):
   Backend KHÔNG có endpoint tổng hợp công nợ NCC đúng hình dạng /api/bao-cao/cong-no-ncc mà bản
   thiết kế README mục 4.6 mô tả. Router thật `app/routers/cong_no_ncc.py` (prefix /api/cong-no) có
   3 API khác nhau (ncc-summary + ncc/<id>/detail đọc từ muahang.suppliers bằng id số thật,
   ncc-module đọc từ ketoan.cong_no gộp theo TÊN đối tác kèm sẵn danh sách đơn nợ `don_list`).
   Màn này dùng `ncc-module` (giàu dữ liệu nhất, có sẵn danh sách hoá đơn nên KHÔNG cần gọi thêm
   API "chi tiết" riêng) và tự CHUYỂN HÌNH DẠNG dữ liệu thật sang đúng khung `dong[].khach{}` mà
   phần lõi bên dưới (KHÔNG SỬA) cần, qua 3 điểm mở rộng CFG (không có ở bản KH, không đổi hành vi
   bên KH): `CFG.chuyen(raw, q)` (sau khi tải danh sách), `CFG.chiTietTuDanhSach(id)` (panel/hàng mở
   rộng dùng lại `don_list` đã tải sẵn — khỏi gọi thêm API chi tiết vì ncc-module không có endpoint
   .../<id>), `CFG.xuatChuaCo` (khoá nút Xuất Excel — chưa có endpoint xuất cho ncc-module).
   Vì ncc-module trả HẾT một lần (không hỗ trợ page/size/sort/tinh_trang phía máy chủ, và tham số
   filter của nó là theo TRẠNG THÁI ĐƠN HÀNG chứ không phải tuổi nợ), toàn bộ lọc/sắp/phân trang/
   tuổi nợ của bên NCC được tính LẠI Ở TRÌNH DUYỆT trong `chuyenNCC()` từ dữ liệu thật (han_thanh_toan,
   con_lai của từng đơn trong don_list) — không có số nào bịa. "Đối tác" bên NCC không có id số thật
   (ncc-module gộp theo tên) nên khách.id = TÊN hiển thị của nhóm (2026-09-25; trước là "nccN") —
   kt-doi-tuong.js tra lại nhóm theo tên. Liên kết "Hồ sơ nhà cung cấp (Mua hàng)" / "Lập phiếu chi"
   ở menu dòng vẫn KHÔNG trỏ đúng hồ sơ NCC thật (cần backend thêm supplier_id vào ncc-module).
   Bộ lọc riêng NCC gửi thẳng lên ncc-module: filter (Nhóm đơn), thang, tu_ngay, den_ngay (theo
   ngày phát sinh cn.ngay) — đúng các bộ lọc của màn cũ /app#cong-no-ncc.
   ═══════════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const trang = document.querySelector('main[data-ben]');
  if (!trang) return;
  const BEN = trang.dataset.ben;

  /* ── Ghép dữ liệu thật của ncc-module vào khung dùng chung (chỉ dùng ở CFG.ncc) ── */
  function parseNgayLinhHoat(s) {
    if (!s) return null;
    s = String(s).trim();
    let m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return new Date(+m[1], +m[2] - 1, +m[3]);
    m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/); // han_thanh_toan là TEXT tự do, đôi khi ghi DD/MM/YYYY
    if (m) return new Date(+m[3], +m[2] - 1, +m[1]);
    return null;
  }
  /* Tổng RÒNG trên MỌI đối tượng (không theo bộ lọc tình trạng) — đúng con số "Còn Nợ" màn cũ hiện
     (màn cũ cộng cả đối tượng trả thừa, con_lai âm). Bộ lọc mặc định "Còn nợ" của màn mới chỉ cộng
     đối tượng con_lai > 0 nên cao hơn đúng bằng phần trả thừa — hiện cả hai để đối chiếu được. */
  function tongRong(ds) {
    return ds.reduce((a, r) => ({
      con_lai: a.con_lai + r.con_lai, so: a.so + 1,
      tra_thua: a.tra_thua + (r.con_lai < 0 ? r.con_lai : 0), so_tra_thua: a.so_tra_thua + (r.con_lai < 0 ? 1 : 0),
    }), { con_lai: 0, so: 0, tra_thua: 0, so_tra_thua: 0 });
  }
  /* Ô tìm "Tên … hoặc mã đơn": khớp tên đối tượng HOẶC mã đơn/mã công nợ của bất kỳ khoản nào
     (màn cũ gửi q= lên /api/cong-no — ilike cả doi_tac lẫn ma_don). Trước chỉ khớp tên. */
  function khopTim(ten, ds, s) {   // không phân biệt dấu + hoa/thường (KT.khopTim)
    if (KT.khopTim(ten, s)) return true;
    return (ds || []).some((p) => KT.khopTim(p.ma_don, s) || KT.khopTim(p.id, s));
  }
  /* Sắp xếp theo ?sort=<cột>_<asc|desc>. Tên so theo tiếng Việt, không phân biệt hoa/thường
     (trước dùng `<` thô → "anh Nam", "chị Thu"… chữ thường bị dồn xuống cuối, sau mọi tên viết hoa). */
  function sapXep(ds, sort) {
    const m = /^(.+)_(asc|desc)$/.exec(sort || 'con_lai_desc') || [null, 'con_lai', 'desc'];
    const cot = m[1], dau = m[2] === 'asc' ? 1 : -1;
    return ds.slice().sort((a, b) => dau * (cot === 'ten'
      ? String(a.khach.ten).localeCompare(String(b.khach.ten), 'vi', { sensitivity: 'base', numeric: true })
      : (Number(a[cot]) || 0) - (Number(b[cot]) || 0)));
  }
  let _rawByKey = {};
  function chuyenNCC(raw, q) {
    const denNgay = q.den_ngay || KD.iso(new Date());
    const homNay = new Date(denNgay + 'T00:00:00');
    const ngayCon = (d) => Math.round((d - homNay) / 86400000);

    _rawByKey = {};
    const mapped = (raw.items || []).map((it, i) => {
      // BUG FIX 2026-09-25: id trước là chỉ số 'ncc'+i → link "Sổ chi tiết" sang /ketoan/doi-tuong
      // gọi /api/cong-no/ncc/ncc0/detail (cần id số muahang.suppliers) → 422, trang trắng.
      // Dùng tên hiển thị (ncc-module đã gộp theo tên chuẩn hoá nên duy nhất trong một lần tải);
      // kt-doi-tuong.js tra lại đúng nhóm này trong ncc-module theo tên.
      const id = it.doi_tac || ('ncc' + i);
      const donConNo = (it.don_list || []).filter((p) => (p.con_lai || 0) > 0);
      let quaHan = 0, denHan7 = 0, maxQuaHanNgay = 0;
      donConNo.forEach((p) => {
        const han = parseNgayLinhHoat(p.han_thanh_toan);
        if (!han) return;
        const soNgay = ngayCon(han);
        if (soNgay < 0) { quaHan += Number(p.con_lai) || 0; maxQuaHanNgay = Math.max(maxQuaHanNgay, -soNgay); }
        else if (soNgay <= 7) { denHan7 += Number(p.con_lai) || 0; }
      });
      let nhomTuoi = 'chua_den_han';
      if (!donConNo.length) nhomTuoi = 'da_thu_du';
      else if (maxQuaHanNgay > 60) nhomTuoi = 'qh_tren_60';
      else if (maxQuaHanNgay > 30) nhomTuoi = 'qh_31_60';
      else if (maxQuaHanNgay > 0) nhomTuoi = 'qh_1_30';
      const r = {
        khach: { id, ma: '', ten: it.doi_tac || '(Chưa rõ NCC)', sdt: '', nv_kd: '' },
        so_phieu: donConNo.length, tong_no: Number(it.tong_no) || 0, da_thu: Number(it.da_tra) || 0,
        con_lai: Number(it.con_lai) || 0, qua_han: quaHan, den_han_7_ngay: denHan7,
        tuoi_no_max_ngay: maxQuaHanNgay, nhom_tuoi: nhomTuoi,
        // 2 nhóm của màn cũ (/app#cong-no-ncc): Nợ thực (đơn xong + nhập tay) / Dự kiến (còn gắn đơn chưa xong).
        no_thuc: Number(it.no_thuc_phai_tra) || 0, no_du_kien: Number(it.no_du_kien) || 0,
        so_don_tat_ca: it.so_don || 0, so_don_thuc: it.so_don_thuc || 0, so_don_nhap_tay: it.so_don_nhap_tay || 0, so_don_du_kien: it.so_don_du_kien || 0,
      };
      _rawByKey[id] = { r, don_list: it.don_list || [] };
      return r;
    });
    const tatCa = tongRong(mapped);

    const tt = q.tinh_trang || 'con_no';
    let ds = mapped;
    if (tt === 'con_no') ds = ds.filter((r) => r.con_lai > 0);
    else if (tt === 'qua_han') ds = ds.filter((r) => r.qua_han > 0);
    else if (tt === 'chua_den_han') ds = ds.filter((r) => r.con_lai > 0 && !r.qua_han);
    else if (tt === 'qh_1_30' || tt === 'qh_31_60' || tt === 'qh_tren_60') ds = ds.filter((r) => r.nhom_tuoi === tt);
    else if (tt === 'da_thu_du') ds = ds.filter((r) => r.con_lai <= 0);
    // 'tat_ca' → không lọc

    if (q.tim) { const s = String(q.tim).trim(); ds = ds.filter((r) => khopTim(r.khach.ten, _rawByKey[r.khach.id].don_list, s)); }

    ds = sapXep(ds, q.sort);

    const tong = ds.reduce((a, r) => ({
      tong_no: a.tong_no + r.tong_no, da_thu: a.da_thu + r.da_thu, con_lai: a.con_lai + r.con_lai,
      qua_han: a.qua_han + r.qua_han, den_han_7_ngay: a.den_han_7_ngay + r.den_han_7_ngay,
      no_thuc: a.no_thuc + r.no_thuc, no_du_kien: a.no_du_kien + r.no_du_kien,
      so_khach_con_no: a.so_khach_con_no + (r.con_lai > 0 ? 1 : 0), so_khach_qua_han: a.so_khach_qua_han + (r.qua_han > 0 ? 1 : 0),
    }), { tong_no: 0, da_thu: 0, con_lai: 0, qua_han: 0, den_han_7_ngay: 0, no_thuc: 0, no_du_kien: 0, so_khach_con_no: 0, so_khach_qua_han: 0 });

    const page = Math.max(1, +q.page || 1), size = Math.max(1, +q.size || 10);
    const soTrang = Math.max(1, Math.ceil(ds.length / size)), trangHopLe = Math.min(page, soTrang);
    return {
      den_ngay: denNgay, nhan_vien: [], tong, tat_ca: tatCa,
      trang: trangHopLe, so_trang: soTrang, tong_dong: ds.length,
      dong: ds.slice((trangHopLe - 1) * size, trangHopLe * size),
    };
  }
  function chiTietTuDanhSachNCC(id) {
    const x = _rawByKey[id];
    if (!x) return Promise.reject(new Error('Không tìm thấy công nợ của nhà cung cấp này trong danh sách vừa tải — thử tải lại trang.'));
    const homNay = new Date(ngayTinh() + 'T00:00:00');   // cùng mốc "Tính đến ngày" với dòng danh sách
    const phieu = x.don_list.map((p) => {
      const conLai = Number(p.con_lai) || 0, daTra = Number(p.da_tra) || 0, tong = Number(p.so_tien) || 0;
      let trangThai = conLai <= 0 ? 'da_thu_du' : (daTra > 0 ? 'thu_mot_phan' : 'chua_thu'); let quaHanNgay = 0;
      const han = parseNgayLinhHoat(p.han_thanh_toan);
      if (conLai > 0 && han && han < homNay) { trangThai = 'qua_han'; quaHanNgay = Math.round((homNay - han) / 86400000); }
      return {
        id: p.id, so_phieu: p.ma_don || ('#' + p.id), don_hang: p.ma_don || '',
        ngay: p.ngay, han_tt: p.han_thanh_toan, tong, da_thu: daTra, con_lai: conLai,
        trang_thai: trangThai, qua_han_ngay: quaHanNgay,
        // Cột của bảng con màn cũ: khách của đơn, nhóm (Phải trả/Dự kiến), ngày thanh toán.
        khach_don: p.customer_name || '', nhom: p.nhom || '', tien_trinh: p.tien_trinh_mh || '',
        ngay_tra: p.ngay_tra || '', ghi_chu: p.ghi_chu || '', ma_cn: p.id,
      };
    });
    // ncc-module không có sổ giao dịch trả tách dòng — như bên KH, suy từ mỗi đơn có da_tra > 0
    // (số đã trả luỹ kế + ngay_tra của đơn đó; màn cũ cũng chỉ hiện đúng 2 giá trị này).
    const lichSu = x.don_list.filter((p) => Number(p.da_tra) > 0)
      .map((p) => ({ ngay: p.ngay_tra || p.ngay, so_ct: p.ma_don || p.id, so_tien: Number(p.da_tra) || 0, hinh_thuc: p.ngay_tra ? 'Ngày thanh toán' : 'Chưa ghi ngày trả' }))
      .sort((a, b) => (a.ngay < b.ngay ? 1 : -1));
    return Promise.resolve({
      khach: x.r.khach, tong_no: x.r.tong_no, da_thu: x.r.da_thu, con_lai: x.r.con_lai,
      qua_han: x.r.qua_han, nhom_tuoi: x.r.nhom_tuoi, phieu,
      no_thuc: x.r.no_thuc, no_du_kien: x.r.no_du_kien,
      so_don: { thuc: x.r.so_don_thuc, nhap_tay: x.r.so_don_nhap_tay, du_kien: x.r.so_don_du_kien },
      lich_su_thu: lichSu,
    });
  }

  /* ── ĐỢT 1 — ghi chú riêng bên KH (data-ben="kh"), cùng khuôn mẫu 3-điểm-mở-rộng như NCC ở trên ──
     README mục 4.3 giả định /api/bao-cao/cong-no đã gộp sẵn theo khách + hoá đơn + lịch sử thu.
     Endpoint đó (bao_cao.py) thật ra CHỈ gộp theo doi_tac trong một khoảng ngày PHÁT SINH (không
     tách kh/ncc, không có hoá đơn con) — không đúng hình dạng màn cần. Nguồn thật dùng ở đây là
     GET /api/cong-no (app/routers/cong_no.py) — danh sách PHẲNG mọi khoản phải thu/phải trả
     (CongNoOut). `CFG.thamSoCoDinh = {loai:'phai_thu', limit:2000, offset:0}` được lõi dùng chung
     gộp thêm vào query khi gọi API (xem điểm mở rộng thứ 4 ở hàm tai() bên dưới — NCC không khai
     nên không đổi hành vi NCC); `chuyenKH` tự lọc phòng khi backend vẫn trả cả phai_tra, rồi GỘP
     theo `doi_tac` (CongNo không có id/mã khách riêng nên doi_tac dùng luôn làm "mã"), tính tuổi nợ/
     quá hạn ở trình duyệt. "Lịch sử thu" suy từ mỗi hoá đơn có da_tra>0 (CongNo không có sổ giao
     dịch thu tách dòng) — gần đúng, không phải nhật ký từng lần thu. Không có bảng khách hàng thật
     nên không có SĐT/NV Kinh Doanh (nhan_vien luôn rỗng, giống hệt hạn chế của nhánh NCC ở trên). */
  let _rawByKeyKH = {};
  const NGUON_THU_HO = 'saleadmin_vc_phai_thu';
  let _thuHoKH = { so: 0, con_lai: 0 };
  /* Hạn thu KH: ketoan.cong_no phải thu KHÔNG có han_thanh_toan (0/65 khoản) → như Dashboard cũ và
     màn Tổng quan (kt-tong-quan.js hanThu): hạn = ngày phát sinh + 30 ngày. Trước đây màn này coi
     "không có hạn" = "chưa đến hạn" → Quá hạn luôn 0, lệch Tổng quan (40 khoản quá 30 ngày). */
  const HAN_NO_MAC_DINH = 30;
  function hanThuKH(r) {
    if (r.han_thanh_toan) return { iso: String(r.han_thanh_toan).slice(0, 10), mac_dinh: false };
    if (!r.ngay) return null;
    const d = new Date(String(r.ngay).slice(0, 10) + 'T00:00:00'); d.setDate(d.getDate() + HAN_NO_MAC_DINH);
    return { iso: KD.iso(d), mac_dinh: true };
  }
  function conLaiCuaKH(r) { return Number(r.con_lai != null ? r.con_lai : (r.so_tien - r.da_tra)) || 0; }
  function chuyenKH(raw, q) {
    const denNgay = q.den_ngay || KD.iso(new Date());
    const homNay = new Date(denNgay + 'T00:00:00');

    _rawByKeyKH = {};
    const theo = {};
    // BUG FIX 2026-09-25: loại dòng "thu hộ KH qua ĐVVC" (ref_source saleadmin_vc_phai_thu) giống
    // hệt màn cũ tab "KH / Phải thu" (index.html loadCongNo: "SA tự quản lý, KT không cần theo dõi").
    // Các dòng này ĐẾM TRÙNG khoản phải thu của chính đơn báo giá — vd Anh Tùng NV26010-26-00010 có
    // cả CN-2026-0022 (baogia_quote, còn 11tr) lẫn CN-2026-0057 (thu hộ, còn 11tr) cho cùng một đơn.
    // Trước đây màn mới cộng cả hai → "Còn phải thu" cao hơn thật 25.834.399đ (4 dòng).
    const phaiThu = raw.filter((r) => r.loai === 'phai_thu');
    const dsThuHo = phaiThu.filter((r) => r.ref_source === NGUON_THU_HO);
    _thuHoKH = { so: dsThuHo.length, con_lai: dsThuHo.reduce((a, r) => a + conLaiCuaKH(r), 0) };
    phaiThu.filter((r) => r.ref_source !== NGUON_THU_HO).forEach((r) => {
      const ten = r.doi_tac || '(Chưa rõ khách)';
      (theo[ten] = theo[ten] || []).push(r);
    });
    let mapped = Object.keys(theo).map((ten) => {
      // BUG FIX 2026-09-25: id trước là chỉ số 'kh'+i — kt-doi-tuong.js (Chi tiết đối tượng)
      // lại đọc ?id= làm chính tên đối tác (doi_tac), vì CongNo không có id khách hàng thật.
      // Link "Sổ chi tiết"/"Hồ sơ khách" từ danh sách này trỏ sang trang trống/sai khách.
      // Dùng thẳng tên (đã là khoá gộp theo khách ở theo[ten] nên vốn đã duy nhất trong trang).
      const id = ten, ds = theo[ten];
      const tong_no = ds.reduce((a, r) => a + (Number(r.so_tien) || 0), 0);
      const da_thu = ds.reduce((a, r) => a + (Number(r.da_tra) || 0), 0);
      // BUG FIX 2026-09-25: trước đây clamp Math.max(0, ...) TỪNG hoá đơn rồi mới cộng dồn theo
      // khách — nếu 1 khách có cả hoá đơn còn nợ VÀ hoá đơn lỡ trả dư (con_lai âm, vd đặt cọc dư),
      // phần trả dư bị clamp về 0 thay vì bù trừ, làm "Còn phải thu" của khách đó CAO hơn thực tế
      // và phá vỡ đẳng thức "Tổng nợ = Đã thu + Còn phải thu" ghi ngay trên đầu bảng (kt_cong_no_kh.html).
      // Cộng dồn RAW (không clamp) để con_lai luôn đúng bằng tong_no - da_thu ở mức khách hàng;
      // dữ liệu hiện tại (2026-09-25) có 7 hoá đơn trả dư nhưng đều là khách 1-hoá-đơn nên số hiển
      // thị mặc định (lọc "Còn nợ") không đổi — sửa để KHÔNG âm thầm sai khi có khách nhiều hoá đơn.
      const con_lai = ds.reduce((a, r) => a + conLaiCuaKH(r), 0);
      let quaHan = 0, maxQuaHanNgay = 0;
      ds.forEach((r) => {
        const h = hanThuKH(r), cl = conLaiCuaKH(r); if (cl <= 0 || !h) return;
        const han = new Date(h.iso + 'T00:00:00');
        const soNgay = Math.round((han - homNay) / 86400000);
        if (soNgay < 0) { quaHan += cl; maxQuaHanNgay = Math.max(maxQuaHanNgay, -soNgay); }
      });
      let nhomTuoi = 'chua_den_han';
      if (con_lai <= 0) nhomTuoi = 'da_thu_du';
      else if (maxQuaHanNgay > 60) nhomTuoi = 'qh_tren_60';
      else if (maxQuaHanNgay > 30) nhomTuoi = 'qh_31_60';
      else if (maxQuaHanNgay > 0) nhomTuoi = 'qh_1_30';
      const r0 = {
        khach: { id, ma: '', ten, sdt: '', nv_kd: '' },
        so_phieu: ds.filter((r) => conLaiCuaKH(r) > 0).length, tong_no, da_thu, con_lai,
        qua_han: quaHan, tuoi_no_max_ngay: maxQuaHanNgay, nhom_tuoi: nhomTuoi,
      };
      _rawByKeyKH[id] = { r: r0, ds };
      return r0;
    });
    const tatCa = tongRong(mapped);

    const tt = q.tinh_trang || 'con_no';
    if (tt === 'con_no') mapped = mapped.filter((r) => r.con_lai > 0);
    else if (tt === 'qua_han') mapped = mapped.filter((r) => r.qua_han > 0);
    else if (tt === 'chua_den_han') mapped = mapped.filter((r) => r.con_lai > 0 && !r.qua_han);
    else if (tt === 'qh_1_30' || tt === 'qh_31_60' || tt === 'qh_tren_60') mapped = mapped.filter((r) => r.nhom_tuoi === tt);
    else if (tt === 'da_thu_du') mapped = mapped.filter((r) => r.con_lai <= 0);
    // 'tat_ca' → không lọc

    if (q.tim) { const s = String(q.tim).trim(); mapped = mapped.filter((r) => khopTim(r.khach.ten, _rawByKeyKH[r.khach.id].ds, s)); }

    mapped = sapXep(mapped, q.sort);

    const tong = mapped.reduce((a, r) => ({
      tong_no: a.tong_no + r.tong_no, da_thu: a.da_thu + r.da_thu, con_lai: a.con_lai + r.con_lai, qua_han: a.qua_han + r.qua_han,
      so_khach_con_no: a.so_khach_con_no + (r.con_lai > 0 ? 1 : 0), so_khach_qua_han: a.so_khach_qua_han + (r.qua_han > 0 ? 1 : 0),
    }), { tong_no: 0, da_thu: 0, con_lai: 0, qua_han: 0, so_khach_con_no: 0, so_khach_qua_han: 0 });

    const page = Math.max(1, +q.page || 1), size = Math.max(1, +q.size || 10);
    const soTrang = Math.max(1, Math.ceil(mapped.length / size)), trangHopLe = Math.min(page, soTrang);
    return {
      den_ngay: denNgay, nhan_vien: [], tong, tat_ca: tatCa, thu_ho: _thuHoKH,
      trang: trangHopLe, so_trang: soTrang, tong_dong: mapped.length,
      dong: mapped.slice((trangHopLe - 1) * size, trangHopLe * size),
    };
  }
  function chiTietTuDanhSachKH(id) {
    const x = _rawByKeyKH[id];
    if (!x) return Promise.reject(new Error('Không tìm thấy công nợ của khách này trong danh sách vừa tải — thử tải lại trang.'));
    const homNay = new Date(ngayTinh() + 'T00:00:00');   // cùng mốc "Tính đến ngày" với dòng danh sách
    const phieu = x.ds.map((r) => {
      const conLai = conLaiCuaKH(r), daTra = Number(r.da_tra) || 0, tong = Number(r.so_tien) || 0;
      let trangThai = conLai <= 0 ? 'da_thu_du' : (daTra > 0 ? 'thu_mot_phan' : 'chua_thu'); let quaHanNgay = 0;
      const h = hanThuKH(r), han = h ? new Date(h.iso + 'T00:00:00') : null;
      if (conLai > 0 && han && han < homNay) { trangThai = 'qua_han'; quaHanNgay = Math.round((homNay - han) / 86400000); }
      return { id: r.id, so_phieu: r.id, don_hang: r.ma_don || '', ngay: r.ngay, han_tt: h ? h.iso : null, han_mac_dinh: !!(h && h.mac_dinh), tong, da_thu: daTra, con_lai: conLai, trang_thai: trangThai, qua_han_ngay: quaHanNgay,
        nguon: r.ref_source || '', ghi_chu: r.ghi_chu || '', ngay_tra: r.ngay_tra || '', ma_cn: r.id };
    });
    // CongNo chỉ lưu MỘT số da_tra luỹ kế + một ngay_tra — không phải sổ giao dịch thu tách dòng.
    const lich_su_thu = x.ds.filter((r) => Number(r.da_tra) > 0)
      .map((r) => ({ ngay: r.ngay_tra || r.ngay, so_ct: r.id, so_tien: Number(r.da_tra) || 0, hinh_thuc: '—' }))
      .sort((a, b) => (a.ngay < b.ngay ? 1 : -1));
    return Promise.resolve({ khach: x.r.khach, tong_no: x.r.tong_no, da_thu: x.r.da_thu, con_lai: x.r.con_lai, qua_han: x.r.qua_han, nhom_tuoi: x.r.nhom_tuoi, phieu, lich_su_thu });
  }

  const CFG = {
    kh: { api: '/api/cong-no', tk: '131', dt: 'khách', Dt: 'Khách hàng', daThu: 'Đã thu', conLai: 'Còn phải thu', thu: 'thu', hd: 'hoá đơn bán hàng',
      lap: 'Ghi nhận thu', loai: 'phai_thu', chiTietHref: '/kd/khach-hang/', lsTieuDe: 'Lần thu gần nhất', lsRong: ['Chưa thu lần nào', 'Khách chưa có khoản đã thu nào ghi nhận.'],
      rongThat: (d) => ['Không có khách nào còn nợ', 'Mọi khoản phải thu đã ghi sổ đến ' + d + ' đều đã được thu đủ.'], loiTai: 'Không tải được công nợ khách hàng',
      // 3 điểm mở rộng cùng khuôn với CFG.ncc — CFG.ncc không đổi hành vi.
      chuyen: chuyenKH, chiTietTuDanhSach: chiTietTuDanhSachKH, xuatChuaCo: true,
      thamSoCoDinh: { loai: 'phai_thu', limit: 2000, offset: 0 } },
    ncc: { api: '/api/cong-no/ncc-module', tk: '331', dt: 'NCC', Dt: 'Nhà cung cấp', daThu: 'Đã trả', conLai: 'Còn phải trả', thu: 'trả', hd: 'hoá đơn mua hàng',
      lap: 'Ghi nhận trả', loai: 'phai_tra', chiTietHref: '/mua-hang/nha-cung-cap/', lsTieuDe: 'Lần trả gần nhất', lsRong: ['Chưa trả lần nào', 'Chưa có phiếu chi, báo nợ hay bù trừ nào cho nhà cung cấp này trong dữ liệu đọc được.'],
      rongThat: (d) => ['Không còn nợ nhà cung cấp nào', 'Mọi hoá đơn mua hàng đã ghi sổ đến ' + d + ' đều đã được trả đủ.'], loiTai: 'Không tải được công nợ nhà cung cấp',
      // 3 điểm mở rộng riêng đợt 2 (NCC dùng ncc-module) — CFG.kh dùng cùng khuôn nhưng nguồn/hàm
      // riêng của nó (chuyenKH/chiTietTuDanhSachKH ở trên), không đụng lẫn nhau.
      chuyen: chuyenNCC, chiTietTuDanhSach: chiTietTuDanhSachNCC, xuatChuaCo: true },
  }[trang.dataset.ben];
  // Nhãn trạng thái phiếu/tuổi nợ theo chiều: bên NCC là "trả", không phải "thu".
  const NHAN_NCC = { chua_thu: 'Chưa trả', thu_mot_phan: 'Trả một phần', da_thu_du: 'Đã trả đủ' };
  const pillPhieu = (k, rieng) => KT.pillPhieu(k, rieng || (trang.dataset.ben === 'ncc' ? NHAN_NCC[k] : ''));
  const pillTuoi = (k) => KT.pillTuoiNo(k, trang.dataset.ben === 'ncc' && k === 'da_thu_du' ? 'Đã trả đủ' : '');

  // NCC mặc định "Tất cả" như tab mặc định màn cũ /app#cong-no-ncc → 6 thẻ số khớp đúng số màn cũ
  // (Tổng/Nợ thực/Dự kiến/Đã trả/Còn nợ ròng/Số NCC). KH giữ "Còn nợ" (cũ: tổng con_lai > 0 — khớp).
  const MAC_DINH = { tim: '', tinh_trang: BEN === 'ncc' ? 'tat_ca' : 'con_no', tu: '', den_ngay: '', nhom: 'all', thang: '', page: 1, size: 10, sort: 'con_lai_desc' };
  const st = Object.assign({}, MAC_DINH, KT.url.doc());
  st.page = +st.page || 1; st.size = +st.size || 10;
  let luot = 0; let dsDong = [];
  const chiTiet = {};          // cache chi tiết theo khách trong lượt tải hiện tại
  const dangMo = new Set();    // id khách đang mở rộng

  /* Khôi phục ô lọc từ URL; giá trị ô không nhận (link gõ tay/cũ: tình trạng lạ, ngày sai dạng, cỡ trang
     ngoài danh sách) thì lấy lại đúng giá trị ô đang hiện — tránh lọc/gửi API một giá trị người dùng không thấy. */
  const napO = (id, k, macDinh) => { const el = $(id); el.value = String(st[k]); if (el.value !== String(st[k])) { el.value = String(macDinh); st[k] = el.tagName === 'SELECT' ? macDinh : el.value; } };
  $('cnk-tim').value = st.tim;
  napO('cnk-tt', 'tinh_trang', MAC_DINH.tinh_trang); napO('cnk-tu', 'tu', ''); napO('cnk-den', 'den_ngay', ''); napO('cnk-co-trang', 'size', MAC_DINH.size);
  if (BEN === 'ncc') { napO('cnk-nhom', 'nhom', MAC_DINH.nhom); napO('cnk-thang', 'thang', ''); }
  const loc = $('cnk-loc'), nutLoc = $('cnk-nut-loc');
  function moLoc(mo) { loc.hidden = !mo; nutLoc.setAttribute('aria-expanded', String(mo)); }
  moLoc(KD.MAN_RONG());   // boolean (bản trước .matches → undefined → khung lọc luôn gập)
  nutLoc.addEventListener('click', () => moLoc(loc.hidden));

  const SO_COT = 7;
  const ngayTinh = () => st.den_ngay || KD.iso(new Date());

  /* ── Thẻ số ── */
  /* 4 thẻ chính; phần tách chi tiết (nợ thực/dự kiến, trả thừa, số đối tượng…) nằm trong ⓘ cạnh nhãn. */
  function veKpi(d) {
    const t = d.tong, all = d.tat_ca;
    const ghi = { tong_no: ['', ''], da_thu: ['', ''], con_lai: ['', ''], qua_han: ['', ''] };
    ghi.tong_no[1] = BEN === 'ncc'
      ? 'Nợ thực ' + KD.tienVnd(t.no_thuc) + ' (đơn đã xong + nhập tay) + Nợ dự kiến ' + KD.tienVnd(t.no_du_kien) + ' (đơn chưa xong).'
      : 'Tổng nợ = ' + CFG.daThu + ' + ' + CFG.conLai + '.';
    ghi.da_thu[0] = t.tong_no ? KD.phanTram((t.da_thu / t.tong_no) * 100) + ' tổng nợ' : '';
    ghi.con_lai[0] = KD.soDem(t.so_khach_con_no) + ' ' + CFG.dt + ' còn nợ';
    const tipCon = [];
    if (all && all.so_tra_thua && Math.round(t.con_lai) !== Math.round(all.con_lai)) tipCon.push('Ròng mọi ' + CFG.dt + ': ' + KD.tienVnd(all.con_lai) + ' — đã trừ ' + KD.soDem(all.so_tra_thua) + ' ' + CFG.dt + ' trả thừa (' + KD.tienVnd(all.tra_thua) + ').');
    else if (all && all.so_tra_thua) tipCon.push('Đã trừ ' + KD.soDem(all.so_tra_thua) + ' ' + CFG.dt + ' trả thừa (' + KD.tienVnd(all.tra_thua) + '). Chỉ tính ' + CFG.dt + ' còn nợ: ' + KD.tienVnd(all.con_lai - all.tra_thua) + '.');
    if (all) tipCon.push(KD.soDem(all.so) + ' ' + CFG.dt + ' có phát sinh công nợ.');
    ghi.con_lai[1] = tipCon.join(' ');
    ghi.qua_han[0] = BEN === 'ncc' ? 'Sắp đến hạn 7 ngày: ' + KD.tienGon(t.den_han_7_ngay)
      : (t.so_khach_qua_han ? KD.soDem(t.so_khach_qua_han) + ' ' + CFG.dt + ' có khoản quá hạn' : 'Không có khoản quá hạn');
    ghi.qua_han[1] = BEN === 'ncc'
      ? (t.so_khach_qua_han ? KD.soDem(t.so_khach_qua_han) + ' NCC có khoản quá hạn.' : 'Không có khoản nào quá hạn.') + ' Đến hạn trong 7 ngày tới (chưa quá hạn): ' + KD.tienVnd(t.den_han_7_ngay) + '.'
      : 'Hoá đơn không ghi hạn: hạn = ngày phát sinh + ' + HAN_NO_MAC_DINH + ' ngày.';
    trang.querySelectorAll('#cnk-kpi [data-kpi]').forEach((the) => {
      const k = the.dataset.kpi, v = t[k], g = ghi[k] || ['', ''];
      the.querySelector('[data-v]').innerHTML = KD.tienGonHtml(v);
      the.querySelector('[data-v]').title = KD.tienVnd(v);
      the.querySelector('[data-phu]').textContent = g[0];
      the.querySelector('[data-tip-o]').innerHTML = KD.tip(g[1], k === 'qua_han' ? 'kd-tip--trai' : '');
    });
  }
  function choKpi() {
    trang.querySelectorAll('#cnk-kpi [data-v]').forEach((el) => { el.innerHTML = '<span class="kd-skel kd-skel--kpi"></span>'; el.title = ''; });
    trang.querySelectorAll('#cnk-kpi [data-phu]').forEach((el) => { el.textContent = ''; });
    trang.querySelectorAll('#cnk-kpi [data-tip-o]').forEach((el) => { el.innerHTML = ''; });
  }

  /* ── Bảng ── */
  /* Bảng chính chỉ giữ cột thiết yếu; số HĐ nợ → dòng phụ dưới tên, quá hạn → dòng phụ dưới tuổi nợ,
     nợ thực/dự kiến (NCC) → dòng mở rộng + panel. */
  function dongKhach(r) {
    const k = r.khach, mo = dangMo.has(String(k.id));
    const phuTen = [k.ma, k.sdt, k.nv_kd ? 'NV ' + k.nv_kd : '', KD.soDem(r.so_phieu) + ' HĐ còn nợ'].filter(Boolean).map(esc).join(' · ');
    return '<tr data-id="' + esc(k.id) + '" tabindex="0"' + (mo ? ' class="is-mo"' : '') + '>'
      + '<td class="kt-col-mo"><button type="button" class="kd-icon-btn kt-mo" data-mo="' + esc(k.id) + '" aria-expanded="' + mo + '" aria-controls="cnk-con-' + esc(k.id) + '" aria-label="Xem hoá đơn còn nợ của ' + esc(k.ten) + '"><i class="bi bi-chevron-right" aria-hidden="true"></i></button></td>'
      + '<td><span class="kt-khach__ten">' + esc(k.ten) + '</span><span class="kt-khach__ma">' + phuTen + '</span></td>'
      + '<td class="num">' + KD.tien(r.tong_no) + '</td>'
      + '<td class="num">' + KT.tienSo(r.da_thu) + '</td>'
      + '<td class="num kt-so--con">' + KT.tienSo(r.con_lai) + '</td>'
      + '<td><span title="' + (r.tuoi_no_max_ngay ? 'Hoá đơn quá hạn lâu nhất: ' + KD.soDem(r.tuoi_no_max_ngay) + ' ngày' : '') + '">' + pillTuoi(r.nhom_tuoi) + '</span>'
      + (r.qua_han ? '<span class="kt-khach__ma kt-so--qua-han">Quá hạn ' + KD.tien(r.qua_han) + '</span>' : '') + '</td>'
      + '<td class="kd-col-act"><button type="button" class="kd-icon-btn" data-menu="' + esc(k.id) + '" aria-haspopup="menu" aria-expanded="false" aria-label="Thao tác với ' + esc(k.ten) + '"><i class="bi bi-three-dots" aria-hidden="true"></i></button></td>'
      + '</tr>'
      + (mo ? dongMoRong(k.id) : '');
  }
  function dongMoRong(id) {
    return '<tr class="kt-mo-rong" id="cnk-con-' + esc(id) + '"><td colspan="' + SO_COT + '"><div class="kt-con" data-con="' + esc(id) + '">' + KD.KHUNG_TAI + '</div></td></tr>';
  }
  /* Bảng con khi mở rộng một đối tượng — hiện MỌI khoản công nợ (còn nợ lên trước) như bảng con
     màn cũ (cũ hiện cả đơn đã trả + nút lọc "Đã trả"), thêm các cột cũ có mà mới thiếu:
     Nguồn/ghi chú (KH), khách của đơn + Nhóm Phải trả/Dự kiến (NCC), Ngày thanh toán. */
  const NHAN_NGUON = { baogia_quote: 'Báo giá', muahang: 'Mua hàng', muahang_po: 'Mua hàng PO', mua_hang: 'Mua hàng', sale_admin: 'Kinh doanh', saleadmin_vc_phai_tra: 'Vận chuyển', saleadmin_vc_phai_thu: 'Thu hộ ĐVVC' };
  const maBaoGia = (md) => String(md || '').split(/[—–]/)[0].trim(); // như _extractMaBg màn cũ
  function oDon(p) {
    const bg = maBaoGia(p.don_hang);
    const link = /^NV\d/.test(bg) ? '<a class="kt-ma" href="/ketoan/don-hang?tim=' + encodeURIComponent(bg) + '" title="Xem chi tiết đơn ' + esc(bg) + '">' + esc(p.don_hang) + '</a>'
      : (p.don_hang ? '<span class="kt-ma">' + esc(p.don_hang) + '</span>' : '<span class="kd-muted">—</span>');
    const phu = [p.ma_cn, BEN === 'kh' ? (NHAN_NGUON[p.nguon] || (p.nguon ? p.nguon : 'Nhập tay')) : ''].filter(Boolean).join(' · ');
    return link + (phu ? '<span class="kt-khach__ma">' + esc(phu) + '</span>' : '');
  }
  function oNoiDung(p) {
    const chinh = BEN === 'ncc' ? (p.khach_don || '') : '';
    if (!chinh && !p.ghi_chu) return '<span class="kd-muted">—</span>';
    return (chinh ? '<span class="kt-cat kt-cat--hep" title="Khách của đơn">' + esc(chinh) + '</span>' : '')
      + (p.ghi_chu ? '<span class="kt-khach__ma kt-cat kt-cat--hep" title="' + esc(p.ghi_chu) + '">' + esc(p.ghi_chu) + '</span>' : '');
  }
  function pillNhom(p) {
    if (p.nhom === 'thuc') return '<span class="pill pill--success">Phải trả</span>';
    if (p.nhom === 'du_kien') return '<span class="pill pill--warning">Dự kiến</span>';
    return '<span class="pill pill--muted">' + esc(p.tien_trinh || '—') + '</span>';
  }
  function pillTrangThaiPhieu(p) {
    if (p.con_lai < 0) return '<span class="pill pill--info" title="Ứng/trả nhiều hơn số nợ — số dư đặt cọc">Trả thừa ' + KD.tien(-p.con_lai) + '</span>';
    return pillPhieu(p.trang_thai, p.trang_thai === 'qua_han' ? 'Quá hạn ' + KD.soDem(p.qua_han_ngay) + ' ngày' : '');
  }
  /* Sửa / Xoá 1 khoản (PUT / DELETE /api/cong-no/{id} — require_ceo_thuchi): chỉ hiện với CEO/admin/trợ lý (data-quyen). */
  function nutSuaXoa(p) {
    const ten = esc(p.don_hang || p.ma_cn || p.id);
    return '<button type="button" class="kd-icon-btn" data-quyen="ceo" data-sua-cn="' + esc(String(p.id)) + '" aria-label="Sửa khoản ' + ten + '" title="Sửa khoản công nợ"><i class="bi bi-pencil" aria-hidden="true"></i></button>'
      + '<button type="button" class="kd-icon-btn" data-quyen="ceo" data-xoa-cn="' + esc(String(p.id)) + '" aria-label="Xoá khoản ' + ten + '" title="Xoá khoản công nợ"><i class="bi bi-trash" aria-hidden="true"></i></button>';
  }
  function bangHoaDon(ct) {
    const ds = ct.phieu.slice().sort((a, b) => ((b.con_lai > 0) - (a.con_lai > 0)) || (a.ngay < b.ngay ? 1 : -1));
    const soCon = ds.filter((p) => p.con_lai > 0).length;
    if (!ds.length) return KD.khoiRong('Không có khoản công nợ nào', 'Đối tượng này chưa có hoá đơn nào trong bộ lọc hiện tại.');
    const ncc = BEN === 'ncc';
    const oHan = (p) => (p.han_tt ? 'Hạn ' + esc(p.han_tt.length === 10 && p.han_tt[4] === '-' ? KD.ngay(p.han_tt) : p.han_tt) + (p.han_mac_dinh ? ' (mặc định)' : '') : 'Chưa ghi hạn');
    return '<div class="kd-table-scroll"><table class="kd-table kd-table--gon kt-con-bang"><caption class="visually-hidden">Các khoản công nợ của ' + esc(ct.khach.ten) + '</caption><thead><tr>'
      + '<th scope="col">Đơn hàng</th><th scope="col">' + (ncc ? 'Khách của đơn · ghi chú' : 'Ghi chú') + '</th>'
      + '<th scope="col">Ngày · hạn' + (ncc ? '' : KD.tip('Không ghi hạn: mặc định ngày phát sinh + ' + HAN_NO_MAC_DINH + ' ngày.')) + '</th>'
      + '<th scope="col" class="num">Số tiền</th><th scope="col" class="num">' + CFG.daThu + '</th><th scope="col" class="num">Còn lại</th>'
      + '<th scope="col">Trạng thái</th><th scope="col" class="kd-col-act"><span class="visually-hidden">Thao tác</span></th></tr></thead><tbody>'
      + ds.map((p) => '<tr' + (p.con_lai > 0 ? '' : ' class="kt-con--xong"') + '><td>' + oDon(p) + '</td><td>' + oNoiDung(p) + '</td>'
        + '<td>' + KD.ngay(p.ngay) + '<span class="kt-khach__ma">' + oHan(p) + '</span></td>'
        + '<td class="num">' + KD.tien(p.tong) + '</td><td class="num">' + KT.tienSo(p.da_thu) + (p.ngay_tra ? '<span class="kt-khach__ma">ngày ' + KD.ngay(p.ngay_tra) + '</span>' : '') + '</td><td class="num kt-so--con">' + KD.tien(p.con_lai) + '</td>'
        + '<td>' + pillTrangThaiPhieu(p) + (ncc ? '<span class="kt-con__nhom">' + pillNhom(p) + '</span>' : '') + '</td>'
        + '<td class="kd-col-act"><span class="kt-con__nut">' + (p.con_lai > 0 ? '<button type="button" class="kd-btn kd-btn--sm" data-gnt-dt="' + esc(ct.khach.id) + '" data-gnt-khoan="' + esc(String(p.id)) + '"><i class="bi bi-cash-coin" aria-hidden="true"></i>Ghi nhận</button>' : '')
        + nutSuaXoa(p) + '</span></td></tr>').join('')
      + '</tbody></table></div>'
      + '<p class="kt-con__chan"><span>' + KD.soDem(ds.length) + ' khoản · ' + KD.soDem(soCon) + ' còn nợ · tính đến ' + KD.ngay(ngayTinh()) + '</span>'
      + (ncc ? '<span>Nợ thực <b class="num">' + KD.tien(ct.no_thuc) + '</b> · Dự kiến <b class="num">' + KD.tien(ct.no_du_kien) + '</b> · ' + moTaSoDon(ct.so_don) + '</span>' : '')
      + '<a class="kd-link kd-link--sm" href="' + soChiTiet(ct.khach) + '">Xem sổ chi tiết công nợ<i class="bi bi-arrow-right" aria-hidden="true"></i></a></p>';
  }
  /* NCC: số đơn theo nhóm như màn cũ — "65 thực (10 nhập tay) · 4 dự kiến". */
  function moTaSoDon(sd) {
    if (!sd) return '';
    return KD.soDem(sd.thuc) + ' đơn thực' + (sd.nhap_tay ? ' (' + KD.soDem(sd.nhap_tay) + ' nhập tay)' : '') + ' · ' + KD.soDem(sd.du_kien) + ' dự kiến';
  }
  /* Sổ chi tiết công nợ theo đối tượng: trang chi tiết L4 của Kế toán (thay cho sổ cái lọc đối tượng). */
  function soChiTiet(k) { return '/ketoan/doi-tuong?ben=' + BEN + '&id=' + encodeURIComponent(k.id); }

  async function layChiTiet(id) {
    if (!chiTiet[id]) {
      const p = CFG.chiTietTuDanhSach ? Promise.resolve().then(() => CFG.chiTietTuDanhSach(id)) : KD.api(CFG.api + '/' + encodeURIComponent(id) + '?den_ngay=' + ngayTinh());
      chiTiet[id] = p.catch((e) => { delete chiTiet[id]; throw e; });
    }
    return chiTiet[id];
  }
  async function napMoRong(id) {
    const hop = trang.querySelector('[data-con="' + CSS.escape(id) + '"]'); if (!hop) return;
    hop.innerHTML = KD.KHUNG_TAI;
    try { const ct = await layChiTiet(id); const h = trang.querySelector('[data-con="' + CSS.escape(id) + '"]'); if (h) h.innerHTML = bangHoaDon(ct); }
    catch (e) { const h = trang.querySelector('[data-con="' + CSS.escape(id) + '"]'); if (h) KD.khoiLoi(h, 'Không tải được hoá đơn của ' + CFG.dt, e, () => napMoRong(id)); }
  }
  function doiMoRong(id) {
    id = String(id);
    const tr = $('cnk-tbody').querySelector('tr[data-id="' + CSS.escape(id) + '"]'); const nut = tr.querySelector('[data-mo]');
    if (dangMo.has(id)) {
      dangMo.delete(id); const con = $('cnk-con-' + id); if (con) con.remove();
      tr.classList.remove('is-mo'); nut.setAttribute('aria-expanded', 'false');
    } else {
      dangMo.add(id); tr.insertAdjacentHTML('afterend', dongMoRong(id));
      tr.classList.add('is-mo'); nut.setAttribute('aria-expanded', 'true'); napMoRong(id);
    }
  }

  function chanBang(t, soDong) {
    return '<tr><td></td><th scope="row">Cộng ' + KD.soDem(soDong) + ' ' + CFG.dt + (soDong !== t.so_khach_con_no ? ' (' + KD.soDem(t.so_khach_con_no) + ' còn nợ)' : '') + ' · mọi trang</th>'
      + '<td class="num">' + KD.tien(t.tong_no) + '</td><td class="num">' + KD.tien(t.da_thu) + '</td><td class="num">' + KD.tien(t.con_lai) + '</td>'
      + '<td class="kt-cong-qh"><span class="kt-khach__ma">Quá hạn</span><span class="num' + (t.qua_han ? ' kt-so--qua-han' : '') + '">' + KD.tien(t.qua_han) + '</span></td><td class="kd-col-act"></td></tr>';
  }

  /* ── Tải ── */
  function soLocBat() { return (st.tinh_trang !== MAC_DINH.tinh_trang ? 1 : 0) + (st.tu ? 1 : 0) + (st.den_ngay ? 1 : 0) + (st.nhom !== MAC_DINH.nhom ? 1 : 0) + (st.thang ? 1 : 0); }
  async function tai() {
    const l = ++luot;
    KT.url.ghi(st, MAC_DINH);
    Object.keys(chiTiet).forEach((k) => delete chiTiet[k]);
    const n = soLocBat(); $('cnk-dem-loc').hidden = !n; $('cnk-dem-loc').textContent = n;
    // Điểm mở rộng thứ 4 (đợt 1, KH): CFG.thamSoCoDinh gộp thêm tham số CỐ ĐỊNH thật sự gửi lên máy
    // chủ (vd loai=phai_thu, limit=2000) — cần vì API thật /api/cong-no không nhận tim/tinh_trang/
    // page/size/sort (những khoá đó FastAPI âm thầm bỏ qua, chỉ để chuyen() dùng lọc/sắp/phân trang
    // ở trình duyệt). NCC không khai thamSoCoDinh nên không đổi hành vi.
    // tu_ngay/den_ngay lọc theo ngày phát sinh ở CẢ HAI API; filter/thang chỉ ncc-module nhận (KH bỏ qua).
    const q = Object.assign({ tim: st.tim, tinh_trang: st.tinh_trang, tu_ngay: st.tu, den_ngay: st.den_ngay, page: st.page, size: st.size, sort: st.sort },
      BEN === 'ncc' ? { filter: st.nhom, thang: st.thang } : {}, CFG.thamSoCoDinh || {});
    if (CFG.xuatChuaCo) {
      $('cnk-xuat').href = '#'; $('cnk-xuat').classList.add('is-disabled'); $('cnk-xuat').setAttribute('aria-disabled', 'true');
      $('cnk-xuat').title = 'Chưa có chức năng xuất Excel cho màn này';
    } else {
      $('cnk-xuat').href = CFG.api + '/xuat?' + KT.url.qs(Object.assign({}, q, { page: '', size: '' }));
    }
    choKpi();
    $('cnk-cuon').hidden = false; $('cnk-tbody').innerHTML = KT.hangCho(SO_COT, 8); $('cnk-tfoot').innerHTML = '';
    $('cnk-tt-khoi').innerHTML = ''; $('cnk-foot').hidden = true;
    try {
      const raw = await KD.api(CFG.api + '?' + KT.url.qs(q));
      // Kiểm lượt TRƯỚC chuyen(): chuyen() ghi đè _rawByKey/_rawByKeyKH (nguồn của panel, dòng mở rộng,
      // hộp Ghi nhận) — phản hồi cũ về muộn trước đây đè dữ liệu của bộ lọc mới dù bảng không vẽ lại.
      if (l !== luot) return;
      const d = CFG.chuyen ? CFG.chuyen(raw, q) : raw;
      veKpi(d);
      const ky = st.thang ? ' · phát sinh tháng ' + st.thang.split('-').reverse().join('/') : (st.tu ? ' · phát sinh từ ' + KD.ngay(st.tu) : '');
      $('cnk-pham-vi').innerHTML = 'Tính đến ' + KD.ngay(d.den_ngay) + esc(ky) + KD.tip('Từ ' + CFG.hd + ' đã ghi sổ (TK ' + CFG.tk + ').'
        + (BEN === 'kh' ? ' Hạn thu theo hoá đơn; không ghi hạn = ngày phát sinh + ' + HAN_NO_MAC_DINH + ' ngày.' : ' Hạn thanh toán theo từng hoá đơn.')
        + (d.thu_ho && d.thu_ho.so ? ' Không gồm ' + KD.soDem(d.thu_ho.so) + ' khoản thu hộ ĐVVC (' + KD.tienVnd(d.thu_ho.con_lai) + ', trùng phải thu đơn báo giá).' : ''));
      dsDong = d.dong;
      if (!d.dong.length) {
        $('cnk-cuon').hidden = true;
        const coLoc = st.tim || soLocBat();   // NCC mặc định "Tất cả": chọn "Còn nợ" mà rỗng vẫn phải hiện nút Đặt lại
        $('cnk-tt-khoi').innerHTML = coLoc
          ? KD.khoiRong('Không có ' + CFG.Dt.toLowerCase() + ' nào khớp bộ lọc', 'Thử bỏ bớt điều kiện lọc hoặc đổi ngày tính.') + '<p class="kt-giua"><button type="button" class="kd-btn kd-btn--sm" data-dat-lai>Đặt lại bộ lọc</button></p>'
          : KD.khoiRong(...CFG.rongThat(KD.ngay(d.den_ngay)));
        const b = $('cnk-tt-khoi').querySelector('[data-dat-lai]'); if (b) b.addEventListener('click', datLai);
        return;
      }
      [...dangMo].forEach((id) => { if (!d.dong.some((r) => String(r.khach.id) === id)) dangMo.delete(id); });
      $('cnk-tbody').innerHTML = d.dong.map(dongKhach).join('');
      dangMo.forEach(napMoRong);
      $('cnk-tfoot').innerHTML = chanBang(d.tong, d.tong_dong);
      $('cnk-foot').hidden = false;
      const a = (d.trang - 1) * st.size + 1, b = Math.min(d.trang * st.size, d.tong_dong);
      $('cnk-hien-thi').textContent = 'Hiển thị ' + KD.soDem(a) + ' - ' + KD.soDem(b) + ' / ' + KD.soDem(d.tong_dong) + ' ' + CFG.dt;
      KD.phanTrang($('cnk-trang'), d.trang, d.so_trang, (p) => { st.page = p; tai(); });
    } catch (e) {
      if (l !== luot) return;
      $('cnk-cuon').hidden = true;
      trang.querySelectorAll('#cnk-kpi [data-v]').forEach((el) => { el.innerHTML = '<span class="kd-muted">—</span>'; });
      KD.khoiLoi($('cnk-tt-khoi'), CFG.loiTai, e, tai);
    }
  }

  /* ── Ghi nhận thu / trả (cơ chế màn cũ: POST /api/cong-no/{id}/tra — trừ công nợ + ghi Sổ quỹ) ── */
  function dsDoiTuongGhiNhan() {
    const so = (v) => Number(v) || 0;
    if (BEN === 'kh') {
      return Object.keys(_rawByKeyKH).map((id) => ({ ten: id, khoan: _rawByKeyKH[id].ds.map((r) => ({ id: r.id, ma_don: r.ma_don, so_tien: so(r.so_tien), da_tra: so(r.da_tra), con_lai: conLaiCuaKH(r) })) }));
    }
    return Object.keys(_rawByKey).map((id) => ({ ten: id, khoan: _rawByKey[id].don_list.map((p) => ({ id: p.id, ma_don: p.ma_don, so_tien: so(p.so_tien), da_tra: so(p.da_tra), con_lai: so(p.con_lai) })) }));
  }
  function moGhiNhan(idDt, idKhoan, cheDo) {
    KTGhiNhanTra.mo({ loai: CFG.loai, doiTuong: dsDoiTuongGhiNhan(), chonDoiTuong: idDt, chonKhoan: idKhoan, cheDo, xong: () => { panel.dong(); tai(); } });
  }
  // Nút đầu trang mở chế độ "Nhiều khoản" (tick nhiều khoản, kể cả khác đối tượng); dòng/panel mở "Một khoản".
  $('cnk-lap').addEventListener('click', () => moGhiNhan(null, null, 'nhieu'));

  /* ── Đồng bộ công nợ (POST /api/cong-no/sync, services/cong_no_dong_bo.py) ──
     Bấm nút → luôn XEM TRƯỚC (?dry_run=true: máy chủ chạy đúng nhánh ghi rồi rollback) → hộp thoại hiện số dòng
     tạo/cập nhật, tổng trước/sau (đúng số thẻ "Còn phải thu/trả" của 2 màn), đối tác đổi nhiều nhất và các khoản cần
     KT kiểm → mới cho bấm "Đồng bộ" chạy thật. Phải thu mỗi đơn = "Còn thu" màn Đơn hàng. */
  const dlgDb = $('cnk-dlg-db');
  const soN = (v) => Number(v) || 0;
  let luotDb = 0, banXemTruoc = null;
  const dongSo = (nhan, t, s, laTien) => {
    const fm = laTien ? KD.tienVnd : KD.soDem, ch = s - t;
    return '<tr><th scope="row">' + nhan + '</th><td class="num">' + fm(t) + '</td><td class="num">' + fm(s) + '</td><td class="num">'
      + (Math.abs(ch) < 0.5 ? '<span class="kd-muted">—</span>' : (ch > 0 ? '+' : '−') + fm(Math.abs(ch))) + '</td></tr>';
  };
  function canhBaoDongBo(r, daChay) {
    const out = [];
    const ck = r.can_kiem || [];
    if (ck.length) {
      const tong = ck.reduce((a, x) => a + soN(x.con_lai_truoc), 0);
      out.push('<b>' + KD.soDem(ck.length) + ' đơn màn Đơn hàng báo thu thừa</b> nhưng công nợ đang còn ' + KD.tienVnd(tong) + ' → ' + (daChay ? 'đã' : 'sẽ')
        + ' về 0 theo Đơn hàng. Nên kiểm cọc hợp đồng / doanh thu của đơn: '
        + ck.slice().sort((a, b) => soN(b.con_lai_truoc) - soN(a.con_lai_truoc)).slice(0, 5)
          .map((x) => esc(x.ma_don) + ' ' + esc(x.doi_tac) + ' (còn ' + KD.tien(soN(x.con_lai_truoc)) + ', thu thừa ' + KD.tien(-soN(x.con_thu_don_hang)) + ')').join('; ')
        + (ck.length > 5 ? '…' : '') + '.');
    }
    const kc = r.khong_con_don || [];
    if (kc.length) out.push(KD.soDem(kc.length) + ' khoản phải thu gắn báo giá không còn duyệt ('
      + kc.map((x) => esc(x.id) + ' ' + esc(x.doi_tac) + ' ' + KD.tien(soN(x.con_lai))).join('; ') + ') — giữ nguyên, xoá tay nếu sai.');
    const gs = r.giu_so_da_thu || [];
    if (gs.length) out.push(KD.soDem(gs.length) + ' khoản giữ số đã thu Kế toán ghi trực tiếp trên Công nợ (có phiếu Sổ quỹ, chưa có doanh thu theo mã đơn).');
    const db = r.don_bo_qua || [];
    if (db.length) out.push(KD.soDem(db.length) + ' đơn không tạo phải thu tự động vì đã có khoản nhập tay: '
      + db.map((x) => esc(x.ma_don) + ' ' + esc(x.doi_tac || '')).join('; ') + '.');
    const pb = r.po_bo_qua || [];
    if (pb.length) out.push(KD.soDem(pb.length) + ' đơn mua không tạo công nợ: '
      + pb.map((x) => esc(x.po) + (x.ma_don ? ' (' + esc(x.ma_don) + ')' : '') + ' — ' + esc(x.ly_do)).join('; ') + '.');
    return out;
  }
  function veDongBo(r, daChay) {
    const s = r.summary || {}, d = r.detail || {}, bg = d.baogia || {}, mh = d.muahang || {};
    const pt = r.tong.phai_thu, pr = r.tong.phai_tra, doi = (s.tao_moi || 0) + (s.cap_nhat || 0);
    const cau = (daChay ? 'Đã đồng bộ: tạo mới ' : 'Sẽ tạo mới ') + KD.soDem(s.tao_moi || 0) + ' khoản · cập nhật ' + KD.soDem(s.cap_nhat || 0)
      + ' · ' + KD.soDem(s.bo_qua || 0) + ' khoản không đổi.';
    const nguon = 'Báo giá: tạo ' + KD.soDem(bg.tao_moi || 0) + ', cập nhật ' + KD.soDem(bg.cap_nhat || 0)
      + ' · Mua hàng: tạo ' + KD.soDem(mh.tao_moi || 0) + ' (' + KD.soDem(mh.bo_qua || 0) + ' đơn mua đã có công nợ).';
    const bang = '<div class="kd-table-scroll"><table class="kd-table kd-table--gon kt-cn-xt__bang"><caption class="visually-hidden">Số trước và sau đồng bộ</caption><thead><tr>'
      + '<th scope="col">Chỉ tiêu</th><th scope="col" class="num">' + (daChay ? 'Trước' : 'Hiện tại') + '</th><th scope="col" class="num">Sau đồng bộ</th><th scope="col" class="num">Chênh</th></tr></thead><tbody>'
      + dongSo('Còn phải thu khách hàng', soN(pt.truoc.con_lai_doi_tac_con_no), soN(pt.sau.con_lai_doi_tac_con_no), true)
      + dongSo('Số khách còn nợ', pt.truoc.so_doi_tac_con_no, pt.sau.so_doi_tac_con_no, false)
      + dongSo('Còn phải trả NCC (ròng)', soN(pr.truoc.con_lai_rong), soN(pr.sau.con_lai_rong), true)
      + '</tbody></table></div>';
    const loai = BEN === 'kh' ? 'phai_thu' : 'phai_tra';
    const top = (r.theo_doi_tac || []).filter((x) => x.loai === loai).slice(0, 6);
    const dsTop = top.length ? '<p class="kd-meta">' + (BEN === 'kh' ? 'Khách' : 'Nhà cung cấp') + ' đổi nhiều nhất (còn nợ trước → sau):</p><ul class="kd-lines kt-cn-xt__ds">'
      + top.map((x) => '<li><span>' + esc(x.doi_tac || '—') + '</span><b class="num">' + KD.tien(soN(x.con_lai_truoc)) + ' → ' + KD.tien(soN(x.con_lai_sau)) + '</b></li>').join('') + '</ul>' : '';
    const khac = daChay && banXemTruoc && (banXemTruoc.tao_moi !== s.tao_moi || banXemTruoc.cap_nhat !== s.cap_nhat)
      ? '<p class="kd-meta">Khác bản xem trước (' + KD.soDem(banXemTruoc.tao_moi) + ' tạo · ' + KD.soDem(banXemTruoc.cap_nhat) + ' cập nhật) vì dữ liệu vừa thay đổi.</p>' : '';
    $('cnk-db-nd').hidden = daChay;
    $('cnk-db-xt').innerHTML = '<p class="kt-cn-xt__cau"><b>' + cau + '</b></p><p class="kd-meta">' + nguon + '</p>' + khac + bang + dsTop
      + canhBaoDongBo(r, daChay).map((c) => '<p class="kd-note kt-cn-xt__note">' + c + '</p>').join('')
      + (!daChay && !doi ? '<p class="kd-note">Không có gì cần đồng bộ — công nợ đã khớp Đơn hàng và Mua hàng.</p>' : '');
    return doi;
  }
  async function xemTruocDb() {
    const l = ++luotDb, ok = $('cnk-db-ok');
    ok.disabled = true; ok.hidden = false; banXemTruoc = null; $('cnk-db-huy').textContent = 'Huỷ'; $('cnk-db-nd').hidden = false;
    $('cnk-db-xt').innerHTML = '<p class="kd-meta">Đang xem trước (chưa ghi gì)…</p>';
    try {
      const r = await KD.api('/api/cong-no/sync?dry_run=true', { method: 'POST', headers: { Accept: 'application/json' } });
      if (l !== luotDb) return;
      const doi = veDongBo(r, false);
      banXemTruoc = r.summary;
      ok.hidden = !doi; ok.disabled = !doi;
    } catch (e) {
      if (l !== luotDb) return;
      $('cnk-db-xt').innerHTML = '';
      KD.baoLoiHopThoai(dlgDb, 'Chưa xem trước được: ' + e.message);
    }
  }
  $('cnk-dong-bo').addEventListener('click', () => { KD.moHopThoai(dlgDb); xemTruocDb(); });
  dlgDb.addEventListener('close', () => { luotDb++; });
  $('cnk-db-ok').addEventListener('click', async () => {
    const nut = $('cnk-db-ok'); nut.disabled = true;
    try {
      const r = await KD.api('/api/cong-no/sync', { method: 'POST', headers: { Accept: 'application/json' } });
      veDongBo(r, true);
      nut.hidden = true; $('cnk-db-huy').textContent = 'Đóng';
      const s = r.summary || {};
      window.showToast && window.showToast('ok', 'Đồng bộ công nợ xong — tạo mới ' + KD.soDem(s.tao_moi || 0) + ' · cập nhật ' + KD.soDem(s.cap_nhat || 0));
      tai();
    } catch (e) { nut.disabled = false; KD.baoLoiHopThoai(dlgDb, 'Chưa đồng bộ được (không ghi gì): ' + e.message); }
  });

  /* ── Thêm / sửa / xoá một khoản công nợ (cơ chế màn cũ /app#cong-no) ──
     Thêm: POST /api/cong-no {loai theo màn, doi_tac, ma_don, ngay, so_tien, da_tra, tai_khoan, han_thanh_toan, ghi_chu}
       — "Đã thu/trả ngay" > 0 thì bắt chọn tài khoản (máy chủ tự ghi 1 phiếu Sổ quỹ). Kế toán + CEO.
     Sửa: PUT /api/cong-no/{id} chỉ các ô đã đổi (không sửa số đã thu/trả — dùng Ghi nhận). Xoá: DELETE (kèm phiếu Sổ quỹ
       của khoản). Hai thao tác này API chỉ cho CEO/admin/trợ lý → nút gắn data-quyen="ceo". */
  const dlgF = $('cnk-dlg-f'), dlgX = $('cnk-dlg-x');
  const docTien = (v) => Number(String(v || '').replace(/[^\d]/g, '')) || 0;
  const NHAN_NGUON_TU_DONG = { baogia_quote: 'Báo giá', muahang: 'Mua hàng', muahang_po: 'Mua hàng', saleadmin_vc_phai_tra: 'Sale Admin', saleadmin_vc_phai_thu: 'Sale Admin' };
  const O_SUA = ['cnk-f-dt', 'cnk-f-ma', 'cnk-f-ngay', 'cnk-f-tien', 'cnk-f-han', 'cnk-f-gc'];
  let dangSua = null, goc = {}, dsDtNgoai = null, dsTkF = null, dangXoa = null;
  function loiF(id, cau) { const o = $(id), p = $(id + '-loi'); o.setAttribute('aria-invalid', String(!!cau)); if (p) { p.textContent = cau || ''; p.hidden = !cau; } return !cau; }
  async function napDoiTacF() {
    if (!dsDtNgoai) {
      try {
        const r = await KD.api(BEN === 'kh' ? '/api/external/customers' : '/api/external/suppliers');
        dsDtNgoai = ((r && r.data) || []).map((x) => (BEN === 'kh' ? x.ho_ten : x.name)).filter(Boolean);
      } catch (e) { dsDtNgoai = []; }
    }
    const daCo = Object.keys(BEN === 'kh' ? _rawByKeyKH : _rawByKey);
    $('cnk-f-dt-ds').innerHTML = [...new Set(daCo.concat(dsDtNgoai))].map((t) => '<option value="' + esc(t) + '"></option>').join('');
  }
  async function napTkF() {
    if (!dsTkF) { const m = await KD.api('/api/meta'); dsTkF = (m && (m.tai_khoan_nh || m.ngan_hang)) || []; }
    $('cnk-f-tk').innerHTML = '<option value="">— Chọn tài khoản —</option>' + dsTkF.map((t) => {
      const v = t.ten_tk || t.ten || t.label || t.id;
      return '<option value="' + esc(String(v)) + '">' + esc(t.ten_nh ? v + ' (' + t.ten_nh + (t.so_tk ? ' · ' + t.so_tk : '') + ')' : String(v)) + '</option>';
    }).join('');
  }
  function capNhatTkBatBuoc() { $('cnk-f-tk-bb').hidden = !(docTien($('cnk-f-da').value) > 0); }
  async function moForm(row) {
    dangSua = row || null;
    const sua = !!row;
    $('cnk-f-td').textContent = sua ? 'Sửa công nợ ' + row.id : (BEN === 'kh' ? 'Thêm công nợ phải thu' : 'Thêm công nợ phải trả');
    $('cnk-f-dt').value = sua ? (row.doi_tac || '') : '';
    $('cnk-f-ma').value = sua ? (row.ma_don || '') : '';
    $('cnk-f-ngay').value = sua ? String(row.ngay || '').slice(0, 10) : KD.iso(new Date());
    $('cnk-f-tien').value = sua ? KD.tien(Number(row.so_tien) || 0) : '';
    $('cnk-f-han').value = sua && /^\d{4}-\d{2}-\d{2}/.test(row.han_thanh_toan || '') ? String(row.han_thanh_toan).slice(0, 10) : '';
    $('cnk-f-gc').value = sua ? (row.ghi_chu || '') : '';
    $('cnk-f-da').value = ''; $('cnk-f-tk').value = '';
    $('cnk-f-tra-khoi').hidden = sua;
    $('cnk-f-da-sua').hidden = !sua;
    if (sua) $('cnk-f-da-sua').textContent = CFG.daThu + ' ' + KD.tienVnd(Number(row.da_tra) || 0) + ' — số đã ' + CFG.thu + ' không sửa ở đây, dùng "' + CFG.lap + '".';
    const tuDong = sua && NHAN_NGUON_TU_DONG[row.ref_source];
    $('cnk-f-nguon').hidden = !tuDong;
    if (tuDong) $('cnk-f-nguon').textContent = 'Khoản tự động từ ' + tuDong + (row.ref_source === 'baogia_quote' ? ': lần "Đồng bộ công nợ" sau sẽ tính lại số tiền và số đã thu theo đơn.' : '.');
    goc = {}; O_SUA.forEach((id) => { goc[id] = $(id).value; });
    ['cnk-f-dt', 'cnk-f-ngay', 'cnk-f-tk'].forEach((id) => loiF(id, ''));
    capNhatTkBatBuoc();
    KD.moHopThoai(dlgF);
    napDoiTacF();
    if (!sua) { try { await napTkF(); } catch (e) { KD.baoLoiHopThoai(dlgF, 'Không tải được danh sách tài khoản: ' + e.message); } }
  }
  ['cnk-f-tien', 'cnk-f-da'].forEach((id) => $(id).addEventListener('blur', () => { const o = $(id); o.value = o.value.trim() ? KD.tien(docTien(o.value)) : ''; }));
  $('cnk-f-da').addEventListener('input', capNhatTkBatBuoc);
  $('cnk-f-tk').addEventListener('change', () => loiF('cnk-f-tk', ''));
  ['cnk-f-dt', 'cnk-f-ngay'].forEach((id) => $(id).addEventListener('input', () => { if ($(id).value.trim()) loiF(id, ''); }));
  $('cnk-them').addEventListener('click', () => moForm(null));
  function thanSua(dt, ngay) {
    const gia = { 'cnk-f-dt': ['doi_tac', dt], 'cnk-f-ma': ['ma_don', $('cnk-f-ma').value.trim() || null], 'cnk-f-ngay': ['ngay', ngay],
      'cnk-f-tien': ['so_tien', docTien($('cnk-f-tien').value)], 'cnk-f-han': ['han_thanh_toan', $('cnk-f-han').value || null],
      'cnk-f-gc': ['ghi_chu', $('cnk-f-gc').value.trim() || null] };
    const doi = {};
    O_SUA.forEach((id) => { if ($(id).value !== goc[id]) doi[gia[id][0]] = gia[id][1]; });
    if ('so_tien' in doi) {   // như POST /api/cong-no: đã trả ≥ số tiền (> 0) → đã trả đủ
      const daTra = Number(dangSua.da_tra) || 0;
      doi.trang_thai = doi.so_tien > 0 && daTra >= doi.so_tien ? 'da_tra' : 'chua_tra';
      if (doi.trang_thai === 'da_tra' && !dangSua.ngay_tra) doi.ngay_tra = KD.iso(new Date());
    }
    return doi;
  }
  $('cnk-f').addEventListener('submit', async (e) => {
    e.preventDefault();
    const dt = $('cnk-f-dt').value.trim(), ngay = $('cnk-f-ngay').value, da = docTien($('cnk-f-da').value), tk = $('cnk-f-tk').value;
    const hop = [loiF('cnk-f-dt', dt ? '' : 'Nhập tên ' + CFG.dt + '.'), loiF('cnk-f-ngay', ngay ? '' : 'Chọn ngày phát sinh.'),
      dangSua ? true : loiF('cnk-f-tk', da > 0 && !tk ? 'Có số đã ' + CFG.thu + ' thì phải chọn tài khoản để ghi Sổ quỹ.' : '')].every(Boolean);
    if (!hop) return;
    const nut = $('cnk-f-ok'); nut.disabled = true;
    try {
      let kq;
      if (dangSua) {
        const doi = thanSua(dt, ngay);
        if (!Object.keys(doi).length) { dlgF.close(); return; }
        kq = await KD.api('/api/cong-no/' + encodeURIComponent(dangSua.id), { method: 'PUT', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(doi) });
      } else {
        kq = await KD.api('/api/cong-no', KD.JSON_POST({
          loai: CFG.loai, doi_tac: dt, ma_don: $('cnk-f-ma').value.trim() || null, ngay,
          so_tien: docTien($('cnk-f-tien').value), da_tra: da, tai_khoan: da > 0 ? tk : null,
          han_thanh_toan: $('cnk-f-han').value || null, ghi_chu: $('cnk-f-gc').value.trim() || null,
        }));
      }
      dlgF.close();
      window.showToast && window.showToast('ok', (dangSua ? 'Đã sửa ' : 'Đã thêm ') + kq.id + ' — ' + kq.doi_tac + ' ' + KD.tienVnd(Number(kq.so_tien) || 0));
      panel.dong(); tai();
    } catch (err) { KD.baoLoiHopThoai(dlgF, 'Chưa lưu được: ' + err.message); } finally { nut.disabled = false; }
  });
  async function suaKhoan(id) {
    try { moForm(await KD.api('/api/cong-no/' + encodeURIComponent(id))); } catch (e) { window.showToast && window.showToast('err', 'Không tải được khoản ' + id + ': ' + e.message); }
  }
  async function xoaKhoan(id) {
    try { dangXoa = await KD.api('/api/cong-no/' + encodeURIComponent(id)); } catch (e) { window.showToast && window.showToast('err', 'Không tải được khoản ' + id + ': ' + e.message); return; }
    const x = dangXoa;
    $('cnk-x-nd').textContent = x.id + ' · ' + (x.doi_tac || '') + (x.ma_don ? ' · ' + x.ma_don : '') + ' · số tiền ' + KD.tienVnd(Number(x.so_tien) || 0)
      + ', đã ' + CFG.thu + ' ' + KD.tienVnd(Number(x.da_tra) || 0) + '. Phiếu Sổ quỹ đã ghi từ khoản này cũng bị xoá.'
      + (x.ref_source === 'baogia_quote' ? ' Khoản tự động từ Báo giá: lần đồng bộ sau sẽ tạo lại nếu đơn còn duyệt.' : '');
    KD.moHopThoai(dlgX);
  }
  $('cnk-x-ok').addEventListener('click', async () => {
    const nut = $('cnk-x-ok'); nut.disabled = true;
    try {
      await KD.api('/api/cong-no/' + encodeURIComponent(dangXoa.id), { method: 'DELETE', headers: { Accept: 'application/json' } });
      dlgX.close(); window.showToast && window.showToast('ok', 'Đã xoá ' + dangXoa.id); panel.dong(); tai();
    } catch (e) { KD.baoLoiHopThoai(dlgX, 'Chưa xoá được: ' + e.message); } finally { nut.disabled = false; }
  });
  $('cnk-panel').addEventListener('click', (e) => { const gn = e.target.closest('[data-gnt-dt]'); if (gn) moGhiNhan(gn.dataset.gntDt, gn.dataset.gntKhoan); });

  /* ── Panel xem nhanh ── */
  const panel = KT.ganPanel({ main: $('cnk-main'), panel: $('cnk-panel'), scrim: $('cnk-scrim'), nutDong: $('cnk-p-dong') });
  let luotP = 0;
  async function moKhach(tr) {
    const id = tr.dataset.id; panel.mo(tr);
    const nd = $('cnk-p-noi-dung'), nut = $('cnk-p-nut'), l = ++luotP;
    nd.innerHTML = KD.KHUNG_TAI; nut.innerHTML = '';
    try {
      const ct = await layChiTiet(id); if (l !== luotP) return;
      const k = ct.khach, con = ct.phieu.filter((p) => p.con_lai > 0);
      // Đối chiếu trong panel (BRIEF2): "Còn phải trả/thu" là số RÒNG của đối tượng, còn danh sách
      // "Hoá đơn còn nợ" chỉ gồm khoản con_lai > 0 — vd CHIẾN PHƯƠNG: ròng 350.717.049 nhưng các
      // hoá đơn còn nợ cộng 728.717.049 vì có 378.000.000 trả trước/ứng (dòng so_tien 0, da_tra > 0)
      // chưa cấn trừ vào hoá đơn cụ thể. Hiện dòng cộng + phần bù trừ để hai số khớp nhau.
      const tongCon = con.reduce((a, p) => a + p.con_lai, 0), traTruoc = ct.phieu.reduce((a, p) => a + (p.con_lai < 0 ? p.con_lai : 0), 0);
      const chanCon = con.length && traTruoc ? '<p class="kt-p-doi-chieu">Cộng hoá đơn còn nợ <b class="num">' + KD.tienVnd(tongCon) + '</b><br>Trả trước/ứng chưa cấn trừ vào hoá đơn <b class="num">' + KD.tienVnd(traTruoc) + '</b><br>= ' + CFG.conLai + ' <b class="num">' + KD.tienVnd(tongCon + traTruoc) + '</b></p>' : '';
      nd.innerHTML = '<div class="kt-p-khach"><span class="kd-avatar" aria-hidden="true">' + esc(initials(k.ten)) + '</span><div>'
        + '<p class="kt-p-ten">' + esc(k.ten) + '</p><div class="kd-chips">' + (k.ma ? '<span class="kd-chip kd-chip--xam">' + esc(k.ma) + '</span>' : '') + pillTuoi(ct.nhom_tuoi) + '</div></div></div>'
        + (k.sdt || k.nv_kd ? '<dl class="kd-kv">'
          + (k.sdt ? '<dt><i class="bi bi-telephone kd-kv__icon" aria-hidden="true"></i><span class="kd-kv__label">Điện thoại</span></dt><dd><a class="kd-tel" href="tel:' + esc(k.sdt) + '">' + esc(k.sdt) + '</a></dd>' : '')
          + (k.nv_kd ? '<dt><i class="bi bi-person-badge kd-kv__icon" aria-hidden="true"></i><span class="kd-kv__label">' + (BEN === 'ncc' ? 'NV Mua Hàng' : 'NV Kinh Doanh') + '</span></dt><dd>' + esc(k.nv_kd) + '</dd>' : '')
          + '</dl>' : '')
        + '<section class="kd-block" aria-labelledby="cnk-p-h1"><h3 class="kd-block__title" id="cnk-p-h1"><i class="bi bi-cash-stack" aria-hidden="true"></i>Tổng quan đến ' + KD.ngay(ngayTinh()) + '</h3>'
        + '<dl class="kt-tq"><dt>Tổng nợ phát sinh</dt><dd>' + KD.tienVnd(ct.tong_no) + '</dd><dt>' + CFG.daThu + '</dt><dd>' + KD.tienVnd(ct.da_thu) + '</dd>'
        + '<dt class="is-dam">' + CFG.conLai + '</dt><dd>' + KD.tienVnd(ct.con_lai) + '</dd>'
        + '<dt>Trong đó quá hạn</dt><dd class="' + (ct.qua_han ? 'kt-so--qua-han' : '') + '">' + KD.tienVnd(ct.qua_han) + '</dd>'
        + (BEN === 'ncc' ? '<dt>Nợ thực phải trả</dt><dd>' + KD.tienVnd(ct.no_thuc) + '</dd><dt>Nợ dự kiến</dt><dd>' + KD.tienVnd(ct.no_du_kien) + '</dd><dt>Số đơn</dt><dd>' + moTaSoDon(ct.so_don) + '</dd>' : '')
        + '</dl></section>'
        + '<section class="kd-block" aria-labelledby="cnk-p-h2"><h3 class="kd-block__title" id="cnk-p-h2"><i class="bi bi-receipt" aria-hidden="true"></i>Hoá đơn còn nợ <span class="kd-muted">' + KD.soDem(con.length) + '</span></h3>'
        + (con.length ? '<ul class="kd-lines kt-lines-2">' + con.map((p) => '<li><span class="kd-strong">' + esc(p.so_phieu) + '</span><b class="num">' + KD.tienVnd(p.con_lai) + '</b>'
          + '<span class="kd-lines__sub">Hạn ' + (p.han_tt ? KD.ngay(p.han_tt) : '—') + ' · ' + pillPhieu(p.trang_thai, p.trang_thai === 'qua_han' ? 'Quá hạn ' + KD.soDem(p.qua_han_ngay) + ' ngày' : '')
          + ' <button type="button" class="kd-link kd-link--sm" data-gnt-dt="' + esc(k.id) + '" data-gnt-khoan="' + esc(String(p.id)) + '">' + CFG.lap + '</button></span></li>').join('') + '</ul>' + chanCon
          : KD.khoiRong('Không còn hoá đơn nào phải ' + CFG.thu, ''))
        + '</section>'
        + '<section class="kd-block" aria-labelledby="cnk-p-h3"><h3 class="kd-block__title" id="cnk-p-h3"><i class="bi bi-box-arrow-in-down" aria-hidden="true"></i>' + CFG.lsTieuDe + '</h3>'
        + (ct.lich_su_thu.length ? '<ul class="kd-lines">' + ct.lich_su_thu.map((t) => '<li><span>' + esc(t.so_ct) + '</span><b class="num">' + KD.tienVnd(t.so_tien) + '</b><span class="kd-lines__sub">' + KD.ngay(t.ngay) + ' · ' + esc(t.hinh_thuc || '—') + '</span></li>').join('') + '</ul>'
          : KD.khoiRong(CFG.lsRong[0], CFG.lsRong[1]))
        + '</section>';
      nut.innerHTML = '<button type="button" class="kd-btn kd-btn--grow kd-btn--primary" data-gnt-dt="' + esc(k.id) + '"' + (con.length ? '' : ' disabled') + '><i class="bi bi-cash-coin" aria-hidden="true"></i>' + CFG.lap + '</button>'
        + '<a class="kd-btn kd-btn--grow" href="' + soChiTiet(k) + '"><i class="bi bi-journal-text" aria-hidden="true"></i>Sổ chi tiết</a>';
    } catch (e) {
      if (l !== luotP) return;
      KD.khoiLoi(nd, 'Không tải được công nợ của ' + CFG.dt, e, () => moKhach(tr));
    }
  }

  /* ── Sự kiện bảng ── */
  $('cnk-tbody').addEventListener('click', (e) => {
    const su = e.target.closest('[data-sua-cn]'); if (su) { e.stopPropagation(); suaKhoan(su.dataset.suaCn); return; }
    const xo = e.target.closest('[data-xoa-cn]'); if (xo) { e.stopPropagation(); xoaKhoan(xo.dataset.xoaCn); return; }
    const gn = e.target.closest('[data-gnt-dt]'); if (gn) { e.stopPropagation(); moGhiNhan(gn.dataset.gntDt, gn.dataset.gntKhoan); return; }
    const mo = e.target.closest('[data-mo]'); if (mo) { e.stopPropagation(); doiMoRong(mo.dataset.mo); return; }
    const m = e.target.closest('[data-menu]');
    if (m) {
      const r = dsDong.find((x) => String(x.khach.id) === m.dataset.menu); if (!r) return;
      KD.menu(m, [
        { nhan: dangMo.has(m.dataset.menu) ? 'Thu gọn hoá đơn' : 'Xem hoá đơn còn nợ', icon: 'bi-receipt', onClick: () => doiMoRong(m.dataset.menu) },
        { nhan: 'Sổ chi tiết công nợ', icon: 'bi-journal-text', href: soChiTiet(r.khach) },
        { nhan: BEN === 'kh' ? 'Hồ sơ khách (Kinh doanh)' : 'Hồ sơ nhà cung cấp (Mua hàng)', icon: 'bi-person-vcard', href: CFG.chiTietHref + encodeURIComponent(r.khach.id) },
        '-',
        { nhan: CFG.lap, icon: 'bi-cash-coin', onClick: () => moGhiNhan(r.khach.id) },
      ]);
    }
  });
  KT.ganDongBang($('cnk-tbody'), moKhach, (tr) => { location.href = '/ketoan/doi-tuong?ben=' + BEN + '&id=' + encodeURIComponent(tr.dataset.id); });
  KT.ganSapXep($('cnk-thead'), () => st.sort, (s) => { st.sort = s; st.page = 1; tai(); });

  /* ── Lọc ── */
  function doiLoc() { st.page = 1; panel.dong(); dangMo.clear(); tai(); }
  function datLai() {
    Object.assign(st, { tim: '', tinh_trang: MAC_DINH.tinh_trang, tu: '', den_ngay: '', nhom: 'all', thang: '' });
    $('cnk-tim').value = ''; $('cnk-tt').value = MAC_DINH.tinh_trang; $('cnk-tu').value = ''; $('cnk-den').value = '';
    if (BEN === 'ncc') { $('cnk-nhom').value = 'all'; $('cnk-thang').value = ''; }
    doiLoc();
  }
  $('cnk-tim').addEventListener('input', KD.debounce(() => { st.tim = $('cnk-tim').value.trim(); doiLoc(); }, 350));
  $('cnk-tt').addEventListener('change', (e) => { st.tinh_trang = e.target.value; doiLoc(); });
  $('cnk-tu').addEventListener('change', (e) => { st.tu = e.target.value; if (st.tu && BEN === 'ncc') { st.thang = ''; $('cnk-thang').value = ''; } doiLoc(); });
  if (BEN === 'ncc') {
    $('cnk-nhom').addEventListener('change', (e) => { st.nhom = e.target.value; doiLoc(); });
    // Như màn cũ: chọn tháng thì bỏ khoảng ngày (máy chủ ưu tiên `thang` nếu gửi cả hai).
    $('cnk-thang').addEventListener('change', (e) => { st.thang = e.target.value; if (st.thang) { st.tu = ''; $('cnk-tu').value = ''; } doiLoc(); });
  }
  $('cnk-den').addEventListener('change', (e) => { st.den_ngay = e.target.value; doiLoc(); });
  $('cnk-dat-lai').addEventListener('click', datLai);
  $('cnk-co-trang').addEventListener('change', (e) => { st.size = +e.target.value; doiLoc(); });
  loc.addEventListener('submit', (e) => e.preventDefault());
  $('cnk-xuat').addEventListener('click', (e) => { if (CFG.xuatChuaCo) { e.preventDefault(); (window.showToast ? window.showToast('info', 'Chưa có chức năng xuất Excel cho màn này') : null); } });

  tai();
})();
