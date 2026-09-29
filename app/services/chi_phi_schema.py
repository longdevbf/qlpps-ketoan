"""DDL idempotent cho ketoan.chi_phi_phat_sinh — gọi ở lifespan app/main.py (cùng kiểu tam_ung_schema).

Bug 28/09/2026 (F1 — form ghi tay Thu chi): chỉ mục `uq_cpps_ref_payroll` (alembic 0007) UNIQUE trên TOÀN BỘ cột
`ref_payroll_thang_pb`, vốn dành cho khoá cầu nối lương → chi phí 'PAYROLL-{thang}-{phong_ban}'
(services/chi_phi_from_payroll.py). Tính năng "Kỳ lương" của loại Ứng Lương (router chi_phi, 04/08/2026) lưu
'YYYY-MM' vào CÙNG cột → khoản Ứng Lương thứ hai chọn cùng kỳ lương bị 409 "Dữ liệu vi phạm ràng buộc / trùng lặp"
(màn cũ /app lẫn màn mới). Sửa: vẫn UNIQUE cho khoá cầu nối, bỏ ràng buộc với giá trị kỳ lương 'YYYY-MM' — đúng dạng
mà HCNS payroll đọc (hcns/app/routers/payroll.py: ref_payroll_thang_pb ~ '^[0-9]{4}-[0-9]{2}$').
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine

_MAU_KY_LUONG = "^[0-9]{4}-[0-9]{2}$"

_DDL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cpps_ref_payroll_cau_noi ON ketoan.chi_phi_phat_sinh (ref_payroll_thang_pb) "
    f"WHERE ref_payroll_thang_pb IS NOT NULL AND ref_payroll_thang_pb !~ '{_MAU_KY_LUONG}'",
    "DROP INDEX IF EXISTS ketoan.uq_cpps_ref_payroll",
)


def dam_bao_chi_muc_ky_luong(engine: Engine) -> None:
    """Tạo chỉ mục UNIQUE mới (chỉ khoá cầu nối) rồi bỏ chỉ mục cũ — một giao dịch, chạy lại nhiều lần vẫn an toàn."""
    with engine.begin() as c:
        for sql in _DDL:
            c.execute(text(sql))
