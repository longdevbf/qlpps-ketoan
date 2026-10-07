"""Khai nguồn số liệu cho từng dòng của 3 báo cáo tài chính (Đợt 1 — 07/10/2026).

Mục đích: người đọc báo cáo biết mỗi con số lấy từ SỔ CÁI (journal_line, theo mã tài khoản) hay
từ BẢNG NGHIỆP VỤ (doanh_thu, chi_phi_phat_sinh, cong_no, so_quy…). Hai nguồn này hiện chưa được
đối chiếu tự động với nhau — xem màn /ketoan/doi-chieu.

Mỗi mục: khoá = đường dẫn của dòng trong JSON báo cáo (đúng khoá `khoa` mà giao diện dùng để mở
popup chi tiết), giá trị là dict:
  loai  : 'so_cai'    — đọc từ sổ cái theo `tk`
          'nghiep_vu' — đọc từ bảng nghiệp vụ `bang`; `tk` là tài khoản TƯƠNG ỨNG nhưng CHƯA đọc
          'tron'      — Cân đối kế toán chế độ auto: tính cả hai, lấy số lớn hơn (xem bao_cao_can_doi)
          'cong_thuc' — dòng tổng/hiệu của các dòng khác
          'chua_tinh' — code đang gán cứng 0, chưa có nguồn nào
  tk    : list mã tài khoản liên quan
  bang  : mô tả bảng nghiệp vụ (None nếu không có)

Chỉ là MÔ TẢ — không module nào dùng bảng này để tính số. Sửa cách tính ở pl_calculator /
bao_cao_can_doi / bao_cao_cashflow thì sửa luôn mô tả ở đây.
"""

_SO_QUY = "ketoan.so_quy (phiếu thu/chi, phân loại theo phan_loai_cf)"


def _nv(tk: list[str], bang: str) -> dict:
    return {"loai": "nghiep_vu", "tk": tk, "bang": bang}


def _ct(tk: list[str] | None = None) -> dict:
    return {"loai": "cong_thuc", "tk": tk or [], "bang": None}


