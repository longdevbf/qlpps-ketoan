---
paths:
  - "templates/**/*.html"
  - "static/**/*.css"
  - "shared/templates/**/*.html"
  - "shared/static/**/*.css"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/cap-chu.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/cap-chu.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->
# Cấp chữ H1–H6 — phân cấp tiêu đề và nội dung

Quyết định ADR-010 (bộ tài liệu `QLPPS-UI-DOC`), 11/09/2026. Nhận toàn bộ nguyên tắc phân cấp chữ
của web mà người duyệt tham khảo, nhưng **hiệu chỉnh con số cho ERP mật độ cao**.

## Sáu luật — mỗi luật kiểm được

**TC-1. Mỗi trang đúng MỘT `<h1>`, và tiêu đề trang PHẢI là `<h1>`, không phải `<div>`.**
Hiện trạng 11/09/2026: **164 template không có `<h1>` nào**, 68 có đúng một, 0 có hơn một.
Vi phạm đang là *thiếu*. `qlpps-saleadmin/templates/_base.html` in tiêu đề bằng
`<div class="page-title">` → mọi trang kế thừa nó đều mất H1.

```jinja
{# ✗ SAI #}  <div class="page-title">{% block page_title %}{% endblock %}</div>
{# ✓ ĐÚNG #} <h1 class="page-title">{% block page_title %}{% endblock %}</h1>
```

**TC-2. Chọn CẤP theo cấu trúc trang, chọn CỠ bằng CSS.** Cấp tiêu đề là vị trí trong dàn ý —
trình đọc màn hình đọc theo nó. Cấm dùng `<h3>` "vì muốn chữ nhỏ hơn". Hiện trạng: `<h3>` dùng
**294 lần**, nhiều hơn `<h2>` (188) — dấu hiệu đang chọn cấp theo cỡ.

**TC-3. Không nhảy cấp.** Dưới `<h2>` là `<h3>`, không phải `<h4>`.

**TC-4. Hai cấp liền kề phải phân biệt được bằng mắt:** cỡ chênh **≥ 1,25 lần**, HOẶC khác nhau ở
**ít nhất 2 trong 3** thuộc tính *(cỡ · độ đậm · màu)*. Các nấc 15/14/13px gần nhau tới mức **cỡ một
mình không đủ** — phân cấp phải gánh bằng độ đậm và màu. Bảng dưới đã kiểm đạt luật này; thêm tổ hợp
mới mà trượt là lỗi.

**TC-5. Tối đa 2 họ font: 1 sans + 1 mono.** CSS trang và `<style>` trong template **cấm khai
`font-family`** — mọi thứ kế thừa từ `body`. Hiện trạng: **32 giá trị `font-family` khác nhau** trong
8 repo, riêng họ sans đã có Segoe UI (66 lần), Noto Sans (31), Inter (13). Cấm nạp webfont ngoài.

**TC-6. Line-height:** đoạn văn / ô bảng `var(--lh-body)` (1,5); tiêu đề và số lớn `var(--lh-tight)` (1,2).

## Bảng cấp — theme ĐANG CHẠY (hệ xanh `--brand #2563EB`, ADR-012)

