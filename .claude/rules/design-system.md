---
paths:
  - "templates/**/*.html"
  - "static/css/**/*.css"
  - "shared/templates/**/*.html"
  - "shared/static/**/*.css"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/design-system.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/design-system.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Design system — GIỚI HẠN CỨNG

Rule này tồn tại để chặn một việc: **tự ý mở rộng hệ thiết kế**. Giao diện hỏng
không phải vì một lần chọn sai màu, mà vì mỗi lần sửa lại thêm một màu, một mức
viền, một cỡ chữ "cho vừa chỗ này". Repo từng có 13 sắc thương hiệu trộn với 12
sắc xám lạnh — đó là lý do nó trông bẩn.

Thao tác nằm ngoài các giới hạn dưới đây **không được tự làm**. Phải đề xuất và
chờ người dùng đồng ý.

> Hệ này **kế thừa nguyên từ `qlpps-marketing`** — 4 app QLPPS dùng chung một hệ.
> Nguồn sự thật gốc: tài liệu `HE-MAU-ERP.md` (bản chuẩn 06/08/2026, phát hành từ
> app Marketing — không commit vào repo này, xin bản mới nhất từ Marketing).
> Sửa token ở đây mà không sửa 3 app kia = bắt đầu trôi khỏi nhau.

## Quyết định pastel (chốt 05/08/2026, áp vào ketoan 06/08/2026)

> **26/08/2026 — công thức pastel đã BỊ BỎ.** Đoạn dưới là lịch sử, không còn
> hiệu lực. Nay nhấn là **khối đặc `--brand` + chữ trắng**, bề mặt giữ trung
> tính. Token `--brand-soft` / `--brand-hover` không còn tồn tại.

Mọi nút/khối từng là **cam đặc + chữ trắng** đã chuyển sang **nền `--brand-soft`
+ chữ `--brand-hover`** (4.57:1 ✔ AA) — kể cả nút hành động chính, tab đang chọn,
avatar, header bảng. Nền **đặc** chỉ còn ở: nút xoá/đăng xuất/từ chối
(`--danger`), icon nhỏ + dải neo mỏng (chấm màu, thanh tiến trình, `::before`),
và chuỗi màu biểu đồ. Hover **không thêm hex mới** — dùng `filter:brightness(.95)`.

## Giới hạn cứng — 7 điều

1. **Đúng 7 màu nền tảng + 4 màu trạng thái.** Không thêm màu thứ 8.
2. **Đúng 1 màu thương hiệu.** Không có primary/secondary.
3. **Đúng 1 mức viền.** Không thêm viền đậm/nhạt thứ hai.
4. **Đúng 2 mức nền, 3 mức chữ.** Không thêm mức trung gian.
5. **Không hard-code hex** trong template hay CSS mới. Dùng `var(--token)`.
6. **Không đổi màu trạng thái** theo thương hiệu.
7. **Không thêm font ngoài, không CSS framework, không build step.**

## Bảng token — nguồn: `static/css/theme.css`

> ⚠️ **BẢN THỬ RIÊNG CỦA KETOAN — áp 08/08/2026.** Bảng dưới đây đã đổi sang
> hệ **hổ phách & cà phê** rút từ logo. 6 app QLPPS kia vẫn ở bảng cũ
> (`--brand:#D23C0E`, `--warning:#F59E0B`, `--info:#2563EB`). Đường lùi đầy đủ
> ghi ở cuối `static/css/theme.css`. **Tên token không đổi một chữ nào** —
> chỉ đổi giá trị, nên không template nào phải sửa.

