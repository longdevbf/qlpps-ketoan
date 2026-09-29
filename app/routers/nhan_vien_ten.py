"""GET /api/nhan-vien/ten — bảng mã NV → họ tên cho lớp hiển thị dùng chung
(static/js/ten-nhan-vien.js đổi mọi chỗ in mã trơn thành tên)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.auth import JWTPayload
from shared.db import get_db

from ..services.nhan_vien_ten import ban_do_ten
from ._deps import require_ketoan_user

router = APIRouter()
_AUTH = Depends(require_ketoan_user)


@router.get("/api/nhan-vien/ten")
def get_ban_do_ten(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    return ban_do_ten(db)
