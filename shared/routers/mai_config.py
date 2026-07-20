"""Mai Config API — CEO/admin set Targets/Goals + Giọng nói cho Mai AI.

Endpoints (require_ceo + write=True chỉ cho ceo/admin):
  GET    /api/mai-config/targets
  POST   /api/mai-config/targets        body MaiTargetIn (create/upsert)
  DELETE /api/mai-config/targets/{id}

  GET    /api/mai-config/voice          → {config, voices}
  POST   /api/mai-config/voice          body VoiceConfigIn (merge, chỉ CEO/admin)
  POST   /api/mai-config/voice/preview  body VoicePreviewIn → mp3 (Nghe thử)

Mounted bởi orchestrator vào CEO main.py với prefix `/api/mai-config`.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_ceo
from shared.db import get_db
from shared.models.mai_target import MaiTarget

router = APIRouter()

_AUTH_READ = Depends(require_ceo(write=False))
_AUTH_WRITE = Depends(require_ceo(write=True))


_ALLOWED_SCOPES = {"company", "department", "employee"}
_ALLOWED_PERIOD_TYPES = {"month", "quarter", "year"}


# ─── Schemas ─────────────────────────────────────────────────────────────
class MaiTargetIn(BaseModel):
    scope: str = Field(..., description="company | department | employee")
    scope_value: Optional[str] = Field(None, description="NULL khi scope=company")
    metric: str = Field(..., description="doanh_thu | leads | don_hang | kpi ...")
    period_type: str = Field(..., description="month | quarter | year")
    period_value: str = Field(..., description="'2026-05' | '2026-Q2' | '2026'")
    target_value: Decimal = Field(..., description="Số tiền/lượng. Numeric(15,0)")


class MaiTargetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    scope: str
    scope_value: Optional[str]
    metric: str
    period_type: str
    period_value: str
    target_value: Decimal
    created_by: Optional[str]
    created_at: datetime
    updated_at: datetime


# ─── Helpers ─────────────────────────────────────────────────────────────
def _validate(body: MaiTargetIn) -> None:
    if body.scope not in _ALLOWED_SCOPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"scope không hợp lệ: {body.scope} (cần {sorted(_ALLOWED_SCOPES)})",
        )
    if body.period_type not in _ALLOWED_PERIOD_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"period_type không hợp lệ: {body.period_type} (cần {sorted(_ALLOWED_PERIOD_TYPES)})",
        )
    if not (body.metric or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "metric không được trống")
    if not (body.period_value or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "period_value không được trống")
    if body.target_value is None or body.target_value < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "target_value phải ≥ 0")
    if body.scope == "company":
        # scope_value bỏ qua khi company — chuẩn hoá về None
        pass
    else:
        if not (body.scope_value or "").strip():
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"scope={body.scope} cần scope_value (tên phòng / username)",
            )


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/targets", response_model=List[MaiTargetOut])
def list_targets(
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    scope: Optional[str] = None,
    metric: Optional[str] = None,
    period_value: Optional[str] = None,
):
    stmt = select(MaiTarget).order_by(
        MaiTarget.scope.asc(),
        MaiTarget.period_value.desc(),
        MaiTarget.metric.asc(),
    )
    if scope:
        stmt = stmt.where(MaiTarget.scope == scope)
    if metric:
        stmt = stmt.where(MaiTarget.metric == metric)
    if period_value:
        stmt = stmt.where(MaiTarget.period_value == period_value)
    return db.execute(stmt).scalars().all()


@router.post("/targets", response_model=MaiTargetOut, status_code=status.HTTP_200_OK)
def upsert_target(
    body: MaiTargetIn,
    user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    _validate(body)
    scope_value = (body.scope_value or None) if body.scope != "company" else None

    # Upsert theo unique key (scope, COALESCE(scope_value,''), metric, period_value)
    existing = db.execute(
        select(MaiTarget)
        .where(MaiTarget.scope == body.scope)
        .where(MaiTarget.metric == body.metric)
        .where(MaiTarget.period_value == body.period_value)
        .where(
            (MaiTarget.scope_value == scope_value)
            if scope_value is not None
            else MaiTarget.scope_value.is_(None)
        )
        .limit(1)
    ).scalar_one_or_none()

    if existing:
        existing.period_type = body.period_type
        existing.target_value = body.target_value
        existing.created_by = existing.created_by or user.username
        db.flush()
        db.commit()
        db.refresh(existing)
        return existing

    rec = MaiTarget(
        scope=body.scope,
        scope_value=scope_value,
        metric=body.metric.strip(),
        period_type=body.period_type,
        period_value=body.period_value.strip(),
        target_value=body.target_value,
        created_by=user.username,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/targets/{tid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_target(
    tid: int,
    _user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    rec = db.get(MaiTarget, tid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy target")
    db.delete(rec)
    db.commit()


# ─── Giọng nói (Gọi Mai) — global toàn công ty ────────────────────────────
# Cấu hình lưu trong shared.app_config (app='mai', key='voice') qua module
# ceo.app.ai_brief.voice_config (getter/setter dùng chung với agent streaming).
_PREVIEW_TEXT = "Dạ chào sếp, em là Mai đây ạ. Sếp cần em hỗ trợ gì không?"


class VoiceConfigIn(BaseModel):
    """Mọi field optional — chỉ field truyền vào mới bị đổi (merge)."""
    enabled: Optional[bool] = None
    voice: Optional[str] = None
    speed: Optional[int] = Field(None, ge=-3, le=3)
    read_aloud_chat: Optional[bool] = None


class VoicePreviewIn(BaseModel):
    voice: Optional[str] = None
    speed: int = Field(0, ge=-3, le=3)


@router.get("/voice")
def get_voice(_user: Annotated[JWTPayload, _AUTH_READ]):
    """Trả cấu hình giọng nói hiện tại + danh sách giọng khả dụng."""
    from ceo.app.ai_brief.voice_config import get_voice_config

    try:
        from shared.services.tts import list_voices
        voices = list_voices()
    except Exception:
        voices = []
    return {"config": get_voice_config(), "voices": voices}


@router.post("/voice")
def update_voice(
    body: VoiceConfigIn,
    user: Annotated[JWTPayload, _AUTH_WRITE],
):
    """Cập nhật (merge) cấu hình giọng nói — chỉ CEO/admin."""
    from ceo.app.ai_brief.voice_config import set_voice_config

    cfg = set_voice_config(
        enabled=body.enabled,
        voice=body.voice,
        speed=body.speed,
        read_aloud_chat=body.read_aloud_chat,
        updated_by=user.sub,
    )
    return {"ok": True, "config": cfg}


@router.post("/voice/preview")
async def preview_voice(
    body: VoicePreviewIn,
    _user: Annotated[JWTPayload, _AUTH_WRITE],
):
    """Nghe thử 1 câu chào của Mai với giọng/tốc độ chỉ định."""
    from shared.services.tts import synthesize, TTSError

    try:
        mp3 = await synthesize(_PREVIEW_TEXT, voice=body.voice, speed=body.speed)
    except TTSError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"ok": False, "error": str(e)},
        )
    return Response(content=mp3, media_type="audio/mpeg")
