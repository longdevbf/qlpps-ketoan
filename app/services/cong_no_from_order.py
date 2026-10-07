"""Helper service — auto tạo CongNo (phai_tra) từ 1 PurchaseOrder của muahang.

Tách từ import endpoint `POST /api/cong-no/import` (bulk) thành unit reusable
cho cả pull (`POST /from-order/{id}`) lẫn auto-trigger SQLAlchemy.

Idempotent qua `ref_id = MH-<order_id>` (partial UNIQUE INDEX uq_cn_ref_id).
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import CongNo
from .id_gen import next_cong_no_id


# Status PO trigger — ghi công nợ phải trả NCC từ "Đã Duyệt Mua" trở đi.
# 2026-06-19: BỔ SUNG "Đã có hàng" + "Đã lấy hàng". Trước đây loại "Đã có hàng"
# vì sợ trùng (giả định PO sẽ lên "Hoàn Thành" ngay sau) — nhưng thực tế hầu hết
# PO KẸT ở "Đã có hàng" (75/80 đơn), rất ít lên "Hoàn Thành" → 55 đơn (~385tr)
# nợ NCC thật không bao giờ ghi được. Lo trùng là thừa vì đã có khóa idempotent
# per-NCC (ref_id = 'MH-{order}-NCC{ncc}') tự skip entry đã tồn tại.
PAYABLE_TRIGGER_STATUSES = {
    "Đã Duyệt Mua", "Đặt hàng", "Đang SX",
    "Đã có hàng", "Đã lấy hàng", "Đã giao", "Hoàn Thành",
}


class CongNoFromOrderError(Exception):
    """Raise khi không thể tạo cong_no từ PO."""

    def __init__(self, code: str, message: str):
        # 'khong_tinh_duoc' (02/10/2026): Mua hàng TỪ CHỐI tính phân bổ cho đơn
        # này (vd `selected_ncc_id` trỏ combo đã bị xoá) → Kế toán cũng không
        # ghi. Cả 2 nơi gọi đều bắt CongNoFromOrderError và ghi lại `message`,
        # nên lý do thật của Mua hàng hiện ra nguyên văn.
        self.code = code  # 'po_not_found'|'po_not_terminal'|'duplicate'|'no_total'|'khong_tinh_duoc'
        self.message = message
        super().__init__(message)


def find_existing_cong_no_for_order(db: Session, order_id: str) -> Optional[CongNo]:
    """Trả 1 CongNo nếu đã có entry phai_tra cho PO này, else None.

    Match CẢ 2 format ref_id: cũ 'MH-{order}' (bulk import) lẫn mới
    'MH-{order}-NCC{ncc}' (pull per-NCC). Dùng .first() vì format mới có nhiều
    entry/đơn (1/NCC).
    """
    return db.execute(
        select(CongNo).where(
            or_(
                CongNo.ref_id == f"MH-{order_id}",
                CongNo.ref_id.like(f"MH-{order_id}-NCC%"),
            )
        )
    ).scalars().first()


def _resolve_combo_parts(db: Session, po, combo_id: str) -> list[tuple[str, Decimal, str]]:
    """Cho 1 combo NCC, tính sub-total per part từ po.items[*].prices + po.combos.

    Trả list (part_ncc_id_str, raw_subtotal, "NCC name (label)") cho từng phần
    (mộc/sơn/đệm/kính/…). Discount KHÔNG áp ở đây — caller tự split.
    """
    from muahang.app.models import Supplier  # lazy

    combos = po.combos or []
    combo = next((c for c in combos if str(c.get("id", "")) == str(combo_id)), None)
    if not combo:
        return []

    parts = combo.get("parts") or []
    if not (isinstance(parts, list) and parts):
        parts = []
        if combo.get("ncc_moc_id"):
            parts.append({"ncc_id": combo["ncc_moc_id"], "label": combo.get("label_moc") or "Mộc"})
        if combo.get("ncc_son_id"):
            parts.append({"ncc_id": combo["ncc_son_id"], "label": combo.get("label_son") or "Sơn"})
    parts = [p for p in parts if isinstance(p, dict) and p.get("ncc_id")]
    if not parts:
        return []

    sup_cache: dict = {}
    def _sup_name(ncc_id) -> str:
        if ncc_id in sup_cache:
            return sup_cache[ncc_id]
        name = str(ncc_id)
        try:
            sup = db.get(Supplier, ncc_id)  # Supplier.id là string 'ncc_xxx'
            if sup and sup.name:
                name = sup.name
        except Exception:
            pass
        sup_cache[ncc_id] = name
        return name

    out: list[tuple[str, Decimal, str]] = []
    for p in parts:
        part_id = p["ncc_id"]
        label = (p.get("label") or "Phần").strip().lower()
        subtotal = Decimal("0")
        for item in (po.items or []):
            prices = item.prices or {}
            price_row = prices.get(part_id) or prices.get(str(part_id)) or {}
            dg = price_row.get("don_gia") if isinstance(price_row, dict) else None
            if dg and float(dg) > 0:
                sl = item.so_luong_calc or item.so_luong_input or 1
                subtotal += Decimal(str(dg)) * Decimal(str(sl))
        if subtotal > 0:
            out.append((str(part_id), subtotal, f"{_sup_name(part_id)} ({label})"))
    return out


def _resolve_all_ncc(db: Session, po) -> list[tuple[str, Decimal, str]]:
    """Trả list (ncc_id_str, so_tien_sau_giam, ncc_name) cho tất cả NCC trong ncc_totals.

    Mỗi NCC = 1 khoản nợ riêng. COMBO NCC (id trong po.combos): tách thành nhiều
    entry — 1 entry/part (mộc/sơn/đệm/kính). Skip individual NCC nếu đã thuộc
    combo (tránh double-count).

    SỐ TIỀN lấy từ `muahang…compute_amounts_per_ncc` — NGUỒN DUY NHẤT
    (sửa 02/10/2026, anh Quang: "tổng công nợ khó khớp thì chấp nhận, nhưng CÒN
    NỢ của từng nhà thì không thể lệch"). Trước đây hàm này TỰ tính phân bổ giảm
    giá, và đã trôi khác Mua hàng ở 2 chỗ đo được trên dữ liệu thật:

      1. KHÔNG biết cờ `discounts['_combo_per_ncc']` (Mua hàng thêm 29/09/2026):
         combo có ô giảm giá RIÊNG từng NCC con thì bên này vẫn chia TỶ LỆ theo
         `po.discount`. Đơn thật ORD-2026-042: Kế toán tính 213.300.000đ còn Mua
         hàng 207.225.440đ; ORD-2026-087: 8.200.000đ vs 6.500.000đ.
      2. Làm tròn khác (`quantize(1)` ở đây vs `quantize(0.01)` bên Mua hàng).

    Lệch này KHÔNG tự lành: `create_cong_no_list_from_order` chỉ ghi MỘT LẦN cho
    mỗi `ref_id` (`if existing: continue`) và `_auto_bridge_to_ketoan` chỉ gọi
    khi PO ĐỔI TRẠNG THÁI và chưa có dòng nào — nên con số sai ở lần ghi đầu
    đứng đó mãi, chỉ sửa được bằng tay qua màn "Đối chiếu Mua hàng".

    GIỮ NGUYÊN: khoá trả về (`COMBO{combo}-PART{ncc}` / `{ncc_id}`) và tên hiển
    thị — `ref_id` phải không đổi, nếu không các dòng Kế toán đã có sẽ không
    khớp nữa và lần ghi sau tạo dòng TRÙNG. Chỉ con số thay đổi.
    """
    from muahang.app.models import Supplier  # lazy
    from muahang.app.services.congno_from_order import compute_amounts_per_ncc  # lazy

    # strict=True để lý do Mua hàng từ chối (combo đã bị xoá/đổi) lộ ra nguyên
    # văn, thay vì âm thầm thành "chưa có ncc_totals". Đổi sang
    # CongNoFromOrderError vì CẢ HAI nơi gọi chỉ bắt đúng loại này —
    # `_dong_bo_phai_tra` (ketoan) bắt rồi ghi `ex.message` vào danh sách bỏ
    # qua; ValueError thoát ra sẽ làm sập cả lượt "Đồng bộ công nợ".
    try:
        tien_theo_ncc = {
            str(k): v[0] for k, v in compute_amounts_per_ncc(po, strict=True).items()
        }
    except ValueError as ex:
        raise CongNoFromOrderError("khong_tinh_duoc", str(ex)) from ex
    if not tien_theo_ncc:
        # Mua hàng không ghi đồng nào (chưa chọn NCC, giảm giá ≥ giá trị hàng…)
        # → Kế toán cũng không ghi. TRƯỚC ĐÂY nhánh fallback dưới đây ghi nợ cho
        # MỌI NCC trong `ncc_totals` — kể cả NCC chỉ đưa vào để SO GIÁ, không
        # mua: đơn thật ORD-2026-209 bị Kế toán ghi 670.000đ cho 2 nhà mà Mua
        # hàng không ghi gì.
        return []

    totals = po.ncc_totals or {}
    names = po.ncc_names or {}
    combos = po.combos or []
    combo_ids = {str(c.get("id", "")) for c in combos if c.get("id")}

    # CHỈ ghi NCC ĐÃ CHỌN (anh Quang 2026-07-08). `ncc_totals` có thể chứa cả các
    # NCC SO SÁNH (báo giá để so, KHÔNG mua) — vd đơn combo vẫn còn NCC đơn lẻ
    # comparison_best trong ncc_totals. Iterate hết → ghi thừa NCC không mua thành
    # công nợ (bug: 1 đơn combo bị tính lên 3 nhà). Lọc xuống đúng selected_ncc_id
    # (fallback comparison_best_ncc nếu chưa chọn tay).
    _selected = getattr(po, "selected_ncc_id", None) or getattr(po, "comparison_best_ncc", None)
    _sel = str(_selected) if _selected is not None else None
    _mk = next((k for k in totals if str(k) == _sel), None) if _sel else None
    if _mk is not None:
        totals = {_mk: totals[_mk]}
    elif _sel and _sel in combo_ids:
        # Đã chọn combo nhưng `ncc_totals` chưa có khoá combo (chỉ còn các NCC đơn
        # lẻ dùng để so giá): vẫn tách theo ĐÚNG combo đã chọn. Mua hàng tính được
        # combo này (đọc po.combos + po.items, không cần ncc_totals) nên 2 bên vẫn
        # khớp. Giá trị 0 chỉ là chỗ giữ khoá — số tiền lấy từ `tien_theo_ncc`.
        totals = {_sel: Decimal("0")}

    # NCC IDs đã thuộc 1 combo (trong ncc_totals) → skip individual entry để tránh trùng
    nccs_in_active_combo: set[str] = set()
    for c in combos:
        if str(c.get("id", "")) not in totals:
            continue
        for p in (c.get("parts") or []):
            if isinstance(p, dict) and p.get("ncc_id"):
                nccs_in_active_combo.add(str(p["ncc_id"]))
        if c.get("ncc_moc_id"): nccs_in_active_combo.add(str(c["ncc_moc_id"]))
        if c.get("ncc_son_id"): nccs_in_active_combo.add(str(c["ncc_son_id"]))

    result: list[tuple[str, Decimal, str]] = []
    for ncc_id_str, _raw_total in totals.items():
        # Skip individual NCC nếu đã được combo bao trùm
        if str(ncc_id_str) not in combo_ids and str(ncc_id_str) in nccs_in_active_combo:
            continue
        # Combo NCC → split thành nhiều entry per part
        if str(ncc_id_str) in combo_ids:
            parts = _resolve_combo_parts(db, po, ncc_id_str)
            if not parts:
                continue
            for part_id, _part_raw, part_name in parts:
                # Số tiền sau giảm giá do Mua hàng quyết — KHÔNG tự chia lại ở đây.
                so_tien = tien_theo_ncc.get(str(part_id), Decimal("0"))
                if so_tien <= 0:
                    continue
                result.append((f"COMBO{ncc_id_str}-PART{part_id}", so_tien, part_name))
            continue
        # NCC đơn
        so_tien = tien_theo_ncc.get(str(ncc_id_str), Decimal("0"))
        if so_tien <= 0:
            continue
        ncc_name = names.get(ncc_id_str) or ""
        if not ncc_name:
            try:
                sup = db.get(Supplier, ncc_id_str)
                ncc_name = sup.name if sup else ncc_id_str
            except (ValueError, TypeError):
                ncc_name = ncc_id_str
        result.append((ncc_id_str, so_tien, ncc_name))
    return result


def create_cong_no_phai_tra_from_order(
    db: Session,
    order_id: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
) -> CongNo:
    """Tạo CongNo (phai_tra) per-NCC cho 1 PO. Trả entry đầu tiên (backward compat).

    Idempotent qua ref_id = 'MH-{order_id}-NCC{ncc_id}'. Raises CongNoFromOrderError.
    """
    created = create_cong_no_list_from_order(
        db, order_id, created_by=created_by,
        require_terminal=require_terminal, commit=commit,
    )
    return created[0]


def create_cong_no_list_from_order(
    db: Session,
    order_id: str,
    *,
    created_by: Optional[str] = None,
    require_terminal: bool = True,
    commit: bool = True,
) -> list[CongNo]:
    """Tạo 1 CongNo per NCC từ ncc_totals của PO.

    - ma_don = po.ref_bao_gia (mã BG, để join đúng với orders-overview)
    - ref_id = 'MH-{order_id}-NCC{ncc_id}' (idempotent per NCC)
    - ghi_chu chứa cả PO id để traceability

    Raises:
        CongNoFromOrderError(code='po_not_found' | 'po_not_terminal' | 'duplicate' | 'no_total')
    """
    from muahang.app.models import PurchaseOrder  # lazy cross-app

    po = db.get(PurchaseOrder, order_id)
    if not po:
        raise CongNoFromOrderError("po_not_found", f"Không tìm thấy đơn {order_id}")

    if require_terminal and po.status not in PAYABLE_TRIGGER_STATUSES:
        raise CongNoFromOrderError(
            "po_not_terminal",
            f"Đơn {order_id} đang ở trạng thái '{po.status}' — chưa thể ghi công nợ "
            f"(cần status ∈ {sorted(PAYABLE_TRIGGER_STATUSES)})",
        )

    # Check duplicate — nếu TẤT CẢ NCC đã có entry thì coi là duplicate
    ncc_entries = _resolve_all_ncc(db, po)
    if not ncc_entries:
        raise CongNoFromOrderError(
            "no_total",
            f"Đơn {order_id} chưa có ncc_totals — không thể xác định số tiền phải trả",
        )

    # ma_don = mã BG (ref_bao_gia) để join đúng với baogia.quotes; fallback po.id
    ma_don_val = (po.ref_bao_gia or po.id) if hasattr(po, "ref_bao_gia") else po.id
    ngay_val = po.created_at.date() if po.created_at else date_cls.today()

    created: list[CongNo] = []
    for ncc_id_str, so_tien, ncc_name in ncc_entries:
        ref_id_val = f"MH-{order_id}-NCC{ncc_id_str}"
        existing = db.execute(
            select(CongNo).where(CongNo.ref_id == ref_id_val)
        ).scalar_one_or_none()
        if existing:
            continue  # idempotent — skip NCC đã có

        cid = next_cong_no_id(db)
        obj = CongNo(
            id=cid,
            ngay=ngay_val,
            doi_tac=ncc_name,
            so_tien=so_tien,
            da_tra=Decimal("0"),
            loai="phai_tra",
            loai_chi_tiet="Công Nợ NCC",
            ma_don=ma_don_val,
            ref_id=ref_id_val,
            ref_source="muahang",
            han_thanh_toan=None,
            trang_thai="chua_tra",
            ghi_chu=f"Auto từ PO {order_id} ({po.ten_don or ''}) | NCC: {ncc_name}".strip(),
            created_by=created_by,
        )
        db.add(obj)
        db.flush()
        created.append(obj)

    if not created:
        raise CongNoFromOrderError(
            "duplicate",
            f"Đơn {order_id} đã có đủ công nợ phải trả cho tất cả NCC",
        )

    if commit:
        db.commit()
        for obj in created:
            db.refresh(obj)
    return created