| Nhóm | Token | Giá trị | Dùng cho |
|---|---|---|---|
| Thương hiệu | `--brand` | `#CC4E05` | **NỀN** khối đặc: nút chính, tab chọn, avatar. Chữ trắng trên nó 4,51:1 |
| | `--brand-ink` | `#B85105` | **CHỮ + icon** nhỏ — đạt AA trên cả 3 bề mặt |
| | `--brand-bright` | `#EA580C` | **SỐ KPI ≥24px đậm** (3,56:1) |
| | `--brand-graph` | `#F2610E` | **THANH biểu đồ** (3,09:1) |
| Nền | `--bg-card` | `#FFFFFF` | thẻ, bảng, modal |
| | `--bg-app` | `#F1F5F9` | **chỉ cho `body`** |
| | `--bg-page` | `#F8FAFC` | mặt lõm trong thẻ |
| Viền | `--border` | `#E2E8F0` | viền chuẩn |
| | `--border-soft` | `#EDF1F6` | kẻ ngang trong bảng |
| Chữ | `--text-1` | `#0F172A` | số, tiêu đề (17,85:1) |
| | `--text-2` | `#334155` | nội dung (10,35:1) |
| | `--text-3` | `#5F6E80` | nhãn + chú thích (5,21:1) |
| | `--text-on-brand` | `#FFFFFF` | chữ trên nền `--brand` |
| Số liệu | `--kpi-neutral` `--kpi-brand` `--kpi-good` `--kpi-data` | `#0F172A` `#EA580C` `#15803D` `#1D4ED8` | tô số KPI theo loại |
| Trạng thái | `--danger` / `-soft` | `#B91C1C` `#FEE2E2` | xoá, lỗi |
| | `--success` / `-soft` | `#15803D` `#DCFCE7` | thành công |
| | `--warning` / `-soft` | `#B45309` `#FEF3C7` | cảnh báo — **tách khỏi brand** |
| | `--info` / `-soft` | `#475569` `#E9EEF4` | thông tin |
| Bên thứ ba | `--facebook` `--messenger` `--zalo` | `#0084FF` `#1877F2` `#0068FF` | **không đổi** |
| Bóng | `--shadow-sm/md/lg` | ám nâu `rgba(96,56,20,…)` | không dùng đen thuần |

**Bốn lý do đằng sau, đừng "tối ưu" lại:**

- **Màu rút từ LOGO, không phải chọn cho đẹp.** Đếm pixel
  `static/papasan_icon_1024.png` ra đúng hai màu: `#FEB041` hổ phách (13.7%)
  và `#603814` nâu cà phê (10.2%). Brand cũ `#D23C0E` **không có trong logo**
  và lệch 21° hue khỏi nó. `#FEB041` nguyên bản chỉ đạt 1.9:1 trên nền trắng
  nên không làm chữ được. (Hệ hổ phách `#9E5D09` là bản **cũ**, đã bị thay
  26/08/2026 bằng cam `#CC4E05` — xem bảng token trên.)
- **`--warning` cố ý DÙNG LẠI brand.** Hổ phách vốn đã nghĩa là "chú ý tôi";
  thêm một sắc vàng thứ hai là thừa. Bớt được một cụm sắc, và sửa luôn một
  lỗi thật: nền `--warning` cũ `#F59E0B` với chữ trắng chỉ **2.15:1** (badge
  đếm việc trong `index.html` đang vi phạm), nay là 5.22:1.
- **`--info` cố ý TRUNG TÍNH.** "Đang chờ người khác" thì nên lùi lại, không
  nên hét lên. Bỏ được xanh dương lạnh vốn đâm vào nền kem ấm. Tổng cụm sắc
  cạnh tranh trên một màn: **5 → 3** (hổ phách = cần bạn xử lý · lục = xong ·
  đỏ = hỏng).
- **Viền cố ý nhạt.** App nhiều bảng, viền đậm gây rối. Nhận biết focus dựa
  vào `--focus-ring`, **không** dựa vào viền.

**Ngoại lệ được hard-code — bảng màu biểu đồ.** Các chuỗi dữ liệu trên cùng một
biểu đồ phải phân biệt được với nhau, nên không gom về `--brand` được. Trong app
này ngoại lệ nằm ở **12 dòng** của `templates/index.html` — các object dạng
`{label:…, value:…, color:'#…'}` (dòng ~7637-7650 và ~8176-8181):

```js
{label:'Tiền & TGNH', value:tien.total, color:'#CC4E05'},
{label:'Phải thu KH', value:ptKh.total, color:'#1F6F72'},
```

