---
paths:
  - "app/models/**/*.py"
  - "alembic/**/*.py"
description: Quy tắc cho model SQLAlchemy 2 và migration Alembic
---

# Model & Migration — chỉ những điều khác mặc định

## Khung chuẩn của một model

```python
from decimal import Decimal
from typing import Optional

from sqlalchemy import String, Numeric, Date, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from shared.db import Base


class SoQuy(Base):
    __tablename__ = "so_quy"
    __table_args__ = (
        Index("ix_sq_ngay", "ngay"),
        {"schema": "ketoan"},        # LUÔN là phần tử CUỐI CÙNG
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    so_tien: Mapped[Decimal] = mapped_column(Numeric(15, 2), server_default="0", nullable=False)
    tai_khoan: Mapped[Optional[str]] = mapped_column(String(128))
```

## Bắt buộc

- **Cú pháp SQLAlchemy 2**: `Mapped[...]` + `mapped_column(...)`. Không dùng cú pháp cũ
  `Column(...)` kiểu 1.x.
- **`Mapped[Optional[str]]` cho cột nullable, `Mapped[str]` cho cột NOT NULL.** Đây không chỉ là
  gợi ý cho editor — SQLAlchemy 2 suy ra `nullable` từ chính annotation đó.
- **`__table_args__` luôn kết thúc bằng `{"schema": "ketoan"}`.** Nếu `__table_args__` chỉ có
  mỗi dict thì viết `__table_args__ = {"schema": "ketoan"}`; nếu có Index thì dùng tuple và đặt
  dict ở cuối. Đặt sai chỗ → SQLAlchemy báo lỗi khó hiểu lúc import.
- **Tiền = `Numeric(15, 2)`**, không `Float`. Không có `Float` nào trong `app/models/` — giữ vậy.
- Đặt tên Index ngắn theo tiền tố bảng: `ix_sq_ngay`, `ix_sq_ma_don` (`sq` = so_quy).

## Migration — quy tắc quan trọng nhất của repo này

**Thêm/đổi cột trong model thì PHẢI có một alembic revision đi kèm trong cùng lần sửa.**
Repo đang có 2 chỗ drift (model khai mà DB không có: `so_quy.ref_sepay`, bảng
`sepay_transactions`) và hậu quả là `GET /api/so-quy` trả 500 `UndefinedColumn`.

Lý do drift gây 500: SQLAlchemy sinh câu `SELECT id, ngay, ..., ref_sepay FROM ketoan.so_quy` —
**liệt kê mọi cột có trong model**, chứ không phải `SELECT *`. Model có cột mà DB chưa có là lỗi
ngay lập tức, không phải "cột đó trả null".

```bash
# Tạo revision (alembic.ini nằm ở devrun)
cd /c/PapasanIT/App_qlpps/ketoan-devrun
"$PY" -m alembic -c alembic.ini revision -m "them cot ref_sepay vao so_quy"
# → file mới trong alembic/versions/ của REPO, tự viết upgrade()/downgrade()
"$PY" -m alembic -c alembic.ini upgrade head
"$PY" -m alembic -c alembic.ini current      # xác nhận đã lên head
```

- Đặt tên file revision theo quy ước sẵn có: `q<N>_<YYYY>_<MM>_<DD>_<mo_ta_khong_dau>.py`
  (ví dụ `q5_2026_05_19_tscd_chi_phi_lap_dat.py`). Hiện có 28 revision, head = `q5_2026_05_19`.
- Mọi `op.add_column` / `op.create_table` phải truyền `schema="ketoan"`.
- **Luôn viết `downgrade()` thật**, không để `pass`. Migration không lùi được là migration không
  dám chạy trên production.
- **KHÔNG thêm `ALTER TABLE` vào `lifespan` trong `main.py`.** Chỗ đó đã có sẵn vài lệnh như vậy
  nhưng đó là nợ kỹ thuật cũ, không phải mẫu để theo.

## Trước khi kết luận "endpoint hỏng"

So model với DB thật đã, đừng đoán:

```sql
SELECT column_name FROM information_schema.columns
WHERE table_schema = 'ketoan' AND table_name = 'so_quy' ORDER BY ordinal_position;
```

Đối chiếu với `Base.metadata.tables["ketoan.so_quy"].columns` — lệch chỗ nào là drift chỗ đó.
