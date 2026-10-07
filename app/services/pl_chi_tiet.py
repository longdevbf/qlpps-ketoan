"""Chi tiết từng dòng Kết quả kinh doanh — "con số này ở đâu ra".

Vì sao có file này (05/10/2026, giám đốc yêu cầu)
─────────────────────────────────────────────────
Báo cáo chỉ hiện tên dòng + số tiền. Không ai lần được số đó gom từ chứng từ nào,
nên cũng không ai cãi được khi nó sai — mà phiên rà soát 05/10 cho thấy nó sai thật
(trả gốc 676.190.483đ bị ghi thành lãi vay, nằm im trong dòng "Chi phí tài chính"
suốt 5 tháng). Màn này mở popup liệt kê đúng những dòng gốc đã cộng nên con số.

NGUYÊN TẮC BẤT BIẾN — đọc trước khi sửa
───────────────────────────────────────
Mỗi khoản khai MỘT mệnh đề `tu_bang` (FROM + WHERE). Tổng và danh sách chi tiết
chạy trên CHÍNH mệnh đề đó:

    tổng   = SELECT SUM(cot_tien), COUNT(*)  FROM {tu_bang}
    chi tiết = SELECT {chon}                 FROM {tu_bang} ORDER BY … OFFSET … LIMIT …

Tuyệt đối KHÔNG viết câu riêng cho popup rồi mong nó khớp số trên báo cáo. Hai câu
truy vấn song song là cách chắc chắn nhất để sinh ra đúng loại lỗi file này sinh ra
để đi tìm. Phân trang chỉ cắt phần HIỂN THỊ — `tong`/`so_dong` luôn tính trên toàn bộ
tập khớp.

Những khoản mà số trên báo cáo KHÔNG phải tổng thuần của bộ lọc (vd "Biến phí khác"
= bộ lọc rộng trừ đi các dòng con) khai thêm `dieu_chinh`: popup hiện rõ trừ cái gì,
cộng lại phải đúng số trên dòng.

Định phí phân bổ (`chi_phi_co_dinh`, 6 phương pháp, tính trong Python), lương
(`hcns.payroll`) và ads phân bổ CHƯA có ở đây — làm sau, vì muốn khớp từng đồng thì
phải sửa các hàm phân bổ trả về phần đóng góp của từng dòng chứ không chỉ trả tổng.
Khoá nào chưa khai thì endpoint trả 404 có thông báo rõ, KHÔNG đoán bừa.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from .pl_calculator import (
    calc_pl_for_month,
    BH_PB_KEYS,
    BHXH_CTY_MULTIPLIER,
    _ads_phan_bo_table_exists,
    _sum_ads,
    _sum_ads_phan_bo_thang,
    _sum_co_dinh_method_dispatcher,
    _sum_cp_phat_sinh_filter,
    _sum_payroll_split,
    _where_cp_phat_sinh,
    rows_co_dinh_duong_thang,
)

SO_DONG_MAC_DINH = 50
SO_DONG_TOI_DA = 200

# Cột hiển thị dùng lại nhiều lần
_C_NGAY = {"key": "ngay", "nhan": "Ngày", "kieu": "ngay"}
_C_TIEN = {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}


def _thangs(tu: date, den: date) -> list[str]:
    """Các tháng 'YYYY-MM' chạm khoảng [tu, den] — cho nguồn ghi theo tháng."""
    out, y, m = [], tu.year, tu.month
    while (y, m) <= (den.year, den.month):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


# ── Mảnh FROM+WHERE dùng lại ──────────────────────────────────────────────────
# Đơn hoàn thành trong kỳ — ĐÚNG định nghĩa của _sum_doanh_thu_thuc_hien/_sum_cogs:
# ngày chốt = ketoan_approved_at → ngay_giao → updated_at (lấy cái đầu tiên có).
_DON_HOAN_THANH = """
    SELECT DISTINCT ma_don FROM saleadmin.vanchuyen
    WHERE trang_thai = 'hoan_thanh'
      AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) >= :tu
      AND COALESCE(ketoan_approved_at::date, ngay_giao, updated_at::date) <= :den