**Bộ màu biểu đồ đã làm lại 08/08/2026** cho khớp hệ hổ phách & cà phê. Đây là
BA biểu đồ tròn riêng (4 · 5 · 6 lát), màu được phép lặp giữa các biểu đồ — chỉ
cần phân biệt trong cùng một biểu đồ:

| Màu | Dùng cho | Tương phản/trắng |
|---|---|---|
| `#603814` nâu cà phê (logo) | TSCĐ · Giá vốn | 10.13 |
| `#2F2A24` than nâu | Vay & nợ · Thuế TNDN | 14.21 |
| `#6B4E7D` mận | Lương | 6.97 |
| `#B02A18` đỏ gạch | Phải trả NCC | 6.58 |
| `#1F6F72` mòng két | Phải thu KH · Định phí | 5.87 |
| `#CC4E05` cam thương hiệu | Tiền & TGNH · Biến phí | 4.51 |
| `#4A9B6B` lục | Vốn chủ sở hữu | 3.39 |
| `#B0873C` cát | Tồn kho · Phải trả VC · Bán hàng | 3.29 |

**Phân biệt bằng ĐỘ SÁNG, không chỉ bằng sắc** — mù màu đỏ-lục làm trộn sắc
nhưng giữ nguyên độ sáng, nên thang tương phản trải từ 3.3 đến 14.2 là kênh
phân biệt chính. Mọi màu đều ≥3:1 (WCAG 1.4.11 cho đối tượng đồ hoạ).
Ngoại lệ đã chấp nhận: cặp hổ phách/cát cách nhau ΔE 20 (dưới mốc 24) — chấp
nhận được vì legend đã ghi đủ nhãn + % + số tiền cho từng lát, màu chỉ là kênh
phụ, và giữ hai sắc hổ phách là thứ neo biểu đồ vào logo.

Cách phân biệt khi sửa: **hex nằm trọn trong nháy trên dòng có `label:`** = màu
chuỗi dữ liệu, giữ nguyên. Mọi hex khác — kể cả trong chuỗi JS như
`this.style.background='#e2e8f0'` — là CSS và **phải** dùng `var(--token)`
(`element.style.background = 'var(--border)'` hợp lệ, `var()` cũng chạy trong
thuộc tính SVG `fill=` / `stroke=`).

Thẻ `<meta name="theme-color">` không nhận `var()` → dùng hex thật `#CC4E05`
(hổ phách, khớp `--brand`). Đổi brand thì phải sửa tay cả `manifest` nếu app có PWA.

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

Nhiều gradient nay là `linear-gradient(135deg,var(--brand-soft),#fff)` — token
này đã bị bỏ, gặp thì thay bằng nền phẳng `var(--bg-page)`. Tức
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
- **Bổ sung 08/08/2026 — người dùng đã chốt: `✓` `✗` `○` `◀` `▶` ĐƯỢC GIỮ.**
  Chúng đang làm việc thật (badge trạng thái "✓ Đã nộp" / "✗ Từ chối", nút phân
  trang "◀ Trước" / "Sau ▶") và chính ketoan cũng đang dùng 89 chỗ. Yêu cầu duy
  nhất: **cỡ chữ đủ lớn để đọc rõ** — dùng `17px` khi đứng trong câu, `22px` khi
  đứng một mình làm glyph. **Đừng quét xoá chúng như emoji** — đợt trước suýt gỡ
  hết, sẽ làm badge trạng thái mất tín hiệu thị giác.

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

## Điều hướng — SIDEBAR DỌC bên trái (đổi 08/08/2026)

> Luật cũ ghi "toàn bộ nằm ở header, không có sidebar" và liệt "sidebar dọc"
> vào mục cấm. **Người dùng đã quyết định đổi 08/08/2026.** Lý do: 35 đích đến
> nhét trong 5 dropdown thì phải mở ra mới thấy — sidebar hiện thường trực nên
> đặt được **số việc chờ duyệt ngay trên mục**, biến điều hướng thành hàng đợi
> công việc. Với app kế toán mà việc chính là duyệt, đó là lý do quyết định.

