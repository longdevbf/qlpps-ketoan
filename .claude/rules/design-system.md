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

> Hệ màu **dùng chung cho cả 8 app QLPPS**: **TRẮNG + XANH `#2563EB`** — quyết
> định của anh Quang 11/09/2026 (ADR-012, ưu tiên cao nhất). Không có màu nhấn
> riêng theo module (cơ chế `body[data-module]` của bản thảo: hoãn vô thời hạn).
> Nguồn giá trị: `static/css/theme.css` — file SINH từ
> `claude-kit/core/static/css/theme.css` qua `sync.py`; lý do + số đo:
> `QLPPS-UI-DOC/01-ADR.md` (ADR-012).
> Tài liệu `HE-MAU-ERP.md` của marketing **đã lỗi thời** — đừng tra. Sửa
> `theme.css` lẻ ở repo này = trôi khỏi 7 app kia.

## Quyết định pastel (chốt 05/08/2026, áp vào ketoan 06/08/2026)

> **26/08/2026 — công thức pastel đã BỊ BỎ.** Đoạn dưới là lịch sử, không còn
> hiệu lực. **Từ 11/09/2026 (ADR-012):** nút chính = **khối đặc `--brand` + chữ
> trắng** (5,17); bề mặt **TRẮNG + XANH NHẠT, xanh đậm là mực** — mục/hàng đang
> chọn, chip: nền `--brand-soft` + chữ `--brand-hover` (5,95). Hai token
> `--brand-soft` / `--brand-hover` **VẪN TỒN TẠI và đang dùng** — câu cũ "không
> còn tồn tại" là sai, đừng dọn chúng.

Mọi nút/khối từng là **cam đặc + chữ trắng** đã chuyển sang **nền `--brand-soft`
+ chữ `--brand-hover`** (4.57:1 ✔ AA) — kể cả nút hành động chính, tab đang chọn,
avatar, header bảng. Nền **đặc** chỉ còn ở: nút xoá/đăng xuất/từ chối
(`--danger`), icon nhỏ + dải neo mỏng (chấm màu, thanh tiến trình, `::before`),
và chuỗi màu biểu đồ. Hover **không thêm hex mới** — dùng `filter:brightness(.95)`.

## Giới hạn cứng — 7 điều

1. **Đúng 7 màu nền tảng + 4 màu trạng thái.** Không thêm màu thứ 8.
   *Ngoại lệ đã duyệt:* bảng `--tile-*` chỉ để làm nền ô icon (ADR-011, `icon-net-trang.md`).
2. **Đúng 1 màu thương hiệu.** Không có primary/secondary.
3. **Viền: đúng 3 token, mỗi cái một vai** — `--border` (viền chuẩn),
   `--border-soft` (kẻ ngang dòng bảng), `--brand-border` (CHỈ viền khối
   `--brand-soft`, thêm 11/09/2026 — ADR-012). Không thêm mức viền thứ tư.
4. **Nền: đúng 3 vai trò + 1 dải, 3 mức chữ** — `--bg-card` (thẻ; riêng ketoan
   còn là nền `body`) · `--bg-app` (nền `body` của 7 app kia) · `--bg-page` (mặt
   lõm) + dải nhấn `--bg-band` (khớp bảng dưới và `theme.css` mục 2). Không thêm
   mức trung gian.
5. **Không hard-code hex** trong template hay CSS mới. Dùng `var(--token)`.
6. **Không đổi màu trạng thái** theo thương hiệu.
7. **Không thêm font ngoài, không CSS framework, không build step.**

## Bảng token — nguồn: `static/css/theme.css`

> **Từ 11/09/2026 ketoan KHÔNG còn bảng màu riêng** — cả 8 app cùng hệ XANH
> (ADR-012). Bảng dưới chép giá trị từ `theme.css`; hai nơi lệch nhau thì
> `theme.css` đúng. **Tên token không đổi một chữ nào** — chỉ đổi giá trị, nên
> không template nào phải sửa. Bảng đối chiếu các hệ đã bị thay nằm ở cuối
> `static/css/theme.css`. Tỉ lệ là WCAG 2.1; viết tắt: thẻ = `#FFFFFF` · nền =
> `--bg-app` · lõm = `--bg-page` · soft = `--brand-soft` · dải = `--bg-band`.

