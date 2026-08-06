---
paths:
  - "app/routers/**/*.py"
  - "app/schemas/**/*.py"
description: Quy tắc cho tầng router (API) và schema Pydantic
---

# Router & Schema — chỉ những điều khác mặc định

## Khung chuẩn của một router

Mọi router mới copy đúng khung này (lấy từ [doanh_thu.py](../../app/routers/doanh_thu.py)):

```python
"""<Tên> API — CRUD."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db

from ..models import DoanhThu
from ..schemas import DoanhThuCreate, DoanhThuOut
from ._deps import require_ketoan_user

router = APIRouter()          # KHÔNG có prefix= ở đây
_AUTH = Depends(require_ketoan_user)


@router.get("", response_model=list[DoanhThuOut])
async def list_doanh_thu(
    user: Annotated[JWTPayload, _AUTH],
    db: Session = Depends(get_db),
):
    ...
```

## Bắt buộc

- **`APIRouter()` không bao giờ khai `prefix=`.** Prefix đặt ở `include_router(...)` trong
  [main.py](../../app/main.py). Khai 2 chỗ → URL bị nhân đôi (`/api/doanh-thu/api/doanh-thu`).
- **Auth khai một lần**: `_AUTH = Depends(require_ketoan_user)` ngay dưới `router = APIRouter()`,
  rồi mỗi endpoint nhận `user: Annotated[JWTPayload, _AUTH]`. 35/44 router đang làm đúng vậy.
  Không viết `Depends(require_ketoan_user)` lặp lại trong từng endpoint.
  *Dependency injection ở đây nghĩa là: FastAPI tự chạy `require_ketoan_user` trước endpoint,
  tự lấy JWT từ header, tự trả 401/403 nếu sai — endpoint chỉ nhận kết quả đã xác thực.*
- **`log_action(...)` gọi ở ROUTER, không ở service.** Cả 122 lời gọi audit trong repo đều ở
  `app/routers/`. Endpoint nào tạo/sửa/xoá dữ liệu đều phải log.
- **`db: Session = Depends(get_db)`** — đồng bộ, không `await db.execute(...)`.

## Schema Pydantic v2

- Schema đọc ra (`...Out`) phải có `model_config = ConfigDict(from_attributes=True)` để đọc được
  từ object SQLAlchemy. Thiếu nó thì FastAPI không convert được ORM object → 500.
- Tách 3 loại: `XCreate` (input tạo), `XUpdate` (input sửa, mọi field `Optional`), `XOut` (output).
  Không dùng chung một schema cho cả 3 — `XCreate` mà có `id` là mở đường cho client tự đặt id.
- Tiền dùng `Decimal`, ngày dùng `date`/`datetime`, không dùng `str`.

## Lỗi trả về

- Dùng `HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="...")`, `detail` viết tiếng
  Việt vì người đọc là kế toán viên.
- Không trả 200 kèm `{"error": ...}` — dùng đúng HTTP status.

## Gọi service

Router **không chứa nghiệp vụ**. Router = validate input → gọi service → log_action → trả schema.
Logic tính toán, đồng bộ, quy tắc kế toán đặt ở `app/services/`. Nếu thấy mình viết quá ~30 dòng
tính toán trong router, đó là dấu hiệu phải tách sang service.
