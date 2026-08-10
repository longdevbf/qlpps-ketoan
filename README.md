# qlpps-ketoan — Kế Toán V2

App kế toán nội bộ của PapasanIT: nơi mọi con số từ 6 app ERP còn lại hội tụ thành
doanh thu, chi phí, công nợ, sổ quỹ, báo cáo tài chính và bút toán kép.

> Viết lại toàn bộ **08/08/2026**. Mọi số liệu bên dưới **đếm lại bằng lệnh trên chính
> repo này**, không chép từ bản cũ. Bản README trước mô tả Sprint 1 trong monorepo
> `App_V2` — **`App_V2` không còn tồn tại**; đừng làm theo tài liệu nào bảo
> `cd App_V2 && docker compose up`.

## Vai trò trong hệ ERP

Hệ QLPPS gồm 7 repo tách rời chạy song song. Kế toán là **điểm hội tụ** — nhận dữ liệu
từ hầu hết các app, và chỉ đẩy tiếp lên CEO Dashboard.

```
Báo giá (8001)      ──chốt báo giá──┐
Sale Admin (8006)   ──đơn hàng──────┤
Mua hàng (8003)     ──PO, NCC───────┤
HCNS (8004)         ──quỹ lương─────┼──► KẾ TOÁN (8005) ──tổng hợp──► CEO Dashboard (8007)
Marketing (8002)    ──chi ADS───────┤
SePay (webhook QR)  ──thu tiền──────┘
```

**Nhận vào** — không nhập tay, mà qua các *bridge idempotent* khoá theo cặp
`(lien_quan, ref_id)` trong `app/services/`: `revenue_from_order`, `cong_no_from_order`,
`from_saleadmin`, `from_vc`, `chi_phi_from_ads`, `chi_phi_from_payroll`,
`inventory_bridge_muahang`, `inventory_bridge_saleadmin`, `sepay_webhook`.

**Đẩy đi / phục vụ**: báo cáo P&L, cân đối, dòng tiền, CPA cho CEO Dashboard; và
**cổng duyệt cấp 1** — kế toán duyệt Đề Nghị Thanh Toán (Sale Admin), Đề Xuất Trả NCC
(Mua hàng), xác nhận cọc trước khi hồ sơ lên CEO.

**Sổ quỹ KHÔNG có form nhập tay.** Mỗi dòng sinh tự động từ DoanhThu / ChiPhiPhatSinh /
CongNo qua `app/services/so_quy_auto.py`. Muốn biết vì sao một dòng xuất hiện → tra
`ref_id`, đừng đi tìm form.

## Stack

| Lớp | Thành phần |
|---|---|
| Web | FastAPI 0.115.5 · uvicorn 0.32.1 · Jinja2 3.1.4 |
| DB | SQLAlchemy 2.0.36 (**Session đồng bộ**, `Mapped[...]` + `mapped_column`) · psycopg 3.2.3 · Alembic 1.14 · PostgreSQL 16, schema `ketoan` |
| Validation | Pydantic 2.10.3 + pydantic-settings 2.7 |
| Cache / Auth | Redis 5.2 (prefix `ketoan:`, **fail-soft**) · JWT SSO qua `shared.auth`, cookie `access_token` |
| Frontend | HTML + CSS thuần **3 file token-based** — không framework, không build step, không font/icon ngoài |
| Phụ trợ / Test | sentry-sdk · structlog · APScheduler · pywebpush · openpyxl · anthropic · pytest 8.3.4 + httpx 0.28 (**đã cài, chưa có `tests/`**) |

Python 3.11.9 trong `.venv/`. Không có linter/formatter.

## Cách chạy

Repo **không tự chạy được**: root repo *chính là* package `ketoan`, và
`app/main.py:104-126` import 6 package anh em ở **module level không try/except**.
Scaffolding bù phần thiếu nằm **ngoài repo**.

```bash
# ĐÃ KIỂM CHỨNG 08/08/2026 — tự bật Postgres + Redis + auth stub 8010 + uvicorn
bash /c/PapasanIT/App_qlpps/ketoan-devrun/run.sh
```

- **ASGI target luôn là `ketoan.app.main:app`** — `app.main:app` sẽ nạp mọi SQLAlchemy
  model thành 2 bản và nổ vì trùng bảng.
