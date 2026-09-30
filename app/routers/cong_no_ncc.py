"""Công nợ NCC chéo — Read-only bridge từ Kế Toán sang Mua Hàng (Tier 2-C bridge).

Logic:
    - Source of truth là `muahang.congno` (V1-compatible). KT KHÔNG tạo bản sao.
    - Tổng nợ phát sinh (`no_phai_tra`):    SUM(so_tien) WHERE loai='no_phai_tra'.
    - Tổng đã thanh toán (`de_xuat_tra` ĐÃ CHI thực — tiền đã rời sổ quỹ):
        SUM(so_tien) WHERE loai='de_xuat_tra' AND da_chi = TRUE.
        (Anh Quang 2026-08-31: chuẩn hoá "đã trả = da_chi" — thống nhất với màn
         bấm Chi ncc_de_xuat.py + summary muahang; 'duyet' chỉ là CEO đồng ý trả,
         tiền chưa rời quỹ.)
    - Còn nợ (balance) = nợ phát sinh - đã thanh toán.

Lazy-import muahang.app.models để tránh side-effect khi muahang chưa migrate;
ở đây ta dùng raw SQL fail-soft (giống `external.py`) để gọn.

Auth: chỉ admin/ceo/manager/kt (require_ketoan_user) — kế toán mới xem được.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..services.cong_no_doi_chieu_mh import ap_dung_de_xuat, tinh_de_xuat
from ._deps import _CEO_THUCHI_ROLES, require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


# CHỈ CEO được ÁP DỤNG đối chiếu Mua hàng (giám đốc chốt 30/09/2026, cùng lần đẩy production
# công nợ) — GET xem đề xuất vẫn cho mọi vai trò Kế toán, chỉ POST áp dụng bị chặn. Tái dùng
# _CEO_THUCHI_ROLES (admin/ceo/assistant_ceo, _deps.py) thay vì tự định nghĩa nhóm role mới —
# cùng nhóm với quyền sửa/xoá lệnh thu chi, message riêng cho đúng ngữ cảnh "đối chiếu".
def require_ceo_doi_chieu(user: JWTPayload = Depends(require_ketoan_user)) -> JWTPayload:
    if user.role not in _CEO_THUCHI_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ CEO được áp dụng đối chiếu")
    return user


_CEO_DOI_CHIEU = Depends(require_ceo_doi_chieu)


def _safe_rows(db: Session, sql: str, **params) -> list[dict[str, Any]]:
    """Execute trả list dict. Fail-soft trả [] nếu bảng muahang chưa tồn tại."""
    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


# Aggregate tổng theo NCC, chia 3 NHÓM lấy từ ketoan.v_nhom_no_don (cùng quy tắc với
# /ncc-module bên dưới) — quyết định người dùng 29/09/2026, xem migration q6_2026_09_30:
#
#   💰 THỰC       : đơn đã lấy hàng/đang giao/đã giao/hoàn thành (hoặc PO.status='Hoàn Thành').
#   📋 DỰ KIẾN    : đơn đặt hàng/đang SX/đã có hàng — hiện riêng, KHÔNG cộng vào "phải trả".
#   ❓ CẦN KIỂM   : nhãn lạ/NULL hoặc nợ KHÔNG gắn PO nào (nhập tay/đầu kỳ) — vẫn cộng vào
#                   "phải trả" như THỰC (giữ đúng hành vi cũ: nợ không gắn PO = đã chốt phải trả),
#                   nhưng tách ra để KT nhìn thấy có gì cần xác minh.
#
# BUG FIX 2026-09-25 (lịch sử, đã thay bởi view): trước đây lọc bằng SQL LOWER() thô, DB collation
# "C" không hạ đúng chữ hoa có dấu → nhóm dự kiến luôn ra 0. View mới ép COLLATE "und-x-icu" nên
# đúng trên cả dev lẫn production — xem alembic/versions/q6_2026_09_30_v_nhom_no_don.py.
#
# Còn nợ (cash flow chốt) = (Nợ thực + Cần kiểm) - Đã trả (KHÔNG cộng dự kiến), clamp >= 0.
_SQL_SUMMARY_SUPPLIERS = """
SELECT id AS supplier_id, name AS supplier_name, short_code AS supplier_code,
       phone AS supplier_phone, group_id AS supplier_group_id
FROM muahang.suppliers
"""

_SQL_SUMMARY_NO = """
SELECT cn.ncc_id, cn.so_tien, cn.ngay, cn.ref_order_id,
       COALESCE(v.nhom_no, 'can_kiem') AS nhom_no