# ─── Kết quả kinh doanh (GET /api/bao-cao/pl) — app/services/pl_calculator.py ─────────────────
NGUON_KQKD: dict[str, dict] = {
    "doanh_thu.dt_thuc_hien": _nv(["511"], "baogia.quotes của đơn hoàn thành (saleadmin.vanchuyen); "
                                           "tháng không có đơn hoàn thành thì lấy ketoan.doanh_thu (tiền thu)"),
    "doanh_thu.chiet_khau": {"loai": "chua_tinh", "tk": ["511"], "bang": None},
    "doanh_thu.giam_tru": _nv(["511"], "ketoan.chi_phi_phat_sinh có tên 'hoàn tiền'"),
    "doanh_thu.giam_tru_tong": _nv(["511"], "ketoan.chi_phi_phat_sinh có tên 'hoàn tiền'"),
    "dt_thuan": _ct(["511"]),
    "cogs": _nv(["632"], "ketoan.cong_no (phai_tra) của đơn hoàn thành; không có thì ketoan.inventory_movement (xuất)"),
    "ln_gop": _ct(),
    "dt_tai_chinh": {"loai": "chua_tinh", "tk": ["515"], "bang": None},
    "cp_tai_chinh.tong": _ct(["635"]),
    "cp_tai_chinh.lai_vay": _nv(["635"], "ketoan.khoan_vay_giao_dich (trả lãi)"),
    "cp_tai_chinh.phi_nh": _nv(["635"], "ketoan.chi_phi_phat_sinh nhóm tai_chinh trừ lãi vay"),
    "cp_tai_chinh.khac": {"loai": "chua_tinh", "tk": ["635"], "bang": None},
    "cp_ban_hang.tong": _ct(["641"]),
    "cp_ban_hang.bien_phi.tong": _ct(["641"]),
    "cp_ban_hang.bien_phi.hoa_hong": _nv(["641"], "hcns.payroll (hoa hồng KD/MKT)"),
    "cp_ban_hang.bien_phi.luong_ot": _nv(["641"], "hcns.payroll (lương làm thêm KD/MKT)"),
    "cp_ban_hang.bien_phi.ads": _nv(["641"], "ketoan.ads_phan_bo_don → ketoan.chi_phi_phat_sinh → marketing.ads_cost"),
    "cp_ban_hang.bien_phi.van_chuyen": _nv(["641"], "saleadmin.vanchuyen"),
    "cp_ban_hang.bien_phi.khuyen_mai": _nv(["641"], "ketoan.chi_phi_phat_sinh (lọc theo tên)"),
    "cp_ban_hang.bien_phi.khac": _nv(["641"], "ketoan.chi_phi_phat_sinh nhóm bán hàng còn lại"),
    "cp_ban_hang.dinh_phi.tong": _ct(["641"]),
    "cp_ban_hang.dinh_phi.luong_co_ban_kd_mkt": _nv(["641"], "hcns.payroll (lương cơ bản KD/MKT × hệ số BHXH)"),
    "cp_ban_hang.dinh_phi.thue_showroom": _nv(["641"], "ketoan.chi_phi_co_dinh nhóm bán hàng, tên có 'thuê'"),
    "cp_ban_hang.dinh_phi.khau_hao_tscd_bh": _nv(["641", "214"], "ketoan.khau_hao_log (TSCĐ bộ phận bán hàng)"),
    "cp_ban_hang.dinh_phi.phi_thuong_xuyen": _nv(["641"], "ketoan.chi_phi_co_dinh nhóm bán hàng"),
    "cp_quan_ly.tong": _ct(["642"]),
    "cp_quan_ly.bien_phi.tong": _ct(["642"]),
    "cp_quan_ly.bien_phi.vpp": _nv(["642"], "ketoan.chi_phi_phat_sinh (lọc theo tên)"),
    "cp_quan_ly.bien_phi.dao_tao": _nv(["642"], "ketoan.chi_phi_phat_sinh (lọc theo tên)"),
    "cp_quan_ly.bien_phi.hoi_hop_cong_tac": _nv(["642"], "ketoan.chi_phi_phat_sinh (lọc theo tên)"),
    "cp_quan_ly.bien_phi.qua_bieu": _nv(["642"], "ketoan.chi_phi_phat_sinh (lọc theo tên)"),
    "cp_quan_ly.bien_phi.khac": _nv(["642"], "ketoan.chi_phi_phat_sinh nhóm quản lý còn lại"),
    "cp_quan_ly.dinh_phi.tong": _ct(["642"]),
    "cp_quan_ly.dinh_phi.luong_co_ban_hcns_kt_ceo": _nv(["642"], "hcns.payroll; bảng lương rỗng thì ketoan.chi_phi_phat_sinh"),
    "cp_quan_ly.dinh_phi.thue_vp": _nv(["642"], "ketoan.chi_phi_co_dinh nhóm quản lý, tên có 'thuê'"),
    "cp_quan_ly.dinh_phi.dien_nuoc_vp": _nv(["642"], "ketoan.chi_phi_co_dinh"),
    "cp_quan_ly.dinh_phi.internet_dien_thoai": _nv(["642"], "ketoan.chi_phi_co_dinh"),
    "cp_quan_ly.dinh_phi.khau_hao_tscd_ql": _nv(["642", "214"], "ketoan.khau_hao_log (TSCĐ bộ phận quản lý)"),
    "cp_quan_ly.dinh_phi.dich_vu_kt_luat": _nv(["642"], "ketoan.chi_phi_co_dinh"),
    "cp_quan_ly.dinh_phi.phi_khac": _nv(["642"], "ketoan.chi_phi_co_dinh"),
    "ln_thuan_hdkd": _ct(),
    "thu_nhap_khac": {"loai": "so_cai", "tk": ["711"], "bang": None},
    "cp_khac": {"loai": "tron", "tk": ["811"], "bang": "ketoan.chi_phi_phat_sinh nhóm khac + sổ cái TK 811 (cộng cả hai)"},
    "ln_khac": _ct(),
    "ln_truoc_thue": _ct(),
    "thue_tndn": {"loai": "cong_thuc", "tk": ["821"], "bang": "Lợi nhuận trước thuế × 20% — không đọc TK 821"},
    "lnst": _ct(),
}

# ─── Lưu chuyển tiền tệ (GET /api/bao-cao/cashflow) — app/routers/bao_cao_cashflow.py ────────
# Mọi khoản mục đọc từ sổ quỹ, KHÔNG đọc sổ cái TK 111/112. Riêng vay/trả nợ cộng thêm sổ vay.
_KHOAN_LCTT = {
    "operating": ("thu_kh", "tra_ncc", "tra_ads", "tra_luong", "tra_lai_vay", "nop_thue_tndn",
                  "thu_khac", "chi_khac"),
    "investing": ("mua_ccdc", "sua_chua", "thanh_ly_tscd", "chi_cho_vay", "thu_hoi_cho_vay",
                  "chi_gop_von", "thu_hoi_gop_von", "thu_lai"),
    "financing": ("nhan_von", "tra_von", "vay_nh", "tra_no_nh", "tra_goc_thue_tc", "chia_co_tuc"),
}
NGUON_LCTT: dict[str, dict] = {
    f"{nhom}.{k}": _nv(["111", "112"], _SO_QUY)
    for nhom, ds in _KHOAN_LCTT.items() for k in ds
}
NGUON_LCTT["operating.chi_khac"] = _nv(["111", "112"], _SO_QUY + " — phần chi còn lại chưa phân loại")
# Hai khoản vay cộng thêm sổ vay → loại riêng để giao diện vẫn gắn nhãn (các dòng còn lại chỉ ghi
# nguồn chung một lần ở đầu bảng — xem nguonChung trong kt-lctt.js).
for _k in ("financing.vay_nh", "financing.tra_no_nh"):
    NGUON_LCTT[_k] = {"loai": "tron", "tk": ["311", "341"], "bang": _SO_QUY + " + ketoan.khoan_vay_giao_dich (sổ vay)"}