| Nhóm | Token | Giá trị | Dùng cho |
|---|---|---|---|
| Thương hiệu | `--brand` | `#2563EB` | chữ nhấn, icon, viền nhấn; **NỀN** khối đặc nút chính (chữ trắng 5,17). 5,17 thẻ · 4,66 nền · 4,81 lõm · 4,59 soft · **4,31 dải ✗** |
| | `--brand-hover` | `#1D4ED8` | hover; **chữ** đặt trên `--brand-soft` (5,95) và trên `--bg-band` (5,59) |
| | `--brand-active` | `#1E40AF` | lúc bấm giữ `:active` — chữ trắng 8,72 |
| | `--brand-soft` | `#EAF2FE` | **NỀN** nhấn: mục/hàng đang chọn, chip. **Sàn độ đậm** — không được tối hơn |
| | `--brand-border` | `#BFDBFE` | viền 1px của khối `--brand-soft` |
| | `--brand-bright` | `#3B82F6` | **CHỈ** số KPI ≥24px đậm, icon lớn (3,68 thẻ · 3,32 nền); nền ô icon qua `--tile-brand` |
| | `--brand-graph` | `#3B82F6` | **CHỈ thanh biểu đồ** — đồ hoạ, không mang chữ (3,68 thẻ · 3,42 lõm) |
| | `--text-on-brand` | `#FFFFFF` | chữ trên `--brand` 5,17 · trên `--brand-hover` 6,70 · trên `--brand-active` 8,72 |
| Bí danh | `--accent` `--accent-hover` `--accent-active` `--accent-soft` `--accent-border` `--text-on-accent` | `var(--brand…)` | tên theo tài liệu thiết kế, cùng giá trị với `--brand…`. **KHÔNG** khai lại bằng hex |
| Nền | `--bg-card` | `#FFFFFF` | thẻ, bảng, modal |
| | `--bg-app` | `#EDF4FC` | **chỉ cho `body`** — thẻ trắng nổi 1,11 lần trên nó. **Riêng ketoan `body` tô `--bg-card`** (trắng, chốt 08/08/2026 — `static/css/base.css`) |
| | `--bg-page` | `#F4F7FB` | mặt lõm trong thẻ: sọc bảng, ô nhập, rãnh thanh, hover hàng, đầu bảng mặc định |
| | `--bg-band` | `#E5EBF4` | dải nhấn: đầu bảng tự style, viên lọc đang chọn, nút phụ |
| Viền | `--border` | `#DFE6F0` | viền chuẩn (1,26 trên thẻ) — viền GÁNH việc tách khối |
| | `--border-soft` | `#EBF0F7` | kẻ ngang giữa các dòng bảng |
| | `--focus-ring` | `0 0 0 3px rgba(37, 99, 235, .30)` | nhận biết focus |
| Chữ | `--text-1` | `#101C44` | số, tiêu đề — 16,51 thẻ · 14,90 nền · 13,78 dải |
| | `--text-2` | `#334166` | nội dung — 10,05 thẻ · 9,07 nền · 8,39 dải |
| | `--text-3` | `#5B6A80` | nhãn + chú thích — 5,50 thẻ · 4,96 nền · 4,59 dải |
| Số liệu | `--kpi-neutral` `--kpi-brand` `--kpi-good` `--kpi-data` | `var(--text-1)` `var(--brand)` `#15803D` `#1D4ED8` | tô số KPI theo loại. `--kpi-brand` và `--kpi-data` cùng họ xanh — **không đặt cạnh nhau** trong một hàng thẻ |
| Ô icon | `--tile-*` | xem `theme.css` mục 6b | **CHỈ** nền ô icon nét trắng (ADR-011, `icon-net-trang.md`); `--tile-brand` = `var(--brand-bright)` |
| Trạng thái | `--danger` / `-soft` / `-fg` | `#B91C1C` `#FEE2E2` `#991B1B` | xoá, lỗi (6,47 thẻ) |
| | `--success` / `-soft` / `-fg` | `#15803D` `#DCFCE7` `#166534` | thành công (5,02 thẻ) |
| | `--warning` / `-soft` / `-fg` | `#B45309` `#FEF3C7` `#92400E` | cảnh báo — **tách khỏi brand** (5,02 thẻ) |
| | `--info` / `-soft` / `-fg` | `#475569` `#E9EEF4` `#334155` | thông tin — **GIỮ XÁM slate, cố ý** (7,58 thẻ) |
| Bên thứ ba | `--facebook` `--messenger` `--zalo` | `#0084FF` `#1877F2` `#0068FF` | **không đổi** — cùng họ xanh nhưng không thay `--brand` |
| Bóng | `--shadow-sm/md/lg/pop` · `--ring` · `--shadow-card` | nhiều lớp `rgba(15,23,42,…)` | không dùng đen thuần; **thẻ gọi `--shadow-sm` — CẤM `--ring` / `--shadow-card` trên thẻ** (mục Thẻ, 11/09/2026) |

