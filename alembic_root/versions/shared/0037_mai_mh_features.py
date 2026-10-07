"""Mai MH features — seed 12 feature_config cho phòng Mua Hàng.

Revision ID: 0037_mai_mh_features
Revises: 0036_mai_kd_features
Create Date: 2026-06-16

Anh Quang 2026-06-16 — Mai trợ lý phòng Mua Hàng (clone từ Mai KD).

Cấu trúc bảng shared.mai_feature_config + shared.mai_generated_message
+ shared.mai_action_log đã có (từ migration 0036). PK (feature_key, dept)
đã hỗ trợ multi-dept. Migration này CHỈ seed INSERT 12 row dept='mh'.

12 feature_key Mai MH (enabled=FALSE, CEO bật từng cái sau khi test):

  Đàm phán / so sánh (3):
    1. mh_negotiate_min_price   — đàm phán theo giá thấp nhất từng đặt
    2. mh_negotiate_bulk        — đàm phán giá theo số lượng lớn
    3. mh_compare_picknbest     — so sánh báo giá nhiều NCC + chọn tốt nhất

  Cảnh báo / phát hiện (2):
    4. mh_price_anomaly_alert   — phát hiện giá NCC tăng bất thường
    5. mh_alt_supplier_suggest  — gợi ý NCC thay thế khi NCC hiện không ổn

  Theo dõi / nhắc (3):
    6. mh_remind_ncc_unresponded — nhắc NCC chưa reply BG
    7. mh_clarify_specs_to_ncc   — hỏi spec rõ NCC khi PO thiếu thông tin
    8. mh_delivery_due_reminder  — nhắc NCC ngày giao sắp tới

  Cảnh báo trễ / sức khoẻ (2):
    9. mh_overdue_alert         — cảnh báo NCC giao trễ
   10. mh_supplier_health_score — điểm sức khoẻ NCC (tổng hợp)

  Báo cáo (1):
   11. mh_daily_report_ceo      — báo cáo MH hàng ngày cho CEO

  Hỏi đáp / chat tool (1 parent):
   12. mh_qa_tools              — parent cho 3 tool QA (best_price/po_status/supplier_history)
"""
from alembic import op


