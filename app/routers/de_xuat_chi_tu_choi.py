"""Kế Toán: TỪ CHỐI "Đề xuất chi" CHƯA CHI ở MỌI cấp — giám đốc yêu cầu 01/10/2026
("đơn chờ chi quá hạn cũng cần nút Từ chối"; "anh Thành duyệt và từ chối được trong quyền của anh — ví dụ ứng lương").

Hai trường hợp: (a) đã duyệt xong (approval_level='done') chưa chi; (b) còn đang chờ duyệt ở cấp Trưởng bộ phận /
Kế toán / Giám đốc mà người bấm KHÔNG phải người duyệt cấp đó (PUT /duyet của shared chỉ cho đúng người của cấp).
Chỉ TỪ CHỐI, không phải duyệt: từ chối chỉ chặn không cho chi tiền nên mở cho người có quyền chi (kế toán) là an toàn;
duyệt thì vẫn theo đúng cấp của shared. Người lập đề xuất của chính mình cũng rút lại được.

Vì sao nằm ở app Kế toán chứ không ở shared/routers/duyet_chi.py: shared/ không deploy được lên production
(vps.py loại trừ `shared`), mà shared chỉ có PUT /duyet (bắt buộc trang_thai='cho_duyet') và POST /chi — không
có đường nào từ chối sau khi CEO đã duyệt xong. Đường này CHỈ GHI vào bảng shared.expense_requests bằng đúng
các trường mà PUT /duyet đã ghi khi từ chối, nên màn Duyệt chi cũ, thông báo và lịch sử đọc được y như cũ.

Cổng quyền = cổng của nút Chi (`_can_chi` trong duyet_chi.py): CEO/admin/trợ lý CEO, hoặc manager/leader/kt CÓ
app 'ketoan' — ai bấm được Chi thì bấm được Từ chối. Chỉ nhận đề xuất approval_level='done' và chưa chi.
Import model và hàm thông báo của shared đặt TRONG hàm (lazy), để production có bản shared cũ hơn cũng không
làm app không khởi động được.
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db

router = APIRouter()
_REQ = require_app("ketoan")
_CEO_ROLES = ("ceo", "admin", "assistant_ceo")
_KT_ROLES = ("manager", "leader", "kt")


class TuChoiTruocChiBody(BaseModel):
    ly_do: str = Field(..., min_length=1)


def _duoc_tu_choi(user: JWTPayload, db: Session) -> bool:
    """Giống `_can_chi` của shared: CEO/admin, hoặc manager/leader/kt có app 'ketoan' (đọc từ DB, không tin JWT cũ)."""
    role = (user.role or "").lower()
    if role in _CEO_ROLES:
        return True
    if role not in _KT_ROLES:
        return False
    from shared.models.user import User  # lazy
    row = db.execute(select(User.apps).where(User.username == user.username).limit(1)).first()
    return bool(row and row[0] and "ketoan" in {str(a).lower() for a in row[0]})


@router.post("/api/de-xuat-chi/{rid}/tu-choi-truoc-chi")
def tu_choi_truoc_chi(
    rid: int,
    body: TuChoiTruocChiBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Đề xuất chưa chi → tu_choi/rejected. Ghi lịch sử level='chi' kèm `tu_cap` (cấp lúc bị từ chối)."""
    if not _duoc_tu_choi(user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được từ chối đề xuất chờ chi")
    from shared.models.expense_request import ExpenseRequest  # lazy
    # Khoá hàng: hai người bấm cùng lúc (hoặc bấm Từ chối đúng lúc người kia bấm Chi) thì người sau thấy trạng thái mới.
    rec = db.execute(
        select(ExpenseRequest).where(ExpenseRequest.id == rid).with_for_update()
    ).scalar_one_or_none()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if getattr(rec, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề xuất này đã chi rồi — không thể từ chối")
    cap_cu = rec.approval_level or ""
    cho_duyet = (rec.trang_thai or "") == "cho_duyet" and cap_cu in ("manager", "ketoan", "ceo")
    duyet_xong = (rec.trang_thai or "") == "da_duyet" and cap_cu == "done"
    if not (cho_duyet or duyet_xong):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đang '{rec.trang_thai}' (cấp '{cap_cu}') — đã kết thúc, không từ chối được nữa",
        )

    try:
        from shared.templates import _lookup_user_info  # lazy
        ho_ten = (_lookup_user_info(user.username)[0] or user.username)
    except Exception:
        ho_ten = user.username
    now = datetime.now(timezone.utc)
    ly_do = body.ly_do.strip()
    rec.approval_history = list(rec.approval_history or []) + [{
        "level": "chi", "username": user.username, "ho_ten": ho_ten,
        "action": "reject", "comment": ly_do, "at": now.isoformat(), "tu_cap": cap_cu,
    }]
    rec.trang_thai = "tu_choi"
    rec.approval_level = "rejected"
    # Trường tương thích UI cũ — y như PUT /duyet khi từ chối
    rec.nguoi_duyet = user.username
    rec.ho_ten_nguoi_duyet = ho_ten
    rec.nhan_xet_duyet = ly_do
    rec.ngay_duyet = now
    db.flush()
    try:
        from shared.services.notify import notify  # lazy
        notify(
            db, target=rec.username, source_app=rec.app_name, event_type="expense:rejected",
            title=f"[Duyệt Chi #{rec.id}] Bị từ chối bởi {ho_ten}", message=ly_do,
            ref_type="expense_request", ref_id=rec.id, url=f"/duyet-chi#id={rec.id}",
            severity="warning", created_by=user.username,
        )
    except Exception:
        import logging
        logging.getLogger(__name__).warning("de_xuat_chi tu_choi_truoc_chi notify failed", exc_info=True)
    db.commit()
    log_action(
        db, app="ketoan", action="tu_choi_truoc_chi_de_xuat_chi", user=user, request=request,
        resource=f"expense_request:{rid}", payload={"ly_do": ly_do, "so_tien": str(rec.so_tien), "tu_cap": cap_cu},
    )
    return {"id": rec.id, "trang_thai": rec.trang_thai, "approval_level": rec.approval_level}