**Lý do đằng sau + luật rút ra — đừng "tối ưu" lại:**

- **Màu lấy từ ẢNH MẪU + quyết định người duyệt, KHÔNG rút từ logo nữa.** Đo 5
  ảnh mẫu Kinh doanh: nút chính `#0560FD`, rãnh nền `#EAF4FE`, mục sidebar đang
  chọn `#DAE9FE`, tiêu đề navy. Người duyệt chọn `#2563EB` (blue-600, chữ trắng
  5,17) thay `#0560FD` (ADR-012). Hệ "hổ phách & cà phê rút từ logo" (thử ở
  ketoan 08/08) và hệ cam (26/08) **đều đã bị thay**. Teal `#0F766E` chỉ còn
  trong ẢNH logo, **không phải token**.
- **`--brand-soft` bị chặn độ đậm ở `#EAF2FE`.** 62 dòng đặt chữ `var(--brand)`
  thẳng lên nền `var(--brand-soft)` (đếm 11/09/2026, 8 repo). Sắc đúng ảnh mẫu
  `#DBEAFE` làm `--brand` trượt còn 4,24 ✗. Muốn nền chọn đậm hơn thì đổi 62
  dòng đó sang chữ `--brand-hover` TRƯỚC, rồi mới hạ `--brand-soft`.
- **Chữ `var(--brand)` KHÔNG đặt trên `--bg-band`** (4,31 ✗) — dùng
  `--brand-hover` (5,59). Chữ trạng thái đặt trên `--brand-soft` / `--bg-band`
  dùng bản `-fg`: bản đặc `--success` 4,45 soft · 4,18 dải và `--warning` 4,46
  soft · 4,19 dải đều trượt.
- **`--brand-bright` chỉ 3,68 trên thẻ** — chỉ chữ ≥24px đậm và đồ hoạ, không
  bao giờ cho chữ nhỏ.
- **`--info` cố ý XÁM slate, không xanh.** Xanh nay là màu thương hiệu; info mà
  xanh thì pill "Chờ duyệt" trông y như mục đang chọn. Vì vậy ô icon
  `.ico-tile--info` dùng `--tile-slate`. "Đang chờ người khác" thì nên lùi lại,
  không nên hét lên.
- **`--warning` TÁCH khỏi brand.** Luật cũ "warning dùng lại brand" của đợt hổ
  phách 08/08 đã hết hiệu lực cùng hệ đó; cảnh báo nay là `#B45309` riêng.
- **Viền cố ý nhạt nhưng GÁNH việc tách khối.** Thẻ trắng chỉ nổi 1,11 lần trên
  nền `--bg-app` — ranh giới khối là viền `--border` + `--ring`, đừng bỏ viền
  thẻ. App nhiều bảng, viền đậm gây rối. Nhận biết focus dựa vào
  `--focus-ring`, **không** dựa vào viền.

**Ngoại lệ được hard-code — bảng màu biểu đồ.** Các chuỗi dữ liệu trên cùng một
biểu đồ phải phân biệt được với nhau, nên không gom về `--brand` được. Trong app
này ngoại lệ nằm ở **15 dòng** của `templates/index.html` — các object dạng
`{label:…, value:…, color:'#…'}` (đếm 11/09/2026: dòng ~8470-8483 và ~9010-9015):

```js
{label:'Tiền & TGNH', value:tien.total, color:'#2563EB'},
{label:'Phải thu KH', value:ptKh.total, color:'#1F6F72'},
```

> **Nợ, đếm 11/09/2026:** code còn hổ phách cũ `#9E5D09` ở lát Tiền & TGNH
> (`index.html:8470`) và lát Biến phí (`index.html:9014`) — dọn sang `#2563EB`.