for _k in ("operating.net", "investing.net", "financing.net", "net_cashflow", "so_du_cuoi_ky"):
    NGUON_LCTT[_k] = _ct()
NGUON_LCTT["so_du_dau_ky"] = _nv(["111", "112"], "ketoan.so_du_dau_ky + ketoan.so_quy trước kỳ")

# ─── Cân đối kế toán (GET /api/bao-cao/can-doi) — app/routers/bao_cao_can_doi.py ─────────────
# Chế độ auto lấy MAX(sổ cái, bảng nghiệp vụ) cho từng dòng; router tự điền `so_cai`,
# `nghiep_vu`, `dang_dung` theo số thật của kỳ. Ở đây chỉ khai tài khoản + bảng.
NGUON_CDKT: dict[str, dict] = {
    "tai_san.tien_va_td.tien_mat_so_quy": _nv(["111"], "ketoan.so_quy (tiền mặt) + số dư đầu kỳ"),
    "tai_san.tien_va_td.tk_ngan_hang": _nv(["112"], "ketoan.tai_khoan_nh + ketoan.so_du_dau_ky + ketoan.so_quy"),
    "tai_san.tien_va_td.tong": _ct(["111", "112"]),
    "tai_san.phai_thu": {"loai": "tron", "tk": ["131", "141"], "bang": "ketoan.cong_no (phai_thu); tạm ứng 141 chỉ có ở sổ cái"},
    "tai_san.hang_ton_kho": {"loai": "tron", "tk": ["156"], "bang": "ketoan.inventory_movement (nhập − xuất)"},
    "tai_san.tscd_nguyen_gia": {"loai": "tron", "tk": ["211", "213"], "bang": "ketoan.tai_san_co_dinh (nguyên giá)"},
    "tai_san.tscd_hao_mon_luy_ke": {"loai": "tron", "tk": ["214"], "bang": "ketoan.khau_hao_log"},
    "tai_san.tscd_rong": _ct(["211", "213", "214"]),
    "tai_san.tong_tai_san": _ct(),
    "nguon_von.no_phai_tra.phai_tra_ncc": {"loai": "tron", "tk": ["331"], "bang": "ketoan.cong_no (phai_tra, nợ thực)"},
    "nguon_von.no_phai_tra.vay_ngan_han": {"loai": "tron", "tk": ["311"], "bang": "ketoan.khoan_vay + ketoan.khoan_vay_giao_dich"},
    "nguon_von.no_phai_tra.vay_dai_han": {"loai": "tron", "tk": ["341"], "bang": "ketoan.khoan_vay + ketoan.khoan_vay_giao_dich"},
    "nguon_von.no_phai_tra.phai_tra_nv": {"loai": "so_cai", "tk": ["334"], "bang": None},
    "nguon_von.no_phai_tra.tong": _ct(),
    "nguon_von.von_csh.von_gop": {"loai": "tron", "tk": ["411"], "bang": "ketoan.von_chu_so_huu"},
    "nguon_von.von_csh.quy_dn": {"loai": "tron", "tk": ["414", "415", "353"], "bang": "ketoan.quy_dn (so_du)"},
    "nguon_von.von_csh.ln_giu_lai": {"loai": "tron", "tk": ["421"], "bang": "ketoan.ky_ke_toan (LN giữ lại cuối kỳ đã chốt)"},
    "nguon_von.von_csh.tong": _ct(),
    "nguon_von.tong_nguon_von": _ct(),
}

# Nhãn hiển thị của các dòng Cân đối có thể đối chiếu hai nguồn — dùng cho màn Đối chiếu và câu
# "nguyên nhân lệch" (luật frontend: không lộ khoá kỹ thuật như tai_san.phai_thu ra màn hình).
NHAN_CDKT: dict[str, str] = {
    "tai_san.tien_va_td.tien_mat_so_quy": "Tiền mặt",
    "tai_san.tien_va_td.tk_ngan_hang": "Tiền gửi ngân hàng",
    "tai_san.phai_thu": "Phải thu ngắn hạn (gồm tạm ứng)",
    "tai_san.hang_ton_kho": "Hàng tồn kho",
    "tai_san.tscd_nguyen_gia": "TSCĐ — nguyên giá",
    "tai_san.tscd_hao_mon_luy_ke": "TSCĐ — hao mòn luỹ kế",
    "nguon_von.no_phai_tra.phai_tra_ncc": "Phải trả người bán",
    "nguon_von.no_phai_tra.vay_ngan_han": "Vay ngắn hạn",
    "nguon_von.no_phai_tra.vay_dai_han": "Vay dài hạn",
    "nguon_von.no_phai_tra.phai_tra_nv": "Phải trả người lao động",
    "nguon_von.von_csh.von_gop": "Vốn góp chủ sở hữu",
    "nguon_von.von_csh.quy_dn": "Các quỹ",
    "nguon_von.von_csh.ln_giu_lai": "Lợi nhuận chưa phân phối",
}