- Cổng **8005**. Health (không cần auth, đã gọi thật hôm nay):
  `curl http://127.0.0.1:8005/health` → `{"status":"ok","service":"ketoan","env":"development"}`
- Đăng nhập dev <http://127.0.0.1:8005/login>: `admin` / `ceo` / `devadmin`, mật khẩu
  `123456`. DB dev dùng chung 7 app: Postgres **5435**, DB `qlpps_dev`, user `qlpps`.

Mọi lệnh khác phải nạp môi trường trước (đặt `PYTHONPATH`, `DATABASE_URL`, biến `$PY`),
**đứng ở thư mục repo, source bằng đường dẫn tuyệt đối**:

```bash
source /c/PapasanIT/App_qlpps/ketoan-devrun/env.sh

"$PY" -m py_compile app/main.py app/routers/*.py app/services/*.py app/models/*.py
"$PY" -c "import ketoan.app.main as m; print(len(m.app.routes), 'routes')"
"$PY" -m pytest -q          # "no tests ran" là đúng cho tới khi bạn tạo tests/

cd /c/PapasanIT/App_qlpps/ketoan-devrun    # alembic.ini nằm ở devrun, không ở repo
"$PY" -m alembic -c alembic.ini current    # head: q5_2026_05_19_tscd_chi_phi_lap_dat
```

**Chưa kiểm chứng trong lần cập nhật này**: `alembic upgrade head`, `alembic revision`,
`py_compile`, `pytest`, `import ketoan.app.main` — kiểm chứng lần cuối 01/08/2026.
Chỉ `run.sh`, `/health`, `/api/so-quy` là đã gọi thật hôm nay.

## Cấu trúc thư mục

```
qlpps-ketoan/
├─ app/                    # toàn bộ code app, phân tầng models → schemas → routers → services
│  ├─ main.py              # BẢN ĐỒ của app: 62 include_router, cache_get_or_set, lifespan
│  ├─ models/    (29 file) # SQLAlchemy 2, __table_args__ kết thúc {"schema": "ketoan"}
│  ├─ schemas/   (24 file) # Pydantic v2: XCreate / XUpdate / XOut (from_attributes)
│  ├─ routers/   (44 file) # HTTP thuần + log_action; prefix khai ở main.py, KHÔNG ở APIRouter()
│  ├─ services/  (21 file) # nghiệp vụ thật + bridge idempotent cross-app
│  └─ pages.py             # ⚠️ CODE CHẾT — trùng tên với routers/pages.py, không ai import
├─ shared/                 # THƯ VIỆN DÙNG CHUNG 7 APP (bản copy trong repo)
│                          # auth · db · config · audit · events · middleware · routers cross-app
├─ alembic/versions/       # 28 revision, head q5_2026_05_19
├─ templates/    (18 file) # Jinja2 — base.html, _header.html, index.html (SPA), 15 trang khác
├─ static/                 # css/ (theme + base + components) · js/ · vendor/ · PWA (manifest, sw.js)
├─ CLAUDE.md               # hướng dẫn cho Claude Code — đọc trước khi sửa code
├─ HE-MAU-ERP.md           # hệ màu chuẩn ERP + số đo tương phản WCAG
├─ .claude/                # bộ kit: 6 rules · 10 skills · 6 agents · settings.json
└─ papasan-frontend-claude/# bộ kit frontend GỐC — nội dung đã merge vào .claude/, có thể gỡ
```

