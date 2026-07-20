"""Domain services — id gen, P&L calculator, cross-app reader."""
from .id_gen import next_cong_no_id
from .pl_calculator import (
    sum_doanh_thu, sum_chi_phi_phat_sinh, sum_chi_phi_co_dinh,
    sum_cong_no_by_loai, group_by_date_doanh_thu, group_by_loai_chi_phi,
    calc_pl_for_month,
)
from .external_reader import (
    read_luong_total, read_don_hang_total, read_ads_total,
)
from .revenue_from_order import (
    create_doanh_thu_from_order,
    find_existing_doanh_thu_for_order,
    REVENUE_TRIGGER_STATUSES,
    RevenueFromOrderError,
)
from .from_vc import (
    create_chi_phi_from_vc,
    create_thu_cod_from_vc,
    create_all_from_vc,
    find_existing_chi_phi_for_vc,
    find_existing_so_quy_for_vc,
    VC_TRIGGER_STATUSES,
    VCAccountingError,
)
from .cong_no_from_order import (
    create_cong_no_phai_tra_from_order,
    create_cong_no_list_from_order,
    find_existing_cong_no_for_order,
    PAYABLE_TRIGGER_STATUSES,
    CongNoFromOrderError,
)
# M1 Inventory
from .inventory_avg import (
    apply_movement,
    get_or_create_balance,
    recalc_balance_from_history,
    InventoryError,
)
from .inventory_bridge_muahang import (
    on_po_delivered,
    PO_TRIGGER_STATUSES,
)
from .inventory_bridge_saleadmin import (
    on_vc_delivered,
    VC_TRIGGER_STATUSES as INV_VC_TRIGGER_STATUSES,
)

__all__ = [
    "next_cong_no_id",
    "sum_doanh_thu", "sum_chi_phi_phat_sinh", "sum_chi_phi_co_dinh",
    "sum_cong_no_by_loai", "group_by_date_doanh_thu", "group_by_loai_chi_phi",
    "calc_pl_for_month",
    "read_luong_total", "read_don_hang_total", "read_ads_total",
    "create_doanh_thu_from_order",
    "find_existing_doanh_thu_for_order",
    "REVENUE_TRIGGER_STATUSES",
    "RevenueFromOrderError",
    "create_chi_phi_from_vc",
    "create_thu_cod_from_vc",
    "create_all_from_vc",
    "find_existing_chi_phi_for_vc",
    "find_existing_so_quy_for_vc",
    "VC_TRIGGER_STATUSES",
    "VCAccountingError",
    "create_cong_no_phai_tra_from_order",
    "create_cong_no_list_from_order",
    "find_existing_cong_no_for_order",
    "PAYABLE_TRIGGER_STATUSES",
    "CongNoFromOrderError",
    # M1 Inventory
    "apply_movement",
    "get_or_create_balance",
    "recalc_balance_from_history",
    "InventoryError",
    "on_po_delivered",
    "PO_TRIGGER_STATUSES",
    "on_vc_delivered",
    "INV_VC_TRIGGER_STATUSES",
]
