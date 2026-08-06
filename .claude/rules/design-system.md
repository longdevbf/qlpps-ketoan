---
paths:
  - "templates/**/*.html"
  - "static/css/**/*.css"
  - "shared/templates/**/*.html"
  - "shared/static/**/*.css"
---

# Design system — GIỚI HẠN CỨNG

Rule này tồn tại để chặn một việc: **tự ý mở rộng hệ thiết kế**. Giao diện hỏng
không phải vì một lần chọn sai màu, mà vì mỗi lần sửa lại thêm một màu, một mức
viền, một cỡ chữ "cho vừa chỗ này". Repo từng có 13 sắc thương hiệu trộn với 12
sắc xám lạnh — đó là lý do nó trông bẩn.

Thao tác nằm ngoài các giới hạn dưới đây **không được tự làm**. Phải đề xuất và
chờ người dùng đồng ý.

> Hệ này **kế thừa nguyên từ `qlpps-marketing`** — 4 app QLPPS dùng chung một hệ.
> Nguồn sự thật gốc: `C:/PapasanIT/qlpps-marketing/.claude/rules/design-system.md`.
> Sửa token ở đây mà không sửa 3 app kia = bắt đầu trôi khỏi nhau.

## Giới hạn cứng — 7 điều

1. **Đúng 7 màu nền tảng + 4 màu trạng thái.** Không thêm màu thứ 8.
2. **Đúng 1 màu thương hiệu.** Không có primary/secondary.
3. **Đúng 1 mức viền.** Không thêm viền đậm/nhạt thứ hai.
4. **Đúng 2 mức nền, 3 mức chữ.** Không thêm mức trung gian.
5. **Không hard-code hex** trong template hay CSS mới. Dùng `var(--token)`.
6. **Không đổi màu trạng thái** theo thương hiệu.
7. **Không thêm font ngoài, không CSS framework, không build step.**

## Bảng token — nguồn: `static/css/theme.css`

| Nhóm | Token | Giá trị | Dùng cho |
|---|---|---|---|
| Thương hiệu | `--brand` | `#D23C0E` | nút chính, tiêu đề, tab chọn, icon, avatar |
| | `--brand-hover` | `#BF370D` | hover/active |
| | `--brand-soft` | `#FDEEE8` | nền nhạt: hàng chọn, chip, tab |
| Nền | `--bg-card` | `#FFFFFF` | thẻ, bảng, modal |
| | `--bg-page` | `#FBF8F5` | nền trang, sọc bảng, vùng lõm |
| Viền | `--border` | `#DFD2C6` | **mức duy nhất** |
| | `--focus-ring` | `0 0 0 3px rgba(210,60,14,.25)` | nhận biết focus |
| Chữ | `--text-1` | `#2A2521` | tiêu đề, số liệu (13.61:1) |
| | `--text-2` | `#54483F` | nội dung (7.94:1) |
| | `--text-3` | `#736659` | chú thích, nhãn (5.26:1) |
| | `--text-on-brand` | `#FFFFFF` | chữ trên nền brand |
| Trạng thái | `--danger` / `-soft` / `-fg` | `#DC2626` `#FEE2E2` `#991B1B` | xoá, lỗi |
| | `--success` / `-soft` / `-fg` | `#16A34A` `#DCFCE7` `#15803D` | thành công |
| | `--warning` / `-soft` / `-fg` | `#F59E0B` `#FEF3C7` `#92400E` | cảnh báo |
| | `--info` / `-soft` / `-fg` | `#2563EB` `#DBEAFE` `#1D4ED8` | thông tin |
| Bên thứ ba | `--facebook` `--messenger` `--zalo` | `#0084FF` `#1877F2` `#0068FF` | **không đổi** |
| Bóng | `--shadow-sm/md/lg` | ám nâu `rgba(90,48,16,…)` | không dùng đen thuần |

**Ba lý do đằng sau, đừng "tối ưu" lại:**

- **`#D23C0E` chứ không phải `#F05424` của logo.** Logo với chữ trắng chỉ đạt
  3.41:1 → trượt WCAG AA. `#D23C0E` giữ nguyên hue 14°, sat 87%, đạt 4.78:1.
- **Xám ám NÂU, không ám xanh.** Xám lạnh (`#64748b`, `#94a3b8`) trên nền kem
  ấm là nguyên nhân chính khiến màn hình trông đục.
- **Viền cố ý nhạt.** App nhiều bảng, viền đậm gây rối. Nhận biết focus dựa
  vào `--focus-ring` màu cam, **không** dựa vào viền.

