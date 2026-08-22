---
paths:
  - "app/services/**/*.py"
description: Quy tắc cho tầng service — nơi chứa nghiệp vụ kế toán thật
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/services-nghiepvu.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/services-nghiepvu.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Service — nơi chứa nghiệp vụ

## Vai trò

`services/` là tầng duy nhất được chứa quy tắc kế toán. Router chỉ điều phối.

**Service mới nên KHÔNG import `fastapi`** — nhận `db: Session` + tham số thuần, trả dữ liệu hoặc
raise exception Python. Như vậy mới test được mà không cần dựng HTTP client.
*Thực tế repo: 18/21 service đang sạch, còn `journal.py`, `quy_dn_calc.py`, `tscd_calc.py` có
import `fastapi`.* Đó là ngoại lệ cũ, không phải mẫu để theo — đừng thêm chỗ thứ 4.

## Idempotency — khái niệm trung tâm của repo này

Nhiều service là **bridge**: tự sinh bản ghi từ nguồn khác (`so_quy_auto`, `chi_phi_from_ads`,
`revenue_from_order`, `cong_no_from_order`, `sepay_webhook`...). Bridge có thể bị gọi lại nhiều
lần cho cùng một nguồn (user bấm 2 lần, webhook retry, sync định kỳ).

*Idempotent = chạy 1 lần hay 10 lần đều cho ra cùng một kết quả, không tạo bản ghi trùng.*

Cách repo làm: khoá theo cặp **`(lien_quan, ref_id)`** — `lien_quan` là tên module nguồn
(`"doanh_thu"`, `"chi_phi"`, `"cong_no"`), `ref_id` là id bản ghi nguồn. Trước khi insert phải
`SELECT` theo cặp đó; có rồi thì UPDATE, chưa có thì INSERT.

**Viết bridge mới phải theo đúng khuôn này.** Đọc
[so_quy_auto.py](../../app/services/so_quy_auto.py) trước khi viết.

## Fail-soft cho bridge

Bridge **không được làm hỏng nghiệp vụ chính**. Nếu sync sổ quỹ lỗi, việc tạo doanh thu vẫn phải
thành công.

```python
try:
    sync_so_quy_from_doanh_thu(db, dt.id)
except Exception:
    logger.exception("sync so_quy that bai cho doanh_thu id=%s", dt.id)
    # KHÔNG raise lại — caller vẫn commit bản ghi chính
```

Ngược lại, tính toán nghiệp vụ chính (số dư, công nợ, khấu hao) **phải fail-hard** — sai thì để
nổ, đừng nuốt.

## Transaction

- Repo hiện có **19 chỗ `db.commit()` trong `app/services/`** — tức là nhiều service đang tự chốt
  transaction. Biết điều này để **không commit hai lần**: nếu service bạn gọi đã commit rồi thì
  router đừng commit lại, và ngược lại. Kiểm tra service trước khi thêm `db.commit()`.
- Với code mới, ưu tiên để **một chủ thể duy nhất commit** cho mỗi thao tác. Nếu service nào cũng
  tự commit thì không gộp được nhiều bước vào một transaction, và rollback mất ý nghĩa.
- Cần ghi rồi đọc lại trong cùng transaction thì dùng `db.flush()`, không phải `commit()`.
  *`flush` đẩy câu INSERT xuống DB để lấy `id` nhưng transaction chưa chốt; `commit` chốt luôn.*

## Cross-app: ưu tiên raw SQL

Đọc dữ liệu app khác thì dùng `text()` fail-soft như
[external_reader.py](../../app/services/external_reader.py), **không** import ORM của
`muahang`/`baogia` — 2 package đó là stub trên máy này, import ở module level làm chết cả app.
Nếu buộc phải dùng ORM thì import lazy trong hàm và bọc `try/except ImportError`.

## Query — tránh N+1

*N+1 query = lấy N bản ghi rồi lặp qua từng cái để query thêm 1 lần nữa → N+1 lượt đi DB.*
Trong vòng lặp mà thấy `db.execute(...)` là dấu hiệu N+1. Cách sửa: gom thành một query dùng
`WHERE id IN (...)` hoặc `selectinload()` cho relationship, rồi tra bằng dict trong Python.