**Bộ màu biểu đồ làm lại 08/08/2026** cho hệ hổ phách & cà phê (hệ đó đã bị
thay); **11/09/2026 lát thương hiệu đổi sang xanh `#2563EB`** (= `--brand`,
ADR-012), 7 màu còn lại giữ nguyên. Đây là BA biểu đồ tròn riêng (4 · 5 · 6
lát), màu được phép lặp giữa các biểu đồ — chỉ cần phân biệt trong cùng một biểu đồ:

| Màu | Dùng cho | Tương phản/trắng |
|---|---|---|
| `#603814` nâu cà phê (logo) | TSCĐ · Giá vốn | 10.13 |
| `#2F2A24` than nâu | Vay & nợ · Thuế TNDN | 14.21 |
| `#6B4E7D` mận | Lương | 6.97 |
| `#B02A18` đỏ gạch | Phải trả NCC | 6.58 |
| `#1F6F72` mòng két | Phải thu KH · Định phí | 5.87 |
| `#2563EB` xanh thương hiệu (= `--brand`) | Tiền & TGNH · Biến phí | 5.17 |
| `#4A9B6B` lục | Vốn chủ sở hữu | 3.39 |
| `#B0873C` cát | Tồn kho · Phải trả VC · Bán hàng | 3.29 |

**Phân biệt bằng ĐỘ SÁNG, không chỉ bằng sắc** — mù màu đỏ-lục làm trộn sắc
nhưng giữ nguyên độ sáng, nên thang tương phản trải từ 3.3 đến 14.2 là kênh
phân biệt chính. Mọi màu đều ≥3:1 (WCAG 1.4.11 cho đối tượng đồ hoạ).
Ngoại lệ cũ "cặp hổ phách/cát cách nhau ΔE 20, dưới mốc 24" **không còn**: lát
xanh đã thay lát hổ phách. Tính lại 11/09/2026 bằng CIE76 (thước cho ra đúng con
số 20 của cặp cũ), cặp gần nhất trong từng biểu đồ: Tồn kho/TSCĐ 35.8 ·
Lương/Vay & nợ 39.5 · Giá vốn/Thuế TNDN 29.6 — cả ba trên mốc 24. Mô phỏng mù
màu (Machado 2009, mức nặng nhất): lát xanh không tạo cặp gần mới; cặp yếu nhất
còn lại là Lương `#6B4E7D` / Định phí `#1F6F72` (ΔE76 11.1 khi mù màu lục) — có
từ trước, không do đổi xanh. Legend ghi đủ nhãn + % + số tiền cho từng lát nên
màu vẫn chỉ là kênh phụ.

Cách phân biệt khi sửa: **hex nằm trọn trong nháy trên dòng có `label:`** = màu
chuỗi dữ liệu, giữ nguyên. Mọi hex khác — kể cả trong chuỗi JS như
`this.style.background='#e2e8f0'` — là CSS và **phải** dùng `var(--token)`
(`element.style.background = 'var(--border)'` hợp lệ, `var()` cũng chạy trong
thuộc tính SVG `fill=` / `stroke=`).

Thẻ `<meta name="theme-color">` không nhận `var()` → phải ghi hex thật. Đổi
brand thì phải sửa tay cả manifest PWA — app này CÓ: `static/manifest.json` khoá
`"theme_color"` (phục vụ ở `/manifest.webmanifest`). Đếm 11/09/2026:
`index.html:13` và `manifest.json` đều còn hổ phách cũ `#9E5D09` — nợ. Giá trị
đích (`#2563EB` hay trắng) còn ⚠️ CẦN NGƯỜI DUYỆT (ADR-012, cùng câu cho meta và
manifest) — chờ câu trả lời rồi mới dọn, đừng tự chọn.

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

Nhiều gradient nay là `linear-gradient(135deg,var(--brand-soft),#fff)` — đã dùng
token nhưng vẫn là gradient; gặp thì thay bằng nền phẳng `var(--bg-page)` (hoặc
`var(--brand-soft)` phẳng nếu đó là khối đang chọn). `--brand-soft` VẪN là token
hợp lệ — câu cũ "token này đã bị bỏ" là sai.

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

## Thẻ — viền và mép làm như Tổng quan HCNS

Người duyệt chốt 11/09/2026, trên ảnh màn Chấm công: *"các border làm như trang
tổng quan của HCNS … không thể để border hay cái rìa như hiện tại được."*
Mẫu: `.hello` · `.kpi` · `.block` trong `qlpps-hcns/templates/tong_quan.html`
(đo bằng trình duyệt thật cùng ngày).

