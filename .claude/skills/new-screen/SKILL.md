---
name: new-screen
description: Tạo màn hình mới đúng chuẩn UI ketoan — hỏi ý chính, chọn SPA hay trang riêng, dựng khung đủ 4 trạng thái, đăng ký điều hướng, chạy /ui-check. Dùng khi người dùng gõ /new-screen <tên màn hình>.
---

# /new-screen — tạo màn hình mới đúng chuẩn

Quy trình bắt buộc, làm theo thứ tự. Thiếu thông tin ở bước nào → HỎI, không đoán.

## Bước 1 — Chốt spec (hỏi người dùng nếu thiếu)

1. **Ý chính**: người dùng vào trang này để làm gì nhất? (→ phần tử to nhất trang)
2. **Hành động chính**: nút primary duy nhất là gì?
3. **Nguồn dữ liệu**: API nào? Đã có router hay cần viết mới?
4. **Ai được xem**: role nào (gate `_mgr`?) — ảnh hưởng mục nav.

## Bước 2 — Chọn loại trang

- **Trang SPA** (nghiệp vụ kế toán, chung dữ liệu): thêm `<div class="page" id="page-<tên>">`
  vào `templates/index.html` + loader vào map `loaders` + tiêu đề vào map `titles`.
- **Trang riêng** (luồng độc lập): tạo `templates/<ten>.html` `{% extends "base.html" %}`
  — ĐỌC chú thích 3 bẫy Jinja đầu `base.html` trước; route thêm vào
  `app/routers/pages.py` (auth cookie).

## Bước 3 — Dựng khung theo chuẩn

- Đọc skill `ui-standards` + rule `frontend-ui.md` trước khi viết dòng CSS đầu tiên.
- Tiêu đề trang 1 lần (page-head); tiêu đề thẻ mô tả KHỐI, không lặp tên trang.
- Mọi khối async đủ 4 trạng thái ngay từ commit đầu (mẫu markup trong ui-standards §5).
- Màu/thang chữ: chỉ `var(--token)` + thang design-system. Nút chữ, không icon.
- Label map cho mọi key trạng thái từ API.

## Bước 4 — Đăng ký điều hướng (không có là trang "mồ côi")

- Thêm mục vào dropdown phù hợp trong `templates/_header.html` (subnav trái tự
  clone theo). SPA: `data-page` + `href="/app#<tên>"`; trang riêng: href thường.
- Gate quyền bằng `{% if _mgr %}` nếu cần.

## Bước 5 — Kiểm chứng

- Chạy `/ui-check` đủ 6 nhóm; chụp screenshot thật (script Playwright scratchpad).
- Đủ pass mới báo xong, kèm ảnh.

## Riêng app này — địa chỉ chính xác của từng thao tác (verify 08/08/2026)

**A. Thêm một trang SPA (mặc định cho nghiệp vụ kế toán).** SPA hiện có **23
trang** (`grep -o 'id="page-[a-z-]*"' templates/index.html` → 23 id, trừ
`page-title`). Phải sửa đủ **4 chỗ**, thiếu chỗ nào là trang câm:

1. `templates/index.html` — thêm `<div class="page" id="page-<ten>">…</div>`.
2. `index.html:3209` map `titles` — thêm `'<ten>':'Tiêu đề hiển thị'` (22 mục).
3. `index.html:3226` map `loaders` — thêm `'<ten>': loadX` (23 mục; hàm chưa
   chắc tồn tại thì bọc `(typeof loadX === 'function') ? loadX : null`).
4. `index.html:3249` map `reloaders` — CHỈ khi trang phụ thuộc bộ chọn tháng
   (`onMonthChange()`); bỏ qua thì đổi tháng trang sẽ không tự nạp lại.

`showPage()` ([index.html:3189](../../templates/index.html#L3189)) tự bỏ
`.active` khỏi mọi `.page`, tự tô mục nav theo `data-page`, và **deep-link
`/app#<ten>` chạy được** — `_header.html:501,505` đọc `location.hash` + lắng
`hashchange`. Tên trang sai thì `showPage` return im lặng, không nổ.

**B. Thêm một trang riêng.** Bắt buộc `{% extends "base.html" %}` — hiện chỉ
`ho_so_ca_nhan.html` và `kt_duyet.html` làm đúng, 13 trang còn lại là khung
standalone cũ, **đừng chép chúng**. Route thêm vào `app/routers/pages.py`
(mẫu gần nhất: `/duyet-ncc` dòng 246, auth bằng cookie `access_token` +
`user_ctx(user)`), rồi tạo template. Nhớ `{% set page_title %}` /
`{% set page_sub %}` ở **cấp cao nhất** file con, không đặt trong block.

**C. Đăng ký điều hướng + gate quyền.** Chỉ sửa `templates/_header.html`; subnav
trái `.ab-subnav` tự clone theo (`abBuildSubnav()` dòng 511), không sửa tay.
Gate dùng `_mgr` — app này **không có `nav_perms`** như marketing:

```jinja
{% if _mgr %}<a class="ab-item" href="/duyet-ncc">Duyệt ĐX Trả NCC</a>{% endif %}
```

`_mgr` khai ở `_header.html:27` từ `user._is_mgr` (`shared.templates.user_ctx()`).
**Gate nav chỉ là ẩn/hiện — route vẫn phải tự chặn** bằng `require_ketoan_user`
trong `app/routers/_deps.py`.

**D. Bẫy đã có người dẫm.** Route `/khuyen-mai` tồn tại
(`pages.py:258`) nhưng `templates/khuyen_mai.html` **không có** → 500 khi mở.
Đó là ví dụ sống của "đăng ký một nửa"; đừng lặp lại.
