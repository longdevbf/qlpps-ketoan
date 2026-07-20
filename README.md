# Kế Toán V2 (FastAPI + Postgres)

Port từ V1 `App_Web/ketoan/` (Flask + JSON local + Sheets sync) sang FastAPI + Postgres schema `ketoan`.

## Stack
- FastAPI 0.115 + SQLAlchemy 2 + Pydantic v2 + Alembic
- Postgres 16 schema `ketoan` (cùng DB với schema `shared`/`baogia`/`marketing`/`muahang`/`hcns`)
- Jinja2 templates (port nguyên từ V1)
- JWT SSO qua `shared.auth` (issued bởi auth_service:8000)
- Cross-schema READ-ONLY: `hcns.payroll`, `muahang.purchase_orders`, `marketing.ads_cost`

## Folder
```
ketoan/
├── app/
│   ├── main.py                        # FastAPI app, mount /static, include 10 routers
│   ├── models/                        # 7 SQLAlchemy 2 models
│   │   ├── doanh_thu.py
│   │   ├── chi_phi_phat_sinh.py
│   │   ├── chi_phi_co_dinh.py
│   │   ├── cong_no.py                 # con_lai = GENERATED column
│   │   ├── so_quy.py
│   │   ├── loai_chi_phi.py
│   │   └── tai_khoan_nh.py
│   ├── schemas/                       # 9 Pydantic v2 schema files (CRUD + bao_cao)
│   ├── routers/                       # 10 routers
│   │   ├── _deps.py                   # require_ketoan_user (admin/ceo/manager only)
│   │   ├── doanh_thu.py
│   │   ├── chi_phi.py
│   │   ├── co_dinh.py
│   │   ├── cong_no.py                 # CRUD + POST /{id}/tra
│   │   ├── so_quy.py
│   │   ├── loai_chi_phi.py
│   │   ├── tai_khoan_nh.py
│   │   ├── bao_cao.py                 # P&L + grouped aggregates
│   │   ├── external.py                # cross-schema reads (raw SQL fail-soft)
│   │   └── pages.py                   # / /app /login /logout
│   └── services/
│       ├── id_gen.py                  # CN-YYYY-NNNN cho cong_no
│       ├── pl_calculator.py           # SQL aggregate doanh thu / chi phí / công nợ
│       └── external_reader.py         # raw SQL read 3 schema khác
├── alembic/
│   ├── env.py                         # filter schema=ketoan
│   ├── script.py.mako
│   └── versions/0001_baseline_ketoan.py
├── templates/                         # 2 file Jinja2 (copy từ V1)
│   ├── login.html
│   └── index.html
├── static/                            # rỗng (V1 không có file CSS/JS riêng — inline trong template)
├── requirements.txt
├── .env.example
└── README.md
```

## 8 modules (port theo V1)
1. **Doanh Thu** — `doanh_thu` table + CRUD `/api/doanh-thu`
2. **Chi Phí Phát Sinh** — `chi_phi_phat_sinh` + `/api/chi-phi`
3. **Chi Phí Cố Định** — `chi_phi_co_dinh` + `/api/co-dinh`
4. **Công Nợ** — `cong_no` + `/api/cong-no` (auto id `CN-YYYY-NNNN`, `con_lai` GENERATED)
5. **Sổ Quỹ** — `so_quy` + `/api/so-quy`
6. **Danh mục: Loại Chi Phí** — `loai_chi_phi` + `/api/loai-chi-phi`
7. **Danh mục: Tài Khoản NH/Tiền Mặt** — `tai_khoan_nh` + `/api/tai-khoan`
8. **Báo Cáo Tổng Hợp (P&L)** — `bao_cao.py` aggregate + cross-app reads

## Quick start (dev)

```bash
# 1. Bring up infra
cd ../   # App_V2/
docker compose up -d

# 2. Migrate baseline shared trước
alembic --name shared upgrade head

# 3. Migrate ketoan
alembic --name ketoan upgrade head

# 4. Cài deps + chạy
cd ketoan
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8005
```

## Endpoints chính

### HTML pages
| Path | Template |
|---|---|
| `/` | redirect /login hoặc /app |
| `/app` | index.html (main SPA) |
| `/login` | login.html |
| `/logout` | xoá cookie + redirect /login |

### API (Bearer JWT, app=ketoan, role ∈ {admin,ceo,manager})