**Cấu trúc** (`_header.html`, khối `.ab-sb`):

- Rail cố định trái **196px**, thu gọn được xuống **52px** chỉ còn icon.
  Trạng thái thu gọn + nhóm nào đang xổ lưu trong `localStorage`
  (`ab_sb_min`, `ab_sb_mo`) nên đổi trang không mất.
- `body{padding-left:var(--sb-w)}` — mọi trang include `_header.html` tự hưởng,
  **không phải sửa từng trang**.
- 8 nhóm xổ được + 1 mục phẳng: Tổng quan · Thu—Chi · Công nợ · Kho & giá vốn ·
  Vốn & tài sản · Báo cáo · Liên phòng ban · Cá nhân · Danh mục.
- **Icon CHỈ ở hàng nhóm**, hàng con thụt lề bằng vạch dẫn — tiết kiệm ~26px
  mỗi dòng, giữ rail hẹp. Icon là **SVG inline** (mục "Không dùng icon" bên
  dưới vẫn cấm emoji + icon font; SVG inline được phép, không kéo CDN nào).
- **Badge số chờ duyệt** trên mục lá (`#ab-sb-bd-<key>`), nhóm cha cộng dồn.
  Khi rail thu gọn, badge biến thành chấm 7px trên góc icon. Fail-soft: API
  hỏng thì badge ở nguyên trạng thái ẩn, không chặn điều hướng.
- **Dưới 1100px sidebar ẩn**, drawer nhận việc — `abBuildDrawer()` chiếu thẳng
  cây `.ab-sb` (bản cũ đọc `.appbar .ab-nav`, nav đó đã gỡ).

**Header nay gồm** (chốt 08/08/2026): logo · **tiêu đề trang** (`#page-title`) ·
**kỳ kế toán** (`#month-picker`) · chuông · avatar. Trên mobile thêm nút drawer.

- Thanh `.topbar` cũ của `index.html` (dải ngang thứ hai ngay dưới appbar,
  chứa tiêu đề + chọn tháng) **đã gỡ hẳn** — nó là một tầng thừa.
- Hai phần tử giữ **NGUYÊN id** khi dời lên header, nên không dòng JS nào
  trong SPA phải sửa: `showPage()` vẫn ghi `#page-title`, `onMonthChange()`
  vẫn bắt `#month-picker`.
- **Kỳ kế toán chỉ render trên `/app`** (`{% if _path.startswith('/app') %}`)
  vì `onMonthChange` do `index.html` định nghĩa; trang riêng không có hàm đó.
  Handler vẫn bọc `typeof … === 'function'` cho chắc.
- Trang riêng không có `showPage()` → `abInit()` lấy tiêu đề từ `document.title`
  (cắt trước dấu `—`).
- Dưới 768px ẩn tiêu đề trang và nhãn "KỲ" để nhường chỗ cho ô chọn + avatar.

**Bẫy đã gặp khi làm**: `.ab-sb-g.open .ab-sb-sub` có 3 class nên THẮNG
`body.sb-min .ab-sb-sub` (2 class + 1 thẻ) — nhóm đang mở vẫn lòi vạch dẫn ra
ngoài rail 52px. Rule ẩn phải viết đủ đặc hiệu:
`body.sb-min .ab-sb-g.open .ab-sb-sub{display:none}`.

**Thêm trang mới thì phải thêm mục vào `.ab-sb` trong `_header.html`**, nếu
không sẽ không có đường nào tới nó nữa. Cơ chế deep-link giữ nguyên: mỗi mục
SPA mang `data-page="<tên>"` + `href="/app#<tên>"`; `abSbSync()` lắng
`hashchange` để đánh dấu mục đang mở và tự xổ nhóm chứa nó.

## Thang đo — chọn trong danh sách, không nội suy

App nội bộ nhiều dữ liệu nên thang **đặc**, không thoáng.

