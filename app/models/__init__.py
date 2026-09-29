"""Models schema `ketoan`.

Import all để Alembic autogenerate detect (qua `import ketoan.app.models`).
"""
from .doanh_thu import DoanhThu
from .chi_phi_phat_sinh import ChiPhiPhatSinh
from .chi_phi_co_dinh import ChiPhiCoDinh
from .cong_no import CongNo
from .so_quy import SoQuy
from .loai_chi_phi import LoaiChiPhi
from .tai_khoan_nh import TaiKhoanNH
from .so_du_dau_ky import SoDuDauKy
from .bao_cao_snapshot import BaoCaoSnapshot
from .khoan_vay import KhoanVay, KhoanVayLaiSuat, KhoanVayGiaoDich
# M1 — Sản Phẩm + Tồn Kho
from .product_category import InvProductCategory
from .product import InvProduct
from .inventory_balance import InventoryBalance
from .inventory_movement import InventoryMovement
from .kiem_ke import KiemKe
# M2 — BOM Giá Vốn
from .bom_master import BOMMaster
from .bom_item import BOMItem
# M4 — Vốn Chủ Sở Hữu + Quỹ DN + TK NH giao dịch
from .von_csh import VonCSH
from .quy_dn import QuyDN
from .quy_dn_giao_dich import QuyDNGiaoDich
from .tai_khoan_nh_giao_dich import TaiKhoanNHGiaoDich
# M5 — Đóng kỳ kế toán + LN giữ lại + P&L snapshot
from .bao_cao_pl_snapshot import BaoCaoPLSnapshot
from .ky_ke_toan import KyKeToan
# Phase 2 — Double-entry journal
from .journal_entry import JournalEntry
from .journal_line import JournalLine
# Phase 3 — TSCĐ + Khấu hao
from .tai_san_co_dinh import TaiSanCoDinh
from .khau_hao_log import KhauHaoLog
# Phase 6A — Phân bổ ads theo nhóm master
from .ads_phan_bo_don import AdsPhanBoDon
# SePay webhook — thu tiền qua QR CK
from .sepay_transaction import SepayTransaction
# Cài đặt Kế toán — đơn vị (letterhead) + chính sách/đánh số (2026-09-25)
from .don_vi import DonVi
from .cai_dat_he_thong import CaiDatHeThong
# Tạm ứng (TK 141) + chi tiết số dư đầu kỳ theo đối tượng (2026-09-25)
from .tam_ung import TamUng, TamUngQuyetToan
from .so_du_dau_ky_doi_tuong import SoDuDauKyDoiTuong
from .thue_tndn_dieu_chinh import ThueTndnDieuChinh
from .phan_bo_242 import PhanBo242

__all__ = [
    "DoanhThu",
    "ChiPhiPhatSinh",
    "ChiPhiCoDinh",
    "CongNo",
    "SoQuy",
    "LoaiChiPhi",
    "TaiKhoanNH",
    "SoDuDauKy",
    "BaoCaoSnapshot",
    "KhoanVay",
    "KhoanVayLaiSuat",
    "KhoanVayGiaoDich",
    # M1
    "InvProductCategory",
    "InvProduct",
    "InventoryBalance",
    "InventoryMovement",
    "KiemKe",
    # M2
    "BOMMaster",
    "BOMItem",
    # M4
    "VonCSH",
    "QuyDN",
    "QuyDNGiaoDich",
    "TaiKhoanNHGiaoDich",
    # M5
    "BaoCaoPLSnapshot",
    "KyKeToan",
    # Phase 2 — Journal
    "JournalEntry",
    "JournalLine",
    # Phase 3 — TSCĐ + Khấu hao
    "TaiSanCoDinh",
    "KhauHaoLog",
    # Phase 6A — Ads phân bổ
    "AdsPhanBoDon",
    # SePay
    "SepayTransaction",
    # Cài đặt Kế toán
    "DonVi",
    "CaiDatHeThong",
    # Tạm ứng + số dư đầu kỳ theo đối tượng
    "TamUng",
    "TamUngQuyetToan",
    "SoDuDauKyDoiTuong",
    # Thuế TNDN điều chỉnh + phân bổ TK 242
    "ThueTndnDieuChinh",
    "PhanBo242",
]