**Ngoại lệ được hard-code — bảng màu biểu đồ.** Các chuỗi dữ liệu trên cùng một
biểu đồ phải phân biệt được với nhau, nên không gom về `--brand` được. Trong app
này ngoại lệ nằm ở **12 dòng** của `templates/index.html` — các object dạng
`{label:…, value:…, color:'#…'}` (dòng ~7637-7650 và ~8176-8181):

```js
{label:'Tiền & TGNH', value:tien.total, color:'#1a3a6e'},
{label:'Phải thu KH', value:ptKh.total, color:'#e67e22'},
```

Cách phân biệt khi sửa: **hex nằm trọn trong nháy trên dòng có `label:`** = màu
chuỗi dữ liệu, giữ nguyên. Mọi hex khác — kể cả trong chuỗi JS như
`this.style.background='#e2e8f0'` — là CSS và **phải** dùng `var(--token)`
(`element.style.background = 'var(--border)'` hợp lệ, `var()` cũng chạy trong
thuộc tính SVG `fill=` / `stroke=`).

Thẻ `<meta name="theme-color">` không nhận `var()` → dùng hex thật `#D23C0E`.

## Trạng thái áp dụng — 01/08/2026

**Toàn bộ 16 template đã chuyển sang hệ này** và đạt cả 2 lệnh tự kiểm
(`index.html` còn đúng 12 dòng màu biểu đồ — ngoại lệ hợp lệ, xem trên).
Khoảng **1 340 mã màu V1** đã đổi sang token theo bảng đối chiếu cuối
`static/css/theme.css`.

Gặp mã V1 ở đâu đó (`#1a3c5e` navy, `#64748b`/`#94a3b8` xám lạnh, `#f8fafc`)
thì **đó là code chưa cập nhật — đừng chép sang chỗ khác**, tra bảng đối chiếu
rồi đổi. Mẫu tốt nhất để nhìn theo: `templates/_header.html`.

### ⚠️ Nợ CÒN LẠI — chưa xử lý

**1. Gradient: 44 chỗ ở 10 file.** Design system cấm tuyệt đối gradient, nhưng
**2 lệnh tự kiểm bên dưới KHÔNG phát hiện được** (chúng chỉ soát hex và cỡ chữ).
Đếm bằng:

```bash
grep -c 'linear-gradient\|radial-gradient' templates/*.html | grep -v ':0'
```

Nhiều gradient nay là `linear-gradient(135deg,var(--brand-soft),#fff)` — tức
đã dùng token nhưng vẫn là gradient. Thay bằng một màu đặc khi có dịp sửa file đó.

⚠️ `templates/index.html` nặng ~560 KB — sửa phải grep theo tên hàm/id,
đừng đọc cả file.

## Không dùng icon — chỉ dùng chữ

Giao diện **không có emoji, không có icon font**. Lý do: hàng trăm emoji rải
trong bảng biểu làm app nội bộ trông thiếu nghiêm túc, và icon font kéo theo
một CDN ngoài — đúng thứ giới hạn số 7 cấm.

- **Không thêm emoji** vào nhãn nút, tiêu đề, ô trống, badge. Nút diễn đạt bằng
  chữ: `Xoá`, `Sửa`, `Tải lên`, `Đổi ảnh`.
- **Không dùng Bootstrap Icons / Font Awesome / bất kỳ icon font nào.** Link CDN
  `bootstrap-icons` đã gỡ khỏi cả 7 file từng dùng.
- **Ký tự chữ chức năng thì được**: `▾` (menu xổ), `☰`/`&#9776;` (menu mobile),
  `×`/`✕` (đóng), `→` (mũi tên trong câu), `•` (dấu phân cách). Đây là ký tự
  typographic, không phải hình vẽ — thang đo còn ghi rõ `22px` dành cho chúng.

Kiểm bằng:

```bash
grep -c 'class="bi \|bootstrap-icons\|font-awesome' templates/*.html | grep -v ':0'
```

## Độ đậm chữ — theo cấp, không tuỳ hứng

| Cấp | Weight | Dùng cho |
|---|---|---|
| Thường | `500` | nội dung, nhãn, ô nhập, mục menu |
| Nhấn | `600` – `700` | tiêu đề cột, mục đang chọn, số liệu, nút |
| Tiêu đề | `800` | tiêu đề thẻ/trang, avatar |
| Logo | `900` | **chỉ** `.ab-logo-txt`, `.brand`, `.logo` |

**Không dùng `400` hay `normal`** — mức thường của hệ là `500`. Kiểm bằng:

