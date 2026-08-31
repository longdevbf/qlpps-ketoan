"""Journal Entry API — sổ nhật ký bút toán nợ–có (Phase 2).

Endpoints (prefix /api/journal):
    GET    /                       — list bút toán (filter from/to/source_type)
    GET    /accounts               — Chart of Accounts (TT200 — 22 mã)
    GET    /balance-summary        — aggregates by account_code (≤ den_ngay)
    GET    /{id}                   — chi tiết + lines
    POST   /                       — manual posting (admin/kt only)
    POST   /{id}/void              — đảo bút toán
"""
from datetime import date as date_cls
from decimal import Decimal
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import JournalEntry
from ..schemas import (
    AccountInfo, JournalEntryIn, JournalEntryOut, JournalEntrySummary,
)
from ..services.journal import (
    ACCOUNTS, get_balance_sheet_aggregates, post_journal, void_journal,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)

_ROLES_POST = ("admin", "ceo", "assistant_ceo", "manager", "kt")


# ─── Chart of Accounts ───────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[AccountInfo])
def list_accounts(
    user: Annotated[JWTPayload, _AUTH],
):
    """Trả Chart of Accounts (TT200 — 22 mã Papasan dùng)."""
    return [
        AccountInfo(code=code, name=name)
        for code, name in sorted(ACCOUNTS.items())
    ]


# ─── Balance summary aggregate ───────────────────────────────────────────────

@router.get("/balance-summary")
def balance_summary(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    den_ngay: Optional[date_cls] = Query(None),
):
    """Trả dict {account_code: net_balance} tới `den_ngay`.

    - Tài sản (111/112/131/156/211): net = SUM(no) - SUM(co).
    - Nguồn vốn (311/331/334/341/353/411/414/415/421): net = SUM(co) - SUM(no).
    - Doanh thu (511/711) / Chi phí (632/635/641/642/811/821) cũng trả luôn.
    """
    den = den_ngay or date_cls.today()
    aggregates = get_balance_sheet_aggregates(db, den)
    return {
        "den_ngay": str(den),
        "accounts": aggregates,
    }


# ─── List ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[JournalEntrySummary])
def list_journal(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    from_date: Optional[date_cls] = Query(None, alias="from"),
    to_date: Optional[date_cls] = Query(None, alias="to"),
    source_type: Optional[str] = Query(None),
    trang_thai: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = 0,
):
    stmt = select(JournalEntry).order_by(
        JournalEntry.ngay.desc(), JournalEntry.id.desc()
    )
    if from_date:
        stmt = stmt.where(JournalEntry.ngay >= from_date)
    if to_date:
        stmt = stmt.where(JournalEntry.ngay <= to_date)
    if source_type:
        stmt = stmt.where(JournalEntry.source_type == source_type)
    if trang_thai:
        stmt = stmt.where(JournalEntry.trang_thai == trang_thai)
    stmt = stmt.limit(limit).offset(offset)
    return db.execute(stmt).scalars().all()


# ─── Detail ──────────────────────────────────────────────────────────────────

@router.get("/{je_id}", response_model=JournalEntryOut)
def get_journal(
    je_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    je = db.get(JournalEntry, je_id)
    if not je:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bút toán không tồn tại")
    return je


# ─── POST manual ─────────────────────────────────────────────────────────────

@router.post(
    "", response_model=JournalEntryOut, status_code=status.HTTP_201_CREATED,
)
def create_journal(
    body: JournalEntryIn,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Manual posting bút toán — admin/kt only."""
    if user.role not in _ROLES_POST:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Chỉ admin/ceo/manager/kt được post bút toán manual",
        )

    je = post_journal(
        db,
        ngay=body.ngay,
        mo_ta=body.mo_ta,
        source_type=body.source_type or "other",
        source_id=body.source_id,
        lines=[ln.model_dump() for ln in body.lines],
        by_user=user.username,
    )
    db.commit()
    db.refresh(je)
    log_action(
        db, app="ketoan", action="journal_post", user=user, request=request,
        resource=f"journal_entry:{je.id}",
        payload={
            "ma_but_toan": je.ma_but_toan,
            "tong_tien": float(je.tong_tien),
            "source_type": je.source_type,
        },
    )
    return je


# ─── Void ────────────────────────────────────────────────────────────────────

@router.post("/{je_id}/void", response_model=JournalEntryOut)
def void(
    je_id: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if user.role not in ("admin", "ceo", "manager", "kt"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chỉ admin/ceo/manager/kt được hủy bút toán",
        )
    rev = void_journal(db, je_id=je_id, by_user=user.username)
    db.commit()
    db.refresh(rev)
    log_action(
        db, app="ketoan", action="journal_void", user=user, request=request,
        resource=f"journal_entry:{je_id}",
        payload={"reversal_id": rev.id, "reversal_ma": rev.ma_but_toan},
    )
    return rev
