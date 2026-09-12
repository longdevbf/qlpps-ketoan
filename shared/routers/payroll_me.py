"""Shared router /api/payroll/me — cho phép NV mọi app (baogia/marketing/muahang/
ketoan/saleadmin/ceo/hcns) xem chấm công + lương cá nhân của mình.

Anh Quang 2026-06-06: NV vào Hồ Sơ Cá Nhân ở app của mình (không link sang HCNS).
Reuse logic /api/payroll/me của HCNS bằng cách import + delegate.
"""
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db

router = APIRouter()


@router.get("/me")
def shared_my_payroll(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    thang: Optional[str] = None,
):
    """Delegate sang hcns.payroll.my_payroll — share cùng logic, cùng DB.

    Auth chỉ cần login (current_user) — endpoint chỉ trả data của user.username.
    """
    try:
        from hcns.app.routers.payroll import my_payroll as _hcns_my_payroll
    except Exception as e:
        raise HTTPException(500, f"Cannot import hcns.payroll: {e}")
    return _hcns_my_payroll(user=user, db=db, thang=thang)


# Bản sao schema LuongThangCaNhanOut / LichSuLuongCaNhanOut của hcns/app/routers/payroll.py.
# Không import từ hcns ở đầu module: giữ đúng cách /me ở trên (import trong thân hàm) để app nạp
# router này vẫn khởi động được khi không import được hcns. Thêm field bên hcns thì thêm cả ở
# đây — response_model lọc bỏ mọi key không khai.
class LuongThangCaNhanOut(BaseModel):
    thang: str
    luong_co_ban: float
    so_ngay_cong: float
    tong_cong: float
    tong_tru: float
    luong_thuc_nhan: float
    luong_m5: float
    luong_m15: float


class LichSuLuongCaNhanOut(BaseModel):
    den: str
    items: list[LuongThangCaNhanOut]


@router.get("/me/lich-su", response_model=LichSuLuongCaNhanOut)
def shared_my_payroll_history(
    user: Annotated[JWTPayload, Depends(current_user)],
    db: Annotated[Session, Depends(get_db)],
    den: Annotated[Optional[str], Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
    so_thang: Annotated[int, Query(ge=1, le=12)] = 6,
):
    """Delegate sang hcns.payroll.my_payroll_history — lịch sử lương cá nhân N tháng.

    Kiểm tham số ở ĐÂY bằng Query vì lời gọi hàm Python bên dưới không qua bộ kiểm của FastAPI.
    """
    try:
        from hcns.app.routers.payroll import my_payroll_history as _hcns_lich_su
    except Exception as e:
        raise HTTPException(500, f"Cannot import hcns.payroll: {e}")
    return _hcns_lich_su(user=user, db=db, den=den, so_thang=so_thang)
