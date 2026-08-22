---
paths:
  - "templates/**/*.html"
  - "static/**/*.css"
  - "static/**/*.js"
  - "shared/templates/**/*.html"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/frontend-ui.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/frontend-ui.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->

# Luật Frontend PAPASAN — 10 luật cứng (chung 7 app QLPPS)

Nguồn: bộ `papasan-erp-claude` (chuẩn hoá từ app Kế Toán 08/08/2026). Vi phạm là
**lỗi**, không phải "tuỳ chọn thẩm mỹ". Chi tiết kỹ thuật: skill `ui-standards`.
Trước khi báo xong việc UI: chạy `/ui-check`.

Thay đổi vị trí/số lượng phần tử trên màn hình: đọc skill `layout-rules` —
skill này cho quyền TỰ quyết bố cục theo thuật toán phân tầng, chỉ cần báo lại
quyết định (lệnh nhanh: `/layout-fix <trang>`).

1. **Số liệu phải khớp nhau.** Các con số đứng cạnh nhau phải đối chiếu được
   (`Doanh thu − Chi phí = Lợi nhuận`; tổng các phần biểu đồ = số ở KPI card).
   Nguồn không khớp → hiển thị cảnh báo "X tr chưa gán danh mục", KHÔNG âm thầm
   render. Công thức KPI tính ở MỘT nơi (backend `app/services/` hoặc một hàm JS
   dùng chung) — cấm tính lại rải rác.

2. **Cấm lộ tên biến kỹ thuật ra giao diện.** `nhan_su`, `created_at`,
   `cho_duyet`… không bao giờ xuất hiện trên màn hình. Mọi key đi qua map nhãn
   (`STATUS_LABEL`). Key thiếu nhãn → fallback "Chưa đặt tên" + `console.warn`,
   không render key thô.

3. **Màu là ngôn ngữ.** Chỉ dùng `var(--token)` từ `theme.css` (xem
   `design-system.md`). Ngữ nghĩa cố định: lục = tốt/tăng · đỏ = xấu/lỗ/xoá ·
   vàng = cần chú ý · xanh dương = thông tin · `--text-1` = số liệu thường.
   **Doanh thu không tô đỏ.** Mỗi màn hình tối đa MỘT nút nhấn chính (pastel
   brand-soft), còn lại outline/ghost.

4. **Mỗi màn hình một ý chính.** Trả lời trước khi code: "người dùng vào trang
   này để làm gì nhất?" → phần tử đó to nhất, mắt chạm đầu tiên. Dashboard chia
   2 tầng: KPI chính (card lớn) và chỉ số vận hành (dải card mỏng) — cấm lưới
   card đều tăm tắp.

5. **Đủ 4 trạng thái.** Mọi khối dữ liệu async phải có: loading (skeleton) ·
   empty (vì sao trống + làm gì tiếp) · error (lỗi gì + cách sửa + nút thử lại)
   · data. Khối cảnh báo khi RỖNG → ẩn hẳn, không render "Không có gì".

6. **Format số & tiền thống nhất.** Một hàm format dùng chung, cấm format tay
   tại chỗ. Tiền: `1.250.000 đ` hoặc `1,25 tr` — một chuẩn cho mỗi ngữ cảnh,
   không trộn trong cùng dải card. Số đếm kèm đơn vị chữ (`2.520 data`) để không
   nhầm với tiền.

7. **Form phải tha thứ.** Validate tại field khi blur. Lỗi submit: giữ nguyên
   dữ liệu, focus field lỗi đầu. Xoá/không hoàn tác → confirm nêu hậu quả.
   Thông báo lỗi = chuyện gì sai + bước tiếp theo; cấm "Đã xảy ra lỗi".

8. **Mobile & accessibility mặc định.** Vùng bấm ≥ 44×44px trên mobile.
   Contrast ≥ 4.5:1 (hệ màu đã đo — đừng chế màu mới). Cỡ chữ theo THANG của
   `design-system.md` (13px là chuẩn nội dung app nội bộ — KHÔNG áp "≥16px" của
   web công cộng). `button` là button, không `div onclick`. Test 375px trước
   desktop.

9. **Hiệu năng là trải nghiệm.** Ảnh có width/height + lazy load dưới fold.
   Không thêm thư viện/CDN mới (giới hạn số 7 của design system). Animation
   200–300ms có mục đích; tắt đi mà không tệ hơn → bỏ.

10. **Tự review trước khi báo xong.** Chạy `/ui-check` với mọi thay đổi UI.
    Chụp screenshot thật và soi "test nheo mắt": làm mờ ảnh, thứ duy nhất còn
    nhận ra phải là ý chính của trang.

## Quy trình chuẩn

1. Thiếu spec (màu nhấn? hành động chính? nguồn dữ liệu?) → **hỏi, không đoán**.
2. Đọc token (`theme.css` + `ui-standards`) trước khi viết style.
3. Component đủ 4 trạng thái ngay từ đầu — không "làm empty state sau".
4. Sửa UI cũ: **cắt trước, chỉnh sau** — liệt kê phần tử bỏ được trước khi đổi màu.
5. Kết thúc task: `/ui-check`, báo pass/fail từng mục.
