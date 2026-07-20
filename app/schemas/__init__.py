"""Pydantic v2 schemas — request/response cho schema `ketoan`."""
from .doanh_thu import DoanhThuCreate, DoanhThuUpdate, DoanhThuOut
from .chi_phi import ChiPhiCreate, ChiPhiUpdate, ChiPhiOut
from .co_dinh import CoDinhCreate, CoDinhUpdate, CoDinhOut
from .cong_no import (
    CongNoCreate, CongNoUpdate, CongNoOut, CongNoTraBody,
)
from .so_quy import SoQuyCreate, SoQuyUpdate, SoQuyOut
from .loai_chi_phi import LoaiChiPhiCreate, LoaiChiPhiUpdate, LoaiChiPhiOut
from .tai_khoan_nh import TaiKhoanNHCreate, TaiKhoanNHUpdate, TaiKhoanNHOut
from .bao_cao import (
    BaoCaoRequest, BaoCaoTongHopOut,
    GroupedAmount, BaoCaoCongNoOut,
)
from .so_du_dau_ky import SoDuDauKyCreate, SoDuDauKyOut
from .bao_cao_snapshot import BaoCaoSnapshotOut
from .product import (
    ProductCreate, ProductUpdate, ProductOut,
    ProductAddonCreate, ProductAddonUpdate, ProductAddonOut,
)
from .khoan_vay import (
    KhoanVayCreate, KhoanVayUpdate, KhoanVayOut, KhoanVayDetailOut,
    KhoanVayLaiSuatOut, KhoanVayGiaoDichOut,
    LaiSuatCreate, TraGocBody, TraLaiBody, TraGocLaiBody,
)
# M1 — Inventory
from .product_category import (
    InvProductCategoryCreate, InvProductCategoryUpdate, InvProductCategoryOut,
    InvProductCategoryNode,
)
from .inventory import (
    InvProductCreate, InvProductUpdate, InvProductOut, InvProductPage,
    InventoryBalanceOut, InventoryBalanceTreeNode,
    InventoryMovementCreate, InventoryMovementOut,
    KiemKeCreate, KiemKeOut,
    TonKhoCanhBaoOut,
)
# M2 — BOM Giá Vốn
from .bom import (
    BOMItemIn, BOMItemOut,
    BOMMasterCreate, BOMMasterUpdate, BOMMasterOut, BOMMasterListOut,
    BOMMarginReportOut,
)
# M4 — VCSH + Quỹ DN + TK NH giao dịch
from .von_csh import (
    VonCSHCreate, VonCSHUpdate, VonCSHOut, VonCSHSummary,
    GopVonBody, TrichQuyBody, KhoiTaoBanDauBody, QuyDNSummaryItem,
)
from .quy_dn import QuyDNCreate, QuyDNUpdate, QuyDNOut
from .quy_dn_giao_dich import QuyDNGiaoDichCreate, QuyDNGiaoDichOut
from .tai_khoan_nh_giao_dich import (
    TaiKhoanNHGiaoDichCreate, TaiKhoanNHGiaoDichOut, TaiKhoanSoDuOut,
)
# M5 — Đóng kỳ + LN giữ lại + P&L snapshot
from .ky_ke_toan import (
    KyKeToanOut, KyKeToanDetailOut, ChotKyResponse, LNGiuLaiLuyKeOut,
)
from .pl_snapshot import PLSnapshotOut
# Phase 2 — Journal (double-entry)
from .journal import (
    JournalLineIn, JournalLineOut, JournalEntryIn, JournalEntryOut,
    JournalEntrySummary, AccountInfo,
)
# Phase 3 — TSCĐ + Khấu hao
from .tai_san import (
    TSCDCreate, TSCDUpdate, TSCDOut, TSCDDetailOut,
    KhauHaoLogOut,
    ChayKhauHaoItem, ChayKhauHaoSkipped, ChayKhauHaoResponse,
    ThanhLyBody,
    TSCDSummaryGroup, TSCDSummary,
)

__all__ = [
    "DoanhThuCreate", "DoanhThuUpdate", "DoanhThuOut",
    "ChiPhiCreate", "ChiPhiUpdate", "ChiPhiOut",
    "CoDinhCreate", "CoDinhUpdate", "CoDinhOut",
    "CongNoCreate", "CongNoUpdate", "CongNoOut", "CongNoTraBody",
    "SoQuyCreate", "SoQuyUpdate", "SoQuyOut",
    "LoaiChiPhiCreate", "LoaiChiPhiUpdate", "LoaiChiPhiOut",
    "TaiKhoanNHCreate", "TaiKhoanNHUpdate", "TaiKhoanNHOut",
    "BaoCaoRequest", "BaoCaoTongHopOut",
    "GroupedAmount", "BaoCaoCongNoOut",
    "SoDuDauKyCreate", "SoDuDauKyOut",
    "BaoCaoSnapshotOut",
    "ProductCreate", "ProductUpdate", "ProductOut",
    "ProductAddonCreate", "ProductAddonUpdate", "ProductAddonOut",
    # M1
    "InvProductCategoryCreate", "InvProductCategoryUpdate", "InvProductCategoryOut",
    "InvProductCategoryNode",
    "InvProductCreate", "InvProductUpdate", "InvProductOut", "InvProductPage",
    "InventoryBalanceOut", "InventoryBalanceTreeNode",
    "InventoryMovementCreate", "InventoryMovementOut",
    "KiemKeCreate", "KiemKeOut",
    "TonKhoCanhBaoOut",
    # M2
    "BOMItemIn", "BOMItemOut",
    "BOMMasterCreate", "BOMMasterUpdate", "BOMMasterOut", "BOMMasterListOut",
    "BOMMarginReportOut",
    # M4
    "VonCSHCreate", "VonCSHUpdate", "VonCSHOut", "VonCSHSummary",
    "GopVonBody", "TrichQuyBody", "KhoiTaoBanDauBody", "QuyDNSummaryItem",
    "QuyDNCreate", "QuyDNUpdate", "QuyDNOut",
    "QuyDNGiaoDichCreate", "QuyDNGiaoDichOut",
    "TaiKhoanNHGiaoDichCreate", "TaiKhoanNHGiaoDichOut", "TaiKhoanSoDuOut",
    # M5
    "KyKeToanOut", "KyKeToanDetailOut", "ChotKyResponse", "LNGiuLaiLuyKeOut",
    "PLSnapshotOut",
    # Phase 2 — Journal
    "JournalLineIn", "JournalLineOut", "JournalEntryIn", "JournalEntryOut",
    "JournalEntrySummary", "AccountInfo",
    # Phase 3 — TSCĐ + Khấu hao
    "TSCDCreate", "TSCDUpdate", "TSCDOut", "TSCDDetailOut",
    "KhauHaoLogOut",
    "ChayKhauHaoItem", "ChayKhauHaoSkipped", "ChayKhauHaoResponse",
    "ThanhLyBody",
    "TSCDSummaryGroup", "TSCDSummary",
]
