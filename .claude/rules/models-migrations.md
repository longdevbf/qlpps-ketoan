---
paths:
  - "app/models/**/*.py"
  - "shared/models/**/*.py"
  - "alembic/**/*.py"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/models-migrations.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/models-migrations.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Sửa model và migration

## Schema nào thuộc về ai

App này sở hữu schema `ketoan`. Schema `shared` là dùng chung. Các schema
của 6 app còn lại thuộc app khác — code ở đây
chỉ **đọc** chúng bằng raw SQL, không được tạo/sửa bảng của chúng.

`alembic/env.py` lọc `include_object` theo `obj.schema == "ketoan"`, nên
migration sinh tự động sẽ **bỏ qua** mọi thay đổi ở schema khác.

## Trước khi tin là bảng tồn tại

Chuỗi migration của mọi app trong hệ này đều có lỗ hổng: có bảng chỉ do SQL thô
trong `lifespan` của `app/main.py` tạo, có bảng chỉ tồn tại dưới dạng
`op.execute("CREATE TABLE …")` nên `Base.metadata.create_all()` bỏ sót. Kiểm
tra trực tiếp trước khi kết luận endpoint hỏng:

```bash
docker exec qlpps_pg psql -U qlpps -d qlpps_dev -Atc   "SELECT to_regclass('ketoan.<ten_bang>')"
```

Trả rỗng nghĩa là bảng không tồn tại. Dựng lại toàn bộ schema + dữ liệu ảo:
`docker compose run --rm seeder` ở thư mục workspace (xem `README-DEV.md`).

## Thêm cột / đổi enum

Giá trị hợp lệ được khai ở **hai chỗ phải khớp nhau**: `CheckConstraint` trong
model và `Literal[...]` trong `app/schemas/`. Sửa một chỗ mà quên chỗ kia thì
BE trả 422 hoặc DB từ chối ghi — và thông báo lỗi không chỉ ra chỗ lệch.

Quy ước đặt tên **không nhất quán giữa các module**: có bảng dùng tiếng Anh
(`draft|pending_approval|approved|completed|cancelled`), có bảng dùng tiếng
Việt (`cho_duyet|da_duyet`). Đọc model trước, đừng suy từ module khác.

## Kiểu khoá ngoại

Ví dụ có thật: `marketing.leads.id` là `String(64)` (`'LEAD-2026-001'`), **không phải** số.
Mọi bảng tham chiếu tới lead phải dùng `text`/`varchar`. Đây từng làm vỡ cả
câu SQL của `/api/cskh/list` khi `COALESCE(po.id, l.id)` ghép `bigint` với
`varchar`.
