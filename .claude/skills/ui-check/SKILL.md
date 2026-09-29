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

> **Lệnh dưới theo hệ XANH — `--brand` `#2563EB` trên nền trắng ám xanh** (ADR-012,
> người duyệt chốt 11/09/2026, áp cả 8 app). Nguồn sự thật: `static/css/theme.css`
> (giá trị + tương phản đã tính, ghi ngay trong comment) và ADR-012 trong
> `QLPPS-UI-DOC/01-ADR.md` (vì sao chọn).
> `qlpps-marketing/docs/HE-MAU-ERP.md` là tài liệu của hệ cũ, đã lỗi thời — đừng tra.
> Whitelist lệnh 1 = mọi hex khai trong `theme.css`, TRỪ 4 màu chỉ làm nền ô icon
> (`7C3AED` `EA580C` `16A34A` `DC2626` — gọi qua `var(--tile-*)`), cộng ngoại lệ
> chuỗi biểu đồ `e67e22`. Whitelist mà lại chứa mã của các hệ đã bị thay — cam
> `A84A03` cùng hai ứng viên bị loại `CC4E05` `B85105` (26/08 → 11/09/2026), hổ
> phách `9E5D09`, cam đỏ `D23C0E` — là file này đã bị kéo về bản cũ: KHÔNG lấy
> nó sửa ngược template.

```bash
# 1. Hex ngoài hệ (rỗng = sạch; màu chuỗi biểu đồ là ngoại lệ hợp lệ; file chat
#    thuộc ngoại lệ của design-system thì chừa ra). Whitelist = hệ XANH ADR-012.
#    Lọc từng MÃ, không lọc cả dòng: khối alias đầu <style> hay dồn nhiều mã lên
#    một dòng, lọc theo dòng thì một mã hợp lệ che luôn các mã lạ đứng cạnh.
#    `[^&]` loại thực thể HTML như &#9776; (icon ☰) khỏi danh sách.
grep -noiE '(^|[^&])#[0-9a-f]{3,8}\b' templates/<file>.html | grep -viE \
 '#(2563EB|1D4ED8|1E40AF|EAF2FE|BFDBFE|3B82F6|FFFFFF|fff|EDF4FC|F4F7FB|E5EBF4|DFE6F0|EBF0F7|101C44|334166|5B6A80|15803D|DCFCE7|166534|B45309|FEF3C7|92400E|B91C1C|FEE2E2|991B1B|475569|E9EEF4|334155|0084FF|1877F2|0068FF|e67e22)$'
# 2. Mã của các hệ ĐÃ BỊ THAY: cam 26/08 → 11/09/2026 (A84A03 9A4703 E8EDF3 F2610E,
#    rgba 168,74,3, ứng viên loại CC4E05 B85105) + hổ phách + cam đỏ + kem ấm — phải rỗng
grep -niE '#(A84A03|9A4703|E8EDF3|F2610E|CC4E05|B85105|9E5D09|7F4B07|FBE7C6|EFE2CB|FDF8F0|E7D7BE|33210F|5E452C|795E43|D23C0E|BF370D|FBE5D0|EBE2D6|FAF5EF|E0D3C2|605D58)|168, *74, *3' templates/<file>.html
# 3. Token BỊA — phải rỗng. `--brand-ink` chưa từng tồn tại ở file nào của 8 app.
#    (`--brand-soft`, `--brand-hover` là token ĐANG DÙNG — đừng dọn chúng.)
grep -n 'brand-ink' templates/<file>.html
# 4. Đúng hệ nhưng dễ đặt sai vai — soi TỪNG dòng bằng mắt:
#    brand-bright / brand-graph / 3B82F6 (3.68 trên thẻ): chỉ số ≥24px đậm, icon
#      lớn, thanh biểu đồ — KHÔNG làm chữ nhỏ.
#    tile-* / 7C3AED EA580C 16A34A DC2626: CHỈ làm nền ô icon, gọi qua var(--tile-*).
#    FF8D28 không được xuất hiện.
grep -niE 'brand-bright|brand-graph|3B82F6|tile-|7C3AED|EA580C|16A34A|DC2626|FF8D28' templates/<file>.html
# Gradient & cỡ chữ lạ
grep -c 'linear-gradient\|radial-gradient' templates/<file>.html
grep -oE 'font-size:[0-9.]+px' templates/<file>.html | sort -u
```

