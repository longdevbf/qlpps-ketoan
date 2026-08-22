---
paths:
  - "app/routers/**/*.py"
  - "shared/routers/**/*.py"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/routers-api.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/routers-api.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Sửa router FastAPI

## Tìm prefix thật của endpoint

Phần lớn prefix khai ở `app/main.py`, nhưng **một số router tự khai prefix bên
trong `APIRouter(prefix=...)`**. Chỉ grep `main.py` là sẽ kết luận sai rằng
endpoint không tồn tại. Luôn kiểm cả hai chỗ:

```bash
grep -n "include_router(<tên>" app/main.py
grep -n "APIRouter(prefix=" app/routers/<tên>.py
```

## Đừng nuốt lỗi

Một số endpoint bọc cả truy vấn trong `except SQLAlchemyError: return []`.
Query hỏng khi đó trông y hệt "không có dữ liệu" — không log,
không toast, debug rất tốn thời gian. Khi thêm handler mới:

- Đừng thêm mẫu này. Để lỗi nổi lên cho `register_error_handlers` xử lý.
- Khi một list endpoint trả `[]` bất thường, **chạy tay câu SQL của nó** trước
  khi kết luận DB rỗng.

## Bind param trong `text()`

`:frm::date` **không bind** — SQLAlchemy để nguyên dấu `:` và Postgres báo
`syntax error at or near ":"`. Luôn dùng:

```python
text("... WHERE d >= CAST(:frm AS date)")   # đúng
text("... WHERE d >= :frm::date")           # sai, im lặng hỏng
```

## Giữ tên field ổn định

Phần lớn route decorator trong hệ này **không** khai `response_model`; chúng
tự dựng dict nên không có gì ràng buộc tên key. Đổi tên field ở router là làm vỡ template đang
đọc nó, mà không có lỗi biên dịch nào báo.

- Thêm `response_model` khi viết endpoint mới.
- Đổi tên field có sẵn thì phải grep template dùng nó trước.
- Trả **đúng một** kiểu shape. Lỗi có thật đã gặp: endpoint trả mảng trần
  trong khi template chỉ nhận `{plan:…}`/`{items:[…]}` → dữ liệu có thật mà
  màn hình báo "chưa có dữ liệu".

## Phân quyền có hai tầng

`Depends(require_app("ketoan"))` mới là tầng ngoài. Nhiều endpoint còn gate
riêng bên trong bằng whitelist role. Đọc cả hai trước khi kết luận một role bị
chặn ở đâu.

## Giá trị enum

`CheckConstraint` trên model và `Literal[...]` trong `app/schemas/` phải khớp,
và **không nhất quán giữa các module** — cùng một hệ mà có bảng dùng tiếng Anh
(`draft|pending_approval|approved`), có bảng dùng tiếng Việt
(`cho_duyet|da_duyet`). Đọc model trước khi ghi giá trị, đừng suy từ bảng khác.

## Khuôn mẫu bắt buộc cho một endpoint

Thứ tự trong mỗi endpoint: **kiểm tra quyền → truy vấn / gọi service → commit →
`log_action` → return**. Mọi tính toán nghiệp vụ đặt ở `app/services/`.

```python
router = APIRouter()
_AUTH = Depends(require_app("ketoan"))       # khai báo MỘT LẦN ở đầu module

@router.get("", response_model=list[DepartmentOut])
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
    active: Optional[bool] = None,
):
```

- `db` và `user` **luôn dùng `Annotated[...]`**, đặt trước query param.
- Endpoint ghi thêm `request: Request` để `log_action` lấy được IP / User-Agent.
- Kiểm tra quyền **tường minh**, không dựa vào frontend:
  `if user.role not in ("admin", "ceo", "manager"): raise HTTPException(403, "…")`.
- Nhân viên thường chỉ được xem bản ghi của chính mình — filter theo username,
  đừng trả cả bảng rồi để frontend lọc.

## Truy vấn

Dùng SQLAlchemy 2 style: `db.execute(select(Model).where(...)).scalars().all()`.
Lấy theo khoá chính: `db.get(Model, id)`. Kiểm tra tồn tại:
`.scalar_one_or_none()`. **Không nối chuỗi SQL** — luôn để SQLAlchemy bind
tham số (nối chuỗi là lỗ hổng SQL injection).

## Mã HTTP và schema

`201` khi tạo · `204` khi xoá (không body) · `404` không tồn tại · `409` trùng
dữ liệu · `403` sai quyền. Message tiếng Việt, nói rõ **cái gì** sai.

Mỗi entity 4 class trong `app/schemas/`: `XBase` (field chung) → `XCreate` →
`XUpdate` (tất cả `Optional[...] = None`) → `XOut` (thêm `id`, `created_at`,
`updated_at` và `model_config = ConfigDict(from_attributes=True)`).

## Audit

Sau `db.commit()` của mọi thao tác ghi:

```python
log_action(db, app="ketoan", action="<verb>_<entity>", user=user, request=request,
           resource=f"<entity>:{id}", payload=fields)
```

Với DELETE thì `payload` là snapshot dữ liệu **trước khi xoá**.