```bash
grep -ohE 'font-weight:\s*[0-9a-z]+' templates/*.html | sort | uniq -c | sort -rn
```

## Điều hướng — toàn bộ nằm ở header, không có sidebar

`index.html` **đã bỏ hẳn sidebar dọc**; cả 33 chức năng chuyển lên `_header.html`:
5 menu thả xuống (Tổng Quan · Thu — Chi · Quản Lý · Liên Phòng Ban · Danh Mục)
cho 23 trang SPA, phần còn lại nằm trong menu user.

Cơ chế: mỗi mục mang `data-page="<tên>"` và `href="/app#<tên>"`.
`showPage()` đã bỏ phụ thuộc `event.currentTarget` (bản cũ ném lỗi khi gọi từ
deep-link) và đánh dấu mục đang chọn bằng `data-page`. `_header.html` lắng
`hashchange` + chạy `abSpaSync()` sau `setTimeout 0` — phải chờ init của SPA
xong vì header nằm đầu `<body>` nên listener của nó chạy trước.

**Thêm trang SPA mới thì phải thêm mục vào `_header.html`**, nếu không sẽ không
có đường nào tới nó nữa.

## Thang đo — chọn trong danh sách, không nội suy

App nội bộ nhiều dữ liệu nên thang **đặc**, không thoáng.

| | Giá trị được dùng (đo từ `templates/_header.html` ngày 01/08/2026) |
|---|---|
| Cỡ chữ | `8-9px` nhãn siêu nhỏ + mũi tên · `10px` nhãn nhóm · `11-12px` meta/tên user · `13px` nav + item menu + nội dung · `14-16px` tiêu đề + avatar lớn · `22px` icon glyph (☰, ✕) |
| Độ đậm | `500` thường · `600-700` nhấn · `800-900` logo/tiêu đề |
| Bo góc | `6px` nav · `8-9px` nút · `12px` menu/thẻ · `50%` avatar |
| Đệm | `7px 12px` nav · `9px 15px` item menu · `14-16px` trong thẻ |
| Hiệu ứng | `.12s`–`.25s`. Không animation trang trí |
| Font | `'Segoe UI', sans-serif` — **không tải font ngoài** |

Cần cỡ chữ không có trong bảng → dùng cỡ gần nhất. Không thêm `17px`, `20px`,
và **không dùng cỡ lẻ `.5px`** (`10.5`, `12.5`, `15.5`… đang có đầy trong các
template V1 — đó là vi phạm, không phải tiền lệ).
`8-9px` và `22px` chỉ dành cho nhãn siêu nhỏ và icon glyph, **không dùng cho
chữ người đọc**.

## Header — cấu trúc bắt buộc

Nguồn: `templates/_header.html`. Mọi class mang tiền tố **`ab-`** để không dính
CSS riêng của trang. Thêm class mới cũng phải `ab-`.

```
[logo | kẻ dọc]  [nav chữ thuần …]              [kẻ dọc | chuông  avatar+tên ▾]
└─ cố định 56px, nền TRẮNG, viền dưới 1px, bóng rất nhẹ, body{padding-top:56px}
```

- **Nền header TRẮNG**, không nhuộm màu thương hiệu.
- **Nav là CHỮ THUẦN** — không nền, không viền, không khối. Trạng thái phân
  biệt **chỉ bằng màu + độ đậm**:
  `thường` = `--text-2`/500 · `hover` = `--brand` · `active` = `--brand-hover`/700.
- **Không tô nền cho mục nav đang chọn.**
- Khối phải: `margin-left:auto`, ngăn bằng kẻ dọc. Avatar tròn 30px nền brand
  chữ trắng; tên 12px/700, vai trò 10px/500.
- **Header giống hệt nhau ở mọi trang.** Không thêm tiêu đề trang, nút quay
  lại, hay logo phụ vào header — đặt trong phần nội dung bên dưới.

**Gate quyền của app này**: app kế toán **không có `nav_perms`** như marketing.
Dùng `user._is_mgr` (từ `shared.templates.user_ctx()`, role ∈
manager/admin/ceo/assistant_ceo/kt). Ví dụ thật trong `_header.html`:

```jinja
{% set _mgr = (user._is_mgr if (user and user._is_mgr is defined) else False) %}
{% if _mgr %}<a class="ab-item" href="/duyet-ncc">Duyệt ĐX Trả NCC</a>{% endif %}
```