- [ ] Lệnh 1–3 rỗng · [ ] lệnh 4 đã soi bằng mắt · [ ] gradient = 0 · [ ] cỡ chữ trong thang
- [ ] Nhấn là **khối đặc** `--brand` + chữ trắng, tối đa 1 khối/màn ngoài điều hướng
- [ ] Mục/hàng đang chọn, chip: nền `--brand-soft` + chữ `--brand-hover` (5.95)
- [ ] Chữ `--brand` KHÔNG nằm trên `--bg-band` (4.31 ✗) → dùng `--brand-hover`;
      chữ trạng thái đặt trên `--brand-soft`/`--bg-band` dùng `-fg`
- [ ] Nền thẻ/modal giữ trắng; header bảng `--bg-page` + `--text-3` IN HOA, KHÔNG
      tô `--brand-soft` (cần dải đậm hơn → `--bg-band`)
- [ ] Thẻ số liệu: nhãn `--text-3` 11px IN HOA · số 29px `--text-1`/`--kpi-*` — chênh ≥3×
- [ ] Một hàng thẻ không quá 3 màu `--kpi-*` khác nhau; `--kpi-brand` và
      `--kpi-data` cùng họ xanh — không đặt cạnh nhau
- [ ] Doanh thu không đỏ; **chi phí không đỏ mặc định**; badge dùng cặp `-soft`/`-fg`
- [ ] `--info` là xám slate CÓ CHỦ Ý (ADR-012) — đừng "sửa" pill thông tin sang xanh
- [ ] Viền màu card (nếu có) mang MỘT nghĩa nhất quán, không trang trí ngẫu nhiên
- [ ] Bố cục trong ngân sách thẻ của `layout-rules` (Tầng 1 ≤4, Tầng 2 ≤6, biểu đồ ≤4)

## 4. Trạng thái & hành vi

- [ ] Đủ 4 trạng thái loading/empty/error/data cho mọi khối async
- [ ] Empty nói vì sao + làm gì tiếp; error có nút thử lại
- [ ] Nút thao tác có CHỮ (không icon-only); xoá có confirm nêu hậu quả

## 5. Form

- [ ] Validate tại field khi blur; lỗi giữ dữ liệu đã nhập + focus field lỗi
- [ ] Thông báo lỗi nói rõ chuyện gì + bước tiếp theo

## 6. Kiểm bằng mắt thật (bắt buộc — luật 10 `frontend-ui.md`; màu đối chiếu `theme.css` + ADR-012)

- [ ] Chụp screenshot thật (Playwright/Chrome — dùng công cụ chụp sẵn có của app nếu có)
- [ ] Bắt cả `console.error` LẪN `pageerror` — hai loại khác nhau
- [ ] Trên ảnh: nút chính là khối xanh đặc chữ trắng, nền trang trắng ám xanh (ngoại
      lệ: ketoan tô `body` `--bg-card` trắng, chốt 08/08/2026). Còn mảng
      cam thương hiệu nào là trang đó còn hex cứng (hay gặp nhất: khối alias đầu
      `<style>`) không ăn theo `theme.css`. Cam còn lại chỉ được mang nghĩa cảnh báo
      (`--warning`, `--tile-orange`) hoặc là một chuỗi biểu đồ
- [ ] Test nheo mắt: làm mờ ảnh — thứ còn nhận ra phải là ý chính của trang
- [ ] Thử ở 375px nếu sửa layout
