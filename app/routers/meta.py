"""Meta — danh mục dropdown từ DB (thay V1 đọc Sheets).

GET /api/meta → {loai_chi_phi, tai_khoan_nh, loai_doanh_thu, loai_thanh_toan, quy_su_dung}
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..models import LoaiChiPhi, TaiKhoanNH, QuyDN
from ..services.enums import LOAI_DOANH_THU, LOAI_THANH_TOAN
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("")
def get_meta(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Trả lookup dropdown cho FE — chỉ active rows + enum cố định."""
    lcp = db.execute(
        select(LoaiChiPhi).where(LoaiChiPhi.active.is_(True)).order_by(LoaiChiPhi.ten)
    ).scalars().all()
    tk = db.execute(
        select(TaiKhoanNH).where(TaiKhoanNH.active.is_(True)).order_by(TaiKhoanNH.ten_tk)
    ).scalars().all()
    quy = db.execute(
        select(QuyDN).where(QuyDN.active.is_(True))
        .order_by(QuyDN.parent_id.nulls_first(), QuyDN.thu_tu, QuyDN.id)
    ).scalars().all()
    return {
        "loai_chi_phi": [
            {"id": x.id, "ten": x.ten, "mo_ta": x.mo_ta} for x in lcp
        ],
        "tai_khoan_nh": [
            {
                "id": x.id,
                "ten_tk": x.ten_tk,
                "loai": x.loai,
                "ten_nh": x.ten_nh,
                "so_tk": x.so_tk,
                "chu_tk": x.chu_tk,
            }
            for x in tk
        ],
        "loai_doanh_thu": LOAI_DOANH_THU,
        "loai_thanh_toan": LOAI_THANH_TOAN,
        "quy_su_dung": [
            {"id": x.id, "ten": x.ten_quy, "parent_id": x.parent_id}
            for x in quy
        ],
    }
