"""Cross-app reader cho văn bản công ty (`hcns.documents`).

Các app khác (marketing/baogia/muahang/...) cần hiển thị văn bản công ty áp
dụng cho phòng ban của họ + văn bản áp dụng toàn công ty mà phòng HCNS đăng.
DB chia schema (`hcns`, `marketing`, ...) nên có thể đọc trực tiếp ở cùng
session — không cần HTTP cross-service.

Visibility logic giống `hcns/app/routers/documents.py::list_documents`:
- `ap_dung_phong_ban` rỗng / chứa 'all' / '*' → áp dụng toàn công ty
- ngược lại → chỉ phòng ban có tên trong list (so sánh case-insensitive,
  trim) thấy được.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


_SQL = text(
    """
    SELECT id, loai, tieu_de, so_hieu, noi_dung, file_url, ngay_ban_hanh,
           ap_dung_phong_ban, created_at, created_by
    FROM hcns.documents
    ORDER BY ngay_ban_hanh DESC NULLS LAST, created_at DESC
    """
)


def _visible(row_pbs, my_pb_low: str) -> bool:
    pbs = list(row_pbs or [])
    if not pbs:
        return True
    low = [str(x).strip().lower() for x in pbs]
    if "all" in low or "*" in low:
        return True
    return bool(my_pb_low) and my_pb_low in low


def list_for_phong_ban(
    db: Session,
    phong_ban: Optional[str],
    *,
    loai: Optional[str] = None,
    bypass_filter: bool = False,
) -> list[dict]:
    """Trả list văn bản hiển thị cho user thuộc `phong_ban` cho trước.

    Format response giữ tên field V1 (giống `hcns` `_to_v1`) để FE tái sử
    dụng helper hiện có.

    `bypass_filter=True` → bỏ qua phòng ban, trả tất cả (dùng cho
    manager/CEO/admin — đồng nhất với HCNS).
    """
    my_pb_low = (phong_ban or "").strip().lower()
    rows = db.execute(_SQL).mappings().all()
    out: list[dict] = []
    for r in rows:
        if loai and r["loai"] != loai:
            continue
        if not bypass_filter and not _visible(r["ap_dung_phong_ban"], my_pb_low):
            continue
        out.append(
            {
                "id": r["id"],
                "ten_van_ban": r["tieu_de"],
                "loai_van_ban": r["loai"],
                "so_hieu": r["so_hieu"],
                "ngay_ban_hanh": r["ngay_ban_hanh"].isoformat()
                if r["ngay_ban_hanh"]
                else None,
                "mo_ta": r["noi_dung"],
                "drive_url": r["file_url"],
                "upload_by": r["created_by"],
                "ap_dung_phong_ban": list(r["ap_dung_phong_ban"] or []),
                "created_at": r["created_at"].isoformat()
                if r["created_at"]
                else None,
            }
        )
    return out
