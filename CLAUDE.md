# CLAUDE.md — hướng dẫn cho Claude Code trong repo này

## Dự án

**Kế Toán V2** — app kế toán nội bộ QLPPS: doanh thu, chi phí, công nợ, sổ quỹ, tồn kho, TSCĐ +
khấu hao, bút toán kép, đóng kỳ, báo cáo P&L / cân đối / dòng tiền. FastAPI 0.115 + SQLAlchemy 2 +
Pydantic v2 + Alembic + Jinja2, Python 3.11, Postgres. Quy mô: 44 router, 29 model, 24 schema, 21
service, 62 `include_router`, **403 route**.

## Điều quan trọng nhất

**Repo này tách ra từ monorepo `App_V2` và KHÔNG tự chạy được.** Root repo *chính là* package
`ketoan`. [app/main.py:104-126](app/main.py#L104-L126) import 6 package anh em (`baogia`,
`ketoan`, `hcns`, `muahang`, `marketing`, `saleadmin`) ở **module level, không try/except** —
thiếu là chết ngay lúc import. Scaffolding nằm **ngoài repo** tại `C:/PapasanIT/ketoan-devrun`
(package alias, auth stub, `alembic.ini`, `dev_patch.sql`, `run.sh`); đọc `HUONG-DAN.md` trước.

- ASGI target là **`ketoan.app.main:app`**, không bao giờ `app.main:app` — sai tên sẽ nạp mọi
  SQLAlchemy model thành 2 bản và nổ vì trùng bảng.
