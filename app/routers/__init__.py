"""FastAPI routers — chi_phi, doanh_thu, co_dinh, cong_no, so_quy,
loai_chi_phi, tai_khoan_nh, bao_cao, external, pages, so_du_dau_ky, meta, uploads,
product_category, inv_products, inventory, von_csh, tai_khoan_nh_giao_dich, ky_ke_toan,
bao_cao_cpa (Phase 6B)."""
from . import (
    chi_phi, doanh_thu, co_dinh, cong_no, so_quy,
    loai_chi_phi, tai_khoan_nh, bao_cao, external, pages,
    so_du_dau_ky, meta, uploads,
    product_category, inv_products, inventory,
    von_csh, tai_khoan_nh_giao_dich,
    ky_ke_toan,
    bom, journal, tai_san,
    bao_cao_cpa, ads_phan_bo, quy_dn,
    sepay,
)

__all__ = [
    "chi_phi", "doanh_thu", "co_dinh", "cong_no", "so_quy",
    "loai_chi_phi", "tai_khoan_nh", "bao_cao", "external", "pages",
    "so_du_dau_ky", "meta", "uploads",
    "product_category", "inv_products", "inventory",
    "von_csh", "tai_khoan_nh_giao_dich",
    "ky_ke_toan",
    "bom", "journal", "tai_san",
    "bao_cao_cpa", "ads_phan_bo", "quy_dn",
    "sepay",
]
