"""Phần dùng chung của hai cửa chi phía Kế toán — Đề nghị TT (de_nghi_tt.py) và Trả NCC (ncc_de_xuat.py) —
cho Việc 3 (08/10/2026): trước khi ghi sổ, kế toán ghi người nhận, ngày nhận và (khi được phép) đổi loại chi phí.

Cửa chi thứ ba (Đề xuất chi) nằm ở shared/routers/duyet_chi.py. Các hàm dưới đây GỌI LẠI đúng luật của bản đó
(`_ngay_ghi_so`, `_loai_chi_khi_chi`) chứ không viết luật thứ hai — hai bản luật sớm muộn sẽ lệch nhau.

Vì sao phải đỡ bản shared CŨ: shared/ và app Kế toán triển khai TÁCH NHAU (de_xuat_chi_tu_choi.py ghi: vps.py
không triển khai shared/). App mới gặp shared cũ thì:
  - `_ngay_ghi_so` chưa có tham số `nhan` → TypeError → kiểm lại không nhãn (vẫn chặn đúng, câu lỗi ghi "Ngày chi");
  - `_loai_chi_khi_chi` chưa có → chỉ riêng việc ĐỔI loại bị từ chối (409), chi theo loại gợi ý vẫn chạy.
Hàm MỚI của shared phải import LAZY (trong hàm): import đầu file thì gặp shared cũ là cả app không khởi động.
"""
import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from shared.routers.duyet_chi import _ngay_ghi_so  # có từ trước Việc 3 → import đầu file an toàn

logger = logging.getLogger(__name__)

# Nhãn "Hạch toán vào" của khoản trả nợ NCC — tiền trả nợ làm giảm Nợ phải trả (TK 331), không phải chi phí.
HACH_TOAN_TRA_NCC = "Trả nợ NCC — giảm Nợ phải trả (TK 331)"


def nguoi_nhan_chuan(gia_tri: Optional[str]) -> Optional[str]:
    """Bỏ khoảng trắng hai đầu; rỗng → None (= không ghi gì, y hệt trước Việc 3)."""
    return (gia_tri or "").strip() or None


def ngay_nhan_hop_le(ngay: Optional[date]) -> Optional[date]:
    """Ngày nhận theo ĐÚNG luật Ngày chi: không ở tương lai, không lùi quá 1 năm. None → None.

    KHÔNG ràng buộc với ngày chi — người dùng chốt 07/10/2026: bên nhận nhận trước hay sau ngày chi đều được.
    """
    if ngay is None:
        return None
    try:
        return _ngay_ghi_so(ngay, None, nhan="Ngày nhận")
    except TypeError:
        logger.warning("shared/ cũ: _ngay_ghi_so chưa có tham số nhan — kiểm Ngày nhận với câu lỗi 'Ngày chi'")
        return _ngay_ghi_so(ngay, None)


def chan_doi_loai_tra_ncc(chon: Optional[str]) -> None:
    """Khoản trả nợ NCC hạch toán KHOÁ ở Nợ 331 — gửi bất kỳ loại chi phí nào lên cũng là 422."""
    if (chon or "").strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Khoản trả nợ nhà cung cấp ghi giảm Nợ phải trả NCC (TK 331), không phải chi phí — không đổi được "
            "loại chi phí. Bỏ trống ô Hạch toán vào rồi bấm Chi lại.",
        )


def loai_khi_chi(db: Session, goi_y: tuple, chon: Optional[str]) -> tuple:
    """(tên loại, nhóm) sau khi áp lựa chọn của kế toán — CÙNG luật với cửa Đề xuất chi.

    Không chọn hoặc chọn trùng gợi ý → trả nguyên `goi_y` mà không cần tới shared mới.
    """
    ten = (chon or "").strip()
    if not ten or ten == goi_y[0]:
        return goi_y
    try:
        from shared.routers.duyet_chi import _loai_chi_khi_chi  # lazy — hàm này chỉ có từ Việc 3
    except ImportError:
        logger.warning("shared/ cũ: chưa có _loai_chi_khi_chi — từ chối đổi loại chi phí sang %r", ten)
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Máy chủ chưa cập nhật phần dùng chung nên chưa đổi được loại chi phí. Giữ loại gợi ý "
            f"'{goi_y[0]}' để chi, và báo quản trị cập nhật máy chủ.",
        )
    return _loai_chi_khi_chi(db, goi_y, ten)