```css
/* ✓ Thẻ / khối thông tin — đúng bốn dòng này */
background: var(--bg-card);
border: 1px solid var(--border);
border-radius: var(--r-lg);      /* 12px · thẻ số liệu nhỏ: var(--r-md) 10px */
box-shadow: var(--shadow-sm);
```

- **Cấm `--shadow-card` và `--ring` trên thẻ.** `--ring` là vòng `0 0 0 1px` đen
  14%: chồng lên `border` thì thành một cái RÌA xám bao quanh thẻ — đúng thứ bị
  chê. `theme.css` mục 12b còn khuyên dùng `--shadow-card` cho khối lớn (quyết
  định 27/08/2026): **mục này thay quyết định đó**.
- **Một thẻ một đường mép.** Không thêm `outline`, `box-shadow: 0 0 0 1px …`,
  viền 2px hay viền màu `--brand` quanh thẻ. Bóng từ `--shadow-md` trở lên chỉ
  dành cho thứ nổi trên trang: menu thả, modal, popover, toast.
- **Ô con nằm trong thẻ** (ô số liệu, ô lịch): viền 1px `var(--border)`, KHÔNG
  đổ bóng — thẻ trong thẻ mà cùng đổ bóng là thành bậc thang.
- **Thân trang trải hết bề ngang** (`max-width:none`, đệm hai bên 16–24px) như
  Tổng quan HCNS. Không bó nội dung vào giữa màn rồi để trống hai bên.
- **Màn dùng chung (`shared/templates/*_core.html`) giữ nền như ảnh mẫu** —
  `#EDF4FC`, đúng giá trị `--bg-app` của theme — ở cả 8 app. HCNS đè `--bg-app`
  thành `#f6faf9` trong `_he_mau.html`, nên màn dùng chung khai
  `html body{background:#EDF4FC}` kèm comment. Mã này có trong whitelist lệnh tự
  kiểm số 1 — **đừng "sửa" về `var(--bg-app)`**.

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
  `thường` = `--text-2`/500 · `hover` = `--brand` · `active` = `--brand-hover`/700
  (bản cũ ghi `--brand-ink` — token đó không tồn tại, đừng chép).
- **Không tô nền cho mục nav đang chọn.**
- Khối phải: `margin-left:auto`, ngăn bằng kẻ dọc. Avatar tròn 30px nền brand
  chữ trắng; tên 12px/700, vai trò 10px/500.
- **Header giống hệt nhau ở mọi trang.** Không thêm tiêu đề trang, nút quay
  lại, hay logo phụ vào header — đặt trong phần nội dung bên dưới.
  *Ngoại lệ đã duyệt 11/09/2026:* ô tiêu đề `.ab-ptitle` của header chứa
  **đường dẫn `Trang chủ › <tên màn>`** cho màn dùng chung — JS của màn tự ghi
  vào (app chưa có ô thì chèn ngay sau nút ☰, hết chỗ thì ẩn), và thân trang
  KHÔNG lặp lại H1 + dòng phụ + breadcrumb nữa. Mẫu: `cham_cong_core.html`.

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
tab chữ thuần, mục đang chọn dùng `--brand` + gạch chân 2px `--brand`; cần khối
thì nền `--brand-soft` + chữ `--brand-hover` (5,95). Không dùng nút bo tròn kiểu
pill có nền.
Ví dụ trong app này: `.tab-nav` ở `templates/products.html` (6 tab) — **đang
dùng màu V1, cần đưa về hệ**.

Không phát minh dạng thứ 3 (breadcrumb, tab dạng thẻ…) mà chưa hỏi.
Đường dẫn trong ô tiêu đề header là ngoại lệ đã duyệt (xem mục Header); breadcrumb
đặt trong thân trang thì vẫn cấm.
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

