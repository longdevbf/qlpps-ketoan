---
name: erp-architecture
description: Kiến trúc & luật phạm vi hệ ERP QLPPS — 8 repo tách từ monorepo App_V2, import chéo package anh em, thư viện shared/ vendored trong từng repo, scaffolding *-devrun, cross-app qua raw SQL fail-soft. LUÔN đọc trước khi sửa file chạm shared/, import package anh em, hoặc làm task liên phân hệ.
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/erp-architecture/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/erp-architecture/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# ERP Architecture — QLPPS (8 app, tách từ monorepo App_V2)

## 1. Cấu trúc thật — 8 repo cạnh nhau, KHÔNG phải monorepo

```
d:\PapaSanIT\
  qlpps-baogia\      ← package `baogia`    · Báo giá        · 8001 · schema baogia
  qlpps-marketing\   ← package `marketing` · Marketing      · 8002 · schema marketing
  qlpps-muahang\     ← package `muahang`   · Mua hàng       · 8003 · schema muahang
  qlpps-hcns\        ← package `hcns`      · HC Nhân sự     · 8004 · schema hcns
  qlpps-ketoan\      ← package `ketoan`    · Kế toán        · 8005 · schema ketoan
  qlpps-saleadmin\   ← package `saleadmin` · Sale Admin     · 8006 · schema saleadmin
  qlpps-ceo\         ← package `ceo`       · CEO Dashboard  · 8007 · KHÔNG có schema
  qlpps-congnghe\    ← package `congnghe`  · Công Nghệ      · 8008 · schema congnghe
                         (tên miền itque.qlpps.com, image Docker RIÊNG)
  claude-kit\        ← nguồn gốc bộ .claude của cả 8 app (sửa ở đây rồi chạy sync)
  seed\ docker\ docker-compose.yml   ← Postgres + dữ liệu ảo (xem README-DEV.md)
```

`qlpps-ceo` là app **chỉ đọc**: không có `app/models/`, không có schema riêng,
không có migration — nó tổng hợp số từ 7 schema kia.

Mỗi repo **chính là** package cùng tên. Chúng tách từ monorepo `App_V2` —
**`App_V2` KHÔNG tồn tại trên máy này**; README/hướng dẫn cũ nào bảo
`cd App_V2` là lỗi thời, đừng làm theo.

**Ba hệ quả sống còn:**

1. **ASGI target luôn là `<package>.app.main:app`** (vd `ketoan.app.main:app`),
   không bao giờ `app.main:app` — sai tên sẽ nạp mọi SQLAlchemy model thành
   2 bản và nổ vì trùng bảng.
2. **`app/main.py` import package anh em ở module level** (không try/except ở
   nhiều chỗ) — thiếu package là chết ngay lúc import. Trên máy này **chưa có
   scaffolding chạy app**: DB đã dựng sẵn (xem skill `chay-app`) nhưng chưa có
   auth stub và chưa có alias package. Đừng hứa "chạy thử rồi" khi chưa chạy.
3. **Import package anh em trong code MỚI phải LAZY** (trong hàm, không đầu
   file) — trên máy dev một số package chỉ là stub; import module level làm
   cả app chết lúc khởi động thay vì chỉ hỏng 1 endpoint.

## 2. `shared/` — thư viện dùng chung, vendored TRONG từng repo

Mỗi repo chứa một bản `shared/` (auth JWT SSO, db Base/session, config, audit,
events, middleware, models schema `shared`, routers cross-app: xin-nghi,
duyet-chi, giao-viec, calendar…). Đây là **code dùng chung của cả 8 app** —
sửa `shared/` ở một repo là lệch khỏi 6 bản còn lại.

Khi task yêu cầu sửa `shared/`:
1. **DỪNG, không sửa ngay.** Gọi agent `shared-impact` (hoặc `/impact`) đo ảnh hưởng.
2. Báo user: sửa ở đây sẽ phải đồng bộ sang N repo kia — chờ duyệt.
3. Khi sửa: giữ tương thích ngược (thêm tham số optional, không đổi signature).
4. Sau khi sửa: liệt kê các app bị ảnh hưởng để user test + đồng bộ.

**Cấm tuyệt đối**: sửa `shared/` "tiện tay" trong lúc làm task của một app.

## 3. Database — 1 Postgres, mỗi app một schema

