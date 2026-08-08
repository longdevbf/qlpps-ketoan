---
name: ui-standards
description: Chuẩn kỹ thuật UI ketoan — design token, màu ngữ nghĩa, thang chữ, format tiền VN, 4 trạng thái, label map, dashboard 2 tầng. Đọc trước khi viết bất kỳ giao diện nào.
---

# UI Standards — PAPASAN Kế Toán

Bổ trợ cho `.claude/rules/frontend-ui.md` (10 luật) và
`.claude/rules/design-system.md` (giới hạn hệ màu). Xung đột → design-system thắng.

## 1. Design tokens — nguồn duy nhất: `static/css/theme.css`

Gọi `var(--token)`, không hex tự chế. Tóm tắt (chi tiết + tương phản đã đo:
`design-system.md`):

| Việc | Token |
|---|---|
| Nút chính / tab chọn / avatar / chip | nền `--brand-soft` + chữ `--brand-hover`, hover `filter:brightness(.95)` |
| Tiêu đề, chữ nhấn, dải neo mỏng | `--brand` |
| Nền trang / nền thẻ / viền | `--bg-page` / `--bg-card` / `--border` |
| Chữ 3 mức | `--text-1` (tiêu đề, số liệu) · `--text-2` (nội dung) · `--text-3` (chú thích) |
| Focus | `box-shadow: var(--focus-ring)` — không viền đậm |
| Bóng | `--shadow-sm/md/lg` — cấm bóng có màu |

## 2. Màu ngữ nghĩa — badge/chip dùng cặp `-soft` nền + `-fg` chữ

| Ý nghĩa | Nền | Chữ | Ví dụ |
|---|---|---|---|
| Tốt / tăng / đã duyệt | `--success-soft` | `--success-fg` | "Đã trả", "Hoạt động" |
| Xấu / lỗ / từ chối | `--danger-soft` | `--danger-fg` | "Quá hạn", "CEO từ chối" |
| Cần chú ý / chờ | `--warning-soft` | `--warning-fg` | "Chờ duyệt" |
| Thông tin / đang xử lý | `--info-soft` | `--info-fg` | "Đang xử lý" |

### Luật áp màu (quan trọng hơn cả bảng token)

- Tỷ lệ **60-30-10**: ~60% diện tích là nền trung tính, ~30% màu thương hiệu ở
  vùng nhận diện (header, tiêu đề), ~10% màu nhấn CHỈ cho hành động chính.
- Số liệu bình thường (doanh thu, chi phí, số đơn…) → `--text-1`. KHÔNG tô màu
  số "cho đẹp". Chỉ tô semantic khi con số **mang phán xét**: LN dương → lục,
  âm → đỏ; delta so kỳ trước → lục/đỏ; quá hạn → warning.
- **Doanh thu tô đỏ = BUG. Chi phí tô đỏ mặc định = BUG** (chi phí là số trung
  tính, chỉ đỏ khi vượt ngân sách).
- Viền màu trên card (nếu dùng) phải mang MỘT nghĩa nhất quán cho mọi card —
  không dùng làm trang trí ngẫu nhiên.
- Màu đặc (`--danger`…) chỉ cho nút hành động nguy hiểm.

## 3. Thang chữ & khối (theo design-system, KHÔNG nội suy)

- Cỡ chữ (thang đã +1px, chốt 08/08/2026): `11` nhãn nhóm · `12-13` meta ·
  **`14` nội dung chuẩn** · `15-17` tiêu đề · KPI hero `29/25/18-20`.
  Weight: `500` thường · `600-700` nhấn · `800` tiêu đề.
  Mobile: **không thu nhỏ chữ**, bảng rộng thì cuộn ngang.
- Bo góc `6/8-9/12`, đệm thẻ `14-16px`, hiệu ứng `.12s–.25s`.

## 4. Format tiền & số — MỘT hàm dùng chung

**Đã có hàm toàn cục trong `/static/js/ui-common.js`** (thêm 08/08/2026, nạp sẵn
qua `_header.html`). **Cấm khai lại trong template** — dùng thẳng:

| Hàm | Dùng cho | Đầu ra |
|---|---|---|
| `fmtVnd(n)` | bảng chi tiết, dòng tiền | `1.250.000 đ` |
| `fmtShort(n)` | KPI card | `1,3 tỷ` · `1,25 tr` · `250.000 đ` |
| `fmtSo(n, 'data')` | số ĐẾM, không phải tiền | `2.520 data` |
| `fmtDate(s)` | ngày | `08/08/2026` |
| `fmtDateTime(s)` | ngày giờ | `08/08/2026 10:30` |

- **Đơn vị chốt là `đ`, không phải `₫`** (theo `frontend-ui.md` luật 6).
  Giá trị rỗng → `—`, không phải `0 đ`.
