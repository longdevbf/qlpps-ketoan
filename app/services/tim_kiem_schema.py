"""DDL idempotent cho hàm SQL `ketoan.bo_dau(text)` — tìm kiếm không phân biệt dấu + hoa/thường (28/09/2026).

Gọi `dam_bao_ham_bo_dau(engine)` trong lifespan app/main.py (cùng kiểu tam_ung_schema / chi_phi_schema).
Thân hàm dựng từ đúng hằng số của `tim_kiem.bo_dau_py()` → SQL và Python luôn đồng nhất (quy tắc: xem tim_kiem.py).
Chỉ dùng hàm có sẵn normalize() (PostgreSQL ≥ 13) + lower() + translate(); KHÔNG dùng extension unaccent.
IMMUTABLE + thân một biểu thức → planner inline được và dùng được trong chỉ mục biểu thức.
Đổi quy tắc bỏ dấu thì phải REINDEX các chỉ mục có dùng ketoan.bo_dau().
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

from .tim_kiem import CHU_D, DAU_KET_HOP, TEN_HAM_SQL


def _e(chuoi: str) -> str:
    """Chuỗi → dạng thoát \\uXXXX cho literal E'…' (DDL thuần ASCII, dễ đọc trong pg_proc)."""
    return "".join(f"\\u{ord(c):04x}" for c in chuoi)


THAN_HAM = f"SELECT translate(lower(normalize(s, NFD)), E'{_e(CHU_D + DAU_KET_HOP)}', '{'d' * len(CHU_D)}')"
DDL = (
    f"CREATE OR REPLACE FUNCTION {TEN_HAM_SQL}(s text) RETURNS text "
    "LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE "
    f"AS $bo_dau$ {THAN_HAM} $bo_dau$"
)
_SQL_THAN_HIEN_TAI = (
    "SELECT p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
    "WHERE n.nspname = 'ketoan' AND p.proname = 'bo_dau' AND p.pronargs = 1"
)


def dam_bao_ham_bo_dau(engine: Engine) -> None:
    """Tạo / cập nhật ketoan.bo_dau(text). Đã đúng thân hàm thì bỏ qua (không khoá catalog mỗi lần khởi động)."""
    with engine.begin() as c:
        than = c.execute(text(_SQL_THAN_HIEN_TAI)).scalar()
        if than is not None and than.strip() == THAN_HAM:
            return
        c.execute(text(DDL))
