"""SQLAlchemy engine + session factory.

Dev: synchronous engine để đơn giản. Performance đủ cho ~10 req/s/app.
Sau Sprint 1 nếu cần scale: switch sang asyncpg + AsyncSession.
"""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import settings


# Anh Quang 2026-06-12: pool sizing cho cấu hình 23 workers (uvicorn) trên
# Postgres max_connections=250. Mỗi worker tối đa 10 conn (5 pool + 5 overflow)
# → 230 conn peak < 250 limit. pool_recycle 30 phút để rotate conn cũ
# (tránh stale conn khi network reset).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    pool_timeout=30,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: `db: Session = Depends(get_db)`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
