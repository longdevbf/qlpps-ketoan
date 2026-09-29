"""Đọc nhanh sổ cái (ketoan.journal_entry/journal_line) cho các màn thuế + phân bổ.

Chỉ tính bút toán `trang_thai = 'da_post'` (bút toán đã đảo có trang_thai 'da_huy',
bút toán đảo của nó cũng 'da_post' nhưng ngược dấu → cộng thẳng vẫn đúng).
"""
from datetime import date
from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import JournalEntry, JournalLine

DA_POST = "da_post"


def tim_but_toan(db: Session, source_type: str, source_id: str) -> Optional[JournalEntry]:
    """Bút toán mới nhất còn hiệu lực của (source_type, source_id)."""
    return db.execute(
        select(JournalEntry)
        .where(JournalEntry.source_type == source_type,
               JournalEntry.source_id == source_id,
               JournalEntry.trang_thai == DA_POST)
        .order_by(JournalEntry.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def phat_sinh(
    db: Session, tai_khoan: Iterable[str], loai: str,
    tu: Optional[date] = None, den: Optional[date] = None,
) -> Decimal:
    """Tổng phát sinh bên `loai` ('no'|'co') của các TK trong [tu, den]."""
    stmt = (
        select(func.coalesce(func.sum(JournalLine.so_tien), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalLine.account_code.in_(list(tai_khoan)),
               JournalLine.loai == loai,
               JournalEntry.trang_thai == DA_POST)
    )
    if tu:
        stmt = stmt.where(JournalEntry.ngay >= tu)
    if den:
        stmt = stmt.where(JournalEntry.ngay <= den)
    return Decimal(db.execute(stmt).scalar() or 0)


def so_du_no(db: Session, tai_khoan: str, den: Optional[date] = None) -> Decimal:
    """Số dư Nợ (Nợ − Có) của 1 TK tới `den` (None = toàn bộ)."""
    return phat_sinh(db, [tai_khoan], "no", den=den) - phat_sinh(db, [tai_khoan], "co", den=den)


def but_toan_ra_dict(je: Optional[JournalEntry]) -> Optional[dict]:
    if je is None:
        return None
    return {"id": je.id, "so_ct": je.ma_but_toan, "ngay": je.ngay.isoformat(),
            "so_tien": int(je.tong_tien)}
