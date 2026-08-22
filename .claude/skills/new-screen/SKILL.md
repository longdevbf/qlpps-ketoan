---
name: new-screen
description: Tạo màn hình mới đúng chuẩn UI PAPASAN — hỏi ý chính, chọn loại trang, dựng khung đủ 4 trạng thái, đăng ký điều hướng, chạy /ui-check. Dùng khi người dùng gõ /new-screen <tên màn hình>.
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/new-screen/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/new-screen/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /new-screen — tạo màn hình mới đúng chuẩn

Quy trình bắt buộc, làm theo thứ tự. Thiếu thông tin ở bước nào → HỎI, không đoán.

## Bước 1 — Chốt spec (hỏi người dùng nếu thiếu)

1. **Ý chính**: người dùng vào trang này để làm gì nhất? (→ phần tử to nhất trang)
2. **Hành động chính**: nút primary duy nhất là gì?
3. **Nguồn dữ liệu**: API nào? Đã có router hay cần viết mới?
4. **Ai được xem**: role nào — ảnh hưởng mục nav và gate quyền.

## Bước 2 — Chọn loại trang (theo cấu trúc app đang làm — xem "Riêng app này")

- App có SPA/tab trung tâm (index.html): tính năng nghiệp vụ chung dữ liệu →
  thêm page/tab vào SPA + đăng ký loader/tiêu đề theo mẫu sẵn có.
- Luồng độc lập → trang riêng: tạo `templates/<ten>.html` theo khung layout
  của app (extends base.html hoặc include _header.html — nhìn trang mới nhất
  cùng loại làm mẫu, KHÔNG bịa khung mới); route thêm vào router pages
  (auth cookie).

## Bước 3 — Dựng khung theo chuẩn

- Đọc skill `ui-standards` + rule `frontend-ui.md` trước khi viết dòng CSS đầu tiên.
- Tiêu đề trang 1 lần (page-head); tiêu đề thẻ mô tả KHỐI, không lặp tên trang.
- Mọi khối async đủ 4 trạng thái ngay từ commit đầu (mẫu markup trong ui-standards §5).
- Màu/thang chữ: chỉ `var(--token)` + thang design-system. Nút chữ, không icon.
- Label map cho mọi key trạng thái từ API.

## Bước 4 — Đăng ký điều hướng (không có là trang "mồ côi")

- Thêm mục vào header/nav/dropdown phù hợp của app. Gate quyền theo cơ chế
  của app nếu cần.

## Bước 5 — Kiểm chứng

- Chạy `/ui-check` đủ 6 nhóm; chụp screenshot thật.
- Đủ pass mới báo xong, kèm ảnh.
