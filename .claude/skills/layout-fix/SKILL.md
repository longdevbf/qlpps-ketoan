---
name: layout-fix
description: Tự phân tích và tái cấu trúc bố cục một trang theo luật phân tầng layout-rules. Dùng khi người dùng gõ /layout-fix <trang> hoặc nói "trang rối quá", "nhiều thẻ quá", "sắp xếp lại trang".
---

# /layout-fix — tái cấu trúc bố cục trang

Tái cấu trúc bố cục cho trang được nêu trong args (trống → trang đang làm việc
gần nhất). Làm theo skill `layout-rules`:

1. **Kiểm kê** mọi phần tử trên trang thành bảng.
2. **Chạy thuật toán phân tầng** (Q1→Q3) cho từng phần tử.
3. **Áp ngân sách thẻ** mỗi tầng; xác định phần tử cần gộp / giáng cấp /
   chuyển cảnh báo tự động / chuyển sang trang báo cáo.
4. **Trình bảng TRƯỚC–SAU** kèm lý do 1 dòng mỗi phần tử.
5. Quyết định trong quyền tự quyết → code luôn và báo lại. Quyết định cần
   duyệt (xóa hẳn chỉ số, đổi ý chính trang) → hỏi user trước.
6. Kết thúc: chạy checklist `/ui-check`, chụp screenshot thật, báo kết quả.
