"""Seed 2 Mai feature config cho Giao Vận Nội Bộ.

Revision ID: 0039_giao_van_mai_features
Revises: 0038_mh_supplier_health
Create Date: 2026-06-18

Anh Quang 2026-06-18 — Wave 2E. Thêm 2 feature_key vào
shared.mai_feature_config (dept='mh', category='giao_van'):

    1. mh_de_xuat_lich_giao_van   — Mỗi chiều 16h, Mai đề xuất lịch giao
       vận ngày mai cho 2 NV nội bộ. Sale Admin review + chốt.

    2. mh_giao_van_defect_report  — Mỗi chiều 18h, Mai tổng hợp lỗi NCC
       30 ngày qua, cảnh báo NCC defect rate cao, auto note vào
       muahang.suppliers.notes_detail.

Cả 2 enabled=FALSE — CEO bật từng cái khi đã sẵn sàng. Idempotent qua
ON CONFLICT (feature_key, dept) DO NOTHING.
"""
from alembic import op


revision = "0039_giao_van_mai_features"
down_revision = "0038_mh_supplier_health"
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
        ('mh_de_xuat_lich_giao_van', 'mh', 'giao_van',
         'Mai đề xuất lịch giao vận ngày mai',
         'Mỗi chiều 16h, Mai phân tích đơn dự kiến giao ngày mai (vanchuyen '
         'ngay_giao = tomorrow hoặc chưa có ngày + trạng thái cho_lay) và '
         'đề xuất lịch cho các NV giao vận nội bộ (phong_ban=Kho Vận, đang '
         'làm). Mai group đơn theo NCC pickup để tối ưu lộ trình, balance '
         'workload round-robin (NV ít việc nhận cụm tiếp theo), tối đa 5 đơn '
         '/chuyến. Save vào saleadmin.lich_giao_van status=de_xuat. Sale '
         'Admin review + chốt thành da_chot trước khi NV nhận lịch.',
         FALSE,
         '{"max_orders_per_trip":5,"gio_sang":"08:00","gio_chieu":"14:00"}'::jsonb,
         $PROMPT$Em là Mai, trợ lý mua hàng/giao vận PAPASAN.

Mỗi chiều 16h, em phân tích đơn vận chuyển dự kiến giao ngày mai và đề xuất
lịch cho các NV giao vận nội bộ. Sale Admin review + chốt.

Quy tắc lập lịch:
  1. Load NV phòng Kho Vận đang làm việc.
  2. Load đơn vanchuyen ngày mai (hoặc chưa có ngày + chờ lấy), chỉ pickup
     nội bộ (pickup_mode=noi_bo hoặc NULL = auto).
  3. Group đơn theo NCC pickup (cùng NCC → cùng NV để đỡ trùng xe).
  4. Balance workload: NV ít đơn nhất nhận cụm NCC tiếp theo. Mỗi chuyến
     (sang/chieu) tối đa 5 đơn.
  5. Save status='de_xuat'. KHÔNG đụng lịch đã 'da_chot'.

Em chỉ ĐỀ XUẤT — quyết định cuối là Sale Admin. Em không gửi tin cho NV
trực tiếp ở bước này; SA chốt xong sẽ tự notify NV qua nút "Chốt lịch".$PROMPT$,
         FALSE),

        ('mh_giao_van_defect_report', 'mh', 'giao_van',
         'Báo cáo lỗi NCC tự động',
         'Mỗi chiều 18h, Mai tổng hợp lỗi NCC 30 ngày qua từ vanchuyen.pickup_issues. '
         'Group theo NCC (pickup_ncc_id ưu tiên, fallback pickup_addr), '
         'tính defect rate = so_loi/tong_don. Phân loại critical (>20%), '
         'warning (>10%), normal. Nếu có NCC critical/warning → DM CEO + '
         'Sale Admin qua shared.notifications. NCC critical có pickup_ncc_id '
         '→ append note Mai auto vào muahang.suppliers.notes_detail. Tối '
         'thiểu 3 đơn / NCC mới được tính.',
         FALSE,
         '{"warning_threshold_pct":10.0,"critical_threshold_pct":20.0,"min_don":3,"window_days":30}'::jsonb,
         $PROMPT$Em là Mai, trợ lý mua hàng PAPASAN — báo cáo lỗi NCC giao vận.

Mỗi chiều 18h, em tổng hợp lỗi NCC pickup 30 ngày qua:
  - Đếm số đơn có pickup_issues (NV ghi nhận khi đi lấy).
  - Tính defect rate = số đơn lỗi / tổng đơn.
  - Bỏ NCC < 3 đơn (sample quá ít, tránh false positive).
  - Phân loại: > 20% critical, > 10% warning, còn lại normal.

Output:
  1. DM CEO + Sale Admin nếu có NCC critical hoặc warning (icon 🔴/🟡, top 3).
  2. Append note vào muahang.suppliers.notes_detail cho NCC critical
     (1 note/NCC/ngày, idempotent). Note rule-based, có số liệu cụ thể:
     "[Mai auto YYYY-MM-DD] NCC có X% lỗi pickup (a/b đơn). Cần dặn NV
      kiểm tra kỹ + cuộc gặp với chủ NCC."

Tone báo cáo, KHÔNG kết luận thay người. Số liệu lấy từ DB, KHÔNG bịa.$PROMPT$,
         FALSE)
        ON CONFLICT (feature_key, dept) DO NOTHING
    """.replace("%", "%%"))


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM shared.mai_feature_config
         WHERE dept = 'mh'
           AND feature_key IN (
               'mh_de_xuat_lich_giao_van',
               'mh_giao_van_defect_report'
           )
        """
    )