FROM muahang.congno cn
LEFT JOIN ketoan.v_nhom_no_don v ON v.po_id = cn.ref_order_id
WHERE cn.loai = 'no_phai_tra' AND cn.ncc_id IS NOT NULL
"""

# "Đã trả" = ĐÃ CHI thực (da_chi=TRUE), KHÔNG phải chỉ mới CEO duyệt.
_SQL_SUMMARY_DA_TRA = """
SELECT ncc_id, SUM(so_tien) AS amt
FROM muahang.congno
WHERE loai = 'de_xuat_tra' AND da_chi = TRUE AND ncc_id IS NOT NULL
GROUP BY ncc_id
"""


def _tong_hop_ncc(db: Session) -> list[dict[str, Any]]:
    """Gộp nợ dự kiến / nợ thực / cần kiểm / đã trả theo NCC, sắp như SQL cũ (balance, thực, tên)."""
    zero = Decimal("0")
    agg: dict[str, dict[str, Any]] = {}
    for r in _safe_rows(db, _SQL_SUMMARY_NO):
        a = agg.setdefault(r["ncc_id"], {"du_kien": zero, "thuc": zero, "can_kiem": zero, "orders": set(), "last": None})
        so_tien = Decimal(str(r.get("so_tien") or 0))
        nhom = r["nhom_no"]
        a[nhom] += so_tien
        if r.get("ref_order_id"):
            a["orders"].add(r["ref_order_id"])
        if nhom != "du_kien" and r.get("ngay") and (a["last"] is None or r["ngay"] > a["last"]):
            a["last"] = r["ngay"]
    paid = {r["ncc_id"]: Decimal(str(r.get("amt") or 0)) for r in _safe_rows(db, _SQL_SUMMARY_DA_TRA)}

    rows: list[dict[str, Any]] = []
    for s in _safe_rows(db, _SQL_SUMMARY_SUPPLIERS):
        a = agg.get(s["supplier_id"], {"du_kien": zero, "thuc": zero, "can_kiem": zero, "orders": set(), "last": None})
        p = paid.get(s["supplier_id"], zero)
        no_phai_tra = a["thuc"] + a["can_kiem"]
        rows.append({
            **s,
            "no_du_kien": a["du_kien"],
            "no_thuc_phai_tra": a["thuc"],
            "no_can_kiem": a["can_kiem"],
            "total_paid": p,
            "balance": max(no_phai_tra - p, zero),
            "n_orders": len(a["orders"]),
            "last_order_date": a["last"],
            "total_orders": no_phai_tra,
        })
    rows.sort(key=lambda r: (-r["balance"], -r["no_thuc_phai_tra"], r["supplier_name"] or ""))
    return rows


@router.get("/ncc-summary")
def ncc_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    only_outstanding: bool = False,
):
    """Tổng hợp công nợ phải trả NCC.

    Args:
        only_outstanding: nếu True chỉ trả NCC còn dư nợ (balance != 0).

    Returns:
        {
          "total_payable": "245000000.00",
          "n_suppliers": 5,
          "items": [
            {
              "supplier_id", "supplier_name", "supplier_code",
              "total_orders", "total_paid", "balance",
              "n_orders", "last_order_date"
            }, ...
          ]
        }
    """
    rows = _tong_hop_ncc(db)

    items: list[dict[str, Any]] = []
    total_payable = 0
    for r in rows:
        balance = r.get("balance") or 0
        if only_outstanding and balance == 0:
            continue
        items.append({
            "supplier_id": r["supplier_id"],
            "supplier_name": r["supplier_name"],
            "supplier_code": r.get("supplier_code"),
            "supplier_phone": r.get("supplier_phone"),
            "supplier_group_id": r.get("supplier_group_id"),
            # 2 nhóm: dự kiến (còn gắn PO, chưa hoàn thành) + thực (hoàn thành / nhập tay)
            "no_du_kien": str(r.get("no_du_kien") or 0),
            "no_thuc_phai_tra": str(r.get("no_thuc_phai_tra") or 0),
            "total_orders": str(r.get("total_orders") or 0),  # = dự kiến + thực
            "total_paid": str(r.get("total_paid") or 0),
            "balance": str(balance),  # = thực - đã trả (cash flow chốt)
            "n_orders": int(r.get("n_orders") or 0),
            "last_order_date": (
                r["last_order_date"].isoformat() if r.get("last_order_date") else None
            ),
        })
        total_payable += int(balance)

    return {
        "total_payable": str(total_payable),
        "n_suppliers": len(items),
        "items": items,
    }


# Chi tiết 1 NCC: list bản ghi nợ phát sinh + thanh toán.
_SQL_SUPPLIER = """
SELECT id, name, short_code, phone, note, group_id
FROM muahang.suppliers
WHERE id = :ncc_id
"""

# nhom_no từ ketoan.v_nhom_no_don (quyết định người dùng 29/09/2026) — po_id ở đây là
# muahang.purchase_orders.id THẬT (cn.ref_order_id), không cần regex như bên ketoan.cong_no.
_SQL_NO_PHAI_TRA = """
SELECT
    cn.id            AS congno_id,
    cn.ref_order_id  AS po_id,
    cn.ngay          AS ngay,
    cn.thang         AS thang,
    cn.nguyen_gia    AS nguyen_gia,
    cn.so_tien_giam  AS so_tien_giam,
    cn.so_tien       AS so_tien,
    cn.mo_ta         AS mo_ta,
    cn.nv_mua_hang   AS nv_mua_hang,
    cn.created_at    AS created_at,
    po.ten_don       AS po_ten_don,
    po.status        AS po_status,
    po.ngay_dat_xuong AS po_ngay_dat,
    COALESCE(v.nhom_no, 'can_kiem') AS nhom_no
