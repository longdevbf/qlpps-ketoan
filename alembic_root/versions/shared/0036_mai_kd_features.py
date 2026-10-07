"""Mai KD features — bảng cấu hình + log cho Mai trợ lý phòng KD.

Revision ID: 0036_mai_kd_features
Revises: 0035_zns_send_log
Create Date: 2026-06-15

Anh Quang 2026-06-15 — Mai trợ lý KD. 6 bảng chính:

1. shared.mai_feature_config — cấu hình bật/tắt từng tính năng theo phòng ban
2. shared.mai_persona — system prompt + guard rails (1 record duy nhất)
3. shared.mai_customer_exclude — NV tắt Mai cho KH cụ thể
4. shared.mai_generated_message — log mọi tin Mai sinh (LLM cost tracking)
5. shared.mai_promotion_used — log Mai dùng KM nào cho KH nào
6. shared.mai_action_log — log mọi action (DM, escalate, reassign...)

KHÔNG ALTER bảng khác — track qua các bảng này (conv_id/message_id ref nhẹ).
"""
from alembic import op


revision = "0036_mai_kd_features"
down_revision = "0035_zns_send_log"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SCHEMA IF NOT EXISTS shared")

    # 1. Feature config — bật/tắt từng tính năng theo phòng ban
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_feature_config (
            feature_key     VARCHAR(64) NOT NULL,
            dept            VARCHAR(16) NOT NULL,       -- 'kd','mkt','mh','kt','hcns','sa','ceo','global'
            category        VARCHAR(32) NOT NULL,       -- 'auto_care','escalation','assistant',...
            label           VARCHAR(255) NOT NULL,
            description     TEXT NULL,
            enabled         BOOLEAN NOT NULL DEFAULT FALSE,
            params          JSONB NOT NULL DEFAULT '{}'::jsonb,
            instruction_prompt TEXT NULL,
            fallback_text   TEXT NULL,
            requires_promotion BOOLEAN NOT NULL DEFAULT FALSE,
            updated_by      VARCHAR(64) NULL,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (feature_key, dept)
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_fc_dept_enabled
                  ON shared.mai_feature_config (dept, enabled)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_fc_category
                  ON shared.mai_feature_config (category)""")

    # 2. Persona Mai (singleton — id=1)
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_persona (
            id              INTEGER PRIMARY KEY DEFAULT 1,
            system_prompt   TEXT NOT NULL,
            tone_description TEXT NULL,
            forbidden_patterns TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
            max_message_length INTEGER NOT NULL DEFAULT 200,
            min_message_length INTEGER NOT NULL DEFAULT 30,
            model           VARCHAR(64) NOT NULL DEFAULT 'claude-haiku-4-5-20251001',
            temperature     NUMERIC(3,2) NOT NULL DEFAULT 0.7,
            updated_by      VARCHAR(64) NULL,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT mai_persona_singleton CHECK (id = 1)
        )
    """)

    # 3. NV tắt Mai cho KH cụ thể
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_customer_exclude (
            id              BIGSERIAL PRIMARY KEY,
            customer_id     BIGINT NOT NULL,
            feature_key     VARCHAR(64) NULL,           -- NULL = tắt tất cả features
            nv_username     VARCHAR(64) NOT NULL,
            reason          TEXT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (customer_id, feature_key)
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_excl_cust
                  ON shared.mai_customer_exclude (customer_id)""")

    # 4. Log mọi tin Mai sinh (cost tracking + dedup + dashboard)
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_generated_message (
            id              BIGSERIAL PRIMARY KEY,
            feature_key     VARCHAR(64) NOT NULL,
            dept            VARCHAR(16) NOT NULL,
            target_type     VARCHAR(16) NOT NULL,       -- 'customer','nv','leader','team'
            customer_id     BIGINT NULL,
            nv_username     VARCHAR(64) NULL,
            conv_id         VARCHAR(64) NULL,           -- Pancake conv_id (nếu gửi Zalo)
            chat_room_id    INTEGER NULL,               -- hcns.chat_rooms (nếu DM nội bộ)
            channel         VARCHAR(16) NOT NULL,       -- 'zalo','chat_internal','log_only'
            model           VARCHAR(64) NULL,
            prompt_tokens   INTEGER NULL,
            completion_tokens INTEGER NULL,
            cost_usd        NUMERIC(10,6) NULL,
            generated_text  TEXT NOT NULL,
            sent            BOOLEAN NOT NULL DEFAULT FALSE,
            sent_at         TIMESTAMPTZ NULL,
            guard_passed    BOOLEAN NOT NULL DEFAULT TRUE,
            guard_fail_reason TEXT NULL,
            customer_replied BOOLEAN NOT NULL DEFAULT FALSE,
            replied_at      TIMESTAMPTZ NULL,
            error           TEXT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_msg_feature_time
                  ON shared.mai_generated_message (feature_key, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_msg_customer_time
                  ON shared.mai_generated_message (customer_id, created_at DESC)
                  WHERE customer_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_msg_nv_time
                  ON shared.mai_generated_message (nv_username, created_at DESC)
                  WHERE nv_username IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_msg_dept_time
                  ON shared.mai_generated_message (dept, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_msg_conv
                  ON shared.mai_generated_message (conv_id, created_at DESC)
                  WHERE conv_id IS NOT NULL""")

    # 5. Log Mai dùng KM nào cho KH nào
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_promotion_used (
            id              BIGSERIAL PRIMARY KEY,
            khuyen_mai_id   VARCHAR(32) NOT NULL,       -- ref marketing.khuyen_mai.id
            customer_id     BIGINT NOT NULL,
            feature_key     VARCHAR(64) NOT NULL,
            message_id      BIGINT NULL,                -- ref mai_generated_message.id
            customer_replied BOOLEAN NOT NULL DEFAULT FALSE,
            customer_redeemed BOOLEAN NOT NULL DEFAULT FALSE,
            redeemed_at     TIMESTAMPTZ NULL,
            sent_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_promo_km_time
                  ON shared.mai_promotion_used (khuyen_mai_id, sent_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_promo_cust
                  ON shared.mai_promotion_used (customer_id, sent_at DESC)""")

    # 6. Action log — tất cả action Mai thực hiện (DM, escalate, reassign, skip)
    op.execute("""
        CREATE TABLE IF NOT EXISTS shared.mai_action_log (
            id              BIGSERIAL PRIMARY KEY,
            feature_key     VARCHAR(64) NOT NULL,
            dept            VARCHAR(16) NOT NULL,
            action          VARCHAR(32) NOT NULL,       -- 'zalo_sent','dm_nv','dm_leader','escalate','reassign','skip','failed'
            target_type     VARCHAR(16) NOT NULL,       -- 'customer','nv','leader','quote','order'
            target_id       VARCHAR(64) NULL,
            nv_username     VARCHAR(64) NULL,
            customer_id     BIGINT NULL,
            ref_id          VARCHAR(64) NULL,           -- quote_id / order_id / ...
            payload         JSONB NULL,
            result          VARCHAR(16) NOT NULL,       -- 'success','failed','skipped'
            skip_reason     TEXT NULL,
            error           TEXT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_act_feature_time
                  ON shared.mai_action_log (feature_key, created_at DESC)""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_act_nv_time
                  ON shared.mai_action_log (nv_username, created_at DESC)
                  WHERE nv_username IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_act_customer_time
                  ON shared.mai_action_log (customer_id, created_at DESC)
                  WHERE customer_id IS NOT NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_mai_act_ref
                  ON shared.mai_action_log (ref_id, feature_key)
                  WHERE ref_id IS NOT NULL""")

    # ── Seed persona default ──
    conn = op.get_bind()
    conn.exec_driver_sql("""
        INSERT INTO shared.mai_persona (id, system_prompt, tone_description, forbidden_patterns, model)
        VALUES (
            1,
            $$Bạn là Mai, nhân viên trợ lý chăm sóc khách hàng bên Papasan (showroom nội thất gỗ ở Buôn Ma Thuột).

Tính cách:
- Thân thiện, lịch sự, dễ thương kiểu miền Nam.
- Xưng "em" với khách, gọi "anh/chị".
- Không sale cứng, không hứa hẹn quá đà.

Quy tắc tuyệt đối:
- KHÔNG bịa khuyến mãi/giảm giá/voucher/quà tặng. Chỉ được nhắc KM khi được cung cấp danh sách cụ thể.
- KHÔNG hứa giao hàng dưới 7 ngày.
- KHÔNG nhắc đối thủ.
- Tin Zalo ngắn 50-150 từ. Không dùng nhiều emoji.
- Mỗi tin có gọi tên khách (nếu biết).
- Tuyệt đối không trùng nội dung tin trước.$$,
            'Thân thiện miền Nam, ngắn gọn, không sale cứng',
            ARRAY['miễn phí lifetime', 'bao đổi trả lifetime']::TEXT[],
            'claude-haiku-4-5-20251001'
        )
        ON CONFLICT (id) DO NOTHING
    """)

    # ── Seed feature_config cho phòng KD (default DISABLED — CEO bật từng cái) ──
    conn.exec_driver_sql("""
        INSERT INTO shared.mai_feature_config (feature_key, dept, category, label, description, enabled, params, instruction_prompt, requires_promotion)
        VALUES
        -- AUTO chăm sóc KH ngủ đông
        ('inactive_3d', 'kd', 'auto_care', 'KH ngủ đông 3 ngày',
         'Mai gửi Zalo tin hỏi thăm nhẹ nhàng cho KH 3 ngày không liên hệ.',
         FALSE, '{"days":3,"max_per_day":1}'::jsonb,
         'KH mới im 3 ngày, chưa cần dụ KM. Tone hỏi thăm tự nhiên, có thể nhắc 1 mẫu mới phù hợp KH đang quan tâm. Tránh nhắc giá / giảm giá. Độ dài 50-80 từ.',
         FALSE),
        ('inactive_5d', 'kd', 'auto_care', 'KH ngủ đông 5 ngày — KM nhẹ',
         'Mai gửi tin có 1 ưu đãi nhẹ để đẩy KH quyết.',
         FALSE, '{"days":5}'::jsonb,
         'KH im 5 ngày, đến lúc đẩy. Có 1 ưu đãi cụ thể (lấy từ DS KM được cung cấp). Tạo urgency 24-48h. Độ dài 80-120 từ.',
         TRUE),
        ('inactive_7d', 'kd', 'auto_care', 'KH ngủ đông 7 ngày', 'Tin có social proof.', FALSE, '{"days":7}'::jsonb,
         'KH im 1 tuần. Gửi tin nhắc về 1 KH khác đã nhận hàng giống nhu cầu KH này. Tone showroom + tự hào. 80-120 từ.', FALSE),
        ('inactive_10d', 'kd', 'auto_care', 'KH ngủ đông 10 ngày', 'Câu hỏi mở kéo KH reply.', FALSE, '{"days":10}'::jsonb,
         'KH im 10 ngày, gần mất. Soạn câu hỏi mở "anh đã quyết chưa hay vẫn đang phân vân?" buộc KH phải reply. 60-100 từ.', FALSE),
        ('inactive_14d', 'kd', 'auto_care', 'KH ngủ đông 14 ngày', 'CSKH dài hạn, không sale.', FALSE, '{"days":14}'::jsonb,
         'KH im 2 tuần, đã nguội. Tone hoàn toàn không sale, chỉ hỏi thăm. "Em chỉ muốn hỏi thăm anh, khi nào cần em luôn sẵn sàng". 50-80 từ.', FALSE),
        ('inactive_90d', 'kd', 'auto_care', 'KH cold 90 ngày', 'Đánh thức bằng mẫu mới.', FALSE, '{"days":90}'::jsonb,
         'KH cold 3 tháng. Mở đầu "Lâu lắm không nhắn anh". Gửi tin có mẫu MỚI ra mắt. Không nhắc deal cũ. 80-120 từ.', FALSE),
        ('inactive_180d', 'kd', 'auto_care', 'KH cold 180 ngày — last try', 'Last try KM mạnh.', FALSE, '{"days":180}'::jsonb,
         'KH cold 6 tháng. Last try trước khi mark LOST. KM mạnh từ DS được cung cấp. Sau tin này nếu im 14 ngày → đánh dấu LOST. 100-150 từ.', TRUE),

        -- AUTO nhắc NV
        ('remind_followup', 'kd', 'escalation', 'Nhắc NV quên follow-up',
         'NV gửi BG / hứa gọi → 24-48h chưa hành động → DM NV.',
         FALSE, '{"hours_threshold":24,"max_reminds_per_day":2}'::jsonb,
         'Tin DM riêng NV nhắc nhẹ về việc follow-up KH. Liệt kê 1-3 deal/KH cụ thể NV cần làm. Tone đồng nghiệp, không khiển trách. 60-100 từ.',
         FALSE),
        ('delivery_due_alert', 'kd', 'escalation', 'Cảnh báo đơn sắp tới hạn giao',
         '1 lần/ngày 8h sáng. Đơn còn 1-2 ngày tới hạn giao.',
         FALSE, '{"days_before":[1,2]}'::jsonb,
         'DM NV về đơn sắp tới hạn giao. Liệt kê: mã đơn, tên KH, sản phẩm, ngày tới hạn. Gợi ý NV check tiến độ với SA. 50-80 từ.',
         FALSE),
        ('nv_idle_alert', 'kd', 'escalation', 'Cảnh báo NV im ắng',
         'NV im > 2h + chưa chấm công về → DM Leader. Skip nếu NV đã chấm về.',
         FALSE, '{"idle_hours":2,"max_alerts_per_day":1}'::jsonb,
         'Tin DM Leader (chị Lan) thông báo NV của chị im ắng > 2h và chưa chấm công về. Tone trung tính, không kết luận. 40-70 từ.',
         FALSE),
        ('post_sale_care', 'kd', 'auto_care', 'Chăm sóc sau bán',
         'Đơn Hoàn Thành → gửi Zalo KH 24h và 7 ngày sau. Skip nếu NV đã contact.',
         FALSE, '{"stages":[24,168]}'::jsonb,
         'Tin Zalo KH sau khi nhận hàng. Stage 24h: hỏi đã nhận chưa, có vấn đề gì không. Stage 7d: xin feedback. Tone chăm sóc tự nhiên, không sale. 60-100 từ.',
         FALSE),

        -- AUTO sau sự kiện BG
        ('followup_bg_24h', 'kd', 'auto_care', 'Sau gửi BG 24h KH chưa mở',
         'BG đã gửi 24h, KH chưa reply → Mai gửi Zalo nhắc.',
         FALSE, '{"hours":24}'::jsonb,
         'Tin Zalo nhắc KH đã nhận BG chưa, hỏi nhẹ. Tone tự nhiên không gấp gáp. 50-80 từ.',
         FALSE),
        ('followup_bg_48h', 'kd', 'auto_care', 'Sau gửi BG 48h chưa reply',
         'BG gửi 48h, KH chưa reply → Mai hỏi cần tư vấn gì thêm.',
         FALSE, '{"hours":48}'::jsonb,
         'Tin Zalo hỏi KH đã xem BG rồi, có gì cần tư vấn thêm không. Tone chuyên nghiệp + quan tâm. 60-100 từ.',
         FALSE),

        -- AUTO mùa/dịp
        ('tet_greeting', 'kd', 'special_event', 'Tết — chúc + KM',
         'Trước Tết 14 ngày, gửi tất cả KH active 12 tháng qua.',
         FALSE, '{"days_before_tet":14,"lookback_months":12,"spread_days":3}'::jsonb,
         'Tin Tết: chúc bình an + KM cụ thể từ DS. Tone trang trọng nhưng ấm áp. 100-150 từ.',
         TRUE),
        ('anniversary_1y', 'kd', 'special_event', 'Kỷ niệm 1 năm KH mua',
         'KH mua hàng đúng 365 ngày trước → Mai gửi chúc mừng + ưu đãi vệ sinh/bảo dưỡng.',
         FALSE, '{"years":1}'::jsonb,
         'Tin kỷ niệm 1 năm KH nhận đơn đầu tiên. Hỏi thăm sản phẩm dùng có ổn không. Mời dùng KM dịch vụ (vệ sinh/bảo dưỡng) nếu có. 80-120 từ.',
         TRUE),

        -- AUTO escalation NV
        ('escalate_unresponded', 'kd', 'escalation', 'Nhắc 3 lần NV không làm → Leader',
         '1 lần/ngày 9h. Mai đã nhắc NV về 1 KH 3+ lần trong 7 ngày mà NV không hành động → báo Leader.',
         FALSE, '{"reminds_threshold":3,"window_days":7}'::jsonb,
         'DM Leader báo NV cụ thể chưa hành động về KH cụ thể dù được nhắc 3 lần. Tone báo cáo, không trách. 50-80 từ.',
         FALSE),
        ('escalate_inactive_count', 'kd', 'escalation', 'NV có > N KH ngủ đông → Leader',
         '1 lần/ngày 9h. NV có > 10 KH ngủ đông > 14 ngày → báo Leader.',
         FALSE, '{"threshold":10,"days":14}'::jsonb,
         'DM Leader báo NV đang để nhiều KH lạnh. Tone gợi ý chia bớt KH hoặc check NV quá tải. 50-80 từ.',
         FALSE),
        ('escalate_long_idle', 'kd', 'escalation', 'NV im > 4h tổng → escalate lần 2',
         'Tiếp nối nv_idle_alert. NV vẫn im sau 4h → DM Leader lần 2.',
         FALSE, '{"hours_threshold":4}'::jsonb,
         'DM Leader thông báo NV vẫn im sau 4h tổng. Tone tăng urgency. 40-60 từ.',
         FALSE),
        ('reassign_on_leave', 'kd', 'escalation', 'NV nghỉ phép > 2 ngày + KH nóng',
         'NV nghỉ + KH nóng không ai chăm → Mai đề xuất 2 PA cho Leader (chuyển NV hoặc Leader xử lý).',
         FALSE, '{"days_leave_threshold":2}'::jsonb,
         'DM Leader đề xuất 2 PA: PA1 chuyển KH cho NV cụ thể (có reasoning), PA2 Leader trực tiếp xử lý. Liệt kê KH nóng cụ thể. 100-150 từ.',
         FALSE),

        -- AUTO duy trì KH thân thiết
        ('birthday_customer', 'kd', 'special_event', 'Sinh nhật KH',
         'KH có ngay_sinh = hôm nay → gửi tin chúc + voucher nếu có KM sinh nhật.',
         FALSE, '{}'::jsonb,
         'Tin chúc sinh nhật KH. Tone ấm áp. Đính voucher từ DS KM nếu có. Không dùng nhiều emoji. 50-80 từ.',
         TRUE),
        ('tag_loyal_customer', 'kd', 'special_event', 'KH mua 2 lần / 12 tháng → tag thân thiết',
         'Auto tag + DM NV phụ trách.',
         FALSE, '{"orders_threshold":2,"window_months":12}'::jsonb,
         'DM NV thông báo KH đã đạt 2 đơn, đề xuất NV chú ý ưu đãi riêng. 40-70 từ.',
         FALSE),
        ('upcoming_birthday_alert', 'kd', 'special_event', 'KH sinh nhật trong 7 ngày → DM NV',
         'Sáng thứ 2, list KH sinh nhật tuần này gửi NV.',
         FALSE, '{"days_ahead":7}'::jsonb,
         'DM NV liệt kê KH sinh nhật trong tuần. Gợi ý NV chuẩn bị quà nhỏ + KM riêng. 60-100 từ.',
         FALSE),

        -- Hỏi đáp / NV trigger
        ('detect_duplicate_lead', 'kd', 'assistant', 'Phát hiện KH cũ đổi NV',
         'Khi lead/customer mới, Mai check lịch sử + comment cảnh báo nếu KH cũ.',
         FALSE, '{"lookback_months":12}'::jsonb,
         'Comment trên hồ sơ KH cảnh báo KH từng do NV nào chăm. Tone trung tính. 40-80 từ.',
         FALSE),
        ('daily_inactive_count', 'kd', 'assistant', 'Báo NV số KH 7-14 ngày',
         'Sáng 8h DM riêng từng NV tổng số KH ngủ đông 7-14 ngày.',
         FALSE, '{"days_min":7,"days_max":14,"min_count":1}'::jsonb,
         'DM NV thông báo TỔNG SỐ KH đang ngủ đông 7-14 ngày. Gợi ý NV vào CRM chăm lại. KHÔNG list top KH, chỉ số tổng. 40-60 từ.',
         FALSE),
        ('mai_pick_followup', 'kd', 'assistant', 'Mai tự chọn KH follow-up theo signal',
         'Mai scan KH có signal hot (mở BG nhiều, hỏi giá lần 2...) và proactive gửi follow-up Zalo trực tiếp.',
         FALSE, '{"signal_threshold":3,"max_per_day_per_nv":5}'::jsonb,
         'Tin Zalo follow-up proactive dựa trên signal KH. Tone tự nhiên, nhắc context cụ thể KH đã quan tâm. 70-120 từ.',
         FALSE),
        ('detect_disengaging_customer', 'kd', 'assistant', 'Phát hiện KH mất quan tâm',
         'Realtime: KH reply thưa dần/ngắn dần/cold words → DM NV.',
         FALSE, '{"score_threshold":3}'::jsonb,
         'DM NV cảnh báo KH có dấu hiệu mất quan tâm. Liệt kê signals cụ thể. Đề xuất gọi điện trực tiếp. 50-80 từ.',
         FALSE),
        ('competitor_mention_alert', 'kd', 'assistant', 'Cảnh báo KH nhắc đối thủ',
         'Realtime: KH chat nhắc tên đối thủ → DM NV gấp.',
         FALSE, '{"competitors":["Tiến Phát","Nguyễn Kim","Sofa House"]}'::jsonb,
         'DM NV CẢNH BÁO KHẨN: KH nhắc đối thủ X. Quote tin gốc. Đề xuất NV gọi ngay + chiến thuật giữ. 50-80 từ.',
         FALSE)
        ON CONFLICT (feature_key, dept) DO NOTHING
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS shared.mai_action_log")
    op.execute("DROP TABLE IF EXISTS shared.mai_promotion_used")
    op.execute("DROP TABLE IF EXISTS shared.mai_generated_message")
    op.execute("DROP TABLE IF EXISTS shared.mai_customer_exclude")
    op.execute("DROP TABLE IF EXISTS shared.mai_persona")
    op.execute("DROP TABLE IF EXISTS shared.mai_feature_config")