- Không trộn 2 chuẩn (`fmtVnd` và `fmtShort`) trong cùng một dải card.
- Trang cũ còn khai hàm cùng tên trong `<script>` của nó thì bản local vẫn
  thắng — không gãy, nhưng **dọn khi sửa tới trang đó**.

## 5. Bốn trạng thái — mẫu markup

```html
<div id="x-loading" class="loading">Đang tải...</div>          <!-- skeleton/nhạt -->
<div id="x-empty" hidden>Chưa có giao dịch — sẽ tự xuất hiện khi thêm Doanh Thu.
  <button class="btn btn-primary btn-sm">Thêm ngay</button></div>
<div id="x-error" hidden>Không tải được (mất kết nối). <button>Thử lại</button></div>
<table id="x-data" hidden>…</table>
```

Empty phải nói *vì sao trống + làm gì tiếp*. Error phải có *nút thử lại*.
Banner cảnh báo rỗng → `hidden`, không render khung trống.

## 6. Label map — không lộ key kỹ thuật

```js
const STATUS_LABEL = { cho_duyet: 'Chờ KT', kt_duyet: 'Chờ CEO', duyet: 'Hoàn tất' };
const label = STATUS_LABEL[key] ?? (console.warn('thiếu nhãn:', key), 'Chưa đặt tên');
```

## 7. Dashboard 2 tầng

Tầng 1: 3–4 KPI chính (card lớn, số 29px). Tầng 2: dải card mỏng chỉ số vận
hành. Biểu đồ đặt sau KPI. Tổng các phần trong biểu đồ = số trên KPI card —
lệch thì hiện cảnh báo, không im lặng.

## 8. Riêng ketoan — bối cảnh Jinja, không SPA framework

- Trang mới extends `templates/base.html` (đọc chú thích 3 bẫy Jinja đầu file).
- Icon: KHÔNG emoji/icon font; nút dùng chữ (`Sửa`, `Xoá`); SVG inline được phép.
- Header/subnav tự động từ `_header.html` — trang mới phải thêm mục vào dropdown.

## 9. Nợ đang dọn — hệ màu bóng & hàm format local (đo 08/08/2026)

Hai món nợ này là lý do đợt chuẩn hoá UI đang chạy. Sửa tới trang nào thì dọn
trang đó, **đừng chép sang trang mới**.

**a) Hệ màu bóng — 11 template tự khai token riêng.** Đợt retheme trước làm bằng
cách *alias* token V1 sang token hệ, nên màu ra đúng và mọi lệnh tự kiểm đều
pass — nhưng code vẫn nói ngôn ngữ V1:

| Số token riêng | File |
|---|---|
| 27 | `xin_nghi` · `phe_duyet` · `giao_viec` · `duyet_chi` · `cham_cong` · `bao_cao_duyet_chi` |
| 24 | `lich_lam_viec` |
| 13 | `chat_widget` |
| 9 | `index` · `ncc_de_xuat` |

Hậu quả cụ thể, tất cả đều là bẫy cho người sửa sau:

- `--navy` `--navy-d` `--primary` `--primary-d` → **4 tên cho 1 màu brand**
- `--blue-txt: var(--brand)` → **token tên "blue" render ra màu cam**
- `--purple-*` `--cyan-*` `--blue-*` → **9 tên cho 1 bộ `--info`**
- Hex thật còn sót trong chính khối alias: `--amber-bg:#fef3c7`,
  `--green-bg:#dcfce7`, `--blue-bg:#dbeafe` — lệnh tự kiểm không bắt vì
  whitelist đúng những mã đó. Vẫn vi phạm giới hạn 5 (cấm hard-code hex).
- `giao_viec.html` tham chiếu 8 token `--gray-*` **không định nghĩa ở đâu** —
  không gãy vì mọi chỗ đều có fallback (`var(--gray-600, var(--text-2))`),
  nhưng fallback đang gánh toàn bộ. Xoá lớp `--gray-*`, giữ token hệ.

Cách dọn: xoá khối `:root{}` alias của trang, thay mỗi `var(--alias)` bằng
token hệ tương ứng. Màu **không đổi** — alias vốn đã trỏ đúng.

**b) `#fff` hard-code: 315 chỗ / 17 file** (index 44 · giao_viec 37 · phe_duyet
28 · cham_cong 25 · duyet_chi 24). Thay bằng `var(--bg-card)`.

**c) Hàm format local đã bị thay bằng bản toàn cục** (xem mục 4). Trang cũ vẫn
còn `fmtMoney` ×4, `fmtVnd` ×3, `fmt` ×1, `fmtDate` ×8 — bản local thắng nên
không gãy, xoá dần. `esc` / `escHtml` / `initials` cũng **đã có toàn cục**.