| Cấp | Dùng cho | Cỡ | Đậm | Màu |
|---|---|---|---|---|
| **H1** | Tên trang — đúng 1 / trang, mọi loại trang | `var(--fs-h)` 18px | 700 | `var(--text-1)` |
| **H2** | Tiêu đề thẻ / section · tiêu đề modal | `var(--fs-title)` 15px | 600 | `var(--text-1)` |
| **H3** | Tiểu mục trong thẻ · nhóm trong form | `var(--fs-body-lg)` 14px | 600 | `var(--text-2)` |
| **H4** | Nhóm nhỏ, tiêu đề phụ | `var(--fs-body)` 13px | 600 | `var(--text-3)` |
| **H5–H6** | Nhãn nhóm IN HOA (nhóm sidebar, nhóm menu) | `var(--fs-eyebrow)` 11px | 700 · IN HOA · `.05em` | `var(--text-3)` |
| `p` | Đoạn văn, ô bảng — **mặc định** | `var(--fs-body)` 13px | 400 | `var(--text-2)` |
| `p` mật độ thấp | Mô tả trong form, giá trị trang chi tiết | `var(--fs-body-lg)` 14px | 400 | `var(--text-2)` |
| Chú thích | Ngày tháng, chữ trợ giúp, "so với kỳ trước" | `var(--fs-meta)` 12px | 400 | `var(--text-3)` |
| Siêu nhỏ | **Chỉ** nhãn nhóm menu thả xuống, số phiên bản | `var(--fs-micro)` 10px | — | `var(--text-3)` |
| Số KPI | Con số lớn trong thẻ KPI — **không phải tiêu đề** | `var(--fs-kpi)` 29px | 700 | `var(--text-1)` |

**Cấm** `var(--fs-display)` ở repo chưa sync theme mới — token đó **chưa tồn tại**; viết ra thì biến
rỗng và H1 rơi về cỡ chữ thân bài 13px. **Cấm** `var(--fs-glyph)` cho chữ người đọc (chỉ cho ☰ ✕).
**Cấm** `font-size` px trần — dùng `var(--fs-*)`.

## Vì sao không lấy nguyên con số web

Tham khảo web: body 16px, H1 32–48px. ERP này: body **13px**. Lý do đo được: chính mockup người
duyệt đưa đo ra chữ ô bảng 13–14px (6/6 phép đo); 16 ÷ 13 = **+23% bề rộng mỗi cột** → bảng 11 cột
ở khung 1280px phải cuộn ngang. Luật `frontend-ui.md` cũng đã chốt: *13px là chuẩn nội dung app nội
bộ — không áp ≥16px của web công cộng.*

## Khi theme mới được sync

"Theme mới" ở mục này là **bản thảo cỡ chữ** của `QLPPS-UI-DOC`, **không phải** hệ xanh
ADR-012. Theme hệ xanh (sync 11/09/2026) **chưa có** `--fs-display` — kiểm:
`grep -c -- '--fs-display' static/css/theme.css` ra `0` thì lệnh cấm ở trên vẫn hiệu lực.

Bảng cấp dịch lên một nấc: **H1 → `--fs-display` 32px · H2 → `--fs-h` 18px · H3 → `--fs-title` 15px.**
Bảng đầy đủ ở `QLPPS-UI-DOC/01-ban-thao/04-typography-spacing.md §3.2.0`.
**Thay bảng trong file này bằng bảng đó trong CÙNG lần sync theme.**

`--fs-h` hiện có **218 lượt gọi** với vai "tiêu đề trang". Sau sync giá trị vẫn là 18px nên không vỡ gì,
nhưng những chỗ đó cần đổi sang `<h1>` + `--fs-display` mới lên 32px.

## Tự kiểm trước khi báo xong

```bash
# TC-1: template (không phải partial _*.html) có số <h1> khác 1
python -c "import re,pathlib;[print(n,p) for p in sorted(pathlib.Path('templates').rglob('*.html')) if not p.name.startswith('_') for n in [len(re.findall(r'<h1[\s>]',p.read_text(encoding='utf-8',errors='ignore'),re.I))] if n!=1]"
#   Lưu ý: file bọc chỉ include template dùng chung sẽ báo 0 — H1 của nó nằm ở template dùng chung.

# TC-5: CSS trang / template tự khai font-family (phải rỗng)
grep -rnE "font-family\s*:" static/css/ templates/ | grep -vE "theme\.css|app\.css|vendor|bootstrap|inherit"

# font-size px trần (phải giảm dần về 0)
grep -rnE "font-size\s*:\s*[0-9.]+px" templates/ static/css/ | grep -v theme.css
```

Và **xem ảnh thật**: nheo mắt nhìn trang — thứ nổi lên đầu tiên phải là H1, sau đó mới tới tiêu đề thẻ.