Schema: `shared` (users, notifications, products, calendar, approvals…) +
`baogia`, `marketing`, `muahang`, `hcns`, `ketoan`, `saleadmin`, `congnghe`.
Model khai
`__table_args__` kết thúc `{"schema": "<tên>"}`. Alembic mỗi app filter đúng
schema của mình. **`alembic.ini` KHÔNG có trong repo nào** — bản dùng được nằm ở
`d:/PapaSanIT/docker/seeder/alembic.ini` (7 section, mỗi app một
`script_location`).

Schema `shared` **không app nào migrate** — `include_object` của cả 6 app đều
lọc theo schema riêng. Bảng `shared` thuộc repo `auth_service` không có ở đây;
chúng được dựng bằng `metadata.create_all` trong bộ seeder.

**Cross-app đọc dữ liệu — 2 cách, ưu tiên cách 1:**
1. Raw SQL `text()` **fail-soft** (bọc try/except, log, trả rỗng) — chạy được
   cả khi package anh em là stub. Mẫu: `services/external_reader.py` (ketoan).
2. ORM import lazy trong hàm (`from muahang.app.models import PurchaseOrder`)
   — chỉ khi cần object thật; stub thì hỏng đúng hàm đó.

**Fail-soft vs fail-hard** — bắt chước đúng loại:
- Fail-soft (log rồi đi tiếp): sync sổ quỹ, cache Redis, đọc cross-app, emit event.
- Fail-hard (để exception bay): validate, ghi bản ghi nghiệp vụ chính, phân quyền.
- Không bao giờ `except Exception: pass` trống.

## 4. Phạm vi mỗi task

- Đầu task nói rõ: "Phạm vi: app `<tên>`" — chỉ sửa trong repo đó; `shared/`
  chỉ đọc trừ khi được duyệt riêng (mục 2).
- Lỗi ở app khác → **báo**, không tự sửa: "Lưu ý ngoài phạm vi: …".
- Task đụng ≥2 app → dừng, trình kế hoạch, chờ duyệt.
- Không định nghĩa lại thực thể chung (Khách hàng, Sản phẩm, User…) — dùng
  `shared/models` hoặc đọc từ app chủ quản; không đặt tên trường khác nhau
  giữa các app cho cùng một thứ.

## 5. Dòng nghiệp vụ — dữ liệu chảy giữa các app

```
Báo giá (chốt) → Sale Admin (đơn hàng) → Kế toán (doanh thu, công nợ KH)
Mua hàng (PO, NCC)                     → Kế toán (công nợ NCC)
HCNS (chấm công, lương)                → Kế toán (quỹ lương)
Marketing (chi ads, data, inbox)       → Kế toán (chi phí) · Sale Admin (cơ hội)
Mọi app                                → CEO Dashboard (CHỈ ĐỌC, tổng hợp)
```

- Làm màn hình ở một mắt xích: luôn hỏi dữ liệu đến từ đâu, đi tiếp đâu.
  Không tạo bản ghi "cụt" không nối được mắt xích sau.
- Số tổng hợp ở Kế toán/CEO phải truy ngược được về chứng từ gốc — không có
  đường truy ngược → báo user trước khi code.
- Sổ quỹ Kế toán **KHÔNG nhập tay** — tự sinh từ nguồn (DoanhThu, ChiPhi,
  CongNo…) idempotent qua `(lien_quan, ref_id)`. Muốn biết vì sao một dòng
  xuất hiện → tìm `ref_id`, đừng tìm form nhập.

## 6. Quy ước code chung (mọi app)

- **Tên nghiệp vụ = tiếng Việt không dấu** (`doanh_thu`, `so_tien`, `cong_no`);
  tên kỹ thuật = tiếng Anh (`session`, `payload`, `router`). Docstring/comment
  tiếng Việt. Không dịch tên nghiệp vụ sang tiếng Anh.
- **Tiền dùng `Decimal`/`Numeric`, cấm `float`** — sai số nhị phân cộng dồn là
  lỗi thật với kế toán.
- Session SQLAlchemy **đồng bộ** (`db.execute(...)` không `await`).
- Trong `app/` dùng **import tương đối** (`from ..models import …`) — tuyệt
  đối không `from app.models import …` (nhân đôi model).
- Phân tầng `models/ → schemas/ → routers/ → services/` (nghiệp vụ thật nằm ở
  services). Prefix router đặt ở `include_router` trong `main.py`, không khai
  trong `APIRouter(...)`.
- Audit (`log_action`) gọi ở tầng **router** cho endpoint ghi/sửa/xoá.
- Không thêm dependency, linter, formatter mới khi user chưa đồng ý.
