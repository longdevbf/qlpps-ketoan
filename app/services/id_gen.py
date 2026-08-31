"""ID generator cho `cong_no` — pattern 'CN-YYYY-NNNN' theo năm hiện tại."""
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


def next_cong_no_id(db: Session) -> str:
    """Sinh id mới CN-YYYY-NNNN cho công nợ (DB-08, 2026-08-28).

    - Advisory lock theo năm → 2 request đồng thời KHÔNG sinh trùng id (tránh 500 PK).
    - MAX sequence bằng SQL (không kéo toàn bộ id năm về Python — O(1) thay vì O(n)).
    """
    year = datetime.now().year
    prefix = f"CN-{year}-"
    # Khoá theo năm: giữ tới hết transaction → serialize sinh id giữa các request.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
               {"k": f"cong_no_id:{year}"})
    max_seq = db.execute(text("""
        SELECT COALESCE(MAX(CAST(substring(id FROM :plen) AS INTEGER)), 0)
        FROM ketoan.cong_no
        WHERE id LIKE :pat AND substring(id FROM :plen) ~ '^[0-9]+$'
    """), {"plen": len(prefix) + 1, "pat": f"{prefix}%"}).scalar()
    return f"{prefix}{int(max_seq or 0) + 1:04d}"