| | Giá trị được dùng (đo từ `templates/_header.html` ngày 01/08/2026) |
|---|---|
| Cỡ chữ | `9-10px` nhãn siêu nhỏ + mũi tên · `11px` nhãn nhóm · `12-13px` meta/tên user · **`14px` nội dung chuẩn** + nav + item menu · `15-17px` tiêu đề + avatar lớn · `22px` icon glyph (☰, ✕) · `18-20px` số KPI tầng 2 · `25-29px` số KPI tầng 1 |
| Độ đậm | `500` thường · `600-700` nhấn · `800-900` logo/tiêu đề |
| Bo góc | `6px` nav · `8-9px` nút · `12px` menu/thẻ · `50%` avatar |
| Đệm | `7px 12px` nav · `9px 15px` item menu · `14-16px` trong thẻ |
| Hiệu ứng | `.12s`–`.25s`. Không animation trang trí |
| Font | `'Segoe UI', sans-serif` — **không tải font ngoài** |

Cần cỡ chữ không có trong bảng → dùng cỡ gần nhất.
**Không dùng cỡ lẻ `.5px`** (`10.5`, `12.5`… đó là vi phạm, không phải tiền lệ).
`9-10px` và `22px` chỉ dành cho nhãn siêu nhỏ và icon glyph, **không dùng cho
chữ người đọc**.

**Thang đã NÂNG +1px toàn dải — chốt 08/08/2026** theo yêu cầu người dùng
("cho chữ lớn hơn cho dễ nhìn"). 1 387 khai báo `font-size` đã đổi:
`8→9 · 9→10 · 10→11 · 11→12 · 12→13 · 13→14 · 14→15 · 15→16 · 16→17`.
Glyph `22px` và KPI `25/29px` giữ nguyên. **Nội dung chuẩn nay là `14px`,
không còn là `13px`** — mọi chỗ tài liệu cũ nói "13px là chuẩn nội dung"
đã lỗi thời. `17px` trước đây bị cấm, nay là cỡ tiêu đề lớn hợp lệ.

**Trên mobile KHÔNG được thu nhỏ chữ.** Bản cũ hạ bảng xuống 12px và `th`
xuống 10px ở breakpoint 768/480 — màn nhỏ là lúc cần chữ TO hơn. Bảng nhiều
cột xử lý bằng cuộn ngang + cột đầu dính, không bằng cách bóp chữ. Chỉ
`padding` được co.

**Cỡ KPI — chốt 08/08/2026.** Thang cũ dừng ở `22px`, nhưng dashboard
(`index.html` `.stats-row.tier-1`) đã dùng `29px` từ lâu và skill `ui-standards`
cũng ghi `29/25/18-20`. Hai tài liệu mâu thuẫn với rule này; nay hợp nhất theo
thực tế đang chạy:

| Vai trò | Cỡ | Ví dụ thật |
|---|---|---|
| KPI tầng 1 — số quyết định của trang | `29px` (`25px` khi `max-height:820px`) | `.stats-row.tier-1 .value` |
| KPI tầng 2 — chỉ số vận hành, dải card mỏng | `18-20px` (ketoan đang dùng `16px`, hợp lệ vì nằm trong thang) | `#s-don`, `#s-ads` |

`25/29px` và `18-20px` **chỉ dành cho SỐ LIỆU KPI** — không dùng cho tiêu đề,
nhãn, hay bất kỳ chữ người đọc nào. Cỡ `18/20px` gặp ở `chat_widget.html` và
`giao_viec.html` hiện **không** phải KPI → vẫn là vi phạm, phải hạ về thang.

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
  `thường` = `--text-2`/500 · `hover` = `--brand-ink` · `active` = `--brand-ink`/700.
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
nền `--brand` đặc chỉ khi cần khối. Không dùng nút bo tròn kiểu pill có nền.
Ví dụ trong app này: `.tab-nav` ở `templates/products.html` (6 tab) — **đang
dùng màu V1, cần đưa về hệ**.

Không phát minh dạng thứ 3 (breadcrumb, tab dạng thẻ…) mà chưa hỏi.
*Sidebar dọc đã được duyệt 08/08/2026 và nay là điều hướng CHÍNH — xem mục
"Điều hướng" ở trên.*