"""


def _cp(nhan: str, giai_thich: str, **loc: Any) -> dict[str, Any]:
    """Khoản lấy từ `chi_phi_phat_sinh` — dùng CHUNG bộ lọc với pl_calculator."""
    return {
        "nhan": nhan,
        "nguon": "ketoan.chi_phi_phat_sinh",
        "giai_thich": giai_thich,
        "loc_cp": loc,
        "cot_tien": "so_tien",
        "chon": ("id, ngay, so_tien, COALESCE(loai_chi_phi,'') AS loai_chi_phi, "
                 "COALESCE(ten_khoan,'') AS ten_khoan, COALESCE(nhom_chi_phi,'') AS nhom_chi_phi, "
                 "COALESCE(nguoi_chi,'') AS nguoi_chi, COALESCE(ma_don,'') AS ma_don, "
                 "COALESCE(ghi_chu,'') AS ghi_chu"),
        "sap_xep": "ngay DESC, id DESC",
        "cot": [_C_NGAY, {"key": "loai_chi_phi", "nhan": "Loại chi phí"},
                {"key": "ten_khoan", "nhan": "Nội dung"},
                {"key": "nguoi_chi", "nhan": "Người chi"},
                {"key": "ma_don", "nhan": "Mã đơn"}, _C_TIEN],
    }


_QL_EXCLUDE_NCC = [
    "%ncc%", "%nhà cung cấp%", "%nha cung cap%",
    "%mua hàng%", "%mua hang%", "%công nợ%", "%cong no%",
    "%lương%", "%luong%",
    "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%",
    "%hoàn tiền%", "%hoan tien%",
]
_BH_EXCLUDE = [
    "%khuyến mãi%", "%khuyen mai%",
    "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%",
    "%hoàn tiền%", "%hoan tien%",
]

KHOAN: dict[str, dict[str, Any]] = {
    # ── Doanh thu ─────────────────────────────────────────────────────────────
    "doanh_thu.dt_thuc_hien": {
        "nhan": "Doanh thu bán hàng và cung cấp dịch vụ",
        "nguon": "baogia.quotes · đơn hoàn thành trong kỳ",
        "giai_thich": ("Tổng giá trị đơn (chưa VAT) của các đơn có vận chuyển chuyển sang "
                       "'hoàn thành' trong kỳ. Cùng tập đơn với Giá vốn."),
        "tu_bang": f"baogia.quotes q WHERE q.quote_number IN ({_DON_HOAN_THANH})",
        "cot_tien": "q.tong_chua_thue",
        "chon": ("q.quote_number AS ma_don, q.customer_name, q.salesperson, "
                 "q.ngay_hoan_thanh AS ngay, q.tong_chua_thue AS so_tien, "
                 "q.tong_don, COALESCE(q.discount_amount,0) AS giam_gia"),
        "sap_xep": "q.tong_chua_thue DESC, q.quote_number",
        "cot": [{"key": "ma_don", "nhan": "Mã đơn"}, {"key": "customer_name", "nhan": "Khách hàng"},
                {"key": "salesperson", "nhan": "Nhân viên"}, _C_NGAY,
                {"key": "giam_gia", "nhan": "Giảm giá", "kieu": "tien"}, _C_TIEN],
        # Kỳ chưa có đơn nào hoàn thành (vd tháng đang chạy dở) → báo cáo quay về
        # `ketoan.doanh_thu` = tiền THU thực. Chi tiết phải đi theo đúng nhánh đó.
        "du_phong": {
            "nguon": "ketoan.doanh_thu · tiền thu thực (kỳ chưa có đơn hoàn thành)",
            "tu_bang": ("ketoan.doanh_thu dt WHERE dt.ngay >= :tu AND dt.ngay <= :den "
                        "AND COALESCE(dt.loai, '') NOT IN ('Hoàn Tiền', 'Hoan Tien')"),
            "cot_tien": "dt.so_tien",
            "chon": ("dt.id, dt.ngay, dt.so_tien, COALESCE(dt.ma_don,'') AS ma_don, "
                     "COALESCE(dt.nv_kinh_doanh,'') AS nv_kinh_doanh, "
                     "COALESCE(dt.loai_thanh_toan,'') AS loai_thanh_toan, "
                     "COALESCE(dt.mo_ta,'') AS mo_ta"),
            "sap_xep": "dt.ngay DESC, dt.id DESC",
            "cot": [_C_NGAY, {"key": "ma_don", "nhan": "Mã đơn"},
                    {"key": "nv_kinh_doanh", "nhan": "Nhân viên"},
                    {"key": "loai_thanh_toan", "nhan": "Hình thức"},
                    {"key": "mo_ta", "nhan": "Diễn giải"}, _C_TIEN],
        },
    },
    "doanh_thu.giam_tru": _cp(
        "Hoàn tiền khách (giảm trừ doanh thu)",
        "Các khoản hoàn tiền của đơn ĐÃ ghi doanh thu — trừ thẳng vào doanh thu, không tính là chi phí.",
        name_like_any=["%hoàn tiền%", "%hoan tien%"], also_ten_khoan=True),

    # ── Giá vốn ───────────────────────────────────────────────────────────────
    "cogs": {
        "nhan": "Giá vốn hàng bán",
        "nguon": "ketoan.cong_no · đơn hoàn thành trong kỳ",
        "giai_thich": ("Công nợ phải trả nhà cung cấp gắn với các đơn hoàn thành trong kỳ. "
                       "Cùng tập đơn với Doanh thu (nguyên tắc phù hợp)."),
        "tu_bang": (f"ketoan.cong_no cn WHERE cn.loai = 'phai_tra' "
                    f"AND cn.ma_don IN ({_DON_HOAN_THANH})"),
        "cot_tien": "cn.so_tien",
        "chon": ("cn.id, cn.ngay, cn.so_tien, cn.doi_tac, COALESCE(cn.ma_don,'') AS ma_don, "
                 "COALESCE(cn.loai_chi_tiet,'') AS loai_chi_tiet, COALESCE(cn.ghi_chu,'') AS ghi_chu"),
        "sap_xep": "cn.so_tien DESC, cn.id",
        "cot": [_C_NGAY, {"key": "doi_tac", "nhan": "Nhà cung cấp"},
                {"key": "ma_don", "nhan": "Mã đơn"}, {"key": "ghi_chu", "nhan": "Ghi chú"}, _C_TIEN],
        # Chưa có công nợ NCC gắn đơn → báo cáo quay về phiếu xuất kho.
        "du_phong": {
            "nguon": "ketoan.inventory_movement · phiếu xuất kho",
            "tu_bang": ("ketoan.inventory_movement im WHERE im.loai = 'xuat' "
                        "AND im.ngay >= :tu AND im.ngay <= :den"),
            "cot_tien": "im.thanh_tien",
            "chon": ("im.id, im.ngay, im.thanh_tien AS so_tien, im.so_luong, "
                     "COALESCE(im.source_app,'') AS source_app, COALESCE(im.ghi_chu,'') AS ghi_chu"),
            "sap_xep": "im.ngay DESC, im.id DESC",
            "cot": [_C_NGAY, {"key": "so_luong", "nhan": "Số lượng"},
                    {"key": "source_app", "nhan": "Nguồn"},
                    {"key": "ghi_chu", "nhan": "Ghi chú"}, _C_TIEN],
        },
    },

    # ── Tài chính ─────────────────────────────────────────────────────────────
    "cp_tai_chinh.lai_vay": {
        "nhan": "Lãi vay theo sổ vay",
        "nguon": "ketoan.khoan_vay_giao_dich",
        "giai_thich": ("Các giao dịch loại 'trả lãi' (và phần lãi của 'trả gốc+lãi') trong kỳ. "
                       "Kiểm kỹ cột Loại: khoản trả GỐC bị gán nhầm thành trả LÃI sẽ nằm ở đây."),
        "tu_bang": ("ketoan.khoan_vay_giao_dich gd "
                    "LEFT JOIN ketoan.khoan_vay v ON v.id = gd.khoan_vay_id "
                    "WHERE gd.ngay >= :tu AND gd.ngay <= :den "
                    "AND (gd.loai = 'tra_lai' OR gd.loai = 'tra_goc_lai')"),
        "cot_tien": ("CASE WHEN gd.loai = 'tra_lai' THEN gd.so_tien "
                     "ELSE COALESCE(gd.so_tien_lai, 0) END"),
        "chon": ("gd.id, gd.ngay, gd.loai, COALESCE(v.ma_khoan,'') AS ma_khoan, "
                 "COALESCE(v.nguon_vay,'') AS nguon_vay, COALESCE(gd.ghi_chu,'') AS ghi_chu, "
                 "CASE WHEN gd.loai = 'tra_lai' THEN gd.so_tien "
                 "ELSE COALESCE(gd.so_tien_lai, 0) END AS so_tien"),
        "sap_xep": "gd.ngay DESC, gd.id DESC",
        "cot": [_C_NGAY, {"key": "ma_khoan", "nhan": "Khoản vay"},
                {"key": "nguon_vay", "nhan": "Nguồn vay"}, {"key": "loai", "nhan": "Loại"},
                {"key": "ghi_chu", "nhan": "Ghi chú"}, _C_TIEN],
    },
    "cp_tai_chinh.phi_nh": dict(_cp(
        "Phí ngân hàng và lãi vay ghi ở sổ chi phí",
        "Mọi chi phí nhóm 'tài chính', TRỪ đi phần lãi vay đã có trong sổ vay để không tính hai lần.",
        nhom="tai_chinh"), tru_khoan=["cp_tai_chinh.lai_vay"], chan_duoi_0=True),

    # ── Chi phí bán hàng ──────────────────────────────────────────────────────
    "cp_ban_hang.bien_phi.van_chuyen": {
        "nhan": "Vận chuyển",
        "nguon": "saleadmin.vanchuyen",
        "giai_thich": "Cước vận chuyển của chính các đơn hoàn thành trong kỳ.",
        "tu_bang": ("saleadmin.vanchuyen vc WHERE vc.trang_thai = 'hoan_thanh' "
                    "AND COALESCE(vc.ketoan_approved_at::date, vc.ngay_giao, vc.updated_at::date) >= :tu "
                    "AND COALESCE(vc.ketoan_approved_at::date, vc.ngay_giao, vc.updated_at::date) <= :den"),
        "cot_tien": "COALESCE(vc.chi_phi_vc, 0)",
        "chon": ("vc.id, vc.ma_vh, COALESCE(vc.ma_don,'') AS ma_don, COALESCE(vc.ten_kh,'') AS ten_kh, "
                 "COALESCE(vc.don_vi_vc,'') AS don_vi_vc, vc.ngay_giao AS ngay, "
                 "COALESCE(vc.chi_phi_vc,0) AS so_tien"),
        "sap_xep": "vc.ngay_giao DESC NULLS LAST, vc.id DESC",
        "cot": [_C_NGAY, {"key": "ma_vh", "nhan": "Mã VC"}, {"key": "ma_don", "nhan": "Mã đơn"},
                {"key": "ten_kh", "nhan": "Khách hàng"}, {"key": "don_vi_vc", "nhan": "Đơn vị VC"}, _C_TIEN],
    },
    "cp_ban_hang.bien_phi.khuyen_mai": _cp(
        "Khuyến mãi",
        "Chi phí nhóm 'bán hàng' có tên chứa 'khuyến mãi'.",
        nhom="ban_hang", name_like_any=["%khuyến mãi%", "%khuyen mai%"]),
    "cp_ban_hang.bien_phi.khac": dict(_cp(
        "Biến phí bán hàng khác",
        ("Chi phí nhóm 'bán hàng' sau khi loại khuyến mãi, quảng cáo và hoàn tiền "
         "(đã tính ở dòng riêng), rồi trừ tiếp các khoản gắn mã vận chuyển để không trùng cước VC."),
        nhom="ban_hang", exclude_name_like=_BH_EXCLUDE, also_ten_khoan=True),
        tru_loc=[("Khoản đã gắn mã vận chuyển (tránh trùng cước VC)",
                  dict(nhom="ban_hang"), "ref_vc IS NOT NULL")], chan_duoi_0=True),

    # ── Chi phí quản lý ───────────────────────────────────────────────────────
    "cp_quan_ly.bien_phi.vpp": _cp(
        "Văn phòng phẩm", "Chi phí nhóm 'quản lý' có tên chứa VPP / văn phòng phẩm.",
        nhom="quan_ly", name_like_any=["%vpp%", "%văn phòng phẩm%", "%van phong pham%"]),
    "cp_quan_ly.bien_phi.dao_tao": _cp(
        "Đào tạo", "Chi phí nhóm 'quản lý' có tên chứa 'đào tạo'.",
        nhom="quan_ly", name_like_any=["%đào tạo%", "%dao tao%"]),
    "cp_quan_ly.bien_phi.hoi_hop_cong_tac": _cp(
        "Hội họp, công tác", "Chi phí nhóm 'quản lý' có tên chứa 'hội họp' hoặc 'công tác'.",
        nhom="quan_ly", name_like_any=["%hội họp%", "%hoi hop%", "%công tác%", "%cong tac%"]),
    "cp_quan_ly.bien_phi.qua_bieu": _cp(
        "Quà biếu", "Chi phí nhóm 'quản lý' có tên chứa 'quà'.",
        nhom="quan_ly", name_like_any=["%quà%", "%quà biếu%", "%qua bieu%"]),
    "cp_quan_ly.bien_phi.khac": dict(_cp(
        "Biến phí quản lý khác",
        ("Chi phí nhóm 'quản lý' sau khi loại tiền trả nhà cung cấp (đó là giá vốn), lương, "
         "quảng cáo và hoàn tiền; rồi trừ tiếp 4 dòng con đã hiện riêng ở trên."),
        nhom="quan_ly", exclude_name_like=_QL_EXCLUDE_NCC, also_ten_khoan=True),
        tru_khoan=["cp_quan_ly.bien_phi.vpp", "cp_quan_ly.bien_phi.dao_tao",
                   "cp_quan_ly.bien_phi.hoi_hop_cong_tac", "cp_quan_ly.bien_phi.qua_bieu"],
        chan_duoi_0=True),

    # ── Khấu hao ──────────────────────────────────────────────────────────────
    "cp_ban_hang.dinh_phi.khau_hao_tscd_bh": {
        "nhan": "Khấu hao TSCĐ bán hàng",
        "nguon": "ketoan.khau_hao_log",
        "giai_thich": "Bút toán khấu hao từng tháng của tài sản thuộc bộ phận bán hàng.",
        "tu_bang": ("ketoan.khau_hao_log kh JOIN ketoan.tai_san_co_dinh ts ON ts.id = kh.tscd_id "
                    "WHERE ts.bo_phan = 'ban_hang' AND kh.thang = ANY(:thangs)"),
        "cot_tien": "kh.so_tien",
        "chon": ("kh.id, kh.thang, kh.so_tien, ts.ma_tscd, ts.ten_tscd, ts.nguyen_gia, "
                 "COALESCE(kh.ghi_chu,'') AS ghi_chu"),
        "sap_xep": "kh.thang DESC, kh.id DESC",
        "cot": [{"key": "thang", "nhan": "Tháng"}, {"key": "ma_tscd", "nhan": "Mã TSCĐ"},
                {"key": "ten_tscd", "nhan": "Tài sản"},
                {"key": "nguyen_gia", "nhan": "Nguyên giá", "kieu": "tien"}, _C_TIEN],
        "theo_thang": True,
    },
    "cp_quan_ly.dinh_phi.khau_hao_tscd_ql": {
        "nhan": "Khấu hao TSCĐ quản lý",
        "nguon": "ketoan.khau_hao_log",
        "giai_thich": "Bút toán khấu hao từng tháng của tài sản thuộc bộ phận quản lý.",
        "tu_bang": ("ketoan.khau_hao_log kh JOIN ketoan.tai_san_co_dinh ts ON ts.id = kh.tscd_id "
                    "WHERE ts.bo_phan = 'quan_ly' AND kh.thang = ANY(:thangs)"),
        "cot_tien": "kh.so_tien",
        "chon": ("kh.id, kh.thang, kh.so_tien, ts.ma_tscd, ts.ten_tscd, ts.nguyen_gia, "
                 "COALESCE(kh.ghi_chu,'') AS ghi_chu"),
        "sap_xep": "kh.thang DESC, kh.id DESC",
        "cot": [{"key": "thang", "nhan": "Tháng"}, {"key": "ma_tscd", "nhan": "Mã TSCĐ"},
                {"key": "ten_tscd", "nhan": "Tài sản"},
                {"key": "nguyen_gia", "nhan": "Nguyên giá", "kieu": "tien"}, _C_TIEN],
        "theo_thang": True,
    },

    # ── Thu nhập / chi phí khác (sổ cái) ──────────────────────────────────────
    "thu_nhap_khac": {
        "nhan": "Thu nhập khác",
        "nguon": "ketoan.journal_line · TK 711",
        "giai_thich": "Bút toán ghi Có TK 711 đã post trong kỳ.",
        "tu_bang": ("ketoan.journal_line jl JOIN ketoan.journal_entry je ON je.id = jl.journal_id "
                    "WHERE jl.account_code = '711' AND jl.loai = 'co' "
                    "AND je.trang_thai = 'da_post' AND je.ngay >= :tu AND je.ngay <= :den"),
        "cot_tien": "jl.so_tien",
        "chon": ("jl.id, je.ngay, je.ma_but_toan, COALESCE(je.mo_ta,'') AS mo_ta, "
                 "COALESCE(je.source_type,'') AS source_type, jl.so_tien"),
        "sap_xep": "je.ngay DESC, jl.id DESC",
        "cot": [_C_NGAY, {"key": "ma_but_toan", "nhan": "Bút toán"},
                {"key": "mo_ta", "nhan": "Diễn giải"}, {"key": "source_type", "nhan": "Nguồn"}, _C_TIEN],
    },
    "cp_khac": {
        "nhan": "Chi phí khác",
        "nguon": "ketoan.chi_phi_phat_sinh + ketoan.journal_line (TK 811)",
        "giai_thich": ("Gồm HAI nguồn: chi phí nhóm 'khác' trên sổ chi phí (đã loại hoàn tiền, "
                       "tạm ứng, quảng cáo vì đã tính ở dòng khác) CỘNG bút toán Nợ TK 811."),
        "gop": ["cp_khac.so_chi_phi", "cp_khac.tk_811"],
    },
    "cp_khac.so_chi_phi": _cp(
        "Sổ chi phí — nhóm khác",
        "Chi phí nhóm 'khác', loại bỏ hoàn tiền, tạm ứng và quảng cáo.",
        nhom="khac",
        exclude_name_like=["%hoàn tiền%", "%hoan tien%", "%tạm ứng%", "%tam ung%",
                           "%marketing%", "%ads%", "%quảng cáo%", "%quang cao%"],
        also_ten_khoan=True),
    "cp_khac.tk_811": {
        "nhan": "Bút toán TK 811",
        "nguon": "ketoan.journal_line · TK 811",
        "giai_thich": "Bút toán ghi Nợ TK 811 đã post trong kỳ.",
        "tu_bang": ("ketoan.journal_line jl JOIN ketoan.journal_entry je ON je.id = jl.journal_id "
                    "WHERE jl.account_code = '811' AND jl.loai = 'no' "
                    "AND je.trang_thai = 'da_post' AND je.ngay >= :tu AND je.ngay <= :den"),
        "cot_tien": "jl.so_tien",
        "chon": ("jl.id, je.ngay, je.ma_but_toan, COALESCE(je.mo_ta,'') AS mo_ta, "
                 "COALESCE(je.source_type,'') AS source_type, jl.so_tien"),
        "sap_xep": "je.ngay DESC, jl.id DESC",
        "cot": [_C_NGAY, {"key": "ma_but_toan", "nhan": "Bút toán"},
                {"key": "mo_ta", "nhan": "Diễn giải"}, {"key": "source_type", "nhan": "Nguồn"}, _C_TIEN],
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Khoản tính bằng PYTHON (không gói gọn trong một câu SQL)
#
# Định phí phân bổ, lương và ads không phải "SUM một bảng theo WHERE" mà là kết quả
# của vòng lặp phân bổ / nhiều nhánh nguồn. Với chúng, bất biến được giữ bằng cách
# gọi CHÍNH hàm mà `calc_pl_for_month` gọi, rồi cộng lại — không viết lại logic.
# ══════════════════════════════════════════════════════════════════════════════

_COT_CO_DINH = [
    {"key": "thang", "nhan": "Tháng"},
    {"key": "loai_chi_phi", "nhan": "Loại chi phí"},
    {"key": "ten_khoan", "nhan": "Nội dung"},
    {"key": "so_tien_thang", "nhan": "Số tiền gốc", "kieu": "tien"},
    {"key": "cach_phan_bo", "nhan": "Cách phân bổ"},
    {"key": "so_tien", "nhan": "Vào kỳ này", "kieu": "tien"},
]


def _ham_co_dinh(nhom: str, keys: list[str]):
    """Định phí đường thẳng khớp từ khoá — mỗi dòng kèm phần phân bổ vào từng tháng."""
    def f(db: Session, tu: date, den: date) -> dict[str, Any]:
        dong = []
        for m in _thangs(tu, den):
            for r in rows_co_dinh_duong_thang(db, m, nhom, keys):
                dong.append({
                    "id": r.get("id"), "thang": m,
                    "loai_chi_phi": r.get("loai_chi_phi") or "",
                    "ten_khoan": r.get("ten_khoan") or "",
                    "so_tien_thang": float(r.get("so_tien_thang") or 0),
                    "cach_phan_bo": r.get("cach_phan_bo") or "",
                    "so_tien": round(r["phan_bo"], 2),
                })
        return {"cot": _COT_CO_DINH, "dong": dong,
                "tong": round(sum(d["so_tien"] for d in dong), 2)}
    return f


def _ham_dinh_phi_con_lai(nhom: str, tru: list[tuple[str, list[str]]]):
    """Định phí "khác" = tổng cả 6 phương pháp phân bổ TRỪ các dòng đã hiện riêng."""
    def f(db: Session, tu: date, den: date) -> dict[str, Any]:
        dong = []
        for m in _thangs(tu, den):
            bm = _sum_co_dinh_method_dispatcher(db, m, nhom)["by_method"]
            for pp, v in bm.items():
                if v:
                    dong.append({"thang": m, "phuong_phap": pp, "so_tien": round(float(v), 2)})
        tong_tat_ca = round(sum(d["so_tien"] for d in dong), 2)
        dieu_chinh, da_tru = [], 0.0
        for nhan, keys in tru:
            t = sum(
                sum(r["phan_bo"] for r in rows_co_dinh_duong_thang(db, m, nhom, keys))
                for m in _thangs(tu, den)
            )
            if t:
                dieu_chinh.append({"nhan": "Trừ: " + nhan, "so_tien": -round(t, 2)})
                da_tru += t
        con = max(0.0, tong_tat_ca - da_tru)
        return {
            "cot": [{"key": "thang", "nhan": "Tháng"},
                    {"key": "phuong_phap", "nhan": "Phương pháp phân bổ"},
                    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
            "dong": dong, "tong_loc": tong_tat_ca,
            "dieu_chinh": dieu_chinh, "tong": round(con, 2),
        }
    return f


_COT_LUONG = [
    {"key": "thang", "nhan": "Tháng"},
    {"key": "phong_ban", "nhan": "Phòng ban"},
    {"key": "so_nguoi", "nhan": "Số người"},
    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"},
]


def _ham_luong(phan: str, truong: str, nhan_bhxh: bool = False, du_phong_cp: bool = False):
    """Lương — tổng lấy từ CHÍNH `_sum_payroll_split` mà báo cáo gọi.

    CẢNH BÁO (đo 05/10/2026): `_sum_payroll_split` nối `hcns.employees e ON e.id =
    p.employee_id`, mà `hcns.payroll` KHÔNG có cột `employee_id` và `hcns.employees`
    KHÔNG có cột `id` — câu truy vấn luôn ném lỗi, hàm rơi vào nhánh fallback (cũng
    nối sai) rồi trả về 0 cho MỌI phòng ban. Nghĩa là mọi dòng lương trên KQKD đang
    bằng 0 bất kể bảng lương có số hay không. Hiện `hcns.payroll` rỗng nên chưa lộ.

    Ở đây KHÔNG tự "sửa" bằng cách đọc `p.phong_ban` cho đúng: làm thế popup sẽ ra số
    trong khi dòng báo cáo vẫn 0, tức là nói dối theo chiều ngược lại. Tổng vẫn lấy
    đúng từ hàm của báo cáo; danh sách dòng đọc `p.phong_ban` chỉ để NHÌN, và nếu hai
    bên lệch thì ghi rõ cảnh báo.
    """
    def f(db: Session, tu: date, den: date) -> dict[str, Any]:
        tong = 0.0
        for m in _thangs(tu, den):
            v = float(_sum_payroll_split(db, m).get(phan, {}).get(truong, 0) or 0)
            tong += v * BHXH_CTY_MULTIPLIER if nhan_bhxh else v

        dong = []
        try:
            for m in _thangs(tu, den):
                rows = db.execute(text("""
                    SELECT COALESCE(LOWER(phong_ban), 'khac') AS pb, COUNT(*) AS n,
                           COALESCE(SUM(luong_co_ban), 0) AS luong_co_ban,
                           COALESCE(SUM(hoa_hong), 0)     AS hoa_hong,
                           COALESCE(SUM(luong_ot), 0)     AS luong_ot
                    FROM hcns.payroll WHERE thang = :thang GROUP BY pb
                """), {"thang": m}).mappings().all()
                for r in rows:
                    pb = r["pb"] or ""
                    if ("bh" if any(k in pb for k in BH_PB_KEYS) else "ql") != phan:
                        continue
                    v = float(r[truong] or 0)
                    if nhan_bhxh:
                        v *= BHXH_CTY_MULTIPLIER
                    if v:
                        dong.append({"thang": m, "phong_ban": pb,
                                     "so_nguoi": int(r["n"] or 0), "so_tien": round(v, 2)})
        except (ProgrammingError, OperationalError):
            db.rollback()
            dong = []

        ghi_chu = f"Đã nhân hệ số BHXH công ty đóng {BHXH_CTY_MULTIPLIER}." if nhan_bhxh else ""
        tong_dong = round(sum(d["so_tien"] for d in dong), 2)
        if abs(tong_dong - round(tong, 2)) > 0.5:
            ghi_chu = (ghi_chu + " CẢNH BÁO: bảng lương có "
                       f"{tong_dong:,.0f}đ nhưng báo cáo đang tính {tong:,.0f}đ — hàm tính "
                       "lương của báo cáo nối sai bảng nhân sự nên luôn ra 0. Cần sửa "
                       "`_sum_payroll_split` trong pl_calculator.py.").strip()

        if tong or not du_phong_cp:
            return {"cot": _COT_LUONG, "dong": dong, "tong": round(tong, 2), "ghi_chu": ghi_chu}

        # Báo cáo: payroll không có số → lấy lương từ sổ chi phí (chốt 27/08/2026).
        kh_dp = _cp("Lương ghi ở sổ chi phí",
                    "Bảng lương HCNS không ra số nên báo cáo lấy khoản có chữ 'lương' ở sổ chi phí.",
                    nhom="quan_ly", name_like_any=["%lương%", "%luong%"])
        t, _n = _tong(db, kh_dp, tu, den)
        tb, p = _tu_bang(kh_dp, tu, den)
        rows = db.execute(text(
            f"SELECT {kh_dp['chon']} FROM {tb} ORDER BY {kh_dp['sap_xep']} LIMIT {SO_DONG_TOI_DA}"
        ), p).mappings().all()
        return {"cot": kh_dp["cot"], "dong": [dict(r) for r in rows], "tong": round(t, 2),
                "nguon_thuc_te": "ketoan.chi_phi_phat_sinh (bảng lương HCNS không ra số)",
                "ghi_chu": ghi_chu}
    return f


def _ham_ads(db: Session, tu: date, den: date) -> dict[str, Any]:
    """Quảng cáo — ba nhánh nguồn, đi đúng nhánh mà `calc_pl_for_month` chọn."""
    thangs = _thangs(tu, den)
    if _ads_phan_bo_table_exists(db):
        tong = sum(float(_sum_ads_phan_bo_thang(db, m) or 0) for m in thangs)
        if tong > 0:
            rows = db.execute(text("""
                SELECT thang_hoan_thanh, thang_chi_ads, loai_phan_bo,
                       COALESCE(quote_number,'') AS quote_number, COALESCE(nhom_master,'') AS nhom,
                       so_tien_phan_bo AS so_tien
                FROM ketoan.ads_phan_bo_don
                WHERE (thang_hoan_thanh = ANY(:ths) AND vc_status = 'hoan_thanh'
                       AND quote_number IS NOT NULL)
                   OR (thang_chi_ads = ANY(:ths) AND loai_phan_bo = 'no_match')
                ORDER BY so_tien_phan_bo DESC
                LIMIT :lim
            """), {"ths": thangs, "lim": SO_DONG_TOI_DA}).mappings().all()
            return {
                "nguon_thuc_te": "ketoan.ads_phan_bo_don",
                "cot": [{"key": "thang_hoan_thanh", "nhan": "Tháng hoàn thành"},
                        {"key": "quote_number", "nhan": "Mã đơn"},
                        {"key": "nhom", "nhan": "Nhóm hàng"},
                        {"key": "loai_phan_bo", "nhan": "Loại phân bổ"},
                        {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
                "dong": [dict(r) for r in rows], "tong": round(tong, 2),
            }
    kh_cp = _cp("Quảng cáo ghi ở sổ chi phí",
                "Bảng phân bổ ads không có số nên báo cáo lấy chi phí có chữ marketing / ads / quảng cáo.",
                name_like_any=["%marketing%", "%ads%", "%quảng cáo%", "%quang cao%"],
                also_ten_khoan=True)
    t, n = _tong(db, kh_cp, tu, den)
    if t > 0:
        tb, p = _tu_bang(kh_cp, tu, den)
        rows = db.execute(text(
            f"SELECT {kh_cp['chon']} FROM {tb} ORDER BY {kh_cp['sap_xep']} LIMIT {SO_DONG_TOI_DA}"
        ), p).mappings().all()
        return {"nguon_thuc_te": "ketoan.chi_phi_phat_sinh", "cot": kh_cp["cot"],
                "dong": [dict(r) for r in rows], "tong": round(t, 2)}
    return {"nguon_thuc_te": "marketing.ads_cost (dự phòng)", "cot": [], "dong": [],
            "tong": round(_sum_ads(db, tu, den), 2),
            "ghi_chu": "Lấy từ bảng chi phí quảng cáo cũ của Marketing — không có dòng chi tiết."}


KHOAN.update({
    "cp_ban_hang.bien_phi.ads": {
        "nhan": "Quảng cáo, marketing",
        "nguon": "ads_phan_bo_don → sổ chi phí → marketing.ads_cost",
        "giai_thich": ("Ba nguồn xếp theo thứ tự ưu tiên; dòng 'Nguồn thực tế' trong popup "
                       "cho biết kỳ này đang lấy từ đâu."),
        "ham": _ham_ads,
    },
    "cp_ban_hang.bien_phi.hoa_hong": {
        "nhan": "Hoa hồng KD/MKT", "nguon": "hcns.payroll",
        "giai_thich": "Hoa hồng trên bảng lương của các phòng kinh doanh / marketing.",
        "ham": _ham_luong("bh", "hoa_hong"),
    },
    "cp_ban_hang.bien_phi.luong_ot": {
        "nhan": "Lương làm thêm KD/MKT", "nguon": "hcns.payroll",
        "giai_thich": "Lương làm thêm giờ của các phòng kinh doanh / marketing.",
        "ham": _ham_luong("bh", "luong_ot"),
    },
    "cp_ban_hang.dinh_phi.luong_co_ban_kd_mkt": {
        "nhan": "Lương cơ bản KD/MKT (gồm BHXH công ty)", "nguon": "hcns.payroll",
        "giai_thich": f"Lương cơ bản phòng KD/MKT × {BHXH_CTY_MULTIPLIER} (phần công ty đóng BHXH).",
        "ham": _ham_luong("bh", "luong_co_ban", nhan_bhxh=True),
    },
    "cp_quan_ly.dinh_phi.luong_co_ban_hcns_kt_ceo": {
        "nhan": "Lương cơ bản HCNS/KT/CEO (gồm BHXH công ty)",
        "nguon": "hcns.payroll (rỗng thì lấy sổ chi phí)",
        "giai_thich": f"Lương cơ bản khối quản lý × {BHXH_CTY_MULTIPLIER}. Bảng lương HCNS "
                      "rỗng thì báo cáo lấy khoản có chữ 'lương' ở sổ chi phí.",
        "ham": _ham_luong("ql", "luong_co_ban", nhan_bhxh=True, du_phong_cp=True),
    },
    "cp_ban_hang.dinh_phi.thue_showroom": {
        "nhan": "Tiền thuê mặt bằng (bán hàng)", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Chi phí cố định nhóm bán hàng có chữ 'thuê' hoặc 'showroom', phân bổ theo tháng.",
        "ham": _ham_co_dinh("ban_hang", ["%thuê%", "%thue%", "%showroom%"]),
    },
    "cp_ban_hang.dinh_phi.phi_thuong_xuyen": {
        "nhan": "Phí thường xuyên (bán hàng)", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Toàn bộ định phí nhóm bán hàng (cả 6 phương pháp phân bổ) trừ tiền thuê mặt bằng.",
        "ham": _ham_dinh_phi_con_lai("ban_hang", [("Tiền thuê mặt bằng",
                                                   ["%thuê%", "%thue%", "%showroom%"])]),
    },
    "cp_quan_ly.dinh_phi.thue_vp": {
        "nhan": "Tiền thuê mặt bằng (quản lý)", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Chi phí cố định nhóm quản lý có chữ 'thuê', phân bổ theo tháng.",
        "ham": _ham_co_dinh("quan_ly", ["%thuê%", "%thue%"]),
    },
    "cp_quan_ly.dinh_phi.dien_nuoc_vp": {
        "nhan": "Điện nước văn phòng", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Chi phí cố định nhóm quản lý có chữ 'điện' hoặc 'nước'.",
        "ham": _ham_co_dinh("quan_ly", ["%điện%", "%dien%", "%nước%", "%nuoc%"]),
    },
    "cp_quan_ly.dinh_phi.internet_dien_thoai": {
        "nhan": "Internet, điện thoại", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Chi phí cố định nhóm quản lý có chữ 'internet' hoặc 'điện thoại'.",
        "ham": _ham_co_dinh("quan_ly", ["%internet%", "%điện thoại%", "%dien thoai%"]),
    },
    "cp_quan_ly.dinh_phi.dich_vu_kt_luat": {
        "nhan": "Dịch vụ kế toán, luật", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Chi phí cố định nhóm quản lý có chữ 'kế toán' hoặc 'luật'.",
        "ham": _ham_co_dinh("quan_ly", ["%kế toán%", "%ke toan%", "%luật%", "%luat%"]),
    },
    "cp_quan_ly.dinh_phi.phi_khac": {
        "nhan": "Định phí quản lý khác", "nguon": "ketoan.chi_phi_co_dinh",
        "giai_thich": "Toàn bộ định phí nhóm quản lý trừ 4 dòng đã hiện riêng ở trên.",
        "ham": _ham_dinh_phi_con_lai("quan_ly", [
            ("Tiền thuê mặt bằng", ["%thuê%", "%thue%"]),
            ("Điện nước", ["%điện%", "%dien%", "%nước%", "%nuoc%"]),
            ("Internet, điện thoại", ["%internet%", "%điện thoại%", "%dien thoai%"]),
            ("Dịch vụ kế toán, luật", ["%kế toán%", "%ke toan%", "%luật%", "%luat%"]),
        ]),
    },
})


def _tu_bang(kh: dict[str, Any], tu: date, den: date) -> tuple[str, dict[str, Any]]:
    """Mệnh đề FROM+WHERE của một khoản, kèm tham số."""
    params: dict[str, Any] = {"tu": tu, "den": den}
    if kh.get("theo_thang"):
        params["thangs"] = _thangs(tu, den)
    if "loc_cp" in kh:
        where, p = _where_cp_phat_sinh(tu, den, **kh["loc_cp"])
        return f"ketoan.chi_phi_phat_sinh WHERE {where}", p
    return kh["tu_bang"], params


def _tong(db: Session, kh: dict[str, Any], tu: date, den: date) -> tuple[float, int]:
    tb, p = _tu_bang(kh, tu, den)
    r = db.execute(text(
        f"SELECT COALESCE(SUM({kh['cot_tien']}), 0) AS tong, COUNT(*) AS n FROM {tb}"
    ), p).mappings().first()
    return (float(r["tong"] or 0), int(r["n"] or 0)) if r else (0.0, 0)


def _nhanh(db: Session, kh: dict[str, Any], tu: date, den: date) -> tuple[dict, float, int]:
    """Chọn nhánh nguồn ĐÚNG như hàm tính tổng: nguồn chính = 0 thì quay về dự phòng.

    `_sum_doanh_thu_thuc_hien` và `_sum_cogs` đều có nhánh dự phòng. Nếu chi tiết không
    đi theo thì popup sẽ trống trong khi dòng vẫn có số — ví dụ tháng đang chạy dở chưa
    đơn nào hoàn thành.
    """
    tong, n = _tong(db, kh, tu, den)
    dp = kh.get("du_phong")
    if tong == 0 and dp:
        kh2 = {**kh, **dp}
        tong2, n2 = _tong(db, kh2, tu, den)
        if tong2 or n2:
            return kh2, tong2, n2
    return kh, tong, n


def chi_tiet(
    db: Session, khoa: str, tu: date, den: date,
    trang: int = 1, so_dong: int = SO_DONG_MAC_DINH,
) -> Optional[dict[str, Any]]:
    """Chi tiết một dòng KQKD. `None` nếu khoá chưa được khai (caller trả 404)."""
    kh = KHOAN.get(khoa)
    if kh is None and khoa.startswith(TIEN_TO_ADS_NHOM):
        nhom = khoa[len(TIEN_TO_ADS_NHOM):]
        kh = {"nhan": "Quảng cáo nhóm " + ("chưa gán nhóm hàng" if nhom == "no_match" else nhom),
              "nguon": "ketoan.ads_phan_bo_don",
              "giai_thich": "Phần quảng cáo phân bổ cho nhóm hàng này.",
              "ham": _ham_ads_nhom(nhom)}
    if kh is None:
        return None

    so_dong = max(1, min(int(so_dong or SO_DONG_MAC_DINH), SO_DONG_TOI_DA))
    trang = max(1, int(trang or 1))

    # Khoản gộp nhiều nguồn (vd Chi phí khác = sổ chi phí + bút toán 811): mỗi nguồn
    # một bảng riêng trong popup, tổng = cộng các phần. Phân trang áp cho từng phần.
    if "gop" in kh:
        phan = [chi_tiet(db, k, tu, den, trang=trang, so_dong=so_dong) for k in kh["gop"]]
        phan = [x for x in phan if x]
        return {
            "ok": True, "khoa": khoa, "nhan": kh["nhan"], "nguon": kh["nguon"],
            "giai_thich": kh["giai_thich"],
            "tu": tu.isoformat(), "den": den.isoformat(),
            "tong": round(sum(x["tong"] for x in phan), 2),
            "so_dong": sum(x["so_dong"] for x in phan),
            "trang": trang, "so_trang": max([x["so_trang"] for x in phan] or [1]),
            "so_dong_moi_trang": so_dong,
            "dieu_chinh": [], "cot": [], "dong": [],
            "phan": phan,
        }

    # Khoản tính bằng Python (định phí phân bổ, lương, ads): hàm trả sẵn danh sách,
    # phân trang cắt tại đây. Tổng/so_dong vẫn tính trên TOÀN BỘ như nhánh SQL.
    if "ham" in kh:
        kq = kh["ham"](db, tu, den)
        tat_ca = kq.get("dong", [])
        # Dòng tổng: kèm luôn chứng từ của các dòng lá bên dưới. Chỉ hiện lá CÓ chứng từ
        # trong kỳ — lá bằng 0 đã nằm ở bảng công thức phía trên, lặp lại chỉ tổ rối.
        phan = []
        if kh.get("la_cong_thuc"):
            for la in _la_chung_tu(khoa)[:12]:
                ct = chi_tiet(db, la, tu, den, trang=1, so_dong=10)
                if ct and ct.get("so_dong"):
                    phan.append(ct)
        n = len(tat_ca)
        so_trang = max(1, -(-n // so_dong))
        trang = min(trang, so_trang)
        return {
            "ok": True, "khoa": khoa, "nhan": kh["nhan"],
            "nguon": kq.get("nguon_thuc_te") or kh["nguon"],
            "giai_thich": kh["giai_thich"],
            "ghi_chu": kq.get("ghi_chu", ""),
            "tu": tu.isoformat(), "den": den.isoformat(),
            "tong_loc": kq.get("tong_loc", kq["tong"]),
            "dieu_chinh": kq.get("dieu_chinh", []),
            "tong": kq["tong"], "so_dong": n,
            "trang": trang, "so_trang": so_trang, "so_dong_moi_trang": so_dong,
            "cot": kq["cot"],
            "dong": tat_ca[(trang - 1) * so_dong: trang * so_dong],
            "phan": phan,
        }

    kh, tong, n = _nhanh(db, kh, tu, den)
    so_trang = max(1, -(-n // so_dong))
    trang = min(trang, so_trang)

    tb, p = _tu_bang(kh, tu, den)
    rows = db.execute(text(
        f"SELECT {kh['chon']} FROM {tb} ORDER BY {kh['sap_xep']} OFFSET :_off LIMIT :_lim"
    ), {**p, "_off": (trang - 1) * so_dong, "_lim": so_dong}).mappings().all()

    # Điều chỉnh: số trên báo cáo = tổng bộ lọc − các khoản đã hiện ở dòng khác.
    dieu_chinh: list[dict[str, Any]] = []
    con_lai = tong
    for k_tru in kh.get("tru_khoan", []):
        t, _ = _tong(db, KHOAN[k_tru], tu, den)
        if t:
            dieu_chinh.append({"nhan": "Trừ: " + KHOAN[k_tru]["nhan"], "so_tien": -t})
            con_lai -= t
    for nhan, loc, dieu_kien in kh.get("tru_loc", []):
        where, pp = _where_cp_phat_sinh(tu, den, **loc)
        t = float(db.execute(text(
            f"SELECT COALESCE(SUM(so_tien),0) FROM ketoan.chi_phi_phat_sinh "
            f"WHERE {where} AND {dieu_kien}"
        ), pp).scalar() or 0)
        if t:
            dieu_chinh.append({"nhan": "Trừ: " + nhan, "so_tien": -t})
            con_lai -= t
    if kh.get("chan_duoi_0") and con_lai < 0:
        dieu_chinh.append({"nhan": "Chặn không cho âm", "so_tien": -con_lai})
        con_lai = 0.0

    return {
        "ok": True,
        "khoa": khoa,
        "nhan": kh["nhan"],
        "nguon": kh["nguon"],
        "giai_thich": kh["giai_thich"],
        "tu": tu.isoformat(),
        "den": den.isoformat(),
        "tong_loc": round(tong, 2),          # tổng thuần của bộ lọc
        "dieu_chinh": dieu_chinh,            # các khoản trừ, nếu có
        "tong": round(con_lai, 2),           # PHẢI bằng số trên dòng báo cáo
        "so_dong": n,
        "trang": trang,
        "so_trang": so_trang,
        "so_dong_moi_trang": so_dong,
        "cot": kh["cot"],
        "dong": [dict(r) for r in rows],
    }


# ══════════════════════════════════════════════════════════════════════════════
# Dòng TỔNG / dòng tính ra từ dòng khác
#
# Những dòng này không có chứng từ riêng — chúng là phép cộng trừ của các dòng trên.
# Bấm vào vẫn phải trả lời được "ở đâu ra", nên popup hiện ĐÚNG công thức kèm số của
# từng số hạng. Số hạng đọc từ chính kết quả `calc_pl_for_month` nên cộng lại luôn
# bằng số đang hiện trên dòng.
# ══════════════════════════════════════════════════════════════════════════════

def _pl_khoang(db: Session, tu: date, den: date) -> dict[str, Any]:
    """Cộng dồn P&L các tháng chạm khoảng — đúng cách màn KQKD cộng ở trình duyệt."""
    tong: dict[str, Any] = {}

    def cong(dich: dict, nguon: dict) -> None:
        for k, v in nguon.items():
            if isinstance(v, dict):
                cong(dich.setdefault(k, {}), v)
            elif isinstance(v, (int, float)) and not isinstance(v, bool):
                dich[k] = dich.get(k, 0) + v

    for m in _thangs(tu, den):
        cong(tong, calc_pl_for_month(db, m))
    return tong


def _so(d: dict, path: str) -> float:
    cur: Any = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return 0.0
        cur = cur[k]
    try:
        return float(cur)
    except (TypeError, ValueError):
        return 0.0


def _ham_cong_thuc(duong_dan: str, so_hang: list):
    """Dòng tổng: hiện từng số hạng kèm dấu, cộng lại = số trên dòng."""
    def f(db: Session, tu: date, den: date) -> dict[str, Any]:
        pl = _pl_khoang(db, tu, den)
        dong = []
        for nhan, path, dau in so_hang:
            dong.append({"khoan": ("− " if dau < 0 else "+ ") + nhan,
                         "so_tien": round(_so(pl, path) * dau, 2)})
        return {
            "cot": [{"key": "khoan", "nhan": "Số hạng"},
                    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
            "dong": dong,
            # `duong_dan` rỗng = báo cáo không có sẵn ô này (vd "Các khoản giảm trừ",
            # "Lợi nhuận khác" được màn hình tự cộng) → tổng = cộng chính các số hạng.
            "tong": round(_so(pl, duong_dan) if duong_dan
                          else sum(x["so_tien"] for x in dong), 2),
            "ghi_chu": ("Dòng này không có chứng từ riêng — nó là phép cộng của các dòng "
                        "trên. Bấm vào từng dòng số hạng ở bảng báo cáo để xem chứng từ."),
        }
    return f


def _tong_ke(nhan: str, duong_dan: str, giai_thich: str, so_hang: list) -> dict:
    # `so_hang` giữ lại để `_la_chung_tu` lần xuống tới các dòng CÓ chứng từ.
    return {"nhan": nhan, "nguon": "Tính từ các dòng khác của báo cáo",
            "giai_thich": giai_thich, "la_cong_thuc": True, "so_hang": so_hang,
            "ham": _ham_cong_thuc(duong_dan, so_hang)}


def _la_chung_tu(khoa: str, sau: int = 0, da_qua: Optional[set] = None) -> list[str]:
    """Lần từ một dòng tổng xuống các dòng LÁ thật sự có chứng từ.

    Dòng tổng là phép cộng của dòng khác, mà dòng đó lại có thể là tổng tiếp. Người xem
    không quan tâm tầng nào — họ muốn thấy chứng từ. Hàm này đi hết các tầng, trả về
    danh sách khoá lá theo đúng thứ tự xuất hiện, bỏ trùng.
    """
    da_qua = da_qua if da_qua is not None else set()
    if khoa in da_qua or sau > 6:
        return []
    da_qua.add(khoa)
    kh = KHOAN.get(khoa)
    if kh is None:
        return []
    if not kh.get("la_cong_thuc"):
        return [khoa]
    ra: list[str] = []
    for _nhan, path, _dau in kh.get("so_hang", []):
        for x in _la_chung_tu(path, sau + 1, da_qua):
            if x not in ra:
                ra.append(x)
    return ra


KHOAN.update({
    "dt_thuan": _tong_ke(
        "Doanh thu thuần", "dt_thuan",
        "Doanh thu bán hàng trừ các khoản giảm trừ.",
        [("Doanh thu bán hàng và cung cấp dịch vụ", "doanh_thu.dt_thuc_hien", 1),
         ("Chiết khấu thương mại", "doanh_thu.chiet_khau", -1),
         ("Hoàn tiền khách", "doanh_thu.giam_tru", -1)]),
    "ln_gop": _tong_ke(
        "Lợi nhuận gộp", "ln_gop", "Doanh thu thuần trừ giá vốn hàng bán.",
        [("Doanh thu thuần", "dt_thuan", 1), ("Giá vốn hàng bán", "cogs", -1)]),
    "cp_tai_chinh.tong": _tong_ke(
        "Chi phí tài chính", "cp_tai_chinh.tong", "Lãi vay cộng phí ngân hàng.",
        [("Lãi vay theo sổ vay", "cp_tai_chinh.lai_vay", 1),
         ("Phí ngân hàng, lãi ghi ở sổ chi phí", "cp_tai_chinh.phi_nh", 1),
         ("Chi phí tài chính khác", "cp_tai_chinh.khac", 1)]),
    "cp_ban_hang.bien_phi.tong": _tong_ke(
        "Biến phí bán hàng", "cp_ban_hang.bien_phi.tong", "Cộng các khoản biến phí bán hàng.",
        [("Hoa hồng", "cp_ban_hang.bien_phi.hoa_hong", 1),
         ("Lương làm thêm KD/MKT", "cp_ban_hang.bien_phi.luong_ot", 1),
         ("Quảng cáo, marketing", "cp_ban_hang.bien_phi.ads", 1),
         ("Vận chuyển", "cp_ban_hang.bien_phi.van_chuyen", 1),
         ("Khuyến mãi", "cp_ban_hang.bien_phi.khuyen_mai", 1),
         ("Biến phí bán hàng khác", "cp_ban_hang.bien_phi.khac", 1)]),
    "cp_ban_hang.dinh_phi.tong": _tong_ke(
        "Định phí bán hàng", "cp_ban_hang.dinh_phi.tong", "Cộng các khoản định phí bán hàng.",
        [("Lương cơ bản KD/MKT", "cp_ban_hang.dinh_phi.luong_co_ban_kd_mkt", 1),
         ("Tiền thuê mặt bằng", "cp_ban_hang.dinh_phi.thue_showroom", 1),
         ("Khấu hao TSCĐ bán hàng", "cp_ban_hang.dinh_phi.khau_hao_tscd_bh", 1),
         ("Phí thường xuyên", "cp_ban_hang.dinh_phi.phi_thuong_xuyen", 1)]),
    "cp_ban_hang.tong": _tong_ke(
        "Chi phí bán hàng", "cp_ban_hang.tong", "Biến phí cộng định phí bán hàng.",
        [("Biến phí bán hàng", "cp_ban_hang.bien_phi.tong", 1),
         ("Định phí bán hàng", "cp_ban_hang.dinh_phi.tong", 1)]),
    "cp_quan_ly.bien_phi.tong": _tong_ke(
        "Biến phí quản lý", "cp_quan_ly.bien_phi.tong", "Cộng các khoản biến phí quản lý.",
        [("Văn phòng phẩm", "cp_quan_ly.bien_phi.vpp", 1),
         ("Đào tạo", "cp_quan_ly.bien_phi.dao_tao", 1),
         ("Hội họp, công tác", "cp_quan_ly.bien_phi.hoi_hop_cong_tac", 1),
         ("Quà biếu", "cp_quan_ly.bien_phi.qua_bieu", 1),
         ("Biến phí quản lý khác", "cp_quan_ly.bien_phi.khac", 1)]),
    "cp_quan_ly.dinh_phi.tong": _tong_ke(
        "Định phí quản lý", "cp_quan_ly.dinh_phi.tong", "Cộng các khoản định phí quản lý.",
        [("Lương cơ bản HCNS/KT/CEO", "cp_quan_ly.dinh_phi.luong_co_ban_hcns_kt_ceo", 1),
         ("Tiền thuê mặt bằng", "cp_quan_ly.dinh_phi.thue_vp", 1),
         ("Điện nước văn phòng", "cp_quan_ly.dinh_phi.dien_nuoc_vp", 1),
         ("Internet, điện thoại", "cp_quan_ly.dinh_phi.internet_dien_thoai", 1),
         ("Khấu hao TSCĐ quản lý", "cp_quan_ly.dinh_phi.khau_hao_tscd_ql", 1),
         ("Dịch vụ kế toán, luật", "cp_quan_ly.dinh_phi.dich_vu_kt_luat", 1),
         ("Định phí quản lý khác", "cp_quan_ly.dinh_phi.phi_khac", 1)]),
    "cp_quan_ly.tong": _tong_ke(
        "Chi phí quản lý doanh nghiệp", "cp_quan_ly.tong", "Biến phí cộng định phí quản lý.",
        [("Biến phí quản lý", "cp_quan_ly.bien_phi.tong", 1),
         ("Định phí quản lý", "cp_quan_ly.dinh_phi.tong", 1)]),
    "ln_thuan_hdkd": _tong_ke(
        "Lợi nhuận thuần từ hoạt động kinh doanh", "ln_thuan_hdkd",
        "Lợi nhuận gộp cộng doanh thu tài chính, trừ chi phí tài chính, bán hàng và quản lý.",
        [("Lợi nhuận gộp", "ln_gop", 1), ("Doanh thu hoạt động tài chính", "dt_tai_chinh", 1),
         ("Chi phí tài chính", "cp_tai_chinh.tong", -1),
         ("Chi phí bán hàng", "cp_ban_hang.tong", -1),
         ("Chi phí quản lý doanh nghiệp", "cp_quan_ly.tong", -1)]),
    "ln_truoc_thue": _tong_ke(
        "Lợi nhuận kế toán trước thuế", "ln_truoc_thue",
        "Lợi nhuận thuần cộng thu nhập khác, trừ chi phí khác.",
        [("Lợi nhuận thuần từ HĐKD", "ln_thuan_hdkd", 1),
         ("Thu nhập khác", "thu_nhap_khac", 1), ("Chi phí khác", "cp_khac", -1)]),
    "thue_tndn": _tong_ke(
        "Chi phí thuế TNDN hiện hành", "thue_tndn",
        "20% lợi nhuận trước thuế, chỉ tính khi có lãi.",
        [("Lợi nhuận kế toán trước thuế", "ln_truoc_thue", 1)]),
    "lnst": _tong_ke(
        "Lợi nhuận sau thuế", "lnst", "Lợi nhuận trước thuế trừ thuế TNDN.",
        [("Lợi nhuận kế toán trước thuế", "ln_truoc_thue", 1),
         ("Chi phí thuế TNDN hiện hành", "thue_tndn", -1)]),
    "doanh_thu.chiet_khau": _tong_ke(
        "Chiết khấu thương mại", "doanh_thu.chiet_khau",
        "Chiết khấu đã trừ ngay lúc lập đơn nên không ghi riêng — dòng này luôn bằng 0.", []),
    "dt_tai_chinh": _tong_ke(
        "Doanh thu hoạt động tài chính", "dt_tai_chinh",
        "Chưa khai khoản thu tài chính nào — dòng này luôn bằng 0.", []),
    "cp_tai_chinh.khac": _tong_ke(
        "Chi phí tài chính khác", "cp_tai_chinh.khac",
        "Chưa tách khoản tài chính khác — dòng này luôn bằng 0.", []),
})


# ── Ba chỗ còn sót, bổ sung 05/10/2026 ────────────────────────────────────────
TIEN_TO_ADS_NHOM = "cp_ban_hang.bien_phi.ads_by_nhom."


def _ham_ads_nhom(nhom: str):
    """Quảng cáo của MỘT nhóm hàng — chỉ có số khi ads lấy từ bảng phân bổ."""
    def f(db: Session, tu: date, den: date) -> dict[str, Any]:
        thangs = _thangs(tu, den)
        if not _ads_phan_bo_table_exists(db):
            return {"cot": [], "dong": [], "tong": 0.0,
                    "ghi_chu": "Chưa có bảng phân bổ quảng cáo nên không tách được theo nhóm hàng."}
        rows = db.execute(text("""
            SELECT thang_hoan_thanh, thang_chi_ads, loai_phan_bo,
                   COALESCE(quote_number,'') AS quote_number, COALESCE(nhom_master,'') AS nhom,
                   so_tien_phan_bo AS so_tien
            FROM ketoan.ads_phan_bo_don
            WHERE COALESCE(nhom_master, 'no_match') = :nhom
              AND ((thang_hoan_thanh = ANY(:ths) AND vc_status = 'hoan_thanh'
                    AND quote_number IS NOT NULL)
                OR (thang_chi_ads = ANY(:ths) AND loai_phan_bo = 'no_match'))
            ORDER BY so_tien_phan_bo DESC
        """), {"ths": thangs, "nhom": nhom}).mappings().all()
        return {
            "cot": [{"key": "thang_hoan_thanh", "nhan": "Tháng hoàn thành"},
                    {"key": "quote_number", "nhan": "Mã đơn"},
                    {"key": "loai_phan_bo", "nhan": "Loại phân bổ"},
                    {"key": "so_tien", "nhan": "Số tiền", "kieu": "tien"}],
            "dong": [dict(r) for r in rows],
            "tong": round(sum(float(r["so_tien"] or 0) for r in rows), 2),
        }
    return f


KHOAN.update({
    "doanh_thu.giam_tru_tong": _tong_ke(
        "Các khoản giảm trừ doanh thu", "", "Chiết khấu thương mại cộng hoàn tiền khách.",
        [("Chiết khấu thương mại", "doanh_thu.chiet_khau", 1),
         ("Hoàn tiền khách", "doanh_thu.giam_tru", 1)]),
    "ln_khac": _tong_ke(
        "Lợi nhuận khác", "", "Thu nhập khác trừ chi phí khác.",
        [("Thu nhập khác", "thu_nhap_khac", 1), ("Chi phí khác", "cp_khac", -1)]),
})
