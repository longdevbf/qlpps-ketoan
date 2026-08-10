# Bàn giao đợt chuẩn hoá UI — Kế Toán V2

> Viết ngày **08/08/2026**, cuối phiên làm việc. Mọi số liệu trong file này
> **đếm lại bằng lệnh trên chính repo**, không chép từ trí nhớ.
> Đọc file này TRƯỚC khi làm tiếp bất kỳ việc UI nào của app kế toán.
>
> ⚠️ **CẬP NHẬT 10/08/2026:** đã có phiên đồng bộ UI toàn hệ 7 app.
> Trạng thái mới nhất + bẫy mới ở
> `papasan-erp-claude/BAN-GIAO-2026-08-10.md` — đọc file đó trước file này.

---

## 0. Đọc gì trước

| Thứ tự | File | Vì sao |
|---|---|---|
| 1 | File này | Trạng thái thật + việc còn nợ |
| 2 | [.claude/rules/design-system.md](.claude/rules/design-system.md) | Giới hạn cứng hệ màu, thang chữ, điều hướng — **đã viết lại 08/08** |
| 3 | [.claude/rules/frontend-ui.md](.claude/rules/frontend-ui.md) | 10 luật frontend |
| 4 | [CLAUDE.md](CLAUDE.md) | Kiến trúc app, chế độ mentor, điều cấm |

⚠️ `HE-MAU-ERP.md` **không còn đúng cho ketoan** — có banner cảnh báo ở đầu file.

---

## 1. Bối cảnh: người dùng muốn gì

Yêu cầu gốc: *"chỉnh sửa lại toàn bộ giao diện sao cho như luật, và như trang
dashboard đang làm rất tốt việc ấy"*. Sau đó bổ sung dần qua nhiều lượt:

1. Đổi hệ màu cho khớp logo, tối giản màu, chữ phân cấp rõ
2. Nền màn hình về trắng
3. Chữ to hơn 1–3px
4. Sửa responsive, làm cả giao diện điện thoại
5. Chuyển điều hướng từ header xuống **sidebar dọc bên trái**
6. Gộp tiêu đề trang + kỳ kế toán lên header, bỏ thanh `.topbar`
7. Bảng nào cũng phải thấy hết, không phải cuộn ngang

**Cách làm người dùng đã chốt**: làm **từng trang một**, mỗi lượt xong một
trang hoàn chỉnh rồi mới sang trang khác (không làm một lượt lớn toàn bộ).

---

## 2. Trạng thái hiện tại — đo được

```
hex ngoài hệ        : 0 file        (12 dòng màu biểu đồ trong index.html là ngoại lệ đã duyệt)
điểm gãy            : 480 / 768 / 1100   (đúng 3, theo base.css)
cỡ chữ              : 9 10 11 12 13 14 15 16 17 18 20 22 25 29
ô icon rỗng         : 0
phụ đề trôi nổi     : 0
nút nền đậm + chữ đậm: 0
mục sidebar         : 35 mục / 8 nhóm
ASSET_V             : 4        theme.css?v=4    ui-common.js?v=3    notifications_bell.js?v=5
```

Quét responsive **12 trang × 375px và 430px**: chỉ còn **1 chỗ** (mục 5).

---

## 3. Hệ màu — BẢN THỬ RIÊNG CỦA KETOAN

**Đã tách khỏi 6 app QLPPS kia.** Mỗi repo có `static/css/theme.css` riêng nên
sửa ketoan không lan sang app khác — đã kiểm chứng.

### Vì sao đổi

Đếm pixel `static/papasan_icon_1024.png`: logo chỉ có **2 màu** —
`#FEB041` hổ phách (13,7%) và `#603814` nâu cà phê (10,2%).
Brand cũ `#D23C0E` **không có trong logo** và lệch 21° hue.
Tệ hơn: `--warning:#F59E0B` gần trùng hổ phách logo → badge cảnh báo trông
"thương hiệu" hơn cả brand.

### Bảng token đang chạy

| Token | Giá trị | Ghi chú |
|---|---|---|
| `--brand` | `#9E5D09` | hổ phách hạ sáng để đạt AA (5,22:1) |
| `--brand-hover` | `#7F4B07` | chữ trên nền `--brand-soft` (5,96:1) |
| `--brand-soft` | `#FBE7C6` | nút chính, tab chọn, chip |
| `--bg-page` | `#FDF8F0` | **chỉ dùng cho bề mặt LÕM** (dải tổng, đầu bảng, hover) |
| `--bg-card` | `#FFFFFF` | thẻ, bảng, **và NỀN TRANG** |
| `--border` | `#E7D7BE` | mức duy nhất |
| `--text-1/2/3` | `#33210F` `#5E452C` `#7D6248` | 15,4 → 8,9 → 5,7:1 |
| `--warning` | `= --brand` | **cố ý trùng brand** |
| `--info` | `#7D6248` | **cố ý trung tính nâu** |
| `--danger` | `#B02A18` | |
| `--success` | `#2E7D4F` | |

