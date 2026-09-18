"""Dao Tao sessions cho Kế Toán — đọc/ghi cross-schema marketing.dao_tao_sessions.

Pattern copy từ muahang/app/routers/dao_tao.py: bảng nằm trong schema
marketing, ketoan router proxy cross-schema (default scope phong_ban='Kế Toán').
"""
from datetime import date, datetime, timezone
from typing import Annotated, Any, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from marketing.app.models.dao_tao_session import DaoTaoSession
from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db
from shared.services.documents import list_for_phong_ban as _list_company_docs
from shared.services.employees import ten_nv


router = APIRouter()
_REQ = require_app("ketoan")

_DEFAULT_PHONG_BAN = "Kế Toán"
_MANAGER_ROLES = {"admin", "ceo", "assistant_ceo", "manager"}


class DaoTaoFileIn(BaseModel):
    file_id: str
    name: str
    view_url: Optional[str] = None
    download_url: Optional[str] = None
    mime: Optional[str] = None
    ext: Optional[str] = None


class DaoTaoCreate(BaseModel):
    ten: str = Field(min_length=1, max_length=255)
    ngay: Optional[date] = None
    giang_vien: Optional[str] = Field(default=None, max_length=128)
    phong_ban: Optional[str] = Field(default=None, max_length=64)
    mo_ta: Optional[str] = None


class DaoTaoUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    ten: Optional[str] = None
    ngay: Optional[date] = None
    giang_vien: Optional[str] = None
    phong_ban: Optional[str] = None
    mo_ta: Optional[str] = None


def _new_id() -> str:
    now = datetime.now(timezone.utc)
    return f"DT-{now.strftime('%y%m%d')}{uuid.uuid4().hex[:4].upper()}"


