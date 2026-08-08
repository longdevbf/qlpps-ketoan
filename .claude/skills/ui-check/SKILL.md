---
name: ui-check
description: Checklist QC giao diện 6 nhóm — chạy trước khi báo xong mọi thay đổi UI. Dùng khi người dùng gõ /ui-check hoặc khi kết thúc task UI.
---

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

```bash
# Hex ngoài hệ (rỗng = sạch; 12 dòng màu biểu đồ index.html là ngoại lệ hợp lệ)
grep -nE '#[0-9a-fA-F]{3,6}' templates/<file>.html | grep -v '&#' | grep -viE \
 '9E5D09|7F4B07|FBE7C6|FFFFFF|#fff|FDF8F0|E7D7BE|33210F|5E452C|7D6248|B02A18|F9E2DD|8A1F11|2E7D4F|E1EFE5|1F5C39|F1E9DD|FEB041|603814|0084FF|1877F2|0068FF|e67e22'
# Gradient & cỡ chữ lạ
grep -c 'linear-gradient\|radial-gradient' templates/<file>.html
grep -oE 'font-size:[0-9.]+px' templates/<file>.html | sort -u
```

- [ ] Lệnh 1 rỗng · [ ] gradient = 0 · [ ] cỡ chữ nằm trong thang
- [ ] Nút chính pastel (brand-soft + brand-hover), tối đa 1 nút nhấn/màn hình
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

- [ ] Chụp screenshot thật (Playwright ở scratchpad, mẫu script các phiên trước)
- [ ] Bắt cả `console.error` LẪN `pageerror`
- [ ] Test nheo mắt: làm mờ ảnh — thứ còn nhận ra phải là ý chính của trang
- [ ] Thử ở 375px nếu sửa layout