Không có `tests/`, `docs/`, `scripts/`. `alembic.ini`, `run.sh`, `env.sh`,
`dev_patch.sql`, auth stub nằm ở `C:\PapasanIT\App_qlpps\ketoan-devrun\` (ngoài repo).

## Tính năng chính

**Trang HTML** — tất cả render qua `app/routers/pages.py`, auth bằng cookie `access_token`:

| Màn hình / route | Mô tả | Template |
|---|---|---|
| `GET \| POST /login`, `GET /logout` | SSO — forward sang auth service, set cookie | `login.html` |
| `GET /app` | **SPA Kế toán** — 23 trang con (dashboard, doanh thu, chi phí, công nợ, sổ quỹ, P&L, cân đối, cashflow, CPA, TSCĐ, khoản vay, phân phối LN, quản lý quỹ, danh mục…) | `index.html` |
| `GET /products` | Sản phẩm · thuộc tính · tồn kho · BOM (6 tab) | `products.html` |
| `GET /de-nghi-tt` | Duyệt Đề Nghị Thanh Toán cấp 1 (nguồn: Sale Admin) | `de_nghi_tt.html` |
| `GET /duyet-ncc` | Duyệt Đề Xuất Trả NCC cấp 1 (nguồn: Mua hàng) — gate `_mgr` | `ncc_de_xuat.html` |
| `GET /phe-duyet` | Phê duyệt liên phòng ban — gate `_mgr` | `phe_duyet.html` |
| `GET /duyet-chi`, `/xin-nghi`, `/giao-viec`, `/lich-lam-viec`, `/cham-cong`, `/dao-tao`, `/ho-so-ca-nhan` | Trang cross-app dùng chung toàn ERP | tương ứng |
| `GET /khuyen-mai` | ⚠️ route có nhưng **thiếu `templates/khuyen_mai.html`** → 500 khi mở | *(không có)* |
| `GET /health` | Healthcheck, không cần auth | — |

**API** — 62 `include_router`, **403 route đăng ký** (`len(app.routes)`), tương ứng
**328 path / 398 operation** trong OpenAPI (đếm từ `/openapi.json` của app đang chạy):

| Nhóm | Prefix | Router phụ trách |
|---|---|---|
| Doanh thu | `/api/doanh-thu` | `doanh_thu.py`, `revenue_from_order.py` |
| Chi phí | `/api/chi-phi`, `/api/co-dinh`, `/api/loai-chi-phi` | `chi_phi.py`, `chi_phi_bridges.py`, `co_dinh.py`, `loai_chi_phi.py` |
| Công nợ | `/api/cong-no` | `cong_no.py`, `cong_no_ncc.py`, `cong_no_vc.py`, `cong_no_from_order.py` |
| Sổ quỹ & ngân hàng | `/api/so-quy`, `/api/tai-khoan`, `/api/so-du-dau-ky` | `so_quy.py`, `tai_khoan_nh.py`, `tai_khoan_nh_giao_dich.py`, `so_du_dau_ky.py` |
| Thu tiền tự động | `POST /api/sepay/webhook` | `sepay.py` |
| Vốn & quỹ | `/api/von-csh`, `/api/quy`, `/api/quy-dn`, `/api/khoan-vay` | `von_csh.py`, `quy_dn.py`, `khoan_vay.py` |
| Kho & sản phẩm | `/api/product`, `/api/product-category`, `/api/inventory`, `/api/bom` | `inv_products.py`, `product_category.py`, `product_attributes.py`, `inventory.py`, `bom.py` |
| Kế toán tổng hợp | `/api/journal`, `/api/tai-san`, `/api/ky-ke-toan` | `journal.py`, `tai_san.py`, `ky_ke_toan.py` |
| Báo cáo | `/api/bao-cao` | `bao_cao.py`, `bao_cao_pnl.py`, `bao_cao_can_doi.py`, `bao_cao_cashflow.py`, `bao_cao_cpa.py`, `bao_cao_duyet_chi.py` |
| Đọc chéo app khác | `/api/external` | `external.py` (raw SQL fail-soft) |

Phân quyền: **một pattern duy nhất** — `require_ketoan_user` trong
`app/routers/_deps.py` (role ∈ admin/ceo/assistant_ceo/manager/kt), khai một lần thành
`_AUTH = Depends(...)` đầu file (35/44 router). Audit `log_action` gọi ở **tầng router**
(122 chỗ), không ở service.

## Model chính (29 model)

**Dòng tiền & công nợ** — `DoanhThu` · `ChiPhiPhatSinh` · `ChiPhiCoDinh` · `CongNo`
(mã `CN-YYYY-NNNN`, cột `con_lai` là GENERATED = `so_tien - da_tra`) · `SoQuy`
(tự sinh, idempotent) · `SepayTransaction` · `LoaiChiPhi`.

**Tài khoản & vốn** — `TaiKhoanNH` + `TaiKhoanNHGiaoDich` · `SoDuDauKy` · `KhoanVay` ·
`VonCSH` · `QuyDN` + `QuyDNGiaoDich` (cây quỹ + audit trail thu/chi).

**Kho & giá vốn (M1–M2)** — `Product` · `ProductCategory` · `InventoryMovement` ·
`InventoryBalance` · `KiemKe` (bình quân gia quyền) · `BOMMaster` + `BOMItem`.

**Kế toán tổng hợp (Phase 2–6, M5)** — `JournalEntry` + `JournalLine` (bút toán kép:
header + dòng Nợ/Có) · `TaiSanCoDinh` + `KhauHaoLog` · `KyKeToan` (khoá kỳ theo tháng,
PK `'YYYY-MM'`, LN giữ lại luỹ kế) · `AdsPhanBoDon` (phân bổ chi phí ads vào đơn → CPA).

**Snapshot báo cáo** — `BaoCaoSnapshot` · `BaoCaoPLSnapshot`.

Quy ước: tên nghiệp vụ **tiếng Việt không dấu**; tiền luôn `Numeric(15,2)` / `Decimal` —
**cấm `float`**.

## Giao diện & design system

Đây là app có UI được chuẩn hoá **bài bản nhất** trong 7 app — bộ luật UI của nó chính
là bản gốc mà kit chung `papasan-erp-claude` nhân ra cho 6 app còn lại.

- **CSS 3 tầng, thứ tự nạp bắt buộc**: `theme.css` (token màu) → `base.css` (bố cục,
  `--page-max: 1200px`) → `components.css` → `{% block page_css %}`. Sai thứ tự thì mọi
  ghi đè riêng của trang im lặng mất tác dụng.
- ⚠️ **Hệ màu ketoan đã TÁCH khỏi 6 app kia (bản thử 08/08/2026)**: chuyển sang hệ
  **hổ phách & cà phê** rút thẳng từ logo — brand `#9E5D09` (logo là `#FEB041` hổ phách
  + `#603814` nâu cà phê; brand cũ `#D23C0E` không có trong logo). `--warning` cố ý
  trùng brand và `--info` cố ý trung tính nâu, đưa số cụm sắc trên một màn từ **5 xuống 3**.
  Tên token không đổi. Lý do + đường lùi ghi trong `static/css/theme.css`.