FROM muahang.congno cn
LEFT JOIN muahang.purchase_orders po ON po.id = cn.ref_order_id
LEFT JOIN ketoan.v_nhom_no_don v ON v.po_id = po.id
WHERE cn.ncc_id = :ncc_id AND cn.loai = 'no_phai_tra'
ORDER BY cn.ngay DESC NULLS LAST, cn.created_at DESC
LIMIT 500
"""

_SQL_THANH_TOAN = """
SELECT
    id,
    ngay,
    thang,
    so_tien,
    mo_ta,
    nv_mua_hang,
    nguoi_tao,
    nguoi_duyet,
    ngay_duyet,
    trang_thai,
    da_chi,
    created_at
FROM muahang.congno
WHERE ncc_id = :ncc_id AND loai = 'de_xuat_tra'
ORDER BY ngay DESC NULLS LAST, created_at DESC
LIMIT 500
"""


def _serialize_row(r: dict[str, Any]) -> dict[str, Any]:
    """Convert datetime/date/Decimal sang JSON-friendly."""
    out: dict[str, Any] = {}
    for k, v in r.items():
        if v is None:
            out[k] = None
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            # Decimal -> str (giữ độ chính xác cho FE)
            out[k] = str(v) if v.__class__.__name__ == "Decimal" else v
    return out


@router.get("/ncc/{supplier_id}/detail")
def ncc_detail(
    supplier_id: str,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chi tiết công nợ 1 NCC.

    Returns:
        {
          "supplier": {id, name, ...},
          "summary":  {total_orders, total_paid, balance, n_orders},
          "no_phai_tra": [{congno_id, po_id, po_ten_don, po_status, ngay, so_tien, ...}],
          "thanh_toan":  [{id, ngay, so_tien, trang_thai, nguoi_duyet, ...}]
        }
    """
    sup_rows = _safe_rows(db, _SQL_SUPPLIER, ncc_id=supplier_id)
    if not sup_rows:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"NCC {supplier_id!r} không tồn tại"
        )
    supplier = _serialize_row(sup_rows[0])

    no_rows = [_serialize_row(r) for r in _safe_rows(db, _SQL_NO_PHAI_TRA, ncc_id=supplier_id)]
    tt_rows = [_serialize_row(r) for r in _safe_rows(db, _SQL_THANH_TOAN, ncc_id=supplier_id)]

    # Aggregate summary client-side để khỏi query thêm (nhỏ). Cộng bằng Decimal
    # rồi mới làm tròn 1 LẦN duy nhất ở tổng — trước dùng int(float(so_tien))
    # per-row (Decimal → float → int CẮT CỤT phần lẻ, vd 32497424.89 →
    # 32497424) khiến total_orders/balance lệch so với SUM thật trong DB khi
    # có dòng congno mang số lẻ đồng — vi phạm quy tắc "tiền dùng Decimal,
    # không dùng float" của dự án.
    def _sum_so_tien(rows: list[dict[str, Any]]) -> int:
        total = sum(
            (Decimal(str(r.get("so_tien") or 0)) for r in rows), Decimal("0")
        )
        return int(total.to_integral_value(rounding=ROUND_HALF_UP))

    total_orders = _sum_so_tien(no_rows)
    # "Đã trả" = ĐÃ CHI thực (da_chi=TRUE) — thống nhất với summary (2026-08-31, L7).
    # Trước dùng trang_thai='duyet' → detail báo đã trả NHIỀU hơn thực chi.
    total_paid = _sum_so_tien([r for r in tt_rows if r.get("da_chi") is True])
    n_orders = len({r.get("po_id") for r in no_rows if r.get("po_id")})

    # 29/09/2026: tách total_orders_thuc = tổng đơn nhóm thực/cần kiểm (KHÔNG cộng dự kiến) —
    # quyết định người dùng: "công nợ/còn nợ/phải trả" chỉ cộng nợ thực. balance vẫn tính trên
    # total_orders gốc (không đổi cách trừ đã trả — đã trả không tách theo đơn/nhóm được).
    total_orders_thuc = _sum_so_tien([r for r in no_rows if r.get("nhom_no") != "du_kien"])
    total_orders_du_kien = total_orders - total_orders_thuc

    # BƯỚC 3 30/09/2026: balance_thuc < 0 = đã trả nhiều hơn hoá đơn thực (nhóm thực/cần kiểm,
    # KHÔNG cộng dự kiến — cùng cơ số total_orders_thuc) → tách "trả trước" dương, giữ nguyên
    # balance (ròng trên total_orders gốc, có thể âm) cho nơi cần đối chiếu kỹ thuật.
    balance_thuc = total_orders_thuc - total_paid
    tra_truoc = max(0, -balance_thuc)
    balance_thuc_duong = max(0, balance_thuc)

    return {
        "supplier": supplier,
        "summary": {
            "total_orders": str(total_orders),
            "total_orders_thuc": str(total_orders_thuc),
            "total_orders_du_kien": str(total_orders_du_kien),
            "total_paid": str(total_paid),
            "balance": str(total_orders - total_paid),
            "balance_thuc": str(balance_thuc),
            "balance_thuc_duong": str(balance_thuc_duong),
            "tra_truoc": str(tra_truoc),
            "n_orders": n_orders,
            "n_payments_total": len(tt_rows),
            "n_payments_approved": sum(1 for r in tt_rows if r.get("da_chi") is True),
        },
        "no_phai_tra": no_rows,
        "thanh_toan": tt_rows,
    }


