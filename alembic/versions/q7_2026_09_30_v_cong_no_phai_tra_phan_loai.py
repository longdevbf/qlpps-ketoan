"""Add view ketoan.v_cong_no_phai_tra_phan_loai — 1 dòng/dòng ketoan.cong_no phai_tra,
phân loại nguồn (đơn mua/cước ĐVVC/cọc trả trước/nhập tay) + nhóm nợ (thực/dự kiến/cần kiểm).

Quyết định người dùng 30/09/2026: view q6 (`ketoan.v_nhom_no_don`) chỉ trả lời
"đơn mua này (PO) thuộc nhóm nợ nào" — mỗi nơi đọc (ncc-module, ncc-summary,
_tong_hop, _phai_tra_ncc, bản in) phải TỰ nối lại (REGEXP_MATCH ref_id → PO,
rồi trường hợp cọc/trả trước tự nối tiếp qua ma_bao_gia=ma_don) — 4 CHỖ LẶP
CÙNG MỘT LOGIC NỐI, có nguy cơ trôi (như regex cũ từng hụt 22/296 dòng).

Migration này gom cả bước NỐI vào MỘT view theo DÒNG (không phải theo PO):
mỗi dòng `ketoan.cong_no` (loai='phai_tra') ra đúng 1 dòng kết quả, đã có sẵn
`nhom_no` cuối cùng — nơi đọc chỉ cần `JOIN v ON v.id = cn.id`, không tự
REGEXP_MATCH/phân biệt cọc nữa. Đây là VIEW THỨ 5 (không phải bản định nghĩa
thứ 5 song song) — nó ĐỌC q6 + `ketoan.cong_no`, không định nghĩa lại 3 nhóm.

`khoa_ncc` chuẩn hoá tên đối tác (bỏ mọi cụm "(...)", hạ chữ thường, gộp
khoảng trắng) — CÙNG logic `_norm_key()`/`_strip_brackets()` ở
app/routers/cong_no_ncc.py:503-514, để phía Mua hàng gộp "A ĐẠT" và
"A ĐẠT -ME TÂY" đúng như Kế toán đang gộp trên màn Công nợ NCC.

Bốn `loai_dong`:
  - don_mua:         ref_id LIKE 'MH-%' — nối PO qua REGEXP_MATCH (cùng cách
                      đã sửa ở cong_no_ncc.py SỬA LỖI NỐI PO 2026-09-30).
  - cuoc_dvvc:        ref_source = 'saleadmin_vc_phai_tra'.
  - tra_truoc_coc:    so_tien = 0 AND da_tra > 0 (không phải don_mua/cuoc_dvvc)
                      — cọc/đặt cọc nhập tay, đi theo nhóm của PO có
                      ma_bao_gia = ma_don nếu khớp đúng 1 (ma_bao_gia UNIQUE
                      trên purchase_orders — không có case nhiều PO phải phân
                      biệt, xem cong_no_ncc.py SỬA LỖI 3 2026-09-30).
  - nhap_tay_dau_ky:  còn lại (nhập tay không phải cọc, đầu kỳ...).

`nhom_no` giữ ĐÚNG quy tắc hiện có ở 4 nơi đọc (cong_no_ncc.py, cong_no_dong_bo.py,
bao_cao_can_doi.py): don_mua/tra_truoc_coc nối được PO → COALESCE(q6.nhom_no,
'can_kiem'); còn lại (cuoc_dvvc/nhap_tay_dau_ky, hoặc tra_truoc_coc không khớp
PO) → 'thuc' (giữ hành vi cũ: nợ không gắn đơn mua coi là đã chốt).

BẪY COLLATE: bản thân view q6 đã ép COLLATE "und-x-icu" cho so sánh nhãn tiếng
Việt; view này KHÔNG so sánh nhãn trực tiếp (chỉ JOIN qua q6.nhom_no đã tính
sẵn), nhưng `khoa_ncc` dùng `lower()` trên tên đối tác có dấu — production
datctype=C không hạ đúng chữ hoa có dấu (lower('Đã Giao') vẫn giữ 'Đ') nên
cũng ép COLLATE "und-x-icu" cho an toàn, cùng lý do đã ghi ở migration q6.

SỬA LỖI 2026-09-30 (kiểm chứng độc lập, 180/350 dòng sai): regex bỏ cụm
"(...)" dùng `\s`/`\(`/`\)` (cú pháp lớp ký tự tắt kiểu Perl/PCRE) — Python
string `'\\s*\\([^)]*\\)\\s*'` tự nó đúng cú pháp, nhưng khi chuỗi SQL này đi
qua op.execute()/SQLAlchemy rồi Postgres LƯU LẠI định nghĩa view, backslash bị
NHÂN ĐÔI (`pg_get_viewdef` trả `\\s`, tức 2 backslash thật trước mỗi `s`) —
khiến regex đã lưu khớp literal "\s" thay vì lớp ký tự khoảng trắng, nên cụm
"(...)" không bị xoá cho tên có dấu tiếng Việt (khớp Unicode qua COLLATE làm
lộ khác biệt mà tên ASCII thuần không lộ). Đổi sang lớp POSIX `[[:space:]]`,
`[(]`, `[)]` — không dùng backslash nên tránh hẳn vấn đề escape khi lưu view.

Revision ID: q7_2026_09_30
Revises: q6_2026_09_30
"""
from typing import Union