def _serialize(s: DaoTaoSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "ten": s.ten,
        "ngay": s.ngay.isoformat() if s.ngay else None,
        "giang_vien": s.giang_vien,
        "phong_ban": s.phong_ban,
        "mo_ta": s.mo_ta,
        "files": list(s.files or []),
        "files_count": len(s.files or []),
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_list(db: Session, rows: list) -> list[dict[str, Any]]:
    # `created_by` lưu username — tra tên MỘT lượt cho cả danh sách rồi gắn THÊM
    # `created_by_ten` cạnh trường cũ (UI vẫn so `created_by` với username để phân quyền).
    ten = ten_nv(db, [r.created_by for r in rows]) if rows else {}
    out = []
    for r in rows:
        d = _serialize(r)
        d["created_by_ten"] = ten.get(r.created_by, r.created_by)
        out.append(d)
    return out


@router.get("/sessions")
def list_sessions(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
    phong_ban: Optional[str] = Query(default=None),
    all: bool = Query(default=False, description="Bỏ filter Kế Toán nếu manager"),
) -> list[dict[str, Any]]:
    q = db.query(DaoTaoSession)
    if phong_ban:
        q = q.filter(DaoTaoSession.phong_ban == phong_ban)
    elif not all or user.role not in _MANAGER_ROLES:
        q = q.filter(
            (DaoTaoSession.phong_ban == _DEFAULT_PHONG_BAN)
            | (DaoTaoSession.phong_ban.is_(None))
            | (DaoTaoSession.created_by == user.username)
        )
    rows = q.order_by(DaoTaoSession.created_at.desc()).all()
    return _serialize_list(db, rows)


@router.get("/me")
def list_my_sessions(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> list[dict[str, Any]]:
    """Sessions do mình tạo / phong_ban Kế Toán / general (no phong_ban)."""
    pb: Optional[str] = None
    try:
        row = db.execute(text(
            "SELECT phong_ban FROM hcns.employees "
            "WHERE username=:u AND trang_thai IN ('active', 'Đang làm') LIMIT 1"
        ), {"u": user.username}).first()
        if row:
            pb = row[0]
    except SQLAlchemyError:
        db.rollback()
    except Exception:
        pass
    pb = pb or _DEFAULT_PHONG_BAN

    rows = (
        db.query(DaoTaoSession)
        .filter(
            (DaoTaoSession.created_by == user.username)
            | (DaoTaoSession.phong_ban == pb)
            | (DaoTaoSession.phong_ban.is_(None))
        )
        .order_by(DaoTaoSession.created_at.desc())
        .all()
    )
    return _serialize_list(db, rows)


@router.get("/van-ban-cong-ty")
def list_company_documents(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
    loai: Optional[str] = Query(default=None),
) -> dict[str, Any]:
    """Văn bản công ty áp dụng cho phòng ban của user (đọc từ HCNS)."""
    pb: Optional[str] = None
    try:
        row = db.execute(text(
            "SELECT phong_ban FROM hcns.employees "
            "WHERE username=:u AND trang_thai IN ('active', 'Đang làm') LIMIT 1"
        ), {"u": user.username}).first()
        if row:
            pb = row[0]
    except SQLAlchemyError:
        db.rollback()
    except Exception:
        pass
    pb = pb or _DEFAULT_PHONG_BAN
    role = (user.role or "").lower()
    bypass = role in _MANAGER_ROLES
    docs = _list_company_docs(db, phong_ban=pb, loai=loai, bypass_filter=bypass)
    return {"phong_ban": pb, "documents": docs}


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def create_session(
    body: DaoTaoCreate,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    data = body.model_dump(exclude_none=True)
    data.setdefault("phong_ban", _DEFAULT_PHONG_BAN)
    sess = DaoTaoSession(
        id=_new_id(),
        created_by=user.username,
        files=[],
        **data,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    try:
        from shared.services.calendar_sync import upsert_event_from_dao_tao
        upsert_event_from_dao_tao(db, sess)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    log_action(
        db, app="ketoan", user=user, action="create_dao_tao",
        resource=f"dao_tao:{sess.id}", request=request,
        payload={"ten": sess.ten, "phong_ban": sess.phong_ban},
    )
    return _serialize(sess)


@router.get("/sessions/{sid}")
def get_session(
    sid: str,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    sess = db.get(DaoTaoSession, sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session không tồn tại")
    return _serialize_list(db, [sess])[0]


@router.api_route("/sessions/{sid}", methods=["PATCH", "PUT"])
def update_session(
    sid: str,
    body: DaoTaoUpdate,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    sess = db.get(DaoTaoSession, sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session không tồn tại")
    if sess.created_by != user.username and user.role not in _MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền sửa session")

    diff: dict = {}
    for k, v in body.model_dump(exclude_unset=True).items():
        old = getattr(sess, k)
        if old != v:
            diff[k] = {"old": str(old) if old is not None else None,
                       "new": str(v) if v is not None else None}
            setattr(sess, k, v)
    if diff:
        db.commit()
        db.refresh(sess)
        try:
            from shared.services.calendar_sync import upsert_event_from_dao_tao
            upsert_event_from_dao_tao(db, sess)
            db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
        log_action(
            db, app="ketoan", user=user, action="update_dao_tao",
            resource=f"dao_tao:{sid}", request=request, payload={"diff": diff},
        )
    return _serialize(sess)


@router.delete("/sessions/{sid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    sid: str,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    sess = db.get(DaoTaoSession, sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session không tồn tại")
    if sess.created_by != user.username and user.role not in _MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền xóa session")

    try:
        from shared.services.calendar_sync import delete_event_by_source
        delete_event_by_source(db, "dao_tao_session", str(sess.id))
    except Exception:
        pass
    db.delete(sess)
    db.commit()
    log_action(
        db, app="ketoan", user=user, action="delete_dao_tao",
        resource=f"dao_tao:{sid}", request=request,
    )


@router.post("/sessions/{sid}/files")
def add_file_meta(
    sid: str,
    body: DaoTaoFileIn,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    sess = db.get(DaoTaoSession, sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session không tồn tại")

    files = list(sess.files or [])
    item = body.model_dump(exclude_none=True)
    item["uploaded_by"] = user.username
    item["uploaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    files.append(item)
    sess.files = files
    db.commit()
    db.refresh(sess)
    log_action(
        db, app="ketoan", user=user, action="add_dao_tao_file",
        resource=f"dao_tao:{sid}", request=request,
        payload={"file_id": body.file_id, "name": body.name},
    )
    return _serialize(sess)


@router.delete("/sessions/{sid}/file/{file_id}")
def delete_file_meta(
    sid: str,
    file_id: str,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    sess = db.get(DaoTaoSession, sid)
    if not sess:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session không tồn tại")
    if sess.created_by != user.username and user.role not in _MANAGER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền xóa file")

    new_files = [f for f in (sess.files or []) if f.get("file_id") != file_id]
    if len(new_files) == len(sess.files or []):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File không tồn tại")
    sess.files = new_files
    db.commit()
    db.refresh(sess)
    log_action(
        db, app="ketoan", user=user, action="delete_dao_tao_file",
        resource=f"dao_tao:{sid}", request=request, payload={"file_id": file_id},
    )
    return _serialize(sess)
