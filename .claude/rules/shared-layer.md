---
description: shared/ là code dùng chung nhiều app — quy tắc bảo vệ
paths:
  - "shared/**"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/shared-layer.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/shared-layer.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# ⛔ Tầng shared/ — CHỈ ĐỌC theo mặc định

Thư mục `shared/` **không thuộc riêng app HCNS**. Nó được dùng chung bởi các app
anh em cùng hệ thống (8 repo, xem skill `erp-architecture`).

## Quy tắc

1. **Không sửa file nào trong `shared/` khi chưa hỏi và được đồng ý.**
   Áp dụng cả với thay đổi nhỏ nhất (đổi tên biến, thêm field).
2. Khi cần một hành vi mới mà `shared/` chưa có → **ưu tiên viết trong `app/`**
   của HCNS trước. Chỉ đề xuất đưa lên `shared/` khi thật sự >1 app cần.
3. Khi buộc phải sửa `shared/`, trước tiên phải báo cáo:
   - File nào, hàm nào.
   - **App nào khác đang dùng hàm đó** (không kiểm chứng được từ repo này vì các
     app kia nằm ở thư mục khác → phải nói rõ là chưa kiểm chứng).
   - Rủi ro nếu app kia vỡ.
4. `shared/models/` đặc biệt nhạy: đổi model ở đây kéo theo migration cho
   **nhiều schema**, không chỉ `hcns`.

## Đọc thì thoải mái
Đọc `shared/` để hiểu và làm ví dụ dạy học là khuyến khích — đặc biệt:
- `shared/auth/jwt.py` — cách tạo/verify JWT, `require_app()`
- `shared/db/session.py` — dependency `get_db`, vòng đời session
- `shared/middleware/` — bắt lỗi tập trung, sliding session
- `shared/audit/logger.py` — `log_action` ghi vết thao tác