**Rail trái `.ab-subnav` (clone dropdown, duyệt 06/08/2026) ĐÃ BỊ THAY**
08/08/2026 bằng **sidebar dọc `.ab-sb`** làm điều hướng chính — xem mục
"Điều hướng" ở đầu file. `abBuildSubnav()` và CSS `.ab-subnav` đã gỡ hẳn.

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
- Sửa `C:/PapasanIT/App_qlpps/qlpps-marketing` để "cho khớp" — hệ đi một chiều từ đó sang.

## Tự kiểm trước khi báo xong

```bash
# 1. Có màu nào ngoài hệ lọt vào không?  (đã chạy thử 01/08/2026: _header.html
#    ra RỖNG = sạch. dao_tao 51 / products 32 / xin_nghi 42 dòng = nợ V1.)
grep -nE '#[0-9a-fA-F]{3,6}' templates/<file>.html | grep -v '&#' | grep -viE \
 'CC4E05|B85105|EA580C|F2610E|FFFFFF|#fff|F1F5F9|F8FAFC|E2E8F0|EDF1F6|0F172A|334155|5F6E80|15803D|DCFCE7|B45309|FEF3C7|B91C1C|FEE2E2|475569|E9EEF4|1D4ED8|0084FF|1877F2|0068FF|e67e22'

# 2. Xám ẤM lọt vào hệ lạnh — phải rỗng
grep -niE '#(605D58|795E43|E0D3C2|EBE2D6|FAF5EF|33210F|5E452C|9E5D09|7F4B07|FBE7C6|EFE2CB|FDF8F0|E7D7BE|D23C0E|FBE5D0)' templates/<file>.html

# 3. Token đã bỏ — phải rỗng
grep -n 'brand-soft\|brand-hover' templates/<file>.html

# 4. Cam dùng sai vai — kiểm từng dòng bằng mắt
#    CC4E05 chỉ được làm NỀN khối đặc · FF8D28 không được xuất hiện
grep -niE 'CC4E05|FF8D28' templates/<file>.html

# 5. Cỡ chữ có nằm ngoài thang không?
grep -oE 'font-size:[0-9]+px' templates/<file>.html | sort -u
```

> `grep -v '&#'` là bắt buộc — thiếu nó thì thực thể HTML như `&#9776;` (icon ☰)
> bị báo nhầm thành mã màu.
>
> Lệnh 2 dùng `[0-9]+` nên **không bắt được cỡ lẻ** `12.5px`. Muốn soát cả cỡ
> lẻ thì đổi thành `[0-9.]+` — các template V1 của app này có đầy `.5px`.

Ra kết quả ngoài danh sách → **sửa lại cho vào hệ, hoặc hỏi người dùng**. Không
tự nới giới hạn rồi báo là xong.

## Riêng app này

Bản này **là bản GỐC** mà bộ kit chung `papasan-erp-claude` nhân ra cho 6 app kia
— sửa ở đây thì báo để đồng bộ ngược lên kit. Số liệu dưới đây **đếm lại bằng
lệnh ngày 08/08/2026**, không chép từ tài liệu cũ.

- **Layout kế thừa — hiện mới nửa đường.** `templates/base.html` (5 KB) là khung
  chuẩn duy nhất, nhưng chỉ **2/15 trang** thật sự `{% extends "base.html" %}`:
  `ho_so_ca_nhan.html`, `kt_duyet.html`. **13 trang còn lại vẫn standalone** —
  tự viết `<html>`; 12 trong số đó `{% include "_header.html" %}` (`index.html`,
  `products.html`, `xin_nghi.html`, `duyet_chi.html`, `giao_viec.html`,
  `lich_lam_viec.html`, `cham_cong.html`, `phe_duyet.html`, `dao_tao.html`,
  `de_nghi_tt.html`, `ncc_de_xuat.html`, `bao_cao_duyet_chi.html`), riêng
  `login.html` cố ý không có header (chưa đăng nhập thì không có nav).
  (`ls templates/*.html` = 18 file, trừ 3 file không phải trang: `base.html`
  khung, `_header.html` partial, `chat_widget.html` partial do `index.html`
  include → 15 trang.) **Trang MỚI luôn extends base.html**;
  đừng chép khung standalone của trang cũ — đó là nợ, không phải mẫu.
