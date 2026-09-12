---
paths:
  - "templates/**/*.html"
  - "static/**/*.css"
  - "static/**/*.js"
  - "shared/templates/**/*.html"
  - "shared/static/**/*.css"
---
<!-- SINH TỰ ĐỘNG — ĐỪNG sửa file này.
     Sửa `claude-kit/core/rules/icon-net-trang.md` (chung 7 app) hoặc `claude-kit/overlay/ketoan/rules/icon-net-trang.md` (riêng app này),
     rồi chạy: cd d:\PapaSanIT\claude-kit && python sync.py -->
# Icon có nền riêng — nét TRẮNG, nền ĐẶC

Quyết định của người duyệt, 11/09/2026 (ADR-009 + ADR-011 trong bộ tài liệu `QLPPS-UI-DOC`).
Thay hoàn toàn kiểu cũ **nền pastel + nét màu**. Không giữ kiểu cũ làm biến thể.
Nền phải **SÁNG như ảnh mẫu** — người duyệt: *"màu tôi muốn nó sáng như trong ảnh ấy"*.

## Luật

Icon nằm trong **khối nền riêng của nó** (tile vuông bo góc, huy hiệu tròn, ô icon) thì:

1. **Nét tạo hình màu trắng** — khối đặt `color: var(--text-on-brand)`, glyph dùng `currentColor`.
   Glyph **không** tự khai `fill` / `stroke` màu.
2. **Nền là màu ĐẶC, lấy từ bảng `--tile-*`** dưới đây. **Không bao giờ** nền pastel, `*-soft`,
   hex trần — và **không** sắc tối (`-fg`, `-hover`, sắc 700 trở xuống).

Ví dụ chuẩn — ảnh mẫu người duyệt gửi, màn Chấm công HCNS, đo bằng PIL: Ngày công `#2563EB` ·
Tổng giờ làm `#7C3AED` · Ngày thiếu giờ `#EA580C` · Lệnh đi `#16A34A`. Mỗi ô nền đặc, icon nét
trắng, cạnh đó số lớn + nhãn.

## ⚠️ Bẫy: đổi nét sang trắng mà QUÊN đổi nền → icon TÀNG HÌNH

Nét trắng trên các nền pastel đang có trong code: `#DBEAFE` **1,22:1** · `#FEE2E2` 1,22 ·
`#EDE9FE` 1,19 · `#FFEDD5` 1,15 · `#D1FAE5` 1,13 · `#CFFAFE` 1,12. Icon biến mất hoàn toàn.

**Đổi nền và nét trong CÙNG MỘT lần sửa.** Gặp tile nền pastel cũ khi đang sửa file → đổi cả hai.

## Nền được duyệt — bảng `--tile-*` (ADR-011)

Luật chọn: **mức "600" — sắc SÁNG NHẤT mà nét trắng vẫn đạt ≥ 3:1** (WCAG 2.1 SC 1.4.11).
Sáng hơn (mức 500) thì trượt ngưỡng; tối hơn (mức 700, `-fg`, `-hover`) thì đạt ngưỡng nhưng
**tối, trái ý người duyệt** — cả hai đều cấm.

| Nghĩa của ô | Modifier | Nền | Trắng trên nền |
|---|---|---|---|
| **Đếm · số liệu · thông tin chung — MẶC ĐỊNH** (không phải trạng thái info — info dùng `--tile-slate`, hàng dưới) | *(không)* | `var(--tile-blue)` #2563EB | 5,17 : 1 |
| Thời gian · nhóm phân loại thứ hai | `--tim` | `var(--tile-violet)` #7C3AED | 5,70 : 1 |
| Cần chú ý · thiếu · chờ · sắp hết hạn | `--warning` | `var(--tile-orange)` #EA580C | 3,56 : 1 |
| Tốt · đạt · đã duyệt · có mặt | `--success` | `var(--tile-green)` #16A34A | 3,30 : 1 |
| Xấu · lỗi · từ chối · quá hạn | `--danger` | `var(--tile-red)` #DC2626 | 4,83 : 1 |
| Trung tính · chưa phân loại · "info" của theme đang chạy (xám) | `--info` `--neutral` | `var(--tile-slate)` #475569 | 7,58 : 1 |
| Thương hiệu của app | `--brand` | `var(--tile-brand)` = `--brand-bright` #3B82F6 | 3,68 : 1 · cả 8 app |