- **Phong cách pastel** (chốt 05/08/2026): nút chính = nền `--brand-soft` + chữ
  `--brand-hover`; nền đặc chỉ còn ở nút nguy hiểm. **Không emoji, không icon font,
  không gradient, không font ngoài, không sidebar dọc.**
- **Header dùng chung** `templates/_header.html`: appbar trắng 56px, nav chữ thuần,
  5 dropdown, subnav TRÁI 210px tự clone từ dropdown (ngoại lệ đã duyệt riêng ketoan),
  drawer dưới 1100px.
- **Nguồn chuẩn**: [HE-MAU-ERP.md](HE-MAU-ERP.md) (token + tương phản WCAG AA) ·
  [.claude/rules/design-system.md](.claude/rules/design-system.md) (giới hạn cứng) ·
  [.claude/rules/frontend-ui.md](.claude/rules/frontend-ui.md) (10 luật). Trước khi báo
  xong mọi thay đổi UI: chạy **`/ui-check`**.

**Nợ UI còn lại** (kiểm 08/08/2026):

- ✅ Gradient: **đã sạch** — `grep linear-gradient|radial-gradient templates/*.html` = 0/18 file.
- ❌ Kế thừa layout mới đi được nửa đường: chỉ **2/15 trang** `extends "base.html"`
  (`ho_so_ca_nhan.html`, `kt_duyet.html`); 13 trang còn lại vẫn là khung standalone (12 trang
  tự `include "_header.html"`, `login.html` cố ý không có header). 18 file trong `templates/`
  trừ `base.html` + 2 partial (`_header.html`, `chat_widget.html`) = 15 trang.
  **Trang mới phải extends base.html.**
- ❌ Chưa có hàm format tiền dùng chung: 8 biến thể `fmtVnd`/`fmtMoney`/`fmt` rải rác, và
  đơn vị trộn `₫` với `đ`. Mẫu tốt nhất để chép: `ncc_de_xuat.html:168`.
- ❌ `.tab-nav` trong `products.html` còn màu V1; cỡ chữ lẻ `.5px` còn trong template V1.
- ❌ `templates/index.html` nặng ~536 KB JS inline — chỉ được grep theo tên hàm/id.

## Làm việc với Claude Code

