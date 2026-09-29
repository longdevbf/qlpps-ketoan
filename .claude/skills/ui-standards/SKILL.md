---
name: ui-standards
description: Chuẩn kỹ thuật UI PAPASAN ERP — design token, màu ngữ nghĩa, thang chữ, format tiền VN, 4 trạng thái, label map, dashboard 2 tầng. Đọc trước khi viết bất kỳ giao diện nào.
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/ui-standards/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/ui-standards/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# UI Standards — PAPASAN ERP (chung 7 app)

Bổ trợ cho `.claude/rules/frontend-ui.md` (10 luật) và
`.claude/rules/design-system.md` (giới hạn hệ màu). Xung đột → design-system thắng.
Nguồn sự thật về màu: `static/css/theme.css` (giá trị + tương phản đã tính, ghi ngay
trong comment) và ADR-012 trong `QLPPS-UI-DOC/01-ADR.md` — hệ TRẮNG + XANH `--brand`
`#2563EB`, người duyệt chốt 11/09/2026, cấp cao nhất: bản nào (kể cả design-system)
lệch hai nguồn này thì hai nguồn này thắng.

## 1. Design tokens — nguồn duy nhất: `static/css/theme.css`

Gọi `var(--token)`, không hex tự chế. Tóm tắt (giá trị + tương phản đã tính: comment
trong `theme.css`; giới hạn dùng: `design-system.md`):

| Việc | Token |
|---|---|
| Nút chính · avatar | khối đặc: nền `--brand` + chữ trắng `--text-on-brand` (5.17) · hover nền `--brand-hover` · lúc bấm `--brand-active` |
| Mục/hàng đang chọn · chip · tab dạng khối | nền `--brand-soft` + chữ `--brand-hover` (5.95) · viền 1px (nếu có) `--brand-border` |
| Chữ nhấn, icon, viền nhấn | `--brand` (5.17 trên thẻ) — trên `--bg-band` chỉ 4.31 ✗, dùng `--brand-hover` |
| Số ≥24px đậm, icon lớn · thanh biểu đồ | `--brand-bright` · `--brand-graph` — KHÔNG cho chữ nhỏ (3.68 trên thẻ) |
| Nền | `--bg-app` CHỈ cho `body` · `--bg-card` thẻ/bảng/modal · `--bg-page` mặt lõm trong thẻ · `--bg-band` dải nhấn |
| Viền | `--border` · kẻ ngang giữa các dòng bảng `--border-soft` |
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

Trạng thái KHÔNG nhuộm theo thương hiệu. `--info` cố ý giữ XÁM slate (ADR-012):
info mà xanh thì pill "Đang xử lý" trông y như mục đang chọn. Badge đặt trên nền
`--brand-soft`/`--bg-band` dùng chữ `-fg` — bản đặc `--success`/`--warning` trượt
4.5:1 trên hai nền đó (4.45/4.46 trên soft, 4.18/4.19 trên band).

### Luật áp màu (quan trọng hơn cả bảng token)

- Tỷ lệ **60-30-10**: ~60% diện tích là nền trắng/ám xanh, ~30% màu thương hiệu
  ở vùng nhận diện (mục đang chọn `--brand-soft`, chữ nhấn, icon — header vẫn nền
  trắng, tiêu đề là navy `--text-1`), ~10% khối đặc `--brand` CHỈ cho hành động chính.
- Số liệu bình thường (doanh thu, chi phí, số đơn…) → `--text-1`. KHÔNG tô màu
  số "cho đẹp". Chỉ tô semantic khi con số **mang phán xét**: LN dương → lục,
  âm → đỏ; delta so kỳ trước → lục/đỏ; quá hạn → warning.
- **Doanh thu tô đỏ = BUG. Chi phí tô đỏ mặc định = BUG** (chi phí là số trung
  tính, chỉ đỏ khi vượt ngân sách).
- Viền màu trên card (nếu dùng) phải mang MỘT nghĩa nhất quán cho mọi card —
  không dùng làm trang trí ngẫu nhiên.
- Màu TRẠNG THÁI đặc (`--danger`…) làm nền chỉ cho nút hành động nguy hiểm
  (khối đặc `--brand` là nút chính — xem mục 1).

## 3. Thang chữ & khối (theo design-system, KHÔNG nội suy)

- Cỡ chữ: `10` nhãn nhóm · `11-12` meta · `13` nội dung chuẩn · `14-16` tiêu đề
  · KPI hero `29/25/18-20`. Weight: `500` thường · `600-700` nhấn · `800` tiêu đề.
- Bo góc `6/8-9/12`, đệm thẻ `14-16px`, hiệu ứng `.12s–.25s`.

## 4. Format tiền & số — MỘT hàm dùng chung

- Dùng lại hàm format sẵn có của app (tìm `fmt(`/`fmtVnd(` trước khi viết mới),
  đừng rải `toLocaleString` khắp nơi. Trang mới: 1 hàm `fmtVnd()` đầu file.
- Chuẩn hiển thị: bảng chi tiết = `1.250.000 đ`; KPI card = rút gọn `1,25 tr`.
  Không trộn 2 chuẩn trong cùng một dải card.
- Số đếm kèm đơn vị chữ: `2.520 data`, `4.768 tin`, `35 đơn`.

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

## 8. Bối cảnh chung — Jinja server-render, không SPA framework

- Không React/Vue/build step. Trang mới theo khung layout sẵn có của app
  (base.html / _header.html — xem mục "Riêng app này").
- Icon: KHÔNG emoji/icon font; nút dùng chữ (`Sửa`, `Xoá`); SVG inline được phép.
- Trang mới phải đăng ký điều hướng vào header/nav — trang không có đường vào
  là trang "mồ côi".
