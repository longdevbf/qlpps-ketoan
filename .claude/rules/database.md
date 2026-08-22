---
description: Quy tắc cho models SQLAlchemy và migration Alembic
paths:
  - "app/models/**"
  - "alembic/**"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/database.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/database.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Database (app/models · alembic)

## Models
- Kế thừa `Base` từ `shared.db`, khai báo kiểu SQLAlchemy 2:
  `Mapped[...]` + `mapped_column(...)`.
- **Mọi bảng phải có `{"schema": "hcns"}`** trong `__table_args__`, đặt cuối:
```python
__table_args__ = (
    Index("ix_departments_ten", "ten", unique=True),
    {"schema": "hcns"},
)
```
- Cột thời gian dùng `DateTime(timezone=True)` + `server_default=func.now()`;
  `updated_at` thêm `onupdate=func.now()`.
- Thêm `__repr__` ngắn để debug dễ.
- Tên index theo mẫu `ix_<bảng>_<cột>`; unique constraint `uq_<bảng>_<cột>`.

## Migration
- **KHÔNG tự chạy `alembic upgrade` / `downgrade`.** Chỉ viết file migration,
  người dùng tự chạy. `alembic.ini` không nằm trong repo này (ở thư mục cha).
- Tên file theo mẫu đang có: `NNNN_mo_ta_ngan.py` (`0020_...` là số kế tiếp).
- Header phải khai báo đủ:
```python
revision: str = "0020_ten_moi"
down_revision: Union[str, None] = "0019_hoso_workflow"
```
- `op.create_index(...)` / `op.create_table(...)` luôn truyền `schema="hcns"`.
- Dùng `if_not_exists=True` khi tạo index để migration chạy lại được an toàn.
- **Bắt buộc viết `downgrade()` thật**, đảo ngược đúng thứ tự của `upgrade()`.
- Docstring đầu file ghi rõ migration này thêm/sửa gì và **vì sao**.

## An toàn dữ liệu
- Thêm cột NOT NULL vào bảng đã có dữ liệu → phải có `server_default`, nếu không
  migration sẽ fail trên DB production.
- Xoá/đổi tên cột là thay đổi **phá vỡ** — phải trình bày 2 phương án và hỏi
  trước khi viết (xem CHẾ ĐỘ MENTOR trong `CLAUDE.md`).