@router.get("/dvvc-summary")
def dvvc_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Tổng hợp công nợ Đơn Vị Vận Chuyển (cross-app từ saleadmin).

    Logic:
    - Source of truth: `saleadmin.donvi_vc` + `saleadmin.vanchuyen`.
    - Mỗi ĐVVC: tổng `chi_phi_vc` đã phát sinh - tổng `da_tra_dvvc` (đã thanh toán)
      = số tiền KT còn phải trả NCC (ĐVVC).
    - Cộng `congno_cuoi_ky` (số dư đầu kỳ chuyển sang) làm baseline.

    Returns:
        {ok, items: [{dvvc_id, ten_dvvc, sdt, the_manh, congno_cuoi_ky,
                      tong_chi_phi, tong_da_tra, con_phai_tra, n_van_chuyen}], totals: {...}}
    """
    rows = _safe_rows(db, """
        SELECT
            d.id            AS dvvc_id,
            d.ten_dvvc      AS ten_dvvc,
            d.sdt           AS sdt,
            d.the_manh      AS the_manh,
            COALESCE(d.congno_cuoi_ky, 0) AS congno_cuoi_ky,
            COALESCE(SUM(v.chi_phi_vc), 0) AS tong_chi_phi,
            COALESCE(SUM(v.da_tra_dvvc), 0) AS tong_da_tra,
            COUNT(v.id)::int AS n_van_chuyen
        FROM saleadmin.donvi_vc d
        LEFT JOIN saleadmin.vanchuyen v ON v.dvvc_id = d.id
            AND COALESCE(v.trang_thai, '') NOT IN ('huy', 'Đã hủy')
        WHERE d.active = true
        GROUP BY d.id, d.ten_dvvc, d.sdt, d.the_manh, d.congno_cuoi_ky
        ORDER BY d.ten_dvvc
    """)

    items = []
    total_chi = total_tra = total_con = 0
    for r in rows:
        cp = float(r.get("tong_chi_phi") or 0)
        tra = float(r.get("tong_da_tra") or 0)
        cuoi_ky = float(r.get("congno_cuoi_ky") or 0)
        con_pt = cp - tra + cuoi_ky
        total_chi += cp
        total_tra += tra
        total_con += con_pt
        items.append({
            "dvvc_id": r.get("dvvc_id"),
            "ten_dvvc": r.get("ten_dvvc") or "",
            "sdt": r.get("sdt") or "",
            "the_manh": r.get("the_manh") or "",
            "congno_cuoi_ky": cuoi_ky,
            "tong_chi_phi": cp,
            "tong_da_tra": tra,
            "con_phai_tra": con_pt,
            "n_van_chuyen": int(r.get("n_van_chuyen") or 0),
        })

    return {
        "ok": True,
        "items": items,
        "totals": {
            "tong_chi_phi": total_chi,
            "tong_da_tra": total_tra,
            "con_phai_tra": total_con,
            "n_dvvc": len(items),
        },
    }


@router.get("/ncc-module")
def ncc_module(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    filter: str = "all",  # all | da_xong | chua_tra | da_tra
    thang: Optional[str] = None,    # "YYYY-MM" — lọc nhanh theo tháng (cn.ngay)
    tu_ngay: Optional[str] = None,  # "YYYY-MM-DD" — khoảng tùy chọn (cn.ngay >=)
    den_ngay: Optional[str] = None, # "YYYY-MM-DD" — khoảng tùy chọn (cn.ngay <=)
):
    """Module Quản Lý Công Nợ NCC — từ ketoan.cong_no.

    Trả danh sách per-NCC tổng hợp + từng đơn nợ, kèm trạng thái đơn BG.
    filter:
      - all: tất cả phai_tra
      - da_xong: chỉ đơn có baogia.quotes.tien_trinh_mh='Hoàn Thành'
      - chua_tra: con_lai > 0
      - da_tra: trang_thai='da_tra'
    Lọc thời gian (theo cn.ngay — ngày phát sinh nợ): `thang`="YYYY-MM" (nhanh)
    HOẶC khoảng `tu_ngay`/`den_ngay`. `thang` ưu tiên hơn khoảng nếu cùng truyền.
    """
    where_parts = ["cn.loai = 'phai_tra'"]
    params: dict[str, Any] = {}
    if filter == "chua_tra":
        where_parts.append("cn.con_lai > 0")
    elif filter == "da_tra":
        where_parts.append("cn.trang_thai = 'da_tra'")

    # ── Lọc thời gian trên cn.ngay ────────────────────────────────────────────
    if thang:
        try:
            y, m = (int(x) for x in thang.split("-"))
            params["d_from"] = date(y, m, 1)
            # đầu tháng kế tiếp (xử lý rollover tháng 12 → năm sau)
            params["d_to"] = date(y + (m // 12), (m % 12) + 1, 1)
            where_parts.append("cn.ngay >= :d_from AND cn.ngay < :d_to")
        except (ValueError, TypeError):
            pass
    else:
        if tu_ngay:
            params["d_from"] = tu_ngay
            where_parts.append("cn.ngay >= :d_from")
        if den_ngay:
            params["d_to_incl"] = den_ngay
            where_parts.append("cn.ngay <= :d_to_incl")

    where = " AND ".join(where_parts)

    # JOIN thêm saleadmin.vanchuyen (LATERAL — lấy VC mới nhất per ma_don) để biết KT đã
    # đối chiếu xong chưa (hiển thị vc_trang_thai, KHÔNG còn dùng để phân nhóm — xem dưới).
    #
    # Nhóm nợ (thực/dự kiến/cần kiểm) lấy từ ketoan.v_nhom_no_don (quyết định người dùng
    # 29/09/2026, thay hẳn _is_done/has_link cũ — xem migration q6_2026_09_30). Nối theo PO
    # trích từ cn.ref_id (dạng 'MH-ORD-2026-XXX-NCC...' hoặc 'MH-ORD-2026-XXX' không hậu tố).
    #
    # SỬA LỖI NỐI PO 2026-09-30: regex cũ `REGEXP_REPLACE(ref_id, '^MH-(ORD-...)-NCC.*', '\1')`
    # chỉ khớp khi ref_id CÓ '-NCC' theo sau — với ref_id không có hậu tố đó (dạng cũ
    # 'MH-ORD-2026-040'), REGEXP_REPLACE không match gì nên trả nguyên chuỗi gốc (còn 'MH-' ở
    # đầu) → po.id không bao giờ khớp → 22/296 dòng ketoan.cong_no (408.506.000đ, đo 30/09/2026)
    # bị coi như "không có PO" một cách ÂM THẦM. REGEXP_MATCH lấy đúng cụm 'ORD-\d+-\d+' bất kể
    # có hậu tố hay không, chỉ còn đúng 1 dòng thật sự mồ côi (đơn 050, không còn PO nào khớp).
    #
    # SỬA LỖI 2 2026-09-30: "cần kiểm" CHỈ cho dòng THỰC SỰ gắn đơn Mua hàng (ref_id LIKE 'MH-%')
    # mà không nối được PO nào. Bản trước COALESCE(v.nhom_no,'can_kiem') vô điều kiện → 46 dòng
    # nhập tay/đầu kỳ (ref_id NULL) + dòng ĐVVC bị gộp nhầm vào "cần kiểm", ra số âm vô nghĩa
    # (-746 triệu ở modal Đồng bộ). Dòng không gắn đơn Mua hàng là nợ THỰC (đã chốt, giữ hành vi cũ).
    #
    # SỬA LỖI 3 2026-09-30 (Phúc Khánh −17tr): dòng ĐẶT CỌC/TRẢ TRƯỚC (so_tien=0, da_tra>0)
    # không có ref_id nên rơi thẳng vào 'thuc' — trong khi HOÁ ĐƠN mà khoản cọc đó ứng trước lại
    # bị nhóm 'du_kien' (đơn còn đang chạy) và bị ẩn khỏi "thực" → cọc trừ vào một tổng không có
    # hoá đơn tương ứng, ra số âm giả. Cọc phải đi theo nhóm của ĐƠN nó gắn: tra qua
    # cn.ma_don = ma_bao_gia (ma_bao_gia UNIQUE trên purchase_orders — luôn khớp 0 hoặc 1 PO,
    # không có case "nhiều PO" phải phân biệt). Không khớp PO nào → giữ 'thuc' như cũ.
    #
    # REFACTOR 2026-09-30 (migration q7): 3 JOIN nối PO + 2 view ở trên gộp vào MỘT view theo
    # DÒNG ketoan.v_cong_no_phai_tra_phan_loai (đã có po_id + nhom_no tính sẵn) — tránh 4 nơi
    # (ncc_module, _tong_hop, _phai_tra_ncc, bản in) mỗi nơi tự lặp lại cùng logic nối, có nguy
    # cơ trôi. Đã kiểm SQL trực tiếp trên dev: 0 dòng lệch nhom_no so với công thức cũ (tự nối)
    # trước khi đổi — xem alembic/versions/q7_2026_09_30_v_cong_no_phai_tra_phan_loai.py.
    sql = f"""
        SELECT
            cn.id, cn.ngay, cn.doi_tac, cn.so_tien, cn.da_tra, cn.con_lai,
            cn.trang_thai, cn.ma_don, cn.ref_id, cn.ref_source, cn.ghi_chu, cn.han_thanh_toan,
            cn.ngay_tra,
            q.quote_number, q.tien_trinh_mh, q.customer_name, q.salesperson, q.tong_don,
            vc.trang_thai AS vc_trang_thai, vc.ma_vh,
            po.id          AS po_id,
            po.status      AS po_status,
            po.approved_at AS po_approved_at,
            vw.nhom_no
        FROM ketoan.cong_no cn
        LEFT JOIN ketoan.v_cong_no_phai_tra_phan_loai vw ON vw.id = cn.id
        LEFT JOIN baogia.quotes q ON q.quote_number = cn.ma_don
        LEFT JOIN LATERAL (
            SELECT trang_thai, ma_vh
            FROM saleadmin.vanchuyen
            WHERE ma_don = cn.ma_don
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 1
        ) vc ON TRUE
        LEFT JOIN muahang.purchase_orders po ON po.id = vw.po_id
        WHERE {where}
        ORDER BY cn.con_lai DESC, cn.doi_tac, cn.ngay DESC
    """
    rows = _safe_rows(db, sql, **params)

    if filter == "da_xong":
        rows = [r for r in rows if r.get("nhom_no") == "thuc"]

    # Phân nhóm hiển thị (2 cột "Thực"/"Dự kiến", CẦN KIỂM gộp vào "Thực" — giữ đúng hành vi
    # cũ: nợ không gắn PO nào coi là đã chốt, KT phải trả) — gộp lại = TỔNG cong_no.phai_tra:
    #   💰 Nợ Thực Phải Trả = nhom_no='thuc' HOẶC 'can_kiem' (nhãn lạ/NULL/không gắn PO).
    #   📋 Nợ Dự Kiến       = nhom_no='du_kien' (đơn còn đang chạy: đặt hàng/đang SX/đã có hàng).

    # Gộp NCC duplicate — key = tên NCC chính (bỏ phần "(nhóm hàng)" trong ngoặc)
    # → "A TOẢN MÂY (mây)" + "A TOẢN MÂY (mây hàng nghệ)" + "A TOẢN MÂY"
    #   đều về cùng 1 nhóm "A TOẢN MÂY".
    # → Display name = phần trước ngoặc, trimmed.
    import re
    _BRACKET_RE = re.compile(r"\s*\([^)]*\)\s*")

    def _strip_brackets(s: str) -> str:
        """Bỏ MỌI cụm `(...)` trong tên, gộp space dư."""
        if not s:
            return ""
        cleaned = _BRACKET_RE.sub(" ", s).strip()
        return " ".join(cleaned.split())

    def _norm_key(s: str | None) -> str:
        """Key gộp: bỏ ngoặc + lowercase + collapse space."""
        return _strip_brackets(s or "").lower()

    ncc_map: dict[str, dict] = {}
    for r in rows:
        raw_name = r.get("doi_tac") or "(Chưa rõ NCC)"
        display_name = _strip_brackets(raw_name) or raw_name.strip() or "(Chưa rõ NCC)"
        key = _norm_key(raw_name) or "(chưa rõ ncc)"
        if key not in ncc_map:
            ncc_map[key] = {
                "doi_tac": display_name,
                "so_don": 0,
                "tong_no": 0.0,               # = du_kien + thuc (TỔNG mọi đơn)
                "no_du_kien": 0.0,            # còn gắn đơn, chưa hoàn thành
                "no_thuc_phai_tra": 0.0,      # đã hoàn thành + nợ nhập tay
                "da_tra": 0.0,                # SUM(da_tra) TỪ MỌI đơn
                "con_lai": 0.0,               # SUM(con_lai) TỪ MỌI đơn (không clamp)
                "con_lai_thuc": 0.0,          # SUM(con_lai) CHỈ đơn nhóm thực/cần kiểm — quyết
                                               # định 29/09/2026: "còn nợ/phải trả" không cộng dự kiến.
                "no_can_kiem": 0.0,           # SUM(so_tien) riêng đơn nhóm 'can_kiem' (đã gộp vào
                                               # no_thuc_phai_tra ở trên — trường này chỉ để HIỆN
                                               # riêng, không dùng để tính tổng, tránh đếm 2 lần).
                "du_kien_da_ung": 0.0,        # SUM(da_tra) của các dòng CỌC/TRẢ TRƯỚC đi theo
                                               # nhóm dự kiến (quyết định 30/09/2026) — không giấu
                                               # tiền đã chi, chỉ hiện riêng vì hoá đơn chưa chốt.
                "so_don_du_kien": 0,
                "so_don_thuc": 0,
                "so_don_nhap_tay": 0,         # nợ nhập tay (đã gộp vào thực)
                "so_don_da_xong": 0,
                "so_don_chua_tra": 0,
                "don_list": [],
            }
        g = ncc_map[key]
        g["so_don"] += 1
        so_tien = float(r.get("so_tien") or 0)
        da_tra_row = float(r.get("da_tra") or 0)
        con_lai_row = float(r.get("con_lai") or 0)
        tt_mh = r.get("tien_trinh_mh") or ""
        nhom = r.get("nhom_no") or "can_kiem"
        g["tong_no"] += so_tien
        g["da_tra"]  += da_tra_row
        if nhom == "du_kien":
            # 📋 Dự Kiến: đơn còn đang chạy (đặt hàng/đang SX/đã có hàng) — chưa cộng vào phải trả.
            g["no_du_kien"] += so_tien
            g["so_don_du_kien"] += 1
            if da_tra_row > 0:
                # Dòng cọc/trả trước (so_tien=0) hoặc hoá đơn dự kiến đã có tạm ứng — tiền THẬT đã
                # chi, không giấu (xem SỬA LỖI 3 ở khối SQL phía trên).
                g["du_kien_da_ung"] += da_tra_row
        else:
            # 💰 Thực: đơn đã xong (nhom='thuc') HOẶC cần kiểm (nhãn lạ/không gắn PO) — coi là
            # nợ đã chốt, KT phải trả, giữ đúng hành vi cũ cho nợ nhập tay/đầu kỳ.
            g["no_thuc_phai_tra"] += so_tien
            g["so_don_thuc"] += 1
            g["con_lai_thuc"] += con_lai_row
            if nhom == "can_kiem" and not r.get("po_id"):
                g["so_don_nhap_tay"] += 1
            else:
                g["so_don_da_xong"] += 1
            if nhom == "can_kiem":
                g["no_can_kiem"] += so_tien
            nhom = "thuc" if nhom != "can_kiem" else "can_kiem"
        # con_lai tổng = SUM(con_lai per đơn). Đã trả + còn nợ cộng từ MỌI đơn.
        g["con_lai"] += con_lai_row
        if con_lai_row > 0:
            g["so_don_chua_tra"] += 1
        g["don_list"].append({
            "id": r["id"],
            "ngay": r["ngay"].isoformat() if r.get("ngay") else None,
            "ma_don": r.get("ma_don") or "",
            "so_tien": so_tien,
            "da_tra": da_tra_row,
            "con_lai": con_lai_row,
            "trang_thai": r.get("trang_thai") or "",
            "han_thanh_toan": r.get("han_thanh_toan"),
            "ngay_tra": r["ngay_tra"].isoformat() if r.get("ngay_tra") else None,
            "ghi_chu": r.get("ghi_chu") or "",
            "tien_trinh_mh": tt_mh,
            "vc_trang_thai": r.get("vc_trang_thai") or "",
            "ma_vh": r.get("ma_vh") or "",
            "po_id": r.get("po_id") or "",
            "po_status": r.get("po_status") or "",
            "po_approved_at": r["po_approved_at"].isoformat() if r.get("po_approved_at") else None,
            "nhom": nhom,
            "customer_name": r.get("customer_name") or "",
            "salesperson": r.get("salesperson") or "",
        })

    # Anh Quang 2026-06-19: 2 nhóm → tổng = du_kien + thuc (thực đã gồm nhập tay).
    for g in ncc_map.values():
        g["tong_no"] = g["no_du_kien"] + g["no_thuc_phai_tra"]
        # BƯỚC 3 30/09/2026 (quyết định người dùng): con_lai_thuc < 0 nghĩa là đã trả NHIỀU hơn
        # hoá đơn hiện có (tiền ứng trước cho NCC, chưa có hoá đơn để trừ) — đây là TÀI SẢN của
        # công ty, không phải "nợ âm". Tách 2 field DƯƠNG song song, GIỮ NGUYÊN con_lai_thuc (ròng,
        # có thể âm) cho nơi cần đối chiếu kỹ thuật — không đổi ý nghĩa field cũ, chỉ THÊM field mới.
        g["tra_truoc"] = max(0.0, -g["con_lai_thuc"])
        g["con_lai_thuc_duong"] = max(0.0, g["con_lai_thuc"])

    items = sorted(ncc_map.values(), key=lambda x: -x["con_lai"])
    tong_du_kien   = sum(x["no_du_kien"]       for x in items)
    tong_thuc      = sum(x["no_thuc_phai_tra"] for x in items)
    tong_can_kiem  = sum(x["no_can_kiem"]      for x in items)
    da_tra         = sum(x["da_tra"]           for x in items)
    con_lai        = sum(x["con_lai"]          for x in items)
    con_lai_thuc   = sum(x["con_lai_thuc"]     for x in items)
    so_don_du_kien = sum(x["so_don_du_kien"]   for x in items)
    du_kien_da_ung = sum(x["du_kien_da_ung"]   for x in items)
    tong_tra_truoc       = sum(x["tra_truoc"]          for x in items)
    so_ncc_tra_truoc     = sum(1 for x in items if x["tra_truoc"] > 0)
    con_lai_thuc_duong   = sum(x["con_lai_thuc_duong"] for x in items)

    return {
        "filter": filter,
        "stats": {
            "tong_no": tong_du_kien + tong_thuc,
            "no_du_kien": tong_du_kien,
            "no_thuc_phai_tra": tong_thuc,
            # Riêng để hiện dòng "Ngoài số trên — Nợ dự kiến ... Cần kiểm" (30/09/2026) — đã
            # gộp vào no_thuc_phai_tra ở trên, hai field này chỉ để HIỂN THỊ, không cộng thêm.
            "no_can_kiem": tong_can_kiem,
            "so_don_du_kien": so_don_du_kien,
            "du_kien_da_ung": du_kien_da_ung,
            "da_tra": da_tra,
            "con_lai": con_lai,
            # "còn nợ/phải trả" hiển thị (quyết định 29/09/2026) — CHỈ cộng đơn nhóm thực/cần
            # kiểm, KHÔNG cộng dự kiến. con_lai (ở trên) giữ nguyên = tổng RÒNG mọi đơn, dùng cho
            # nơi cần đối chiếu "trả thừa" (xem ghi chú BRIEF2 trong kt-tong-quan.js/kt-cong-no.js).
            "con_lai_thuc": con_lai_thuc,
            # BƯỚC 3 (30/09/2026): "Còn phải trả" HIỂN THỊ mới = chỉ NCC còn nợ dương (không cộng
            # trả trước bù trừ giữa các NCC khác nhau — mỗi NCC là 1 quan hệ độc lập). Thẻ KPI và
            # bảng phải dùng field này thay con_lai_thuc để không hiện số bị kéo âm bởi 1 NCC.
            "con_lai_thuc_duong": con_lai_thuc_duong,
            "tong_tra_truoc": tong_tra_truoc,
            "so_ncc_tra_truoc": so_ncc_tra_truoc,
            "so_ncc": len(items),
        },
        "items": items,
    }


# ─── Đối chiếu Mua hàng (BƯỚC 2, quyết định người dùng 30/09/2026 — phương án B) ───────────
# Hệ thống ĐỀ XUẤT, Kế toán DUYỆT TỪNG DÒNG — không có đường tự động ghi đè `ketoan.cong_no`
# (sổ chuẩn) từ `muahang.congno`. Xem app/services/cong_no_doi_chieu_mh.py cho thuật toán khớp
# + chốt chặn; memory so-no-ncc-quyet-dinh-29-09.md cho bối cảnh 2 sổ độc lập.


@router.get("/doi-chieu-mh")
def doi_chieu_mh_de_xuat(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Danh sách đề xuất đối chiếu Kế toán ↔ Mua hàng — CHỈ ĐỌC, không ghi gì. Mọi vai trò Kế
    toán xem được (require_ketoan_user); chỉ CEO được ÁP DỤNG (POST .../ap-dung riêng).

    Trả 3 nhóm: `cap_nhat_so_tien` (áp được, có thể có dòng bị chặn nếu đã trả nhiều hơn số
    mới), `tao_dong` (MH có mà KT chưa có dòng), `khong_ap_dung_duoc` (không có nút áp — chỉ để
    KT tự xem và xử lý tay, kèm lý do)."""
    de_xuat = tinh_de_xuat(db)
    ap_duoc = [d for d in de_xuat if d.ap_dung_duoc]
    can_xu_ly = [d for d in de_xuat if not d.ap_dung_duoc]
    return {
        "so_ap_dung_duoc": len(ap_duoc),
        "ap_dung_duoc": [d.to_dict() for d in ap_duoc],
        "can_xu_ly": [d.to_dict() for d in can_xu_ly],
        # THÊM field (30/09/2026, giám đốc chốt) — FE dùng để ẩn/khoá nút "Áp dụng đã chọn" cho
        # vai trò không phải CEO, không đổi/xoá field cũ nào ở trên.
        "duoc_ap_dung": user.role in _CEO_THUCHI_ROLES,
    }


