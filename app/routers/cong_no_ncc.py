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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


def _safe_rows(db: Session, sql: str, **params) -> list[dict[str, Any]]:
    """Execute trả list dict. Fail-soft trả [] nếu bảng muahang chưa tồn tại."""
    try:
        rows = db.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]
    except (ProgrammingError, OperationalError):
        db.rollback()
        return []


# Aggregate tổng theo NCC, chia 2 NHÓM (cùng quy tắc với /ncc-module bên dưới):
#
#   💰 NỢ THỰC PHẢI TRẢ: quote.tien_trinh_mh = 'Hoàn thành' (mọi kiểu hoa/thường)
#                        ➕ nợ KHÔNG gắn PO (nhập tay / đầu kỳ) — đã chốt phải trả.
#   📋 NỢ DỰ KIẾN      : còn gắn PO nhưng đơn CHƯA hoàn thành — MỌI trạng thái còn lại
#                        (Đặt hàng, Đang SX, Đã có hàng, Đã lấy hàng, chưa có báo giá…).
#
# BUG FIX 2026-09-25: trước đây lọc bằng SQL `LOWER(q.tien_trinh_mh) IN ('đặt hàng','đang sx',
# 'đã có hàng')`. DB dùng collation "C" nên LOWER() KHÔNG hạ chữ có dấu viết hoa ('Đ' giữ nguyên:
# LOWER('Đang SX') = 'Đang sx') → nhóm dự kiến LUÔN = 0; thêm nữa 'Đã lấy hàng' và nợ không gắn PO
# (INNER JOIN purchase_orders) rơi ra ngoài cả 2 nhóm. Hậu quả: total_orders của summary thấp hơn
# /ncc/<id>/detail (vd CHUNG XINH ncc_d0e28de0: 247.560.354 / 9 đơn vs 274.610.354 / 12 đơn).
# Nay đọc từng dòng rồi phân nhóm trong Python bằng str.casefold() (chuẩn hoá Unicode đúng) —
# mọi dòng no_phai_tra đều vào đúng 1 nhóm ⇒ total_orders = SUM(so_tien) = đúng số của detail.
#
# Còn nợ (cash flow chốt) = Nợ thực phải trả - Đã trả (KHÔNG cộng dự kiến), clamp >= 0.
_SQL_SUMMARY_SUPPLIERS = """
SELECT id AS supplier_id, name AS supplier_name, short_code AS supplier_code,
       phone AS supplier_phone, group_id AS supplier_group_id
FROM muahang.suppliers
"""

_SQL_SUMMARY_NO = """
SELECT cn.ncc_id, cn.so_tien, cn.ngay, cn.ref_order_id,
       po.id AS po_id, q.tien_trinh_mh
FROM muahang.congno cn
LEFT JOIN muahang.purchase_orders po ON po.id = cn.ref_order_id
LEFT JOIN baogia.quotes q ON q.quote_number = po.ref_bao_gia
WHERE cn.loai = 'no_phai_tra' AND cn.ncc_id IS NOT NULL
"""

# "Đã trả" = ĐÃ CHI thực (da_chi=TRUE), KHÔNG phải chỉ mới CEO duyệt.
_SQL_SUMMARY_DA_TRA = """
SELECT ncc_id, SUM(so_tien) AS amt
FROM muahang.congno
WHERE loai = 'de_xuat_tra' AND da_chi = TRUE AND ncc_id IS NOT NULL
GROUP BY ncc_id
"""

_TIEN_TRINH_HOAN_THANH = "hoàn thành"


def _nhom_no(row: dict[str, Any]) -> str:
    """'thuc' | 'du_kien' cho 1 dòng no_phai_tra (xem quy tắc ở chú thích trên)."""
    if (row.get("tien_trinh_mh") or "").strip().casefold() == _TIEN_TRINH_HOAN_THANH:
        return "thuc"
    return "du_kien" if row.get("po_id") else "thuc"