Hai nước cờ bớt màu: `--warning` dùng lại brand, `--info` thành trung tính →
**cụm sắc trên một màn: 5 → 3** (hổ phách = cần bạn xử lý · lục = xong ·
đỏ = hỏng).

**Đường lùi**: khối "ĐƯỜNG LÙI" ở cuối `static/css/theme.css` có nguyên bảng cũ.

### Màu chuỗi biểu đồ (8 màu, ngoại lệ hard-code)

Ba biểu đồ tròn riêng (4 · 5 · 6 lát), màu **được phép lặp giữa các biểu đồ**.
Phân biệt **bằng ĐỘ SÁNG** chứ không chỉ bằng sắc — mù màu đỏ-lục trộn sắc
nhưng giữ độ sáng. Thang tương phản trải 3,3 → 14,2; tất cả ≥3:1.
Bảng đầy đủ trong `design-system.md`.

---

## 4. Những thứ đã đổi so với luật cũ

| Luật cũ | Nay | Lý do |
|---|---|---|
| "Điều hướng toàn bộ ở header, không sidebar" | **Sidebar dọc là nav chính** | 35 đích đến; sidebar đặt được số chờ duyệt ngay trên mục |
| "Tuyệt đối không sidebar dọc" | đã gỡ | như trên |
| Thang chữ dừng ở 22px | **+1px toàn dải**, nội dung chuẩn **14px**, thêm 17px | người dùng yêu cầu chữ to hơn |
| Mobile thu nhỏ chữ | **KHÔNG thu nhỏ chữ trên mobile** | màn nhỏ là lúc cần chữ to hơn |
| `--bg-page` làm nền trang | **nền trang = trắng**, `--bg-page` chỉ cho bề mặt lõm | người dùng yêu cầu |
| Không dùng icon | **SVG inline được dùng** cho icon sidebar + chuông | vẫn cấm emoji + icon font |

---

## 5. Việc CÒN NỢ — ưu tiên từ trên xuống

### 5.1. `e.message` đổ thẳng ra màn hình — **31 chỗ**

Người dùng nhìn thấy `{"error":"Not Found","code":404}` giữa trang
(đã gặp thật ở `/ho-so-ca-nhan`). Vi phạm frontend-ui luật 2 và luật 5.

**Đã có sẵn công cụ**, chỉ cần áp:

```js
// trong /static/js/ui-common.js — dùng toàn cục, không phải khai lại
khoiLoi(e, 'tenHamTaiLai')   // -> HTML đủ: lỗi gì + làm gì tiếp + nút Thử lại
loiNguoiDoc(e)               // -> {tieu_de, goi_y} nếu cần tự dựng
```

Đã áp cho 2 chỗ ở `ho_so_ca_nhan.html` làm mẫu. Tìm chỗ còn lại:

```bash
grep -rn 'innerHTML' templates/*.html | grep 'e\.message'
```

Nhiều chỗ nằm trong `<td colspan=N>` nên phải bọc lại cho đúng số cột.

### 5.2. `chat_widget.html` (302 KB) — chưa đụng

- `#0084FF` (màu Facebook) dùng làm màu chat
- Vài lớp phủ `rgba(0,0,0,…)` — riêng lớp phủ **video call** thì dùng đen là đúng
- 13 token tự khai riêng
- Cỡ chữ ngoài thang: 18, 20

### 5.3. Lỗi JS `items is not defined` — có sẵn từ trước

Xuất hiện ở nhóm trang cross-app. Đã xác minh **không phải** do đợt sửa UI này.

### 5.4. `#cashflow` còn 1 `div` hụt ~5px ở 430px

Chỗ duy nhất còn lại sau khi quét 12 trang × 2 khổ màn.

### 5.5. Hai đề xuất header chưa chốt

Chỗ giữa header còn trống. Đã đề xuất, người dùng **chưa quyết**:
- **Tìm nhanh (Ctrl+K)** — 35 màn hình thì tìm bằng chuột qua 8 nhóm là chậm
- **Trạng thái chốt sổ** cạnh ô chọn kỳ — kế toán nhìn nhầm kỳ là quyết định sai

### 5.6. Nợ cũ chưa liên quan đợt này

- Schema drift: `so_quy.ref_sepay` + bảng `sepay_transactions` chưa có migration
- Chưa có `tests/`
- Secret còn trong lịch sử git commit `974981c` → **phải rotate key**

---

## 6. Bẫy đã gặp — đừng lặp lại