- `App_V2` KHÔNG tồn tại trên máy này. README bảo `cd App_V2 && ...` — đừng làm theo.
- `baogia`/`muahang` là stub (chưa clone), 3 chỗ hỏng khi gọi: [cong_no.py:136](app/routers/cong_no.py#L136),
  [cong_no.py:185](app/routers/cong_no.py#L185), [cong_no_from_order.py:47](app/routers/cong_no_from_order.py#L47).
- `.env` **không có `DATABASE_URL`** và đặt `APP_ENV=production`; mặc định ở
  [shared/config.py:28](shared/config.py#L28) trỏ cổng 5432 — DB dự án khác. `env.sh` override
  bằng biến môi trường (thắng file `.env`); không sửa `.env`.

## Lệnh (chạy thử và kiểm chứng 01/08/2026)

```bash
# Chạy app — tự bật Postgres/Redis, auth stub, uvicorn. Cổng 8005.
bash /c/PapasanIT/ketoan-devrun/run.sh

# Mọi lệnh khác PHẢI source env.sh trước (đặt PYTHONPATH + DATABASE_URL + $PY).
# Source bằng ĐƯỜNG DẪN TUYỆT ĐỐI và đứng tại thư mục repo — `cd` sang devrun rồi
# chạy py_compile sẽ lỗi "No such file or directory" vì đường dẫn là tương đối.
source /c/PapasanIT/ketoan-devrun/env.sh

# Kiểm tra cú pháp — repo CHƯA có linter, đây là thứ gần nhất (~2.8s)
"$PY" -m py_compile app/main.py app/routers/*.py app/services/*.py app/models/*.py app/schemas/*.py
# App import được không? (nặng hơn py_compile, bắt được cả lỗi import vòng)
"$PY" -c "import ketoan.app.main as m; print(len(m.app.routes), 'routes')"

# Test — CHƯA có tests/, `no tests ran` là đúng cho tới khi bạn tạo
"$PY" -m pytest -q
"$PY" -m pytest tests/test_x.py::test_y -q

# Migration — alembic.ini nằm ở devrun nên phải cd sang đó trước
cd /c/PapasanIT/ketoan-devrun
"$PY" -m alembic -c alembic.ini current    # → q5_2026_05_19 (head)
"$PY" -m alembic -c alembic.ini upgrade head
"$PY" -m alembic -c alembic.ini revision -m "mo ta"
curl http://127.0.0.1:8005/health    # {"status":"ok","service":"ketoan",...}
```

**Repo CHƯA có `tests/`, `conftest.py`, `pytest.ini`, linter, formatter.** `pytest` 8.3.4 +
`pytest-asyncio` 0.24.0 đã cài; `tests/` phải tự tạo. Đăng nhập dev:
http://127.0.0.1:8005/login — `admin` / `ceo` / `devadmin`, mật khẩu `123456`.

## Schema drift đã biết (lỗi thật của repo)

2 chỗ model đã khai mà **không migration nào tạo** (`grep -rn ref_sepay alembic/` → rỗng):
- [app/models/so_quy.py:54](app/models/so_quy.py#L54) — cột `ref_sepay`. Thiếu nó thì
  `GET /api/so-quy` trả 500 `UndefinedColumn`: SQLAlchemy sinh SELECT liệt kê **mọi** cột trong
  model, chứ không `SELECT *`.
- [app/models/sepay_transaction.py](app/models/sepay_transaction.py) — cả bảng `sepay_transactions`.

Vá tạm bằng `ketoan-devrun/dev_patch.sql`. **Cách đúng là thêm alembic revision mới trong repo**;
có revision rồi thì bỏ patch. Khi thêm cột, luôn so `Base.metadata` với
`information_schema.columns` schema `ketoan` trước khi kết luận endpoint hỏng.

## Kiến trúc

**Phân tầng**: `models/` → `schemas/` → `routers/` → `services/` (nơi chứa nghiệp vụ thật).
[app/main.py](app/main.py) là bản đồ — đọc trước. Không router nào tự khai `prefix=` trong
`APIRouter(...)`; prefix luôn đặt ở `include_router` trong `main.py`.
**`shared/` là thư viện dùng chung của cả 6 app** — nằm trong repo nhưng sửa nó là ảnh hưởng app
khác. Cung cấp `shared.db` (`Base`, `get_db`, `engine`), `shared.auth` (JWT SSO, `JWTPayload`,
`require_app`), `shared.audit.log_action`, `shared.events.emit_event`, `shared.config.settings`,
`shared.middleware`.

**Phân quyền**: mọi router API dùng đúng một pattern — [_deps.py](app/routers/_deps.py)
`require_ketoan_user` (role ∈ admin/ceo/assistant_ceo/manager/kt), khai một lần thành
`_AUTH = Depends(require_ketoan_user)` đầu file (35/44 router), rồi
`user: Annotated[JWTPayload, _AUTH]` trong từng endpoint.
**Audit nằm ở tầng router, không phải service**: 122 lời gọi `log_action(...)` đều trong
`app/routers/` — thêm endpoint ghi/sửa/xoá thì log ở router cho đồng bộ.

**Sổ quỹ KHÔNG nhập tay** — ý tưởng trung tâm dễ hiểu sai.
[services/so_quy_auto.py](app/services/so_quy_auto.py) tự sinh entry từ 3 nguồn (DoanhThu → thu,
ChiPhiPhatSinh → chi, CongNo trả → chi), idempotent qua cặp `(lien_quan, ref_id)`, và
**fail-soft**: lỗi sync không block caller. Bridge cùng kiểu: `chi_phi_from_ads`,
`chi_phi_from_payroll`, `revenue_from_order`, `cong_no_from_order`, `from_saleadmin`, `from_vc`,
`sepay_webhook`. Muốn biết vì sao một dòng sổ quỹ xuất hiện → tìm `ref_id`, đừng tìm form nhập.

**Cross-app**: 2 cách — raw SQL `text()` fail-soft
([services/external_reader.py](app/services/external_reader.py)) và ORM import lazy trong hàm
(`from muahang.app.models import PurchaseOrder`). Cách 1 chạy được dù package anh em không có;
cách 2 thì không. **Code mới ưu tiên cách 1.**
**Cache**: [main.py:75](app/main.py#L75) `cache_get_or_set(key, ttl, compute_fn)` — Redis prefix
`ketoan:`, fail-soft về compute trực tiếp khi Redis lỗi.
**Auto-migrate lúc startup**: `lifespan` trong `main.py` chạy vài `ALTER TABLE ... IF NOT EXISTS`
ngoài Alembic — **nợ kỹ thuật, không phải mẫu để bắt chước**; cột mới dùng revision.

**HTML**: [routers/pages.py](app/routers/pages.py) render Jinja2 từ `templates/`, auth bằng cookie
`access_token`. `templates/index.html` là SPA một file **564 KB** (JS inline) — sửa phải grep theo
tên hàm/id, đừng đọc cả file. ⚠️ `app/pages.py` là **code chết**: trùng tên với
`app/routers/pages.py`, không được import ở đâu, `_TEMPLATES_DIR` tính sai một cấp. Đừng sửa nhầm.

## Quy ước giữ nguyên

- **Tên tiếng Việt không dấu** cho bảng/cột/biến nghiệp vụ (`doanh_thu`, `so_tien`, `ngay_tra`).
- **Docstring/comment tiếng Việt**, code (tên hàm, biến kỹ thuật) tiếng Anh.
- Giữ phân tầng `models/` + `schemas/` + `routers/` + `services/` — không gộp, không tái cấu
  trúc. Dùng lại `shared/` thay vì viết lại auth/db/audit/events.
- Model dùng SQLAlchemy 2 (`Mapped[...]` + `mapped_column`), `__table_args__` kết thúc bằng
  `{"schema": "ketoan"}`. Chi tiết theo thư mục: [.claude/rules/](.claude/rules/).

## CHẾ ĐỘ MENTOR

Người dùng repo này là **lập trình viên đang học, MỚI BẮT ĐẦU THẬT SỰ** với FastAPI/SQLAlchemy.
Mục tiêu học: **DB + SQLAlchemy 2**, **kiến trúc FastAPI**, **nghiệp vụ kế toán trong code**,
**test + chất lượng code**. Bốn quy tắc sau ưu tiên cao hơn việc "làm nhanh cho xong":

1. **Giải thích tại chỗ.** Khi dùng khái niệm/pattern họ có thể chưa biết — dependency injection,
   session & transaction lifecycle, idempotency, partial unique index, N+1 query, eager loading,
   fail-soft, migration head/revision — dừng lại giải thích **2-3 câu ngay lúc đó**, kèm ví dụ từ
   chính codebase này. Người mới bắt đầu: giải thích cả khái niệm nền, đừng giả định họ đã biết.
2. **Thay đổi lớn → 2 phương án TRƯỚC khi code**, kèm ưu/nhược, khuyến nghị của bạn và lý do, rồi
   chờ họ chọn. "Lớn" = đổi schema DB, thêm migration, sửa `shared/`, đổi luồng nghiệp vụ, thêm dep.
3. **Sau mỗi task đáng kể → chỉ ra ĐÚNG 1 điều nên tự đọc thêm**, cụ thể và tra được (tên khái
   niệm, trang docs, hoặc file trong repo này), không phải lời khuyên chung chung.
4. **KHÔNG code hộ phần họ nói "để tôi tự làm".** Chỉ gợi ý hướng, chỉ chỗ cần đọc, đặt câu hỏi
   dẫn dắt. Chờ họ nhờ mới viết code.

## Điều cấm

- **KHÔNG tự commit.** Được sửa/tạo file và chạy test/lint tự do — nhưng mọi `git commit` /
  `git push` chỉ khi người dùng nói rõ. Không bao giờ `push --force`.
- Không sửa `.env` (bị git theo dõi, chứa secret thật — xem dưới). Không đổi ASGI target.
- Không sửa `shared/` khi chưa cân nhắc ảnh hưởng 5 app còn lại; không thêm
  linter/formatter/dependency mới nếu người dùng chưa đồng ý.
- Không tin README về cách chạy — nó viết cho monorepo `App_V2` không tồn tại ở đây.

## ⚠️ Bảo mật chưa xử lý

`.env` **đang được git theo dõi** (commit `974981c`) và chứa secret production thật:
`JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`, `SEPAY_WEBHOOK_SECRET`, `EXTERNAL_READ_API_KEY`,
`FCM_SA_JSON_B64` (private key service account Firebase). Cần `git rm --cached .env` + rotate key
đã lộ — `.gitignore` đã có nhưng **không gỡ được file đã nằm trong lịch sử git**.