- Gradient · glassmorphism · bóng có màu · viền đậm · rìa `--ring` / `--shadow-card`
  quanh thẻ (mục Thẻ). *Ngoại lệ gradient, người duyệt chốt 11/09/2026:*
  khối **Lưu ý ở đáy thẻ** — nền chuyển `var(--bg-card)` (trên) → `var(--brand-soft)`
  (đáy), mẫu `.cc-luu-y` trong `shared/templates/cham_cong_core.html`.
  Cùng kiểu cho khối **Quy định / Lưu ý đứng riêng ở cột phụ** (ảnh mẫu Xin nghỉ):
  đáy `var(--warning-soft)` hoặc `var(--danger-soft)` theo nghĩa khối — mẫu `.xn-khoi`
  trong `shared/templates/xin_nghi_core.html`. Ngoài hai chỗ này vẫn cấm.
- Tô nền cho mục nav đang chọn **trên header** (sidebar `.ab-sb` thì có: nền
  `--brand-soft` + chữ `--brand-hover`, đúng ảnh mẫu).
- Thêm màu, mức viền, cỡ chữ, kiểu subnav ngoài danh sách trên.
- Nhuộm nút xoá theo màu thương hiệu — người dùng sẽ bấm nhầm.
- Đổi màu Facebook/Messenger/Zalo — đó là nhận diện của họ.
- Khai lại `esc`, `escHtml`, `initials` trong template — đã có toàn cục qua
  `/static/js/ui-common.js`, nạp sẵn trong `_header.html`.
- Sửa lẻ `static/css/theme.css` hay `.claude/rules/` của repo này để "cho khớp" —
  cả hai SINH từ `claude-kit` qua `sync.py` (giá trị:
  `claude-kit/core/static/css/theme.css`; luật riêng ketoan:
  `claude-kit/overlay/ketoan/`). Hệ đi một chiều từ kit sang;
  `HE-MAU-ERP.md` của marketing đã lỗi thời.

## Tự kiểm trước khi báo xong

```bash
# 1. Có màu nào ngoài hệ lọt vào không?  Whitelist = giá trị hệ XANH trong
#    theme.css (ADR-012, 11/09/2026); màu --tile-* chỉ gọi qua var(), không
#    whitelist. Lọc từng MÃ, không lọc cả dòng (cùng cách với skill ui-check):
#    lọc theo dòng thì một mã hợp lệ che mọi mã lạ trên cùng dòng — bản cũ của
#    lệnh này bỏ sót index.html:1871 (#fff7ed #fed7aa #7c2d12). `$` neo cuối mã
#    nên `fff` không nuốt `#fff7ed`. Chạy 11/09/2026: _header, dao_tao, products,
#    xin_nghi RỖNG = sạch; index.html 78 mã trên 54 dòng, 15 dòng trong đó là
#    màu chuỗi biểu đồ (hợp lệ; 2 dòng còn nợ `#9E5D09` hổ phách cũ — xem trên).
grep -noiE '(^|[^&])#[0-9a-f]{3,8}\b' templates/<file>.html | grep -viE \
 '#(2563EB|1D4ED8|1E40AF|EAF2FE|BFDBFE|3B82F6|FFFFFF|fff|EDF4FC|F4F7FB|E5EBF4|DFE6F0|EBF0F7|101C44|334166|5B6A80|15803D|DCFCE7|166534|B45309|FEF3C7|92400E|B91C1C|FEE2E2|991B1B|475569|E9EEF4|334155|0084FF|1877F2|0068FF)$'

# 2. Xám ẤM lọt vào hệ lạnh — phải rỗng
grep -niE '#(605D58|795E43|E0D3C2|EBE2D6|FAF5EF|33210F|5E452C|9E5D09|7F4B07|FBE7C6|EFE2CB|FDF8F0|E7D7BE|D23C0E|FBE5D0)' templates/<file>.html

# 3. Token BỊA — phải rỗng. `--brand-ink` chưa bao giờ tồn tại; grep ra nghĩa là
#    ai đó chép theo bản tài liệu cũ. (`brand-soft`, `brand-hover` VẪN DÙNG — đừng dọn.)
grep -n 'brand-ink' templates/<file>.html

# 4. Mã hệ CAM đã bị thay (26/08 → 11/09/2026) + cam gốc FF8D28 lọt lại
#    — phải rỗng, gặp thì dọn sang var(--token)
grep -niE 'A84A03|9A4703|E8EDF3|F2610E|CC4E05|B85105|FF8D28|168, ?74, ?3' templates/<file>.html

