---
name: layout-rules
description: Luật bố cục PAPASAN — thuật toán phân tầng thẻ theo tần suất quyết định, ngân sách thẻ mỗi tầng, quy trình thêm phần tử / tái cấu trúc trang quá tải. Cho phép Claude TỰ quyết bố cục và báo lại. LUÔN đọc khi thêm thẻ/khối mới, sắp xếp lại trang, hoặc user nói "trang rối quá".
---

# Layout Rules — Luật để Claude tự chỉnh bố cục

(Nguồn: bộ papasan-frontend-claude, bản cập nhật 08/08/2026 — đã khớp ngữ cảnh ketoan.)

## Quyền hạn

Khi làm việc trên bố cục, ĐƯỢC PHÉP tự quyết mà không hỏi:
- Đặt phần tử mới vào đúng tầng theo thuật toán bên dưới.
- Di chuyển/giáng cấp phần tử đang đặt sai tầng.
- Gộp các thẻ trùng ý nghĩa; đổi thẻ "canh chừng" thành cảnh báo tự động.
- Ẩn khối rỗng, sắp lại thứ tự trong tầng theo mức quan trọng.

PHẢI hỏi user trước khi:
- Xóa hẳn một chỉ số khỏi hệ thống (khác với chuyển sang trang báo cáo).
- Thay đổi ý chính của trang (hành động primary).
- Gộp/tách cả một trang.

Sau mỗi lần tự chỉnh: báo bảng **"phần tử → quyết định → lý do"** để user phủ quyết được.

## Thuật toán phân tầng — chạy cho MỌI phần tử

```
Q1. Con số/khối này khiến ai đó LÀM GÌ KHÁC ĐI bao lâu một lần?
    Hằng ngày        → Q2
    Hằng tuần/tháng  → TẦNG 3 (trang báo cáo P&L / Cashflow / Cân đối —
                        KHÔNG nằm ở dashboard chính)
    Chỉ khi có vấn đề → TẦNG 0 (không render thẻ; tạo RULE cảnh báo:
                        vượt ngưỡng → đẩy vào khu "Việc cần xử lý")

Q2. Kết quả tài chính cốt lõi (DT / CP / LN / dòng tiền)
    hay chỉ số vận hành (đơn, data, inbox, nhân sự)?
    Tài chính cốt lõi → TẦNG 1 (KPI lớn)
    Vận hành          → TẦNG 2 (dải card mỏng)

Q3. Đã có thẻ nào cùng nghĩa/cùng nguồn chưa?
    Có → GỘP (1 thẻ: số chính + số phụ ở caption), không tạo thẻ mới.
```

## Ngân sách thẻ — giới hạn cứng mỗi màn hình

| Khu | Tối đa | Ghi chú ketoan |
|---|---|---|
| Khu "Việc cần xử lý" | 1 khối | = `#kt-pending-card` trong index.html — đã ẩn khi rỗng, automation đẩy vào |
| Tầng 1 — KPI chính | 4 thẻ | số 29px (25px màn thấp) theo thang design-system, nên có delta so kỳ trước |
| Tầng 2 — Vận hành | 6 thẻ | card mỏng, số 18–20px |
| Tầng 3 — Biểu đồ | 4 khối | lưới 2 cột desktop |

**Luật tràn ngân sách**: user muốn thêm khi tầng đã đầy → KHÔNG lặng lẽ thêm,
KHÔNG từ chối. Chạy lại thuật toán cho toàn tầng → đề xuất phần tử yếu nhất bị
giáng cấp → trình bảng trước–sau trong cùng câu trả lời.

## Thẻ "canh chừng" → automation

Thẻ tồn tại chỉ để canh số bất thường (công nợ, quá hạn, đơn chưa ghi doanh thu,
chi vượt ngân sách) → chuyển thành rule `IF <ngưỡng> THEN đẩy vào Việc cần xử lý`;
số gốc xuống Tầng 2/3. Ngưỡng chưa có → hỏi user đúng 1 câu, không tự bịa.

## Lưới & responsive

- Desktop ≥1024px: Tầng 1 = 4 cột · Tầng 2 = 5–6 cột · Tầng 3 = 2 cột.
- Tablet 640–1023px: Tầng 1 = 2 cột; Tầng 3 = 1 cột.
- Mobile <640px: 1 cột; thứ tự DOM = thứ tự quan trọng (Việc cần xử lý → 1 → 2 → 3).
- Trong một tầng: trái→phải theo mức quan trọng giảm dần.
- Khối "Chưa có dữ liệu" chiếm ≥1/4 màn hình → thu thành card mỏng có empty
  state chuẩn (lý do + hành động), không giữ khung to trống.