| Method | Path | Mô tả |
|---|---|---|
| GET/POST/PUT/DELETE | `/api/doanh-thu[/{id}]` | CRUD doanh thu |
| GET/POST/PUT/DELETE | `/api/chi-phi[/{id}]` | CRUD chi phí phát sinh |
| GET/POST/PUT/DELETE | `/api/co-dinh[/{id}]` | CRUD chi phí cố định |
| GET/POST/PUT/DELETE | `/api/cong-no[/{id}]` | CRUD công nợ |
| POST | `/api/cong-no/{id}/tra` | đánh dấu trả công nợ |
| GET/POST/PUT/DELETE | `/api/so-quy[/{id}]` | CRUD sổ quỹ |
| GET/POST/PUT/DELETE | `/api/loai-chi-phi[/{id}]` | danh mục loại CP |
| GET/POST/PUT/DELETE | `/api/tai-khoan[/{id}]` | danh mục TK NH |
| GET | `/api/bao-cao/tong-hop?tu_ngay=&den_ngay=` | P&L (gồm cross-app) |
| GET | `/api/bao-cao/doanh-thu?by=ngay\|thang` | group doanh thu |
| GET | `/api/bao-cao/chi-phi` | group chi phí by loại |
| GET | `/api/bao-cao/cong-no` | tổng phải thu / phải trả |
| GET | `/api/external/luong?thang=YYYY-MM` | đọc `hcns.payroll` |
| GET | `/api/external/don-hang` | đọc `muahang.purchase_orders` |
| GET | `/api/external/ads` | đọc `marketing.ads_cost` |
| GET | `/health` | healthcheck |

## Role matrix
| Role | View | Edit |
|---|---|---|
| `admin` / `ceo` | ✓ | ✓ |
| `manager` (kế toán) | ✓ | ✓ |
| `kd` / `mkt` / `mh` | ✗ (403) | ✗ |

## Business logic giữ lại (port từ V1)
- **P&L calculator** (`services/pl_calculator.py`): tổng hợp doanh thu - CP phát sinh - CP cố định = lợi nhuận gộp; gồm cả lương HCNS, ads MKT, đơn hàng MH
- **Auto-import công nợ** từ V1 (`/api/cong-no/import`) — KHÔNG port Sprint 1, sẽ làm Sprint 2 (cron job)
- **Cong-no `con_lai` GENERATED** — tự động (so_tien - da_tra), V1 tính tay
- **Chuẩn hoá enum**:
  - `cong_no.loai`: `phai_thu` / `phai_tra` (V1 'Công Nợ Khách Hàng' / 'Công Nợ NCC')
  - `cong_no.trang_thai`: `chua_tra` / `da_tra` (V1 'Còn Nợ' / 'Đã Thanh Toán')
  - `so_quy.loai`: `thu` / `chi` (V1 'Thu' / 'Chi')

## Bỏ khi port (theo constraint)
- Toàn bộ Google Sheets sync (`KT_*` sheets, `sheet_capacity.py`)
- `gspread`, `google.auth`, `googleapiclient`
- OAuth2 token + service account (sẽ dùng SSO thay)
- Login từ `LOGIN_SHEET_ID` (chuyển qua auth_service)

## Pending Sprint 2
1. **Hoá đơn URL Drive upload** (`hoa_don_url`) — cần `shared.utils.drive`
2. **Excel export báo cáo** (`/api/bao-cao/export.xlsx`) — `openpyxl`
3. **Auto-import công nợ** từ `muahang.purchase_orders` + `baogia.quotes` (cron + dedup `ref_id`)
4. **Số dư đầu kỳ** (V1 `so_du_dau_ky.json` + `/api/so-quy/summary`) — bảng `so_du_dau_ky` + endpoint summary
5. **Push báo cáo tháng** (V1 `KT_BaoCaoThang`) — chuyển thành snapshot table `bao_cao_thang`
6. **HCNS payroll schema confirm** — V1 đọc sheet, V2 cần confirm `hcns.payroll` columns
7. **Nhân sự / KPI / cơ chế** — V1 đọc HCNS sheet, V2 sẽ đọc qua HCNS V2 endpoints
8. **Cross-schema FK enforce** — Sprint 2 sau khi 6 app stable

## Verify
```bash
cd App_V2 && python3 -m py_compile \
  ketoan/app/main.py ketoan/app/models/*.py \
  ketoan/app/routers/*.py ketoan/app/services/*.py \
  ketoan/app/schemas/*.py \
  ketoan/alembic/env.py ketoan/alembic/versions/0001_baseline_ketoan.py
```
