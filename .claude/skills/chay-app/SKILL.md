---
name: chay-app
description: Chạy / dừng / gỡ lỗi app Kế Toán (qlpps-ketoan) trên máy này — dùng khi được yêu cầu "chạy app", "start app", "mở app lên xem", "bật DB", "seed lại dữ liệu", "đăng nhập thử", khi cần verify một sửa đổi trên app thật thay vì chỉ đọc code, hoặc khi gặp "app không lên", "cổng bận", "container không bật được", "cứ nhảy về /login", "không kết nối được Auth".
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/chay-app/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/chay-app/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Chạy app Kế Toán trên máy này

Toàn bộ môi trường nằm ở `d:\PapaSanIT` (ngoài repo). Tài liệu đầy đủ:
`README-DEV.md`.

## 1. Bật

```bash
cd /d/PapaSanIT
docker compose up -d db redis pgadmin      # hạ tầng
docker compose --profile app up -d         # auth stub (8010) + 7 app (8001-8007)
docker compose ps                          # kiểm tra: db phải "(healthy)"
```

App này chạy ở **http://localhost:8005** · `/health` không cần đăng nhập:

```bash
curl http://localhost:8005/health       # {"status":"ok","service":"ketoan",...}
```

## 2. Đăng nhập

**Mật khẩu chung `123456`.** Vào mọi app: `admin` · `ceo` · `troly` · `quanly`.

Tài khoản theo phòng ban (dùng để **thử phân quyền**): `mkt1` `ads1` `media1`
`cskh1` `letan1` (Marketing) · `kd1` `kd2` (Kinh doanh) · `kt1` (Kế toán) ·
`mh1` (Mua hàng) · `sa1` (Sale Admin) · `ns1` (Nhân sự). Bảng đầy đủ kèm cột
"vào được app nào" ở `README-DEV.md`.

Đăng nhập bằng dòng lệnh để kiểm tra nhanh:

```bash
curl -s -i -c /tmp/ck -X POST http://localhost:8005/login \
  -d "username=admin&password=123456" | grep -i "^location"
# `location: /` = vào được. `location: /login?error=...` = bị chặn, đọc lý do.
curl -s -b /tmp/ck http://localhost:8005/ | head -c 300
```

Bị chặn với thông báo "không có quyền truy cập app" là **đúng**, không phải lỗi
— tài khoản đó không có tên app trong cột `apps`.

## 3. Sửa code rồi xem kết quả

Code được **bind-mount**, không copy vào image:

```bash
docker compose restart ketoan             # nạp lại sau khi sửa .py
docker compose logs -f ketoan             # xem log / traceback
docker compose logs --tail 50 ketoan
```

Sửa template Jinja2 hoặc file trong `static/` thì **không cần restart** — chỉ
tải lại trang.

## 4. Dữ liệu

```bash
docker compose run --rm seeder python -m seed.main report   # thống kê, không đổi gì
docker compose exec -T db psql -U qlpps -d qlpps_dev \
  -c "SELECT count(*) FROM ketoan.<ten_bang>;"
```

**Ba lệnh sau GHI ĐÈ dữ liệu — chỉ chạy khi người dùng yêu cầu rõ:**

```bash
docker compose run --rm seeder                                   # migrate + bơm lại tất cả
docker compose run --rm seeder python -m seed.main accounts      # chỉ tạo lại tài khoản
docker compose run --rm seeder python -m seed.main reset --yes   # XOÁ SẠCH 7 schema
```

⚠️ Dữ liệu là **ảo**: đúng cấu trúc, **không đúng nghiệp vụ**. Đừng suy luận
nghiệp vụ hay nghiệm thu công thức tính toán từ số liệu trong đó.

## 5. Bốn lỗi hay gặp

**`Cannot connect to the Docker daemon`** — Docker Desktop chưa bật. Nói người
dùng bật, không có cách bật bằng lệnh cho chắc chắn.

**Vào trang nào cũng nhảy về `/login`** — cookie không được chấp nhận. Xem
`location` của response `/login`:
- `Không kết nối được Auth` → container stub chưa lên. `docker compose ps auth`
  · `curl http://localhost:8010/health` · `docker compose restart auth`.
  **6/7 app bắt buộc có stub mới đăng nhập được** — chỉ `marketing` có đường dự
  phòng nội bộ `_local_login()` trong `app/routers/pages.py`.
- `Sai username hoặc password` → sai thật, hoặc `active = false` trong
  `shared.users`. Tạo lại: `docker compose run --rm seeder python -m seed.main accounts`
- `không có quyền truy cập app` → đúng như thiết kế, tài khoản đó không có tên
  app trong cột `apps`. Dùng `admin`.

**`address already in use`** — máy này đã có Postgres khác ở 5432 và 5434, nên
compose của QLPPS cố ý dùng **5435 / 6380 / 5051 / 8001-8007 / 8010**. Xem ai
đang giữ cổng: `docker ps --format '{{.Names}}\t{{.Ports}}'`. **Đừng tự
`docker stop` container của dự án khác — hỏi trước.**

**App không lên, log có `ModuleNotFoundError`** — thiếu package anh em. App này
import package khác ở module level; kiểm tra phần `volumes` của service trong
`docker-compose.yml` có mount đủ 7 repo theo đúng **tên package** không
(`./qlpps-baogia` → `/srv/apps/baogia`).

## 6. Dừng

```bash
docker compose --profile app down    # tắt 7 app, GIỮ dữ liệu
docker compose down                  # tắt hết, GIỮ dữ liệu (volume còn)
docker compose down -v               # ⚠️ XOÁ CẢ DỮ LIỆU — chỉ khi được yêu cầu rõ
```
