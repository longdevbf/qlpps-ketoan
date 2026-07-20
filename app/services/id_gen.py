"""ID generator cho `cong_no` — pattern 'CN-YYYY-NNNN' theo năm hiện tại."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CongNo


def next_cong_no_id(db: Session) -> str:
    """Sinh id mới CN-YYYY-NNNN cho công nợ.

    Lấy max sequence năm hiện tại + 1. Race-condition acceptable cho dev;
    production nên dùng SEQUENCE riêng hoặc advisory lock.
    """
    year = datetime.now().year
    prefix = f"CN-{year}-"
    rows = db.execute(
        select(CongNo.id).where(CongNo.id.like(f"{prefix}%"))
    ).all()
    max_seq = 0
    for (cid,) in rows:
        try:
            seq = int(cid[len(prefix):])
            if seq > max_seq:
                max_seq = seq
        except (ValueError, TypeError):
            continue
    return f"{prefix}{max_seq + 1:04d}"
