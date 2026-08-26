---
paths:
  - "templates/**/*.html"
  - "shared/templates/**/*.html"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/templates.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/templates.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Sửa template Jinja2

**Đừng `Read` cả file.** Template lớn nhất của app này: `templates/index.html` (10.986 dòng — SPA một file) và `templates/chat_widget.html` (7.843 dòng).
Dùng `Grep` để định vị rồi
`Read` kèm `offset`/`limit`.

## Trước khi sửa, xác định đúng file

`xin_nghi.html` tồn tại ở **cả hai** nơi: `templates/` và `shared/templates/`.
`shared/templates/` + `shared/static/` là tầng UI thứ hai, chưa migrate theme
(vẫn còn `#0084ff`, `#1a3c5e`). Kiểm tra route render file nào trước khi sửa:

```bash
grep -n '_render(request, "' app/routers/pages.py
```

## Sửa màu

Hầu hết template **không** gọi `var(--brand)` trực tiếp. Chúng khai một khối
alias riêng ở đầu `<style>` với hex chép cứng vào. Gặp ở đâu là dọn ở đó,
tuyệt đối không chép lại — hai bảng dưới đều là **hệ đã bị thay**:

```css
/* ✗ CŨ — hệ cam đỏ. KHÔNG dùng lại. */
--bg:#FBF8F5; --line:#DFD2C6; --text:#2A2521; --muted:#736659;
--primary:#D23C0E; --primary-d:#BF370D; --navy:#D23C0E;

/* ✗ CŨ — hệ hổ phách 11/08/2026. Cũng KHÔNG dùng lại. */
--bg:#FDF8F0; --line:#E7D7BE; --text:#33210F; --muted:#795E43;
--primary:#9E5D09; --primary-d:#7F4B07; --soft:#FBE7C6;
```

Còn khối alias này thì đổi `theme.css` vô tác dụng — "cái bẫy lớn nhất khi nhân
bản" nói ở mục 1 của `HE-MAU-ERP.md`.

Thay bằng token, không khai alias mới:

```css
/* ✓ ĐÚNG — hệ CAM trên slate lạnh, chốt 26/08/2026 */
background: var(--bg-page);  border: 1px solid var(--border);
color: var(--text-2);
/* nhấn: NỀN khối đặc var(--brand) + chữ #fff · CHỮ cam var(--brand-ink) */
```

Nên retheme một trang thường là sửa ~10 dòng alias đó thành `var(--token)`,
**không phải** sửa hàng trăm call site `var(--primary)` bên dưới. Kiểm tra
trước:

```bash
grep -nE '^\s*--[a-z-]+\s*:' templates/<file>.html | head -20
```

Token chuẩn nằm ở `static/css/theme.css`. Không thêm màu mới — dùng lại token
có sẵn.

## Chỗ dùng chung

- `_header.html` là partial của 25/28 template. Muốn thêm CSS/JS cho toàn app
  thì thêm ở đây, đừng chép vào từng file.
- `esc`, `escHtml`, `initials` đã có sẵn toàn cục từ `static/js/ui-common.js`.
  **Đừng khai lại** trong template. Helper nào ≥2 trang dùng thì đưa vào đó.
- `esc()` escape đủ 5 ký tự `& < > " '` — an toàn cả trong ngữ cảnh thuộc tính.

## Bẫy hay gặp

**Tên field lệch với API.** Đây là lỗi số một ở tầng này — cột hiện trống hoặc
form trả 422 im lặng. Xem `CLAUDE.md` § Known failure patterns; soi bằng
subagent `fe-be-field-drift`.

**Thẻ HTML bọc trong hàm escape.** `aplEsc(a + '<br>' + b)` in ra chữ `<br>`.
Thẻ phải nằm **ngoài** hàm escape.

**Destroy chart trong chính event handler của nó.** Gọi hàm vẽ lại (nó
`chart.destroy()`) ngay trong `onClick` của Chart.js làm Chart.js chạy tiếp
`afterEvent` trên chart đã chết → `TypeError: ... 'handleEvent'`. Hoãn bằng
`setTimeout(..., 0)`.

**`chartjs-plugin-datalabels` đăng ký global.** Nạp nó là mọi chart trên trang
đều có nhãn. Chỉ một chart cần nhãn thì viết plugin cục bộ đặt trong
`plugins: [...]` của riêng chart đó.

## Kiểm chứng

Sửa xong phải xem bằng ảnh thật, không suy đoán từ code: dùng `/soi-giao-dien`
Bắt cả `pageerror` (exception JS chưa bắt) chứ không
chỉ `console.error` — hai loại này khác nhau.

## Bảo mật khi render

Jinja2 tự escape HTML mặc định. Thấy cần dùng `|safe` hoặc `innerHTML` với dữ
liệu do người dùng nhập → **dừng lại và cảnh báo về XSS**, đề xuất `textContent`
hoặc escape thủ công.

- Mọi request ghi từ frontend phải đi kèm **CSRF token** — xem `static/js/csrf.js`.
- **Không hard-code dữ liệu nhạy cảm** (token, URL nội bộ, số điện thoại thật)
  vào template hay JS — chúng public với trình duyệt.
- `static/vendor/` là thư viện bên thứ ba — **không sửa tay**.
- **Không refactor / tách file template lớn** trừ khi được yêu cầu rõ ràng.
  Đây là việc lớn, phải trình 2 phương án trước.