**Nav chỉ trỏ tới URL có thật.** Các mục nghiệp vụ trong SPA (`/app`) điều hướng
bằng `showPage()` — hàm đó dùng `event.currentTarget` và **không đọc
`location.hash`** ([index.html:3261](../../templates/index.html#L3261)), nên
không deep-link được từ ngoài vào. Vì vậy toàn bộ SPA gom về một mục → `/app`.

## Subnav — chỉ 2 dạng được phép

**Dạng 1 — menu thả xuống** (khi mục có nhóm con, xem `_header.html` khối `.ab-dd`):

- `.ab-menu`: nền trắng, viền 1px, bo `12px`, `min-width:238px`,
  bóng `0 10px 32px`.
- Nhóm bằng `.ab-mtitle` (10px, 700, `--text-3`, IN HOA, letter-spacing .8px) và
  `.ab-div` (kẻ 1px).
- **Bắt buộc có "cầu nối" trong suốt** phủ khoảng hở giữa nút và menu
  (`::after{top:100%;height:8px}`). Thiếu nó thì chuột đi xuống là menu tự đóng.

**Dạng 2 — tab trong thân trang** (khi các mục ngang hàng, cùng một trang):
tab chữ thuần, mục đang chọn dùng `--brand` + gạch chân 2px `--brand`, nền
`--brand-soft` chỉ khi cần khối. Không dùng nút bo tròn kiểu pill có nền.
Ví dụ trong app này: `.tab-nav` ở `templates/products.html` (6 tab) — **đang
dùng màu V1, cần đưa về hệ**.

Không phát minh dạng thứ 3 (breadcrumb, sidebar dọc, tab dạng thẻ…) mà chưa hỏi.
Sidebar 32 mục ở `index.html` là **ngoại lệ cũ chưa xử lý**, không phải mẫu.

## Điểm gãy — lấy từ đo đạc, không lấy từ tên thiết bị

`@media(max-width:1100px)` chuyển sang drawer. Con số này **đo được**: nav cần
~620px, cộng logo và khối phải thì dưới 1100px nav bắt đầu đè lên chuông (đo:
1050px đè 37px). Đổi điểm gãy thì phải đo lại và ghi số đo vào comment.

Drawer: rộng 280px/`max-width:82vw`, trượt từ trái, backdrop
`rgba(15,38,64,.42)`. Trong drawer nav **có** nền và viền (khác nav trên
desktop) vì không còn thanh ngang làm mốc.

## Tuyệt đối không

- Gradient · glassmorphism · bóng có màu · viền đậm.
- Tô nền cho mục nav đang chọn.
- Thêm màu, mức viền, cỡ chữ, kiểu subnav ngoài danh sách trên.
- Nhuộm nút xoá theo màu thương hiệu — người dùng sẽ bấm nhầm.
- Đổi màu Facebook/Messenger/Zalo — đó là nhận diện của họ.
- Khai lại `esc`, `escHtml`, `initials` trong template — đã có toàn cục qua
  `/static/js/ui-common.js`, nạp sẵn trong `_header.html`.
- Sửa `C:/PapasanIT/qlpps-marketing` để "cho khớp" — hệ đi một chiều từ đó sang.

## Tự kiểm trước khi báo xong

```bash
# 1. Có màu nào ngoài hệ lọt vào không?  (đã chạy thử 01/08/2026: _header.html
#    ra RỖNG = sạch. dao_tao 51 / products 32 / xin_nghi 42 dòng = nợ V1.)
grep -nE '#[0-9a-fA-F]{3,6}' templates/<file>.html | grep -v '&#' | grep -viE \
 'D23C0E|BF370D|FDEEE8|FFFFFF|#fff|FBF8F5|DFD2C6|2A2521|54483F|736659|DC2626|FEE2E2|991B1B|16A34A|DCFCE7|15803D|F59E0B|FEF3C7|92400E|2563EB|DBEAFE|1D4ED8|0084FF|1877F2|0068FF|e67e22'

# 2. Cỡ chữ có nằm ngoài thang không?
grep -oE 'font-size:[0-9]+px' templates/<file>.html | sort -u
```

> `grep -v '&#'` là bắt buộc — thiếu nó thì thực thể HTML như `&#9776;` (icon ☰)
> bị báo nhầm thành mã màu.
>
> Lệnh 2 dùng `[0-9]+` nên **không bắt được cỡ lẻ** `12.5px`. Muốn soát cả cỡ
> lẻ thì đổi thành `[0-9.]+` — các template V1 của app này có đầy `.5px`.

Ra kết quả ngoài danh sách → **sửa lại cho vào hệ, hoặc hỏi người dùng**. Không
tự nới giới hạn rồi báo là xong.
