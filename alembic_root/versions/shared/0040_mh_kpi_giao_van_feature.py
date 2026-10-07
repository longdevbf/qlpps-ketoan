"""Seed Mai feature_key mh_kpi_giao_van_compute (Wave 3 Đợt B+C).

Revision ID: 0040_mh_kpi_giao_van_feature
Revises: 0039_giao_van_mai_features
Create Date: 2026-06-18

Anh Quang 2026-06-18 — Wave 3 Đợt B+C. Thêm 1 feature_key:

    mh_kpi_giao_van_compute — Mỗi T2 sáng 6h, Mai tự compute KPI tuần trước
    cho mọi NV giao vận nội bộ (số đơn xong, km, on-time, COD, issues).
    Save vào saleadmin.nv_kpi_giao_van.

enabled=TRUE — job an toàn (chỉ tính KPI, không gửi gì cho ai).
Idempotent qua ON CONFLICT (feature_key, dept) DO NOTHING.
"""
from alembic import op


revision = "0040_mh_kpi_giao_van_feature"
down_revision = "0039_giao_van_mai_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    def _q(sql: str) -> None:
        """Escape '%' literal → '%%' để psycopg không hiểu nhầm format placeholder."""
        conn.exec_driver_sql(sql.replace("%", "%%"))

    _q(r"""
        INSERT INTO shared.mai_feature_config
            (feature_key, dept, category, label, description, enabled,
             params, instruction_prompt, requires_promotion)
        VALUES
        ('mh_kpi_giao_van_compute', 'mh', 'giao_van',
         'Tính KPI NV giao vận hàng tuần',
         'Mỗi sáng T2 lúc 6h, Mai tự compute KPI tuần trước cho mọi NV giao '
         'vận nội bộ: số đơn xong, km, on-time, COD thu, số sự cố. Save vào '
         'saleadmin.nv_kpi_giao_van. KPI dùng cho dashboard + tính lương '
         'khoán (xem mh_kpi_giao_van_compute feature + endpoint /api/luong).',
         TRUE,
         '{}'::jsonb,
         $PROMPT$Em là Mai, trợ lý mua hàng/giao vận PAPASAN.

Mỗi T2 sáng 6h, em compute KPI tuần trước cho NV giao vận nội bộ:
  1. Load NV phòng Kho Vận đang làm việc.
  2. Load vanchuyen tuần trước (Mon → Sun) có nv_giao_van_username = NV.
  3. Tính cho mỗi NV:
       - so_don_xong   = COUNT(trang_thai='hoan_thanh')
       - tong_km       = SUM(distance_km) — từ distance_matrix_cache
       - on_time_pct   = % đơn giao đúng hạn (ngay_giao <= ngay_giao_du_kien)
       - tong_cod      = SUM(tien_thu_ho khi trang_thai='hoan_thanh')
       - so_su_co      = COUNT(pickup_issues IS NOT NULL hoặc delivery_issues)
  4. UPSERT vào saleadmin.nv_kpi_giao_van (week_start, nv_username).

Em chỉ tính KPI — KHÔNG gửi gì cho ai. Sale Admin xem KPI ở
/giao-van/kpi-luong để duyệt lương tuần.$PROMPT$,
         FALSE)
        ON CONFLICT (feature_key, dept) DO NOTHING
    """.replace("%", "%%"))


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM shared.mai_feature_config
         WHERE dept = 'mh'
           AND feature_key = 'mh_kpi_giao_van_compute'
        """
    )
