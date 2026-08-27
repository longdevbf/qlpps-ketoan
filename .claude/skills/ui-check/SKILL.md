---
name: ui-check
description: Checklist QC giao diện 6 nhóm — chạy trước khi báo xong mọi thay đổi UI. Dùng khi người dùng gõ /ui-check hoặc khi kết thúc task UI.
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/skills/ui-check/SKILL.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/skills/ui-check/SKILL.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# /ui-check — QC giao diện trước khi báo xong

Chạy đủ 6 nhóm, báo kết quả **pass/fail từng mục** kèm bằng chứng (số liệu grep,
ảnh chụp). Fail mục nào → sửa rồi chạy lại, không "note lại làm sau".

## 1. Số liệu khớp

- [ ] Các tổng đứng cạnh nhau đối chiếu được (DT − CP = LN; tổng phần = tổng KPI)
- [ ] Dữ liệu thiếu/chưa phân loại → có cảnh báo hiển thị, không âm thầm render

## 2. Nhãn & ngôn ngữ

- [ ] Không key kỹ thuật lộ ra màn hình (`grep` các key snake_case trong chuỗi render)
- [ ] Không biệt ngữ dev trong UI: "Phase", "Module", "22 dòng", tên hàm/biến
- [ ] Tiêu đề trang và tiêu đề thẻ KHÔNG lặp nhau — thẻ nói "khối này chứa gì"

## 3. Màu & token (lệnh từ design-system.md)

> **Bảng dưới là hệ CAM (chốt 26/08/2026).** Nguồn sự thật:
> `qlpps-marketing/docs/HE-MAU-ERP.md`. Nếu ở đây xuất hiện lại `D23C0E` hay `9E5D09` thì
> file này đã bị kéo về bản cũ — đó là hai hệ **đã bị thay**, KHÔNG được lấy
> nó sửa ngược template.

```bash
# Hex ngoài hệ (rỗng = sạch; màu chuỗi biểu đồ là ngoại lệ hợp lệ)
grep -nE '#[0-9a-fA-F]{3,6}' templates/<file>.html | grep -v '&#' | grep -viE \
 'CC4E05|B85105|EA580C|F2610E|FFFFFF|#fff|F1F5F9|F8FAFC|E2E8F0|EDF1F6|0F172A|334155|5F6E80|15803D|DCFCE7|B45309|FEF3C7|B91C1C|FEE2E2|475569|E9EEF4|1D4ED8|0084FF|1877F2|0068FF|e67e22'
# Xám ẤM lọt vào hệ lạnh — di sản hai hệ cũ, phải rỗng
grep -niE '#(605D58|795E43|E0D3C2|EBE2D6|FAF5EF|33210F|5E452C|9E5D09|7F4B07|FBE7C6|EFE2CB|FDF8F0|E7D7BE|D23C0E|FBE5D0)' templates/<file>.html
# Token đã bỏ cùng công thức pastel — phải rỗng
grep -n 'brand-soft\|brand-hover' templates/<file>.html
# Cam dùng sai vai — kiểm từng dòng bằng mắt.
#   CC4E05 CHỈ được làm NỀN khối đặc, không làm chữ. FF8D28 không được xuất hiện.
grep -niE 'CC4E05|FF8D28' templates/<file>.html
# Gradient & cỡ chữ lạ
grep -c 'linear-gradient\|radial-gradient' templates/<file>.html
grep -oE 'font-size:[0-9.]+px' templates/<file>.html | sort -u
```

- [ ] Lệnh 1–3 rỗng · [ ] lệnh 4 đã soi bằng mắt · [ ] gradient = 0 · [ ] cỡ chữ trong thang
- [ ] Nhấn là **khối đặc** `--brand` + chữ trắng, tối đa 1 khối/màn ngoài điều hướng
- [ ] Bề mặt trung tính: header bảng dùng `--bg-page` + `--text-3` IN HOA, KHÔNG tô brand
- [ ] Thẻ số liệu: nhãn `--text-3` 11px IN HOA · số 29px `--text-1`/`--kpi-*` — chênh ≥3×
- [ ] Một hàng thẻ không quá 3 màu `--kpi-*` khác nhau
- [ ] Doanh thu không đỏ; **chi phí không đỏ mặc định**; badge dùng cặp `-soft`/`-fg`
- [ ] Viền màu card (nếu có) mang MỘT nghĩa nhất quán, không trang trí ngẫu nhiên
- [ ] Bố cục trong ngân sách thẻ của `layout-rules` (Tầng 1 ≤4, Tầng 2 ≤6, biểu đồ ≤4)

## 4. Trạng thái & hành vi

- [ ] Đủ 4 trạng thái loading/empty/error/data cho mọi khối async
- [ ] Empty nói vì sao + làm gì tiếp; error có nút thử lại
- [ ] Nút thao tác có CHỮ (không icon-only); xoá có confirm nêu hậu quả

## 5. Form

- [ ] Validate tại field khi blur; lỗi giữ dữ liệu đã nhập + focus field lỗi
- [ ] Thông báo lỗi nói rõ chuyện gì + bước tiếp theo

## 6. Kiểm bằng mắt thật (bắt buộc — mục 9 HE-MAU-ERP)

- [ ] Chụp screenshot thật (Playwright/Chrome — dùng công cụ chụp sẵn có của app nếu có)
- [ ] Bắt cả `console.error` LẪN `pageerror` — hai loại khác nhau
- [ ] Test nheo mắt: làm mờ ảnh — thứ còn nhận ra phải là ý chính của trang
- [ ] Thử ở 375px nếu sửa layout