from alembic import op

revision: str = "q7_2026_09_30"
down_revision: Union[str, None] = "q6_2026_09_30"
branch_labels = None
depends_on = None


_CREATE_VIEW = """
CREATE OR REPLACE VIEW ketoan.v_cong_no_phai_tra_phan_loai AS
SELECT
    cn.id,
    cn.doi_tac,
    NULLIF(
        TRIM(REGEXP_REPLACE(lower(COALESCE(cn.doi_tac, '') COLLATE "und-x-icu"), '[[:space:]]*[(][^)]*[)][[:space:]]*', ' ', 'g')),
        ''
    ) AS khoa_ncc,
    CASE
        WHEN COALESCE(cn.ref_id, '') LIKE 'MH-%' THEN 'don_mua'
        WHEN COALESCE(cn.ref_source, '') = 'saleadmin_vc_phai_tra' THEN 'cuoc_dvvc'
        WHEN cn.so_tien = 0 AND cn.da_tra > 0 THEN 'tra_truoc_coc'
        ELSE 'nhap_tay_dau_ky'
    END AS loai_dong,
    CASE
        WHEN COALESCE(cn.ref_id, '') LIKE 'MH-%' THEN COALESCE(v_mh.nhom_no, 'can_kiem')
        WHEN cn.so_tien = 0 AND cn.da_tra > 0 AND v_coc.nhom_no IS NOT NULL THEN v_coc.nhom_no
        ELSE 'thuc'
    END AS nhom_no,
    COALESCE(po_mh.id, po_coc.id) AS po_id,
    cn.so_tien,
    cn.da_tra,
    cn.con_lai,
    cn.trang_thai,
    cn.ngay,
    cn.ma_don,
    cn.ref_id
FROM ketoan.cong_no cn
LEFT JOIN muahang.purchase_orders po_mh
       ON COALESCE(cn.ref_id, '') LIKE 'MH-%'
      AND po_mh.id = (REGEXP_MATCH(cn.ref_id, 'ORD-[0-9]+-[0-9]+'))[1]
LEFT JOIN ketoan.v_nhom_no_don v_mh ON v_mh.po_id = po_mh.id
LEFT JOIN muahang.purchase_orders po_coc
       ON COALESCE(cn.ref_id, '') NOT LIKE 'MH-%'
      AND cn.so_tien = 0 AND cn.da_tra > 0
      AND po_coc.ref_bao_gia = cn.ma_don
LEFT JOIN ketoan.v_nhom_no_don v_coc ON v_coc.po_id = po_coc.id
WHERE cn.loai = 'phai_tra'
"""

_DROP_VIEW = "DROP VIEW IF EXISTS ketoan.v_cong_no_phai_tra_phan_loai"


def upgrade() -> None:
    op.execute(_CREATE_VIEW)


def downgrade() -> None:
    # DROP VIEW — view không lưu dữ liệu riêng, chỉ đọc từ ketoan.cong_no + v_nhom_no_don,
    # nên xoá không mất gì; nơi đọc phải tự lùi cách nối trước khi downgrade migration này.
    op.execute(_DROP_VIEW)