| Bẫy | Biểu hiện | Cách tránh |
|---|---|---|
| **Grid/flex item `min-width:auto`** | bảng rộng đẩy cả trang cuộn ngang | thêm `min-width:0` cho item (`.main`, `.content`, `.right-panel`) |
| **`box-sizing` khai bằng `.x *`** | dấu sao chỉ áp cho CON, `.x` có `width:100%`+padding thì tràn | `.x,.x *{box-sizing:border-box}` |
| **Bảng không có `min-width`** | trình duyệt BÓP cột, hàng vắt 3 dòng | `min-width` cho bảng, để `.tbl-wrap` cuộn |
| **`white-space:nowrap` cho MỌI ô** | ô chữ dài bị cắt/chồng | dùng `min-width` cho bảng thay vì cấm xuống dòng |
| **Độ đặc hiệu CSS** | `.a.b .c` (3 class) thắng `body.x .c` (2 class + 1 thẻ) | viết đủ đặc hiệu, đừng đoán |
| **Dấu nháy ngược trong comment CSS-in-JS** | đóng template literal → vỡ file | `node --check` sau mỗi lần sửa JS |
| **`text-overflow:ellipsis`** | `scrollWidth > clientWidth` là CỐ Ý | bộ dò phải lọc bỏ, nếu không báo nhầm |
| **Nền đậm + chữ đậm** | nút Reset chữ tàng hình | đè nền thì phải đè cả `color` |
| **`input[type=month]`** | popup ngoài DOM, không style/đo được, tràn mép | dùng `<select>` — `.value` vẫn `YYYY-MM` |
| **Whitelist lệnh tự kiểm** | đổi hệ màu mà quên đổi whitelist → báo sai hàng loạt | sửa cả `design-system.md` và skill `ui-check` |

---

## 7. Công cụ kiểm tra — ở scratchpad

Đường dẫn:
`C:\Users\PC\AppData\Local\Temp\claude\c--PapasanIT-App-qlpps\<session>\scratchpad\`

| Script | Việc |
|---|---|
| `audit_mobile.py <out> <px>` | quét TOÀN BỘ trang: tràn ngang · nội dung bị cắt · ô bảng chồng chữ · vùng bấm nhỏ |
| `tim_spa.py <out> <px> <hash,hash>` | chỉ ra phần tử GỐC gây tràn trên trang SPA |
| `tim_tran.py <đường-dẫn> <px>` | như trên, cho trang riêng |
| `quet_tran.py` | quét tràn ngang mọi trang × 4 bề ngang |
| `palette.py` · `kiem_bo.py` | đo tương phản WCAG + khoảng cách màu ΔE + mô phỏng mù màu |
| `seed_ncc.py` | đổ dữ liệu mẫu Duyệt ĐX Trả NCC (idempotent, chỉ đụng id `DX-SEED-*`) |

**Chạy bằng venv của `qlpps-hcns`** — nó có Playwright 1.62 khớp chromium đã
cài; bản 1.61 của marketing lệch version nên không chạy:

```bash
"C:/PapasanIT/App_qlpps/qlpps-hcns/.venv/Scripts/python.exe" audit_mobile.py <out> 375
```

Trong Git Bash phải đặt `MSYS_NO_PATHCONV=1` khi truyền đường dẫn URL bắt đầu
bằng `/`, nếu không nó bị đổi thành đường dẫn Windows.

---

## 8. Môi trường chạy — điều PHẢI biết

- **Alias `muahang` đã trỏ về repo thật** (trước là stub) trong
  `ketoan-devrun/muahang/__init__.py`. Nhờ đó `/duyet-ncc` hết 500.
  Bản stub cũ lưu ở `scratchpad/muahang_stub_backup`.
- Đã đổ **8 đề xuất mẫu** vào `muahang.congno` (id `DX-SEED-*`), đủ 4 trạng thái.
- **Sửa template/CSS thì KHÔNG cần restart** (Jinja tự nạp lại). **Đổi alias
  Python thì PHẢI restart.**
- Trong phiên vừa rồi có lúc **2–3 tiến trình uvicorn cùng chạy**, và
  `netstat` hiện cả **socket ma của tiến trình đã chết**. Nếu sửa xong mà app
  không đổi: kiểm đúng tiến trình nào đang giữ cổng 8005 trước khi nghi code.

```bash
bash /c/PapasanIT/App_qlpps/ketoan-devrun/run.sh     # cổng 8005
```

---

## 9. Bản sao lưu

| Đường dẫn (scratchpad) | Nội dung |
|---|---|
| `backup2/` | `templates/` + `static/css/` trước đợt đổi hệ màu |
| `backup3/` | `templates/` trước đợt bỏ dải hero |
| `_header_before_sidebar.html` | header trước khi làm sidebar |
| `muahang_stub_backup/` | stub muahang cũ |

Scratchpad là thư mục tạm theo phiên — **muốn giữ lâu thì chép ra chỗ khác.**
