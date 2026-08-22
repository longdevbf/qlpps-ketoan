---
name: trien-khai
description: Đưa code lên production VPS hoặc kéo code người khác sửa trực tiếp trên VPS về git — dùng khi người dùng nói "deploy", "đẩy lên production", "lên VPS", "kéo code từ VPS về", "sync production", "server đang chạy bản nào", "rollback", hoặc khi cần biết bản trên production khác bản local chỗ nào.
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/trien-khai/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/trien-khai/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Deploy và kéo code — app Kế Toán

Công cụ nằm ở `d:\PapaSanIT\deploy-kit`. **Đọc `deploy-kit/README.md` trước khi
chạy lệnh ghi.**

```bash
cd /d/PapaSanIT/deploy-kit
python vps.py status ketoan      # VPS khác bản local chỗ nào (chỉ đọc)
python vps.py diff ketoan <file> # đọc một file
python vps.py pull ketoan        # kéo về _incoming/, repo chưa bị đụng
python vps.py deploy ketoan      # xem trước
```

## Sự thật phải nói với người dùng, đừng giấu

**Code đang bị sửa TRỰC TIẾP trên VPS.** Git có 32 commit dạng "Sync code mới
nhất từ production VPS". Đo ngày 23/08/2026: **cả 7 app đều đang lệch** — VPS đi
trước git. Hai file `static/css/chat_widget.css` và `static/js/chat_widget.js` có
trên VPS ở cả 7 app mà git không có; `templates/ho_so_ca_nhan.html` khác nội dung
ở cả 7 app.

Nghĩa là **deploy khi đang lệch = xoá mất việc người khác vừa làm trên server**.

## Ba luật cứng

1. **Luôn `status` trước.** Còn lệch thì **kéo về trước, đẩy sau**. `vps.py` tự
   chặn deploy khi lệch; **không được tự thêm `--force`** để đi tiếp — đó là
   quyết định của người dùng, phải hỏi.
2. **Không bao giờ tự chạy `deploy --yes`.** Trình bày danh sách file sẽ đẩy,
   chờ người dùng đồng ý. `deploy` không tham số chỉ xem trước, chạy thoải mái.
3. **Phần kéo từ VPS về luôn đi vào nhánh riêng** `sync/vps-YYYYMMDD`, không
   commit thẳng `main`, và **không tự commit** — người dùng cần đọc `git diff`
   để biết trên server ai đã sửa gì.

## Kiến trúc production — nhớ 2 điều này

- **`docker restart` KHÔNG làm code mới có hiệu lực.** Compose không bind-mount
  code; `/opt/qlpps/Dockerfile` COPY cả thư mục vào image `qlpps:latest`. Phải
  **build lại image**, và đó là việc `qlpps-deploy build <app>` làm.
- **Image dùng CHUNG cho cả 7 app.** Build lại vì một app sẽ nướng code hiện tại
  của **tất cả** `/opt/qlpps` vào image mới. Nói rõ điều này với người dùng mỗi
  lần deploy.

Deploy được: `marketing muahang baogia saleadmin congnghe`.
**Không deploy được bằng tài khoản hiện tại: `hcns`, `ketoan`, `ceo`** — whitelist
ở cấp sudoers trên server, không phải lỗi cấu hình, đừng tìm cách lách.

## Khi người dùng nói "deploy"

1. `python vps.py status ketoan` → đọc kết quả.
2. Lệch → dừng, trình danh sách file, hỏi: kéo về trước hay bỏ phần trên VPS?
3. Khớp → kiểm tra repo sạch và đang ở `main` đã pull mới:
   `git status --porcelain` rỗng, `git rev-parse HEAD` khớp `origin/main`.
4. `python vps.py deploy ketoan` (xem trước) → trình danh sách cho người dùng.
5. Được đồng ý → `python vps.py deploy ketoan --yes`, đọc log tới khi thấy
   health check qua.
6. Hỏng → script tự rollback và tự build lại. Báo nguyên văn log, **không tự
   thử lại**.

## Khi người dùng nói "kéo code từ VPS về"

1. `python vps.py pull ketoan` — tải về `deploy-kit/_incoming/ketoan/`, repo
   chưa bị đụng.
2. Dùng `python vps.py diff ketoan <file>` đọc **từng file**, tóm tắt cho người
   dùng: ai đó đã sửa gì, có vẻ vì lý do gì.
3. Người dùng đồng ý → tạo nhánh `sync/vps-YYYYMMDD` rồi `pull --apply`.
4. **Dừng ở đó.** Không `git commit`, không `git push` khi chưa được bảo.

## Không được làm

- Không `ssh` vào VPS để **sửa file** — làm thế là tạo thêm một hotfix ngoài git,
  đúng cái vòng luẩn quẩn đang cần thoát ra.
- Không chạy migration/`alembic upgrade` trên production bằng công cụ này.
- Không đụng `.env` trên VPS theo bất kỳ chiều nào.
- Không xoá backup trong `~/_qlpps_ops/backup/`.
