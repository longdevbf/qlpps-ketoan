"""Ghi GIẢM công nợ NCC bên Kế toán khi một khoản trả nhà cung cấp thực sự được CHI.

Vì sao có file này (đo trên production 02/10/2026)
──────────────────────────────────────────────────
Tiền trả NCC đi ra khỏi quỹ qua HAI cửa, và trước đây KHÔNG cửa nào làm giảm
công nợ trong `ketoan.cong_no` — sổ CHUẨN:

  (1) Trang "Duyệt ĐX Trả NCC"  → `ketoan/app/routers/ncc_de_xuat.py::chi_ncc`
  (2) Trang "Đề nghị Thanh Toán" → `ketoan/app/routers/de_nghi_tt.py::chi_denghitt`

Cả hai chỉ ghi sổ quỹ rồi đặt `muahang.congno.da_chi = TRUE` — mà `da_chi` chỉ
làm giảm công nợ bên MUA HÀNG (`muahang/app/routers/congno.py` ~dòng 435:
`con_no = max(0, (thuc + can_kiem) − Σ de_xuat_tra.da_chi)`). Sổ Kế toán đứng im,
dù thông báo gửi nhân viên vẫn ghi "công nợ đã giảm" và docstring của
`chi_denghitt` vẫn ghi "giảm công nợ NCC luôn".

Hậu quả thật: 54 lần bấm Chi = 1.281.632.000đ, không lần nào tự giảm công nợ Kế
toán. Anh Quang phải tự tạo tay 11 dòng (268.925.000đ, `created_by='ceopps'`,
30/09) rồi thêm 1 dòng nữa cho phiếu quỹ #859 (70.000.000đ, bút toán V04) — và
vẫn sót phiếu quỹ #911 (CHIẾN PHƯƠNG 50.000.000đ, 30/09): tiền ra khỏi ACB mà
công nợ không giảm đồng nào.

Đặt ở tầng service để HAI cửa dùng CHUNG một hàm. Trước đây mỗi nơi tự làm một
kiểu là đúng nguyên nhân gốc của cả loạt lệch số phiên này (xem
`cong_no_from_order.py::_resolve_all_ncc` — Kế toán tự tính phân bổ giảm giá
khác Mua hàng suốt 5 tháng).

Hình dạng dòng ghi ra
─────────────────────
CỐ Ý giống hệt 11 dòng anh Quang đã tạo tay, để không phá cách đọc số đang dùng:

  so_tien = 0 · da_tra = số tiền chi · ref_id = 'mh-dexuat-{mã đề xuất Mua hàng}'

  * KHÔNG trừ vào một dòng nợ cụ thể nào — khớp đúng cách Kế toán đang làm; chọn
    hoá đơn nào để trừ là việc của người, không đoán hộ.
  * `con_lai` là cột GENERATED (so_tien − da_tra) nên không gán tay → luôn ÂM,
    và view `v_cong_no_phai_tra_phan_loai` xếp dòng này vào
    `loai_dong='tra_truoc_coc'`, `nhom_no='thuc'` → được tính TRỌN vào còn nợ.
  * KHÔNG gán `ma_don`: nếu gán, view sẽ nối dòng sang PO theo `ref_bao_gia` và
    có thể đổi `nhom_no` thành 'du_kien' → khoản đã chi bị ẩn khỏi "nợ thực".
  * `ref_id` là KHOÁ IDEMPOTENT DÙNG CHUNG cho cả hai cửa: trả bằng cửa nào thì
    cửa còn lại cũng không ghi trùng được. Đây là lý do khoá phải là mã đề xuất
    MUA HÀNG, không phải mã DNTT.

CẢNH BÁO — đừng gọi hàm này rồi commit riêng: nó chỉ `db.add` + `db.flush`, cố ý
KHÔNG commit, để nằm chung transaction với phiếu sổ quỹ. Chi và giảm nợ phải cùng
sống hoặc cùng chết; nếu tách ra sẽ lại sinh đúng cảnh "tiền ra mà nợ không giảm".
"""
from __future__ import annotations

import logging
from datetime import date as _date_cls
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CongNo
from .id_gen import next_cong_no_id

logger = logging.getLogger(__name__)

LOAI_CHI_TIET = "Công Nợ NCC"
REF_SOURCE = "muahang_chi"   # khớp 11 dòng anh Quang đã tạo tay 30/09/2026


def ref_id_giam_no(ma_de_xuat_mh: str) -> str:
    """Khoá idempotent dùng chung cho cả hai cửa chi."""
    return f"mh-dexuat-{ma_de_xuat_mh}"


def ghi_giam_cong_no_ncc(
    db: Session,
    *,
    ma_de_xuat_mh: str,
    ncc_ten: str,
    so_tien,
    by: str,
    ngay: Optional[_date_cls] = None,
    nguon: str = "",
) -> Optional[str]:
    """Ghi 1 dòng `ketoan.cong_no` làm giảm công nợ NCC. Trả id dòng mới, hoặc
    `None` nếu đã có (không tạo trùng).

    `ma_de_xuat_mh`: id bản ghi `muahang.congno` (loai='de_xuat_tra') — KHÔNG phải
    id DNTT. Đây là khoá nối hai cửa, xem docstring đầu file.
    `ngay`: mặc định hôm nay; truyền ngày phiếu quỹ khi ghi bù khoản cũ, nếu không
    số của tháng cũ sẽ bị đẩy sang tháng hiện tại.
    `nguon`: mô tả ngắn cửa nào chi, ghi vào ghi_chu để sau còn truy được.

    KHÔNG commit — caller gọi trong cùng transaction với sổ quỹ.
    """
    if not ma_de_xuat_mh:
        logger.warning("ghi_giam_cong_no_ncc: thiếu ma_de_xuat_mh — bỏ qua")
        return None
    tien = Decimal(str(so_tien or 0))
    if tien <= 0:
        logger.warning("ghi_giam_cong_no_ncc: so_tien=%s ≤ 0 (đề xuất %s) — bỏ qua",
                       tien, ma_de_xuat_mh)
        return None

    ref = ref_id_giam_no(ma_de_xuat_mh)
    if db.execute(
        select(CongNo.id).where(CongNo.ref_id == ref, CongNo.loai == "phai_tra")
    ).scalar_one_or_none() is not None:
        return None

    cid = next_cong_no_id(db)
    ten = (ncc_ten or "").strip() or "(Chưa rõ NCC)"
    db.add(CongNo(
        id=cid,
        ngay=ngay or _date_cls.today(),
        doi_tac=ten,
        so_tien=Decimal("0"),
        da_tra=tien,
        loai="phai_tra",
        loai_chi_tiet=LOAI_CHI_TIET,
        ref_id=ref,
        ref_source=REF_SOURCE,
        trang_thai="chua_tra",
        ghi_chu=(f"Ghi nhận khoản đã chi cho NCC {ten} — đề xuất Mua hàng "
                 f"{ma_de_xuat_mh}" + (f" ({nguon})" if nguon else "")),
        created_by=by,
    ))
    db.flush()
    return cid
