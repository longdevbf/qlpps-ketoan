"""DDL idempotent cho 2 bảng của màn Thuế TNDN + Chi phí chờ phân bổ (2026-09-25).

ketoan không còn dùng alembic từ 2026-05 (head = q5_2026_05_19); bảng mới được
tạo bằng SQL `IF NOT EXISTS` lúc khởi động (xem main.py lifespan, bảng
don_vi/cai_dat_he_thong). Hàm `dam_bao_bang()` làm đúng việc đó, gọi được nhiều
lần. Main session gọi nó trong lifespan; trong lúc chưa gắn, service gọi lười
một lần mỗi tiến trình qua `dam_bao_bang_mot_lan()`.
"""
import logging
import threading

from sqlalchemy import text
from sqlalchemy.engine import Engine

_LOG = logging.getLogger(__name__)

DDL = (
    "CREATE TABLE IF NOT EXISTS ketoan.thue_tndn_dieu_chinh ("
    " id SERIAL PRIMARY KEY,"
    " quy VARCHAR(8) NOT NULL,"
    " thu_tu INTEGER NOT NULL DEFAULT 0,"
    " loai VARCHAR(4) NOT NULL CHECK (loai IN ('tang','giam')),"
    " noi_dung VARCHAR(200) NOT NULL,"
    " so_tien NUMERIC(15,0) NOT NULL CHECK (so_tien > 0),"
    " created_by VARCHAR(64),"
    " created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")",
    "CREATE INDEX IF NOT EXISTS ix_tndn_dc_quy ON ketoan.thue_tndn_dieu_chinh (quy)",
    "CREATE TABLE IF NOT EXISTS ketoan.phan_bo_242 ("
    " cpcd_id INTEGER PRIMARY KEY REFERENCES ketoan.chi_phi_co_dinh(id) ON DELETE CASCADE,"
    " loai VARCHAR(10) NOT NULL CHECK (loai IN ('tra_truoc','ccdc')),"
    " tk_cp VARCHAR(10) NOT NULL,"
    " tk_nguon VARCHAR(10) NOT NULL,"
    " bo_phan VARCHAR(60),"
    " je_ghi_nhan_id INTEGER,"
    " created_by VARCHAR(64),"
    " created_at TIMESTAMPTZ NOT NULL DEFAULT now()"
    ")",
)

_da_chay = False
_khoa = threading.Lock()


def dam_bao_bang(engine: Engine) -> None:
    """Chạy toàn bộ DDL trong 1 transaction (idempotent)."""
    with engine.begin() as c:
        for cau in DDL:
            c.execute(text(cau))


def dam_bao_bang_mot_lan() -> None:
    """Gọi `dam_bao_bang` tối đa 1 lần thành công mỗi tiến trình (fail-soft, có log)."""
    global _da_chay
    if _da_chay:
        return
    with _khoa:
        if _da_chay:
            return
        try:
            from shared.db import engine
            dam_bao_bang(engine)
            _da_chay = True
        except Exception as e:  # pragma: no cover — DB lỗi thì lần gọi sau thử lại
            _LOG.warning("tạo bảng thue_tndn_dieu_chinh/phan_bo_242 lỗi: %s", e)