def _tong_hop_ncc(db: Session) -> list[dict[str, Any]]:
    """Gộp nợ dự kiến / nợ thực / đã trả theo NCC, sắp như SQL cũ (balance, thực, tên)."""
    zero = Decimal("0")
    agg: dict[str, dict[str, Any]] = {}
    for r in _safe_rows(db, _SQL_SUMMARY_NO):
        a = agg.setdefault(r["ncc_id"], {"du_kien": zero, "thuc": zero, "orders": set(), "last": None})
        so_tien = Decimal(str(r.get("so_tien") or 0))
        nhom = _nhom_no(r)
        a[nhom] += so_tien
        if r.get("ref_order_id"):
            a["orders"].add(r["ref_order_id"])
        if nhom == "thuc" and r.get("ngay") and (a["last"] is None or r["ngay"] > a["last"]):
            a["last"] = r["ngay"]
    paid = {r["ncc_id"]: Decimal(str(r.get("amt") or 0)) for r in _safe_rows(db, _SQL_SUMMARY_DA_TRA)}

    rows: list[dict[str, Any]] = []
    for s in _safe_rows(db, _SQL_SUMMARY_SUPPLIERS):
        a = agg.get(s["supplier_id"], {"du_kien": zero, "thuc": zero, "orders": set(), "last": None})
        p = paid.get(s["supplier_id"], zero)
        rows.append({
            **s,
            "no_du_kien": a["du_kien"],
            "no_thuc_phai_tra": a["thuc"],
            "total_paid": p,
            "balance": max(a["thuc"] - p, zero),
            "n_orders": len(a["orders"]),
            "last_order_date": a["last"],
            "total_orders": a["du_kien"] + a["thuc"],
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
    po.ngay_dat_xuong AS po_ngay_dat
FROM muahang.congno cn
LEFT JOIN muahang.purchase_orders po ON po.id = cn.ref_order_id
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

    return {
        "supplier": supplier,
        "summary": {
            "total_orders": str(total_orders),
            "total_paid": str(total_paid),
            "balance": str(total_orders - total_paid),
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

    # JOIN thêm saleadmin.vanchuyen (LATERAL — lấy VC mới nhất per ma_don)
    # để biết KT đã đối chiếu xong chưa. Đây là nguồn TIN CẬY NHẤT vì:
    #   - khi KT bấm "Hoàn thành" ở ketoan/external.py:897 → VC.trang_thai='hoan_thanh'
    #   - đồng thời sync quotes.tien_trinh_mh='Hoàn Thành' (có thể fail nếu quote
    #     không match — đơn cũ, migrate, v.v.)
    # → Dùng vc.trang_thai làm primary signal + fallback q.tien_trinh_mh.
    # Anh Quang 2026-06-13: Nợ Dự Kiến = PO đã được CEO/Manager DUYỆT
    # ở app Mua Hàng (approved_at IS NOT NULL) nhưng status chưa 'Hoàn Thành'
    # & chưa 'Bị Từ Chối'. Link: ketoan.cong_no.ref_id 'MH-ORD-XXX-NCC...'
    # → REGEX extract → muahang.purchase_orders.id.
    sql = f"""
        SELECT
            cn.id, cn.ngay, cn.doi_tac, cn.so_tien, cn.da_tra, cn.con_lai,
            cn.trang_thai, cn.ma_don, cn.ref_id, cn.ref_source, cn.ghi_chu, cn.han_thanh_toan,
            cn.ngay_tra,
            q.quote_number, q.tien_trinh_mh, q.customer_name, q.salesperson, q.tong_don,
            vc.trang_thai AS vc_trang_thai, vc.ma_vh,
            po.id          AS po_id,
            po.status      AS po_status,
            po.approved_at AS po_approved_at
        FROM ketoan.cong_no cn
        LEFT JOIN baogia.quotes q ON q.quote_number = cn.ma_don
        LEFT JOIN LATERAL (
            SELECT trang_thai, ma_vh
            FROM saleadmin.vanchuyen
            WHERE ma_don = cn.ma_don
            ORDER BY created_at DESC NULLS LAST, id DESC
            LIMIT 1
        ) vc ON TRUE
        LEFT JOIN muahang.purchase_orders po
               ON po.id = REGEXP_REPLACE(cn.ref_id, '^MH-(ORD-[0-9]+-[0-9]+)-NCC.*', '\\1')
        WHERE {where}
        ORDER BY cn.con_lai DESC, cn.doi_tac, cn.ngay DESC
    """
    rows = _safe_rows(db, sql, **params)

    def _is_done(r: dict) -> bool:
        """Đơn đã xong = VC=hoan_thanh HOẶC quote.tien_trinh_mh='Hoàn thành'
        HOẶC PO status='Hoàn Thành'."""
        if (r.get("vc_trang_thai") or "").lower() == "hoan_thanh":
            return True
        if (r.get("tien_trinh_mh") or "").strip().lower() == "hoàn thành":
            return True
        if (r.get("po_status") or "").strip().lower() == "hoàn thành":
            return True
        return False

    if filter == "da_xong":
        rows = [r for r in rows if _is_done(r)]

    # Phân 2 NHÓM (anh Quang chốt 2026-06-19) — gộp lại = TỔNG cong_no.phai_tra:
    #   💰 Nợ Thực Phải Trả = đơn ĐÃ HOÀN THÀNH (VC=hoan_thanh / TT='Hoàn thành'
    #                          / PO 'Hoàn Thành') ➕ nợ NHẬP TAY/đầu kỳ KHÔNG gắn
    #                          đơn hàng (không link quote/PO & ref_source rỗng) —
    #                          đều là nợ đã chốt, KT phải trả.
    #   📋 Nợ Dự Kiến       = còn GẮN đơn hàng đang chạy (quote khớp / có PO /
    #                          ref_source hệ thống) nhưng CHƯA hoàn thành.

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
        # "Có gắn đơn hàng" = khớp báo giá HOẶC có PO HOẶC ref_source hệ thống
        # (muahang / saleadmin_vc...). Nợ nhập tay/đầu kỳ không có gì trong số này.
        has_link = (
            bool(r.get("quote_number"))
            or bool(r.get("po_id"))
            or bool((r.get("ref_source") or "").strip())
        )
        is_done = _is_done(r)
        g["tong_no"] += so_tien
        g["da_tra"]  += da_tra_row
        # Phân 2 nhóm (ưu tiên is_done trước):
        if is_done:
            # 💰 Thực: đơn đã hoàn thành — đã chốt, KT phải thanh toán.
            g["no_thuc_phai_tra"] += so_tien
            g["so_don_thuc"] += 1
            g["so_don_da_xong"] += 1
            nhom = "thuc"
        elif has_link:
            # 📋 Dự Kiến: còn gắn đơn hàng đang chạy nhưng CHƯA hoàn thành.
            g["no_du_kien"] += so_tien
            g["so_don_du_kien"] += 1
            nhom = "du_kien"
        else:
            # 💰 Thực: nợ nhập tay/đầu kỳ không gắn đơn — coi là nợ đã chốt.
            g["no_thuc_phai_tra"] += so_tien
            g["so_don_thuc"] += 1
            g["so_don_nhap_tay"] += 1
            nhom = "thuc"
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

    items = sorted(ncc_map.values(), key=lambda x: -x["con_lai"])
    tong_du_kien = sum(x["no_du_kien"]       for x in items)
    tong_thuc    = sum(x["no_thuc_phai_tra"] for x in items)
    da_tra       = sum(x["da_tra"]           for x in items)
    con_lai      = sum(x["con_lai"]          for x in items)

    return {
        "filter": filter,
        "stats": {
            "tong_no": tong_du_kien + tong_thuc,
            "no_du_kien": tong_du_kien,
            "no_thuc_phai_tra": tong_thuc,
            "da_tra": da_tra,
            "con_lai": con_lai,
            "so_ncc": len(items),
        },
        "items": items,
    }
