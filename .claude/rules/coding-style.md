---
description: Quy tắc style áp dụng cho toàn dự án (không giới hạn thư mục)
---

# Quy tắc style toàn dự án

Chỉ ghi những điều **khác mặc định**. Cái gì không nói ở đây thì theo PEP 8.

## Ngôn ngữ

- **Tên nghiệp vụ = tiếng Việt không dấu**: `doanh_thu`, `so_tien`, `ngay_tra`, `cong_no`,
  `so_quy`, `chi_phi_phat_sinh`. Áp dụng cho tên bảng, tên cột, tên biến, tên hàm nghiệp vụ.
  **Không** dịch sang tiếng Anh, kể cả khi thấy "revenue" tự nhiên hơn.
- **Tên kỹ thuật = tiếng Anh**: `session`, `payload`, `router`, `response_model`, `db`, `user`.
- **Docstring và comment viết tiếng Việt.** Comment giải thích *tại sao*, không lặp lại *cái gì*
  code đã nói rõ.

```python
# ĐÚNG
def tinh_cong_no_con_lai(db: Session, khach_hang_id: int) -> Decimal:
    """Tính số tiền khách còn nợ = tổng phải thu - tổng đã trả."""

# SAI — dịch tên nghiệp vụ sang tiếng Anh
def calculate_remaining_debt(...)
```

## Session là ĐỒNG BỘ, không phải async

Repo dùng `Session` của `sqlalchemy.orm` (đồng bộ), **không** `AsyncSession`. Endpoint khai
`db: Session = Depends(get_db)` và gọi `db.execute(...)` **không có `await`**. Endpoint có thể
là `async def` nhưng lời gọi DB bên trong vẫn đồng bộ — đừng thêm `await` vào `db.execute`.

```python
cn = db.execute(
    select(CongNo).where(CongNo.ma_don == ma_don).where(CongNo.loai == "phai_thu")
).scalar_one_or_none()          # KHÔNG await
```

## Import

- **Trong `app/` dùng import TƯƠNG ĐỐI** — `from ..models import DoanhThu`, `from ..services
  import so_quy_auto`. Đây là quy ước thực tế của repo (200 chỗ dùng tương đối, 0 chỗ dùng
  `from app.`). Viết `from app.models import ...` sẽ nạp model thành 2 bản (một qua `ketoan.app`,
  một qua `app`) và nổ vì trùng tên bảng — cùng nguyên nhân với lỗi ASGI target sai.
- **Import package anh em (`muahang`, `baogia`, `hcns`...) phải LAZY** — đặt bên trong hàm, không
  ở đầu file. Lý do: `baogia`/`muahang` là stub trên máy này, import ở module level sẽ làm cả app
  chết lúc khởi động chứ không phải lúc gọi endpoint.

```python
async def lay_don_mua(db, po_id: int):
    from muahang.app.models import PurchaseOrder   # lazy: stub thì chỉ hàm này hỏng
    ...
```

## Kiểu dữ liệu tiền tệ

- Tiền dùng `Decimal` / `Numeric`, **không dùng `float`**. `float` làm tròn nhị phân sai số →
  cộng dồn nhiều dòng sổ quỹ sẽ lệch vài đồng, và với app kế toán đó là lỗi thật.

## Fail-soft vs fail-hard

Dự án này phân biệt rõ 2 loại lỗi — bắt chước đúng loại:

- **Fail-soft** (bọc `try/except`, log rồi đi tiếp): sync sổ quỹ, cache Redis, đọc cross-app,
  emit event. Những thứ này hỏng thì nghiệp vụ chính vẫn phải chạy.
- **Fail-hard** (để exception bay lên): validate dữ liệu, ghi bản ghi nghiệp vụ chính, phân quyền.
  Nuốt lỗi ở đây = ghi sai sổ mà không ai biết.

Không bao giờ viết `except Exception: pass` trống — tối thiểu phải log.

## Không được làm

- Không thêm dependency mới vào `requirements.txt` khi chưa hỏi.
- Không tự chạy formatter hàng loạt (repo chưa có formatter; reformat cả file làm diff không đọc được).
- Không sửa `shared/` cho nhu cầu riêng của ketoan — 5 app khác đang dùng chung.
- Không sửa `app/pages.py` (code chết, không được import ở đâu). File thật là `app/routers/pages.py`.