Hàng có nhiều ô là **các phân loại rời** (như 4 ô Chấm công) thì mỗi ô một sắc khác nhau, đừng
lặp hai ô cùng sắc cạnh nhau. **Tím `#7C3AED` là ngoại lệ đã duyệt** của giới hạn "7 màu" trong
`design-system.md` — **chỉ** làm nền ô icon, không lan sang chữ, nút, viền.

**Token chỉ có ở repo đã nhận khối `--tile-*` từ `claude-kit`.** Trước khi dùng, kiểm:
`grep -c -- '--tile-blue' static/css/theme.css` → ra `0` thì **DỪNG**, báo người dùng "repo này
cần nhận khối `--tile-*` từ `claude-kit`". **Cấm** chữa cháy bằng hex hay bằng token tối.
Có ở cả 8 repo sau lần sync 11/09/2026 (hệ xanh ADR-012) — vẫn kiểm bằng lệnh trên,
repo nào ra `0` là chưa nhận sync.

**CẤM** làm nền ô icon:
- `var(--success)` `var(--warning)` `var(--danger)` `var(--kpi-data)` — sắc 700, **tối**.
- Mọi `var(--*-fg)` / `var(--*-hover)` — sắc 700–900 (token -fg/-hover), **tối** (đây là lỗi
  HCNS đã mắc). Hệ xanh: `--brand-hover` #1D4ED8 là blue-700.
- `var(--brand)` / `var(--accent)` — token của chữ và nút, không phải bảng nền ô. Ô thương hiệu
  dùng `var(--tile-brand)`, ô mặc định dùng `var(--tile-blue)`.
- `--*-soft`, mọi `--bg-*`, mọi hex.
- Sắc 500 "trông đẹp" nhưng trượt: cam `#F97316` 2,80 · lục `#22C55E` 2,28 · hổ phách `#F59E0B` 2,15.

## Phạm vi

| ÁP DỤNG — icon có nền riêng | KHÔNG áp dụng — giữ `currentColor` |
|---|---|
| Tile trong thẻ KPI / thẻ thống kê | Icon nav topbar, sidebar |
| Ô "Thao tác nhanh" | Icon trong nút có chữ (viền, ghost) |
| Icon đầu dòng panel thông báo | Icon trong ô nhập (kính lúp, lịch) |
| Icon loại tệp, icon khối "Hướng dẫn"/"Lưu ý" | Icon thao tác hàng bảng (mắt, ba chấm) |
| Huy hiệu tròn trong timeline, mini-stat | Icon inline cạnh chữ |

Nhóm bên phải **không có nền riêng** — nét trắng sẽ nằm trên nền trắng và biến mất.
Nguyên tắc chung một câu: **nền đặc → nét trắng.**

**Người duyệt đã xác nhận (11/09/2026): icon nav trên nền trắng GIỮ NGUYÊN, không đổi.**
Cấm "cải tiến" icon nav topbar/sidebar, icon inline hay icon trong ô nhập thành tile màu —
kể cả với lý do cho đồng bộ với thẻ KPI.

## Mã chuẩn

```css
/* class dùng chung, CSS trang chỉ được thêm modifier */
.ico-tile{
  display:inline-grid; place-items:center; flex:none;
  width:40px; height:40px; border-radius:var(--r-md);
  background:var(--tile-blue);         /* mặc định */
  color:var(--text-on-brand);          /* NÉT TRẮNG */
}
.ico-tile svg{ width:20px; height:20px; }   /* glyph tự dùng currentColor */
.ico-tile--tim    { background:var(--tile-violet); }
.ico-tile--warning{ background:var(--tile-orange); }
.ico-tile--success{ background:var(--tile-green);  }
.ico-tile--danger { background:var(--tile-red);    }
.ico-tile--info,
.ico-tile--neutral{ background:var(--tile-slate);  }
.ico-tile--brand  { background:var(--tile-brand);  }
```