`.claude/` của repo này là **bản gốc** của kit ERP — sửa luật ở đây thì báo để đồng bộ
ngược lên `C:\PapasanIT\App_qlpps\papasan-erp-claude`.

- **Gõ được**: `/ui-check` (QC giao diện 6 nhóm) · `/layout-fix <trang>` (tái cấu trúc
  trang rối) · `/new-screen <tên>` (dựng màn hình mới đúng chuẩn) · `/review-me` ·
  `/explain` · `/commit` · `/learn-log`.
- **Claude tự đọc**: `ui-standards`, `layout-rules`, `erp-architecture`; rules trong
  `.claude/rules/` tự nạp theo thư mục đang sửa.
- **Claude tự gọi agent**: `ui-reviewer` (sau task UI) · `layout-architect` (trước khi
  code dashboard) · `shared-impact` (**trước mọi thay đổi trong `shared/`**) ·
  `code-reviewer` · `mentor` · `test-writer`.
- Repo bật **CHẾ ĐỘ MENTOR**: người dùng đang học FastAPI/SQLAlchemy — Claude giải thích
  khái niệm tại chỗ, trình 2 phương án trước thay đổi lớn, không tự commit.

Chi tiết đầy đủ: [CLAUDE.md](CLAUDE.md).

## Trạng thái & nợ kỹ thuật đã biết

**Schema drift (đang vá tạm).** Hai chỗ model khai mà không migration nào tạo —
`grep -rn ref_sepay alembic/` trả rỗng:

- `app/models/so_quy.py` cột `ref_sepay`
- `app/models/sepay_transaction.py` — cả bảng `sepay_transactions`

Đang vá bằng `ketoan-devrun/dev_patch.sql`, nhờ đó `GET /api/so-quy` trên DB dev hiện tại
**không còn 500** (gọi không token → 401 đúng thiết kế; xác minh 08/08/2026). **Cách đúng là thêm
alembic revision trong repo** rồi bỏ patch. SQLAlchemy sinh SELECT liệt kê **mọi** cột
trong model chứ không `SELECT *` — model có cột mà DB chưa có là 500 ngay.

**Bảo mật — còn nợ thật.** `.env` chứa secret production (`JWT_SECRET_KEY`,
`ANTHROPIC_API_KEY`, `SEPAY_WEBHOOK_SECRET`, `EXTERNAL_READ_API_KEY`, `FCM_SA_JSON_B64`).
File **đã được gỡ khỏi git** ở commit `eaad60a` (`git ls-files` sạch, kiểm 08/08/2026),
nhưng **secret vẫn nằm trong lịch sử tại commit `974981c`** → **phải rotate toàn bộ key**.
`.gitignore` chặn tương lai, không gỡ được quá khứ. Cảnh báo ở `.gitignore:6-7` viết theo
tình trạng cũ, đã lỗi thời một nửa.

**Phụ thuộc devrun.** `baogia` và `muahang` trong `ketoan-devrun` vẫn là **stub** (dù repo
thật đã có tại `C:\PapasanIT\App_qlpps\`). Ba chỗ import ORM cross-app không bọc try/except
→ 500 khi gọi: `app/routers/cong_no.py:136`, `cong_no.py:185`,
`cong_no_from_order.py:47`. Trỏ alias sang repo thật là việc nên làm, chưa làm.

**Nợ kiến trúc.**

- `lifespan` trong `app/main.py` tự chạy vài `ALTER TABLE ... IF NOT EXISTS` ngoài Alembic —
  **nợ kỹ thuật, không phải mẫu**; cột mới luôn dùng revision.
- `app/pages.py` là **code chết** (trùng tên `app/routers/pages.py`, không ai import,
  `_TEMPLATES_DIR` tính sai một cấp) — đừng sửa nhầm.
- **Chưa có `tests/`, `conftest.py`, linter, formatter.**
- `shared/` là bản copy dùng chung 7 app — sửa là lệch khỏi 6 bản kia; luôn gọi agent
  `shared-impact` trước.
- `papasan-frontend-claude/` là kit frontend gốc, đã merge hết vào `.claude/` (bản trong
  `.claude/` mới hơn) — **có thể gỡ**, chờ người dùng quyết.
- Git: nhánh hiện tại `fix/theme-ui-ux`, còn nhiều file chưa commit.