## Quy trình tái cấu trúc trang quá tải

1. **Kiểm kê** mọi phần tử thành bảng.
2. **Chạy thuật toán** cho từng phần tử → cột "quyết định".
3. **Áp ngân sách** → xác định gộp / giáng cấp / chuyển cảnh báo.
4. **Trình bảng trước–sau** + lý do 1 dòng mỗi phần tử.
5. Mục trong quyền tự quyết → code luôn và báo lại; mục cần duyệt → chờ user.

## Ví dụ chuẩn (chính là Dashboard ketoan hiện tại)

| Phần tử | Q1 | Quyết định |
|---|---|---|
| Tổng doanh thu / chi phí / LN trước thuế | hằng ngày, tài chính | Tầng 1 |
| Biến phí / Định phí KT | hằng tuần | Tầng 3 — trang P&L; caption dưới thẻ Chi phí |
| Quỹ lương HCNS | hằng tháng | Tầng 3 — trang P&L |
| Số đơn, Data, Inbox MKT | hằng ngày, vận hành | Tầng 2 |
| Tổng nhân sự | khi có biến động | Tầng 0 — cảnh báo khi đổi; số ở trang nhân sự |
| Công nợ còn | khi có vấn đề | Tầng 0 — rule "quá X ngày" ; số ở Tầng 2 |
| Chi ADS MKT | hằng ngày, vận hành | Tầng 2 + rule "vượt Y% ngân sách" |

Kết quả mẫu: 14 thẻ → 3 KPI lớn + 5 thẻ mỏng + cảnh báo tự động.

## Riêng app này — bố cục THẬT đang chạy (đọc code 08/08/2026)

Dashboard `#page-bao-cao` trong `templates/index.html` **đang khít ngân sách,
không còn chỗ trống** — thêm bất kỳ thẻ nào là tràn, phải chạy luật tràn:

| Tầng | Đang có | Ngân sách | Vị trí trong code |
|---|---|---|---|
| Việc cần xử lý | 1 khối | 1 | `.pending-card#kt-pending-card` — `index.html:276`, `hidden` mặc định, JS mở ở dòng 345 |
| Tầng 1 — KPI | **4/4 ĐẦY** | 4 | `.stats-row` → `s-dt` Tổng Doanh Thu · `s-cp` Tổng Chi Phí · `s-lng` Lợi Nhuận Gộp · `s-lntt` LN Trước Thuế |
| Tầng 2 — Vận hành | **6/6 ĐẦY** | 6 | `.stats-row` `grid-template-columns:repeat(6,1fr)` → `s-don` · `s-ads` · `s-dataMkt` · `s-inboxMkt` · `s-nv` · `s-cn` |
| Tầng 3 — Biểu đồ | **4/4 ĐẦY** | 4 | 2 lưới `1fr 1fr`: Chi Phí Theo Loại · Doanh Thu Theo Loại · Doanh Số Theo NV · Chi Phí ADS Theo Kênh |

- **Hai thẻ tầng 2 đang sai tầng theo thuật toán** (bảng "Ví dụ chuẩn" ở trên đã
  kết luận): `s-nv` Tổng Nhân Sự → đáng lẽ Tầng 0 (cảnh báo khi biến động),
  `s-cn` Công Nợ Còn → Tầng 0 + rule quá hạn. Khi user xin thêm thẻ mới, **đây là
  hai ứng viên giáng cấp đầu tiên** — đề xuất kèm bảng trước–sau, đừng tự xoá.
- Mỗi KPI Tầng 1 đã có dòng caption 11px dưới số (`s-dt-sub`, `s-cp-sub`, hoặc
  công thức cố định `DT - Vốn - ADS`). **Thẻ mới phải có caption cùng kiểu** —
  luật module-notes: số tổng hợp phải truy ngược được về công thức/chứng từ gốc.
- Bề rộng khung: `--page-max: 1200px` (`static/css/base.css:20`, dùng ở dòng 72).
  Tính lưới theo con số này, đừng giả định `1440px`.
- Trang báo cáo Tầng 3 đã có sẵn, **đừng dựng lại**: `#page-pnl`, `#page-can-doi`,
  `#page-cashflow`, `#page-cpa-ads`. Chỉ số "hằng tuần/tháng" đẩy về đây.
- Tầng 2 hiện hard-code `repeat(6,1fr)` inline — sửa số cột thì sửa đúng chỗ đó,
  và kiểm lại mốc tablet/mobile (`base.css`), inline style không có media query.