- **Thứ tự CSS trong `base.html` là bắt buộc**: `theme.css` → `base.css` →
  `components.css` → `{% block page_css %}`. `{% set ASSET_V = '2' %}` là cách
  phá cache thủ công (repo không có build step) — sửa CSS thì tăng số này.
- **Nợ gradient ĐÃ TRẢ XONG.** `grep -c 'linear-gradient\|radial-gradient'
  templates/*.html` ngày 08/08/2026 = **0 ở cả 18 file** (mục "Nợ CÒN LẠI" bên
  trên nói 44 chỗ/10 file — đã lỗi thời, giữ lại làm lịch sử). Trong
  `static/css/` chỉ còn 1 lần xuất hiện chữ "gradient" ở **comment**
  `base.css:86`, không phải khai báo màu.
- **Nợ V1 CÒN THẬT**: `.tab-nav` của `products.html` vẫn dùng màu V1; cỡ chữ lẻ
  `.5px` còn rải trong các template V1 (lệnh tự kiểm số 2 dùng `[0-9]+` nên
  không bắt được — đổi thành `[0-9.]+` khi soát); `index.html` nay **548 KB**
  (không phải 560/564 KB) với JS inline — chỉ được grep theo tên hàm/id.
- **`showPage()` NAY đã deep-link được** — bản hiện tại tra `document.getElementById`
  và `data-page`, không còn `event.currentTarget`
  ([index.html:3189](../../templates/index.html#L3189), comment ngay trong hàm nói rõ).
  Hai chỗ tài liệu nói ngược (mục "Nav chỉ trỏ tới URL có thật" ở trên và comment
  đầu `templates/_header.html` dòng 18-21) là **chú thích cũ chưa xoá** —
  `_header.html:501,505` đang lắng `hashchange` + đọc `location.hash` thật.
- **Ngoại lệ đã duyệt, giữ nguyên**: (1) **sidebar dọc `.ab-sb`** 196px là
  điều hướng chính (duyệt 08/08/2026, thay rail clone `.ab-subnav` cũ — lệch
  có chủ đích so với 6 app kia); (2) **15 dòng màu chuỗi biểu đồ** hard-code
  trong `index.html`; (3) `<meta name="theme-color">` dùng hex thật `#CC4E05`
  vì thuộc tính này không nhận `var()`; (4) **SVG inline** cho icon sidebar.

## Tóm tắt đợt chuẩn hoá UI 08/08/2026

Đọc **`BAN-GIAO-UI.md`** ở gốc repo trước bất kỳ việc UI nào. Tóm tắt:

- Hệ màu: từ 26/08/2026 cả 8 app **dùng chung** hệ CAM trên slate lạnh
  (`--brand:#CC4E05`) — nguồn `qlpps-marketing/docs/HE-MAU-ERP.md`.
  Ghi chú "ketoan có bảng màu riêng" của đợt 08/08 **không còn đúng**: đợt đó
  tách ra để thử hệ hổ phách `#9E5D09`, hệ đó nay đã bị thay.
- Điều hướng ở **sidebar dọc** `.ab-sb` (196px, thu gọn 52px), không còn 5
  dropdown trên header.
- **Thang chữ +1px toàn dải**, nội dung chuẩn `14px`. **Mobile không được thu
  nhỏ chữ.** Nền trang là **trắng**; `--bg-page` chỉ dùng cho bề mặt lõm.
- Hàm dùng chung ở `static/js/ui-common.js`: `fmtVnd` `fmtShort` `fmtSo`
  `fmtDate` `fmtDateTime` `toast` `khoiLoi` `loiNguoiDoc` `esc` `initials` —
  **cấm khai lại trong template**.
- Nợ lớn nhất: **31 chỗ đổ `e.message` thô ra màn hình** — sửa bằng
  `khoiLoi(e, 'tenHamTaiLai')`.