revision = "0037_mai_mh_features"
down_revision = "0037_expense_chung_tu_urls"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    def _q(sql: str) -> None:
        """Escape % literal -> %% để psycopg không hiểu nhầm là format placeholder."""
        conn.exec_driver_sql(sql.replace("%", "%%"))

    # Seed feature_config cho phòng MH — DEFAULT DISABLED (CEO bật từng cái).
    # Anh Quang chốt: instruction_prompt nhúng persona Mai MH tone đàm phán NCC
    # (formal hơn KD, gọi "anh/em NCC" không "anh/chị KH").
    # NOTE: dùng exec_driver_sql nhưng phải escape '%' literal thành '%%' để
    # psycopg không hiểu nhầm là format placeholder. Dùng .replace ngoài cho
    # gọn (toàn bộ '%' trong prompt được literal hoá).
    _q("""
        INSERT INTO shared.mai_feature_config
            (feature_key, dept, category, label, description, enabled,
             params, instruction_prompt, requires_promotion)
        VALUES
        -- ── Đàm phán / so sánh ──────────────────────────────────────────
        ('mh_negotiate_min_price', 'mh', 'negotiation',
         'Đàm phán theo giá thấp nhất từng đặt',
         'Khi tạo PO mới, Mai check sản phẩm có giá thấp nhất từng đặt NCC này, '
         'gửi tin đàm phán Zalo yêu cầu giữ giá hoặc giảm so với lần trước.',
         FALSE, '{"min_n_lan_dat":2}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. Soạn tin Zalo gửi NCC đàm phán '
         'GIỮ giá thấp nhất từng đặt cho 1 SP. Nội dung: nhắc lại lần trước đặt '
         'giá X, lần này SL Y, mong anh/em giữ hoặc giảm thêm. Tone formal, '
         'tôn trọng. Không hứa hẹn. 60-100 từ.',
         FALSE),

        ('mh_negotiate_bulk', 'mh', 'negotiation',
         'Đàm phán giá theo số lượng lớn',
         'Khi PO có 1 SP số lượng ≥ ngưỡng, Mai gửi NCC tin xin discount bulk.',
         FALSE, '{"min_qty":10}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. Soạn tin Zalo gửi NCC xin discount '
         'theo số lượng lớn. Liệt kê SP + số lượng. Đề nghị giá tốt hơn báo giá '
         'lẻ. Tone đàm phán formal, không kì kèo. 70-110 từ.',
         FALSE),

        ('mh_compare_picknbest', 'mh', 'negotiation',
         'So sánh báo giá nhiều NCC + chọn tốt nhất',
         'Khi PO có ≥ 2 NCC báo giá, Mai phân tích chênh lệch + đề xuất NCC '
         'tốt nhất kèm lý do (giá + lịch sử giao đúng hẹn).',
         FALSE, '{"min_ncc":2}'::jsonb,
         'Phân tích bảng giá nhiều NCC cho 1 PO. Output: bảng so sánh giá + đề '
         'xuất NCC nên chọn kèm lý do (giá rẻ nhất / lịch sử giao đúng / chất '
         'lượng ổn). Tone báo cáo, có số liệu cụ thể. Gửi DM Leader Mua Hàng. '
         '100-150 từ.',
         FALSE),

        -- ── Cảnh báo / phát hiện ────────────────────────────────────────
        ('mh_price_anomaly_alert', 'mh', 'alert',
         'Phát hiện giá NCC tăng bất thường',
         'Scheduler tick 10 phút: quét PO mới (Chờ xác nhận / Đang lấy giá / '
         'Chờ duyệt) có prices, so giá NCC vừa báo với giá thấp nhất từng đặt '
         'cùng NCC + SP. Vượt 15%/25%/50% → 3 mức low/medium/high. DM NV; '
         'high thì +Leader.',
         FALSE, '{"diff_pct_threshold":15.0}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. Soạn tin DM NV (hoặc Leader nếu '
         'cảnh báo HIGH) báo giá NCC bất thường. Bắt buộc nêu: tên NCC, tên SP, '
         'mã PO, giá NCC vừa báo, giá thấp nhất NCC này từng báo, % chênh, mức '
         'low/medium/high. Tone trung tính, KHÔNG kết luận thay NV. Mức low: '
         'nhắc nhẹ + gợi ý hỏi lại NCC (50-80 từ). Mức medium: nêu cụ thể số '
         'liệu + đề xuất so sánh NCC khác (80-110 từ). Mức high: TONE GẤP, '
         'cảnh báo nghiêm trọng, yêu cầu xác minh trước khi duyệt (90-120 từ). '
         'KHÔNG bịa số — số liệu lấy từ context cung cấp.',
         FALSE),

        ('mh_alt_supplier_suggest', 'mh', 'alert',
         'Gợi ý NCC thay thế khi NCC hiện không ổn',
         'NCC X có ≥ N đơn giao trễ / báo giá tăng → Mai scan lịch sử PO tìm '
         'NCC khác từng cung cấp SP tương tự + đề xuất.',
         FALSE, '{"min_overdue_count":2,"lookback_months":6}'::jsonb,
         'DM Leader/NV Mua Hàng đề xuất NCC thay thế. Nêu lý do NCC hiện không '
         'ổn (số đơn trễ, giá tăng) + 2-3 NCC khác từng cung cấp SP tương tự '
         '(kèm giá lần cuối + lịch sử giao). Tone báo cáo, dữ liệu cụ thể. '
         '100-140 từ.',
         FALSE),

        -- ── Theo dõi / nhắc ─────────────────────────────────────────────
        ('mh_remind_ncc_unresponded', 'mh', 'reminder',
         'Nhắc NCC chưa reply tin Mai/NV',
         'Tin cuối là Mai/NV gửi NCC, NCC đã ≥ idle_hours_threshold giờ chưa rep '
         '→ Mai gửi Zalo nhắc nhẹ. Tối đa max_reminders_per_conv lần / conv. '
         'Anti-spam 24h. Scheduler tick mỗi 30 phút giờ làm.',
         FALSE,
         '{"idle_hours_threshold":4,"max_reminders_per_conv":2}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. NCC chưa phản hồi tin trước của '
         'Mai/NV đã quá idle_hours_threshold giờ. Soạn tin Zalo nhắc nhẹ NCC '
         'phản hồi sớm. Tone NHẸ NHÀNG, không hối thúc, không trách. Xưng '
         '"em", gọi "anh". Nhắc rằng vẫn đang đợi thông tin từ anh để xử lý '
         'đơn. Có thể kèm icon lịch sự. Tuyệt đối KHÔNG nhắc lại chính xác '
         'nội dung tin trước (Mai không có context tin cũ — tránh bịa). 40-70 '
         'từ.',
         FALSE),

        ('mh_clarify_specs_to_ncc', 'mh', 'reminder',
         'NCC hỏi KT/màu/SL → Mai trả lời tự động từ PO data',
         'NCC vừa gửi câu hỏi về kích thước / màu / chất liệu / SL trong 5-30 '
         'phút qua. Mai cross-ref PO active của NCC qua fuzzy name + compose '
         'câu trả lời từ po_items. Chỉ trả lời tự động khi LLM confident; '
         'không chắc → escalate NV (log mai_action_log, không gửi NCC). '
         'Scheduler tick mỗi 5 phút.',
         FALSE, '{}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. NCC vừa hỏi về kích thước / màu '
         '/ chất liệu / số lượng cho SP trong PO active. Em đã có thông số '
         'CHÍNH XÁC từ DB PAPASAN (block context phía dưới user message). '
         'Yêu cầu BẮT BUỘC: '
         '(1) CHỈ dùng số liệu trong block context, KHÔNG bịa số. '
         '(2) Format kích thước theo "R{rong} × C{cao} × S{sau}mm". '
         '(3) Format SL: "{so_luong_input} {dvt}" (vd "10 cái", "2 bộ"). '
         '(4) Nếu block không có thông tin NCC hỏi → trả lời ngắn: "Em xin '
         'xác nhận lại với bên Papasan rồi báo anh sau ạ." KHÔNG bịa. '
         '(5) Tone formal, gọn 60-120 từ. Xưng "em", gọi "anh". Có thể mở '
         'đầu gọi tên NCC nếu biết.',
         FALSE),

        ('mh_delivery_due_reminder', 'mh', 'reminder',
         'Mai ping NCC trước days_before ngày hạn giao',
         'PO active (status Đặt hàng / Đã đặt hàng / Đang SX / Đã Duyệt Mua) có '
         'deadline = today + days_before ngày → Mai gửi NCC tin xác nhận tiến '
         'độ. Deadline parse từ tien_do_khach_can (dd/mm[/yyyy]), fallback '
         'ngay_dat_xuong + 14 ngày. Chỉ remind 1 lần / PO (idempotency theo '
         'po.id trong mai_action_log.ref_id). Cron daily 9h sáng.',
         FALSE, '{"days_before":2}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. Đơn PO của NCC còn 2 ngày là đến '
         'hẹn giao. Soạn tin Zalo NCC nhắc tiến độ + xác nhận đúng hẹn. Nội '
         'dung: mã PO, ngày đặt, ngày hẹn giao, 1-2 SP chính + SL. Yêu cầu '
         'NCC check tiến độ + sắp xếp giao đúng hẹn, có vấn đề báo PAPASAN '
         'sớm. Tone formal, không gấp gáp, không hứa hộ NCC. Xưng "em", gọi '
         '"anh". 60-100 từ. CHỈ dùng số liệu trong context, KHÔNG bịa ngày.',
         FALSE),

        -- ── Cảnh báo trễ / sức khoẻ ─────────────────────────────────────
        ('mh_overdue_alert', 'mh', 'alert',
         'Cảnh báo NCC giao trễ',
         'Cron daily 8h sáng: PO status (Đặt hàng / Đang SX) có ngay_dat_xuong + '
         'default leadtime 14 ngày quá hạn. Phân loại 1-3 / 4-7 / >7 ngày → '
         'soft / hard / critical. Gửi Zalo NCC + DM NV; hard escalate Leader; '
         'critical escalate CEO/Assistant CEO.',
         FALSE, '{"days_overdue":1,"default_leadtime_days":14}'::jsonb,
         'Em là Mai, trợ lý mua hàng PAPASAN. Soạn 1 trong 2 loại tin: (1) Tin '
         'Zalo gửi NCC nhắc tiến độ giao đơn PO trễ — xưng em, gọi anh/em NCC, '
         'formal, có số liệu (mã PO, ngày đặt, số ngày trễ), KHÔNG xúc phạm. '
         'Soft: 50-80 từ tone nhẹ. Hard: 60-100 từ formal có yêu cầu phản hồi '
         'trong ngày. Critical: 70-110 từ rõ ràng — Sếp yêu cầu chốt ngày giao '
         'mới. (2) Tin DM NV/Leader/CEO nội bộ — báo tình hình + đề xuất hành '
         'động (gọi NCC / escalate / tìm NCC thay thế). Tone hỗ trợ, KHÔNG '
         'trách NV. 60-120 từ. KHÔNG bịa số — lấy từ context.',
         FALSE),

        ('mh_supplier_health_score', 'mh', 'alert',
         'Điểm sức khoẻ NCC (tổng hợp)',
         'Mỗi ngày 5h sáng compute điểm sức khoẻ mỗi NCC (4 sub-score: giá '
         'cạnh tranh 30%, đúng hẹn giao 30%, tốc độ phản hồi Zalo 25%, '
         'chất lượng 15%) → UPSERT shared.mh_supplier_health. Mai dùng kết '
         'quả để báo Top/Bottom 3 NCC, Leader xem dashboard.',
         FALSE, '{"window_months":3,"min_samples":3}'::jsonb,
         'Compute điểm sức khoẻ NCC từ 4 sub-score: '
         '(A) score_price 30% — tỷ lệ NCC này đạt giá thấp nhất từng đặt cho SP '
         '(10 lần gần nhất). '
         '(B) score_ontime 30% — tỷ lệ PO đã giao đúng hoặc sớm hạn '
         '(parse tien_do_khach_can, fallback +14d). '
         '(C) score_response 25% — speed reply Zalo (match supplier.phone với '
         'pancake_conversation.customer_phone). '
         '(D) score_quality 15% — đếm comment tiêu cực trong po_comments. '
         'Total = weighted avg, round 1 decimal. Khi đủ samples (>=3) thì '
         'tính, không đủ thì default 50. UPSERT supplier_id unique.',
         FALSE),

        -- ── Báo cáo ──────────────────────────────────────────────────────
        ('mh_daily_report_ceo', 'mh', 'report',
         'Báo cáo MH hàng ngày cho CEO',
         'Cron 18h chiều mỗi ngày: tổng hợp KPI MH hôm nay (PO mới, PO gửi NCC, '
         'PO duyệt, tổng giá trị, tiền tiết kiệm so với min lịch sử, NCC trễ '
         'giao, top NCC có deal, số lần Mai đàm phán) → DM CEO qua '
         'shared.notifications. Idempotent 1 báo cáo/ngày.',
         FALSE, '{"hour":18}'::jsonb,
         'Compose báo cáo MH cuối ngày cho CEO. Format multi-line text '
         'tiếng Việt có emoji 📦 📤 ✅ 💵 💰 🏆 ⏰ 🤝. Liệt kê: '
         'số PO mới tạo, số PO đã gửi NCC, số PO đã duyệt, tổng giá trị chốt '
         'hôm nay, tiền tiết kiệm so với min lịch sử SP (âm=tiết kiệm), '
         'Top 3 NCC có deal hôm nay (kèm số PO + giá trị), '
         'list NCC trễ giao (max 5), số lần Mai đã đàm phán (count '
         'mh_negotiate_*). Tone báo cáo CEO ngắn gọn, có số liệu cụ thể. '
         'Gửi shared.notifications target_username = ceo/assistant_ceo, '
         'severity=info, title="📊 Báo cáo Mai Mua Hàng — {date}". '
         'Idempotency check qua mai_action_log action=daily_report_sent.',
         FALSE),

        -- ── Hỏi đáp / chat tool (parent) ────────────────────────────────
        ('mh_qa_tools', 'mh', 'assistant',
         'Bộ tool QA cho Mai MH (parent)',
         'Bật/tắt 3 chat tool: mh_best_price_for_product, mh_po_status, '
         'mh_supplier_history. CEO/Leader/NV gọi Mai qua chat box.',
         FALSE, '{"tools":["best_price","po_status","supplier_history"]}'::jsonb,
         'Meta — Mai MH có thể trả lời 3 câu hỏi qua chat tool: '
         '(1) mh_best_price_for_product — tra NCC nào từng đặt SP X giá rẻ nhất '
         '(input: product_name, limit). Trả min/max/avg giá + số lần + ngày gần nhất. '
         '(2) mh_po_status — trạng thái PO X (input: po_id fuzzy). Trả NCC selected + '
         'health_score + Zalo activity. '
         '(3) mh_supplier_history — lịch sử NCC (input: supplier_query). Trả notes + '
         'health_score + SP từng làm + tổng PO/giá trị. '
         'Parent feature_key — không sinh tin auto, bật ON để LLM expose 3 tool.',
         FALSE)
        ON CONFLICT (feature_key, dept) DO NOTHING
    """)

    # ─────────────────────────────────────────────────────────────────
    # Wave 2A — ALTER params + instruction_prompt cho 4 feature ĐÀM
    # PHÁN/COMPARE đã implement đầy đủ trong:
    #   ceo/app/mai/features/mh_negotiate_min_price.py
    #   ceo/app/mai/features/mh_negotiate_bulk.py
    #   ceo/app/mai/features/mh_compare_picknbest.py
    #   ceo/app/mai/features/mh_alt_supplier_suggest.py
    #
    # KHÔNG INSERT lại (ON CONFLICT DO NOTHING ở trên đã handle).
    # UPDATE override chắc chắn áp dụng ngay cả khi row tồn tại từ
    # production runtime cũ.
    # ─────────────────────────────────────────────────────────────────

    # 1. mh_negotiate_min_price
    _q(r"""
        UPDATE shared.mai_feature_config SET
            params = '{"min_n_lan_dat":2,"ratio_threshold":1.05}'::jsonb,
            description = 'Mai phát hiện tin NCC vừa báo giá Zalo và cross-ref với '
                          'lịch sử SP NCC đó từng làm. Nếu giá báo > giá thấp nhất '
                          'từng đặt * 1.05 (>5%), Mai gửi tin đàm phán Zalo yêu '
                          'cầu giữ giá lịch sử. Wave 2A.',
            instruction_prompt = $PROMPT$Em là Mai, trợ lý mua hàng PAPASAN.

Anh sẽ nhận context JSON gồm:
  - ncc_name: tên NCC đang chat.
  - tin_ncc_vua_bao: tin NCC vừa báo giá.
  - gia_ncc_bao_parse: giá Mai parse được (VND).
  - sp_lich_su: ten_sp, dvt, dim, mau_go, gia_thap_nhat_da_dat, gia_lan_cuoi, ngay_lan_cuoi, n_lan_dat.
  - chenh_lech_pct: phần trăm tăng so với giá thấp nhất.

Soạn tin Zalo NCC để đàm phán giữ giá lịch sử. Nội dung:
  1. Chào NCC (anh/em + tên).
  2. Cảm ơn NCC đã báo giá X cho SP Y.
  3. Nhắc lịch sử: bên em đã đặt SP này từ anh/em giá Z (lần cuối ngày T, tổng N lần).
  4. Đề nghị giữ giá Z hoặc giảm thêm.
  5. Lịch sự, không ép, kết thúc bằng cảm ơn + emoji.

Quy tắc:
  - Tone formal, không kì kèo, không trách móc.
  - Phải nêu CHÍNH XÁC số liệu từ context (KHÔNG bịa giá / ngày).
  - Độ dài 60-110 từ.
  - KHÔNG nhắc tên NCC khác hoặc giá NCC khác.
  - KHÔNG hứa số lượng / lịch giao thay PAPASAN.$PROMPT$
         WHERE feature_key = 'mh_negotiate_min_price' AND dept = 'mh'
    """.replace("%", "%%"))

    # 2. mh_negotiate_bulk
    _q(r"""
        UPDATE shared.mai_feature_config SET
            params = '{"min_total":5000000,"min_lines":3,"discount_pct_suggest":4.0}'::jsonb,
            description = 'Khi 1 PO có 1 NCC báo ≥ 3 dòng SP với tổng > 5tr, Mai '
                          'gửi NCC xin discount combo trên tổng đơn (đàm phán '
                          '3-5%). Wave 2A.',
            instruction_prompt = $PROMPT$Em là Mai, trợ lý mua hàng PAPASAN.

Anh sẽ nhận context JSON:
  - ncc_name: tên NCC.
  - po_id, po_ten: mã + tên đơn PAPASAN.
  - tong_don_vnd: tổng đơn PAPASAN gửi NCC (VND).
  - so_dong_co_gia: số dòng SP NCC đã báo giá.
  - top_items: top 5 SP (ten_sp, dvt, so_luong, don_gia, thanh_tien).
  - discount_pct_de_xuat: % giảm Mai đề xuất (3-5%).

Soạn tin Zalo NCC đàm phán combo tổng đơn:
  1. Chào NCC + tên.
  2. Cảm ơn NCC đã báo giá cho đơn PO X.
  3. Nhấn mạnh đơn lớn: tổng N triệu, gồm M dòng SP (kể top 3 SP thanh_tien lớn nhất).
  4. Đề nghị NCC giảm thêm 3-5% trên tổng đơn vì đơn combo.
  5. Cam kết PAPASAN xử lý PO nhanh nếu chốt sớm.

Quy tắc:
  - Tone đàm phán formal, có số liệu cụ thể (số dòng, tổng tiền).
  - Số liệu PHẢI lấy từ context (KHÔNG bịa).
  - Độ dài 80-130 từ.
  - KHÔNG hứa giao tiền sớm / đặt thường xuyên thay PAPASAN.$PROMPT$
         WHERE feature_key = 'mh_negotiate_bulk' AND dept = 'mh'
    """.replace("%", "%%"))

    # 3. mh_compare_picknbest
    _q(r"""
        UPDATE shared.mai_feature_config SET
            params = '{"min_ncc":2}'::jsonb,
            description = 'PO có ≥ 2 NCC báo giá, Mai pick NCC tổng đơn rẻ nhất '
                          '+ DM NV phụ trách kèm bảng so sánh chi tiết và '
                          'history giao đúng/trễ 90 ngày. Wave 2A.',
            instruction_prompt = $PROMPT$Em là Mai, trợ lý mua hàng PAPASAN — đang báo cáo NV mua hàng (DM nội bộ, KHÔNG phải tin gửi NCC).

Anh sẽ nhận context JSON:
  - po_id, po_ten.
  - so_ncc_so_sanh: số NCC trong bảng so sánh.
  - ncc_re_nhat: ncc_id, ten, tong_don, lich_su_90d (hoan_thanh, bi_tu_choi, tong_da_dat).
  - bang_so_sanh: list ncc_name, tong_don, chenh_lech_pct vs rẻ nhất, lich_su_90d.
  - nv_mua_hang: username NV phụ trách.

Soạn DM cho NV:
  1. Em phân tích PO #X (tên Y) đã có Z NCC báo giá.
  2. Bảng so sánh (1 NCC / dòng): tên - tổng - chênh % so với rẻ nhất - lịch sử 90d.
  3. Đề xuất chọn NCC re_nhat vì: (a) giá rẻ nhất (tiết kiệm bao nhiêu), (b) lịch sử giao đúng/trễ.
  4. Nhắc NV vào hệ thống xác nhận để Mai gửi đơn cho NCC.

Quy tắc:
  - Tone báo cáo nội bộ, có số liệu cụ thể.
  - KHÔNG kết luận thay NV — chỉ đề xuất + nêu lý do.
  - Độ dài 100-180 từ.
  - Format dễ đọc (gạch đầu dòng hoặc bảng đơn giản).$PROMPT$
         WHERE feature_key = 'mh_compare_picknbest' AND dept = 'mh'
    """.replace("%", "%%"))

    # 4. mh_alt_supplier_suggest
    _q(r"""
        UPDATE shared.mai_feature_config SET
            params = '{"lookback_months":6,"discount_ratio":0.9}'::jsonb,
            description = 'PO đang lấy giá, Mai scan po_items cùng SP cùng dim '
                          '(tol ±50mm) trong 6 tháng qua để tìm NCC khác từng '
                          'làm SP đó với giá ≤ 90% giá NCC hiện tại. DM NV phụ '
                          'trách kèm top 2 NCC alt rẻ nhất. Wave 2A.',
            instruction_prompt = $PROMPT$Em là Mai, trợ lý mua hàng PAPASAN — đang DM NV phụ trách PO (KHÔNG phải tin gửi NCC).

Anh sẽ nhận context JSON:
  - po_id, po_ten.
  - item_id, sp: ten_sp, dvt, rong, cao, sau, dai.
  - ncc_hien_tai: ncc_id, ncc_name, gia_dang_bao.
  - ncc_alt_de_xuat: list 1-2 NCC (ncc_name, gia_thap_nhat, ngay_lan_cuoi, chenh_lech_pct so với ncc_hien_tai).
  - nv_mua_hang.

Soạn DM cho NV:
  1. Em soi PO #X dòng SP "<ten_sp>" NCC A đang báo giá P_A.
  2. Em check lịch sử thấy NCC B từng làm SP cùng dim này giá W (rẻ hơn N%, lần cuối ngày T).
  3. Nếu có NCC C nữa thì kể tiếp (ngắn gọn).
  4. Đề xuất: anh có muốn em báo giá lại từ NCC B/C không? Em cần anh xác nhận để mở luồng so giá.

Quy tắc:
  - Tone hỗ trợ, không phán xét NV.
  - Số liệu PHẢI lấy từ context.
  - Độ dài 90-140 từ.
  - KHÔNG kết luận thay NV — Mai chỉ flag + đề xuất.$PROMPT$
         WHERE feature_key = 'mh_alt_supplier_suggest' AND dept = 'mh'
    """.replace("%", "%%"))


def downgrade():
    # Chỉ xoá 12 row dept='mh' do migration này seed.
    op.execute("""
        DELETE FROM shared.mai_feature_config
         WHERE dept = 'mh'
           AND feature_key IN (
               'mh_negotiate_min_price',
               'mh_negotiate_bulk',
               'mh_compare_picknbest',
               'mh_price_anomaly_alert',
               'mh_alt_supplier_suggest',
               'mh_remind_ncc_unresponded',
               'mh_clarify_specs_to_ncc',
               'mh_delivery_due_reminder',
               'mh_overdue_alert',
               'mh_supplier_health_score',
               'mh_daily_report_ceo',
               'mh_qa_tools'
           )
    """)