class DoiChieuMhChonBody(BaseModel):
    po_id: str
    ncc_id: Optional[str] = None
    loai: str


class DoiChieuMhApDungBody(BaseModel):
    chon: list[DoiChieuMhChonBody]


@router.post("/doi-chieu-mh/ap-dung")
def doi_chieu_mh_ap_dung(
    body: DoiChieuMhApDungBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _CEO_DOI_CHIEU],
):
    """Áp dụng CÁC DÒNG ĐÃ CHỌN — CHỈ CEO (giám đốc chốt 30/09/2026, cùng lần đẩy production
    công nợ). Số tiền tính lại SỐNG từ `tinh_de_xuat()`, không tin số client gửi lên (đơn combo
    đang audit bên Mua hàng nên số có thể đổi giữa lúc mở hộp thoại và lúc bấm áp dụng). Mỗi
    dòng một giao dịch, lỗi dòng nào báo dòng đó, không chặn các dòng khác."""
    if not body.chon:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chưa chọn dòng nào để áp dụng")
    kq = ap_dung_de_xuat(
        db, chon=[c.model_dump() for c in body.chon], user=user,
    )
    # SỬA lỗi 5 (kiểm chứng độc lập 30/09/2026): audit phải nằm ở ROUTER, không phải service
    # (coding-style.md/routers-api.md) — mỗi dòng đã áp dụng thật (commit rồi) ghi 1 log_action
    # riêng, có `request` nên có IP/User-Agent, payload đủ ref_id/ma_don/ngay/số cũ→mới/da_tra.
    for d in kq.da_ap_dung:
        log_action(
            db, app="ketoan", action=d["action"], user=user, request=request,
            resource=d["resource"], payload=d["log_payload"],
        )
    return {
        "da_ap_dung": kq.da_ap_dung, "loi": kq.loi,
        "so_ap_dung": len(kq.da_ap_dung), "so_loi": len(kq.loi),
        # SỬA lỗi 6 kiểm chứng độc lập 30/09/2026: POST bỏ im lặng khi dữ liệu đã đổi giữa lúc
        # mở hộp thoại và lúc bấm (đơn combo đang audit) — client gửi N dòng nhưng cả áp dụng lẫn
        # lỗi đều 0 vì dòng không còn trong tinh_de_xuat() nữa (đã khớp/đã bị xoá/PO đổi trạng
        # thái). Không phải lỗi hệ thống — trả lý do rõ để UI không hiện "Áp dụng 0 dòng" mập mờ.
        "khong_con_de_xuat": len(kq.da_ap_dung) == 0 and len(kq.loi) == 0,
    }
