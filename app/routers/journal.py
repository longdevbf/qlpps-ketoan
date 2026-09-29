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
    NGHIEP_VU, danh_muc_tk, get_balance_sheet_aggregates, ledger, post_journal, tom_tat_dinh_khoan,
    trial_balance, void_journal,
)
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)

# Bút toán TAY ghi thẳng vốn/doanh thu/tiền (411/421/511/111...) → feed Cân Đối + P&L.
# CHỈ CEO/admin (đồng bộ von_csh + require_ceo_thuchi doanh_thu/so_quy). KT/manager KHÔNG
# được post/void tay — tránh cửa hậu tự tăng vốn/chế doanh thu. (anh Quang 2026-08-31)
_ROLES_POST = ("admin", "ceo", "assistant_ceo")


# ─── Chart of Accounts ───────────────────────────────────────────────────────

@router.get("/accounts", response_model=list[AccountInfo])
def list_accounts(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Chart of Accounts (TT200 Papasan) + TK con của từng tài khoản tiền (1111, 1121…)."""
    return [
        AccountInfo(code=code, name=name)
        for code, name in sorted(danh_muc_tk(db).items())
    ]


@router.get("/nghiep-vu")
def list_nghiep_vu(
    user: Annotated[JWTPayload, _AUTH],
):
    """Các loại nghiệp vụ (mã → nhãn) cho cột "Loại" và ô lọc Thu / Chi của Sổ kế toán."""
    return [{"ma": ma, "nhan": nhan} for ma, nhan in NGHIEP_VU.items()]


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


# ─── Cân đối phát sinh + Sổ cái theo TK ──────────────────────────────────────

def _khoang(tu: Optional[date_cls], den: Optional[date_cls]) -> tuple[date_cls, date_cls]:
    den = den or date_cls.today()
    tu = tu or den.replace(day=1)
    if tu > den:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tu_ngay phải ≤ den_ngay")
    return tu, den


@router.get("/can-doi-phat-sinh")
def can_doi_phat_sinh(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
):
    """Bảng cân đối phát sinh: dư đầu / phát sinh Nợ-Có / dư cuối từng TK (chỉ 'da_post')."""
    tu, den = _khoang(tu, den)
    return {"tu_ngay": tu, "den_ngay": den, "tai_khoan": trial_balance(db, tu, den)}


@router.get("/so-cai")
def so_cai(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    tk: str = Query(..., min_length=3, max_length=20, pattern=r"^\d+$"),
    tu: Optional[date_cls] = Query(None, alias="tu_ngay"),
    den: Optional[date_cls] = Query(None, alias="den_ngay"),
):
    """Sổ cái 1 TK (gồm TK chi tiết cùng đầu số) — dư luỹ kế tính ở máy chủ."""
    tu, den = _khoang(tu, den)
    return ledger(db, tk, tu, den)


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
    return [
        JournalEntrySummary.model_validate(je).model_copy(update=tom_tat_dinh_khoan(je))
        for je in db.execute(stmt).scalars().all()
    ]


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
            "Chỉ CEO/admin được post bút toán manual (ghi thẳng vốn/doanh thu)",
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
    if user.role not in _ROLES_POST:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Chỉ CEO/admin được hủy (đảo) bút toán",
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
