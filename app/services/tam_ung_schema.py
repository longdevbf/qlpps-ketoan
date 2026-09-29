"""DDL idempotent cho 2 màn làm thật 2026-09-25: Tạm ứng (TK 141) + Số dư đầu
kỳ theo hệ thống tài khoản (chi tiết đối tượng).

Cùng cách với các bảng mới gần đây của ketoan (don_vi / cai_dat_he_thong —
xem app/main.py:lifespan): `CREATE TABLE IF NOT EXISTS` chạy lúc khởi động, an
toàn khi chạy lại. Gọi `ensure_schema(engine)` trong lifespan của app/main.py.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

_log = logging.getLogger(__name__)

_DDL: tuple[str, ...] = (
    "CREATE TABLE IF NOT EXISTS ketoan.tam_ung ("
    " id SERIAL PRIMARY KEY,"
    " so_ct VARCHAR(20) NOT NULL UNIQUE,"
    " ngay DATE NOT NULL,"
    " nhan_vien_ma VARCHAR(16) NOT NULL,"
    " nhan_vien_ten VARCHAR(255) NOT NULL,"
    " noi_dung TEXT NOT NULL,"
    " so_tien NUMERIC(15,0) NOT NULL CHECK (so_tien > 0),"
    " han_hoan DATE NOT NULL,"
    " tai_khoan_id INTEGER REFERENCES ketoan.tai_khoan_nh(id) ON DELETE SET NULL,"
    " tai_khoan_ten VARCHAR(255),"
    " tk_tien VARCHAR(10) NOT NULL,"
    " journal_id INTEGER,"
    " so_quy_id INTEGER,"
    " trang_thai VARCHAR(20) NOT NULL DEFAULT 'hieu_luc',"
    " created_by VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
    " updated_by VARCHAR(64), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")",
    "CREATE INDEX IF NOT EXISTS ix_tam_ung_nv ON ketoan.tam_ung (nhan_vien_ma)",
    "CREATE INDEX IF NOT EXISTS ix_tam_ung_ngay ON ketoan.tam_ung (ngay)",
    "CREATE TABLE IF NOT EXISTS ketoan.tam_ung_quyet_toan ("
    " id SERIAL PRIMARY KEY,"
    " tam_ung_id INTEGER NOT NULL REFERENCES ketoan.tam_ung(id) ON DELETE CASCADE,"
    " so_ct VARCHAR(20) NOT NULL UNIQUE,"
    " ngay DATE NOT NULL,"
    " chi_phi NUMERIC(15,0) NOT NULL DEFAULT 0,"
    " tk_cp VARCHAR(10),"
    " hoan NUMERIC(15,0) NOT NULL DEFAULT 0,"
    " chi_bu NUMERIC(15,0) NOT NULL DEFAULT 0,"
    " xu_ly_thua VARCHAR(20),"
    " giam_tam_ung NUMERIC(15,0) NOT NULL,"
    " ket_thuc BOOLEAN NOT NULL DEFAULT false,"
    " ghi_chu TEXT,"
    " journal_id INTEGER, so_quy_id INTEGER, chi_phi_id INTEGER,"
    " trang_thai VARCHAR(20) NOT NULL DEFAULT 'hieu_luc',"
    " created_by VARCHAR(64), created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")",
    "CREATE INDEX IF NOT EXISTS ix_tu_qt_tam_ung ON ketoan.tam_ung_quyet_toan (tam_ung_id)",
    "CREATE TABLE IF NOT EXISTS ketoan.so_du_dau_ky_doi_tuong ("
    " id SERIAL PRIMARY KEY,"
    " tk VARCHAR(10) NOT NULL,"
    " doi_tuong_id VARCHAR(64) NOT NULL,"
    " ma VARCHAR(64),"
    " ten VARCHAR(255) NOT NULL,"
    " du_no NUMERIC(15,0) NOT NULL DEFAULT 0,"
    " du_co NUMERIC(15,0) NOT NULL DEFAULT 0,"
    " updated_by VARCHAR(64), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),"
    " CONSTRAINT uq_sddk_dt_tk_dt UNIQUE (tk, doi_tuong_id)"
    ")",
)


def ensure_schema(engine: Engine) -> None:
    """Tạo 3 bảng nếu chưa có. Fail-soft (log) — giống các auto-migrate khác."""
    try:
        with engine.begin() as conn:
            for ddl in _DDL:
                conn.execute(text(ddl))
    except Exception as e:  # pragma: no cover — chỉ log, không chặn khởi động
        _log.warning("auto-migrate tam_ung/so_du_dau_ky_doi_tuong failed: %s", e)