# 5. Cỡ chữ có nằm ngoài thang không?
grep -oE 'font-size:[0-9]+px' templates/<file>.html | sort -u
```

> `(^|[^&])` ở lệnh 1 là bắt buộc — thiếu nó thì thực thể HTML như `&#9776;`
> (icon ☰) bị báo nhầm thành mã màu.
>
> Lệnh 5 (cỡ chữ) dùng `[0-9]+` nên **không bắt được cỡ lẻ** `12.5px`. Muốn soát cả cỡ
> lẻ thì đổi thành `[0-9.]+` — các template V1 của app này có đầy `.5px`.

Ra kết quả ngoài danh sách → **sửa lại cho vào hệ, hoặc hỏi người dùng**. Không
tự nới giới hạn rồi báo là xong.

## Riêng app này

File này là overlay **THAY HẲN** `core/rules/design-system.md` cho riêng ketoan —
nguồn: `claude-kit/overlay/ketoan/rules/design-system.md`, `sync.py` rải vào
`.claude/rules/`. Sửa ở kit rồi chạy sync, đừng sửa lẻ bản trong repo. Vì thay
hẳn nên luật mới thêm vào core KHÔNG tự tới ketoan — phải chép tay sang đây.
Số liệu dưới đây **đếm lại bằng lệnh ngày 08/08/2026**, không chép từ tài liệu cũ.

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
  `components.css` → `{% block page_css %}`. `{% set ASSET_V = '4' %}` (đo 11/09/2026) là cách
  phá cache thủ công (repo không có build step) — sửa CSS thì tăng số này.
- **Nợ gradient ĐÃ TRẢ XONG.** `grep -c 'linear-gradient\|radial-gradient'
  templates/*.html` ngày 08/08/2026 = **0 ở cả 18 file** (mục "Nợ CÒN LẠI" bên
  trên nói 44 chỗ/10 file — đã lỗi thời, giữ lại làm lịch sử). Trong
  `static/css/` chỉ còn 1 lần xuất hiện chữ "gradient" ở **comment**
  `base.css:86`, không phải khai báo màu.
- **Nợ V1 CÒN THẬT**: `.tab-nav` của `products.html` vẫn dùng màu V1; cỡ chữ lẻ
  `.5px` còn rải trong các template V1 (lệnh tự kiểm số 5 dùng `[0-9]+` nên
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
  trong `index.html`; (3) `<meta name="theme-color">` ghi hex thật vì thuộc
  tính này không nhận `var()` — giá trị chờ người duyệt (đoạn theme-color ở
  mục ngoại lệ hard-code phía trên); (4) **SVG inline** cho icon sidebar.

## Tóm tắt đợt chuẩn hoá UI 08/08/2026

Đọc **`BAN-GIAO-UI.md`** ở gốc repo trước bất kỳ việc UI nào. Tóm tắt:

- Hệ màu: từ 11/09/2026 cả 8 app **dùng chung** hệ TRẮNG + XANH
  (`--brand:#2563EB`, ADR-012 — anh Quang chốt, ưu tiên cao nhất). Nguồn giá
  trị: `static/css/theme.css` (sinh từ `claude-kit`); lý do: `QLPPS-UI-DOC/01-ADR.md`.
  `qlpps-marketing/docs/HE-MAU-ERP.md` đã lỗi thời — đừng tra.
  Ghi chú "ketoan có bảng màu riêng" của đợt 08/08 **không còn đúng**: đợt đó
  tách ra thử hệ hổ phách, rồi cả 8 app sang hệ cam 26/08 — cả hai đã bị thay.
- Điều hướng ở **sidebar dọc** `.ab-sb` (196px, thu gọn 52px), không còn 5
  dropdown trên header.
- **Thang chữ +1px toàn dải**, nội dung chuẩn `14px`. **Mobile không được thu
  nhỏ chữ.** Nền `body` của ketoan là `--bg-card` (trắng, chốt 08/08/2026 —
  khác 7 app dùng `--bg-app`; xem `static/css/base.css`), thẻ `--bg-card`;
  `--bg-page` chỉ dùng cho bề mặt lõm.
- Hàm dùng chung ở `static/js/ui-common.js`: `fmtVnd` `fmtShort` `fmtSo`
  `fmtDate` `fmtDateTime` `toast` `khoiLoi` `loiNguoiDoc` `esc` `initials` —
  **cấm khai lại trong template**.
- Nợ lớn nhất: **31 chỗ đổ `e.message` thô ra màn hình** — sửa bằng
  `khoiLoi(e, 'tenHamTaiLai')`.