Glyph Bootstrap Icons là dạng **tô** → `fill="currentColor"`; SVG nét → `stroke="currentColor"`.
**Đừng** đặt cả `fill` lẫn `stroke` cho glyph tô — nét bị dày, lỗ nhỏ bị bịt.

HCNS có sẵn cách dựng riêng `.so-ic` + biến `--ic-chu` (`static/css/man-hinh.css`) — **cùng luật**:
`--ic-chu` phải là `var(--tile-*)`.

```html
<!-- ✓ ĐÚNG -->
<span class="ico-tile ico-tile--warning" aria-hidden="true"><svg>…</svg></span>

<!-- ✗ SAI — kiểu cũ nền pastel + nét màu, đã bị bỏ -->
<span class="ico-tile" style="background:#FFEDD5;color:#EA580C">…</span>
<!-- ✗ SAI — nét trắng trên nền soft: tàng hình -->
<span class="ico-tile" style="background:var(--warning-soft)">…</span>
<!-- ✗ SAI — nền tối: đạt tương phản nhưng trái ảnh mẫu -->
<span class="so-ic" style="--ic-chu:var(--success-fg)">…</span>
```

Icon chỉ trang trí (có chữ nhãn đi kèm) → `aria-hidden="true"`. Icon mang nghĩa riêng, không có
chữ → `role="img" aria-label="…"`.

## `--info` ở theme đang chạy (ADR-012)

`--tile-*` và `--text-on-brand` có trong `theme.css` hệ xanh ở cả 8 app — code viết theo bảng
trên đúng sau sync. Theme đang chạy **GIỮ `--info` xám slate** `#475569`, cố ý: xanh nay là màu
thương hiệu, info mà xanh thì lẫn với mục đang chọn. Vì vậy `.ico-tile--info` → `--tile-slate`,
**không** chuyển sang `--tile-blue`. Nguồn: `theme.css` mục 7 · `QLPPS-UI-DOC/01-ADR.md`
(ADR-011, ADR-012). Bảng ở `01-ban-thao/09-he-icon.md §9.0` còn ghi `.ico-tile--info` →
`--tile-blue` theo bản thảo (`--info` xanh) — điểm đó **không áp**, ADR-012 đã thay.

## Tự kiểm trước khi báo xong

```bash
# Repo đã có bảng --tile-* chưa? (phải > 0 mới được dùng)
grep -c -- '--tile-blue' static/css/theme.css
# Tile nào còn nền soft / pastel? (phải rỗng)
grep -rnE 'ico-tile[^>]*(-soft\)|#(DBEAFE|D1FAE5|EDE9FE|FFEDD5|CFFAFE|FEE2E2))' templates/ static/
# Ô icon nào đang lấy nền TỐI? (phải rỗng)
grep -rnE '(ico-tile|so-ic|ic-chu)[^>]*var\(--[a-z]+-(fg|hover)\)' templates/ static/
# Theme có bí danh --accent chưa? Ra 0 (repo chưa nhận hệ xanh) thì lệnh kế tiếp phải rỗng
grep -cE -- '^\s*--accent\s*:' static/css/theme.css
grep -rn 'var(--accent' templates/ static/css/ | grep -v theme.css
# Tương phản của một màu nền với nét trắng
python -c "import sys;h=sys.argv[1].lstrip('#');f=lambda c:c/12.92 if c<=.03928 else((c+.055)/1.055)**2.4;L=sum(w*f(int(h[i:i+2],16)/255) for w,i in((.2126,0),(.7152,2),(.0722,4)));r=1.05/(L+.05);print(f'{r:.2f}:1',('DAT' if r>=3 else 'TRUOT'))" "#16A34A"
```

Và **xem ảnh thật**: icon phải nhìn rõ nét trắng trên nền đặc. Chưa nhìn ảnh thì chưa xong.
