"""Mai Proposals API — Mode B: Mai đề xuất, CEO duyệt.

Workflow:
  1) Tool tầng AI tạo proposal (status='pending') — KHÔNG nằm trong router này.
  2) CEO list / xem detail / decide qua các endpoint dưới.
  3) Tool execute từng accepted item sau khi /decide — KHÔNG nằm trong router này.

Endpoints (yêu cầu CEO):
  GET    /                              — list proposals (filter status/type/limit)
  GET    /{id}                          — detail
  POST   /{id}/decide                   — duyệt (approve | partial | reject)
  POST   /{id}/cancel                   — user huỷ proposal pending
  DELETE /{id}                          — admin xoá

Mounted bởi orchestrator vào CEO main.py với prefix `/api/mai-proposals`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, require_ceo
from shared.db import get_db
from shared.models.mai_proposal import MaiProposal

router = APIRouter()

_AUTH_READ = Depends(require_ceo(write=False))
_AUTH_WRITE = Depends(require_ceo(write=True))


_VALID_ACTIONS = {"approve", "reject", "partial"}
_TERMINAL_STATUSES = {"approved", "rejected", "partial", "executed", "cancelled"}


# ─── Schemas ─────────────────────────────────────────────────────────────
class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    username: str
    proposal_type: str
    title: str
    rationale: Optional[str]
    items: list
    status: str
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    accepted_ids: Optional[List[int]]
    executed_results: Optional[list]
    executed_at: Optional[datetime]
    rejection_reason: Optional[str]
    created_at: datetime
    updated_at: datetime


class DecideIn(BaseModel):
    action: str = Field(..., description="approve | reject | partial")
    accepted_indexes: Optional[List[int]] = Field(
        None,
        description="Index 0-based của items được duyệt. Bắt buộc khi action='partial'.",
    )
    comment: Optional[str] = Field(
        None, description="Ghi chú CEO (lưu vào rejection_reason khi reject/partial)."
    )


# ─── Helpers ─────────────────────────────────────────────────────────────
def _get_or_404(db: Session, pid: int) -> MaiProposal:
    rec = db.get(MaiProposal, pid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy proposal")
    return rec


def _ensure_pending(rec: MaiProposal) -> None:
    if rec.status != "pending":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Proposal đang ở status='{rec.status}' — không thể thao tác nữa.",
        )


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/", response_model=List[ProposalOut])
def list_proposals(
    user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
    status_: Optional[str] = Query(
        None,
        alias="status",
        description="Filter status. Default = 'pending' của user hiện tại.",
    ),
    type_: Optional[str] = Query(
        None, alias="type", description="Filter proposal_type (directive | approval | ...)"
    ),
    limit: int = Query(50, ge=1, le=500),
    all_users: bool = Query(
        False,
        description="True = list của mọi user (admin view). Default chỉ user hiện tại.",
    ),
):
    stmt = select(MaiProposal).order_by(MaiProposal.created_at.desc())

    if not all_users:
        stmt = stmt.where(MaiProposal.user_id == int(user.sub))

    # Default: pending nếu không pass status
    effective_status = status_ if status_ is not None else "pending"
    if effective_status and effective_status != "all":
        stmt = stmt.where(MaiProposal.status == effective_status)

    if type_:
        stmt = stmt.where(MaiProposal.proposal_type == type_)

    stmt = stmt.limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/{pid}", response_model=ProposalOut)
def get_proposal(
    pid: int,
    _user: Annotated[JWTPayload, _AUTH_READ],
    db: Annotated[Session, Depends(get_db)],
):
    return _get_or_404(db, pid)


@router.post("/{pid}/decide", response_model=ProposalOut)
def decide_proposal(
    pid: int,
    body: DecideIn,
    user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    """CEO duyệt proposal. KHÔNG execute ở đây — tool layer sẽ execute sau."""
    action = (body.action or "").strip().lower()
    if action not in _VALID_ACTIONS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"action không hợp lệ — phải thuộc {sorted(_VALID_ACTIONS)}",
        )

    rec = _get_or_404(db, pid)
    _ensure_pending(rec)

    items = rec.items or []
    n_items = len(items)
    now = datetime.now(timezone.utc)

    if action == "approve":
        rec.status = "approved"
        rec.accepted_ids = None  # NULL = all
        rec.rejection_reason = None

    elif action == "reject":
        rec.status = "rejected"
        rec.accepted_ids = []
        rec.rejection_reason = (body.comment or "").strip() or None

    else:  # partial
        idxs = body.accepted_indexes or []
        if not idxs:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "action='partial' yêu cầu accepted_indexes không rỗng. "
                "Nếu reject all → dùng action='reject'. Nếu approve all → action='approve'.",
            )
        # Dedup + validate range
        norm = sorted({int(i) for i in idxs})
        for i in norm:
            if i < 0 or i >= n_items:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"index {i} ngoài phạm vi items (0..{n_items - 1}).",
                )
        rec.status = "partial"
        rec.accepted_ids = norm
        rec.rejection_reason = (body.comment or "").strip() or None

    rec.approved_by = user.username
    rec.approved_at = now
    db.commit()
    db.refresh(rec)
    return rec


@router.post("/{pid}/cancel", response_model=ProposalOut)
def cancel_proposal(
    pid: int,
    user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    """User (chủ proposal) huỷ proposal khi còn pending."""
    rec = _get_or_404(db, pid)
    _ensure_pending(rec)
    # Owner-only (CEO khác vẫn được — đã qua require_ceo)
    if rec.user_id != int(user.sub):
        # Cho phép CEO khác huỷ — vẫn là CEO role
        pass
    rec.status = "cancelled"
    rec.approved_by = user.username
    rec.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proposal(
    pid: int,
    _user: Annotated[JWTPayload, _AUTH_WRITE],
    db: Annotated[Session, Depends(get_db)],
):
    rec = _get_or_404(db, pid)
    db.delete(rec)
    db.commit()
