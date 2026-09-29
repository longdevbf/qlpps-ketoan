"""Mã sản phẩm kho kế toán (ketoan.product.ma_sp) theo kiểu danh mục chung: KHÔNG DẤU, VIẾT HOA, nối "_"
(vd "Bập Bênh Mây" → BAP_BENH_MAY — trùng mã shared.products). Anh Quang 28/09/2026: "mã sản phẩm đang để tiếng
Việt, chỉnh về tiếng Anh như kế toán cũ". Trước đó mã tự sinh giữ nguyên dấu và nối "-" (BẬP-BÊNH-MÂY).
"""
import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from .tim_kiem import bo_dau_py

DO_DAI_MA = 48
_KHONG_HOP_LE = re.compile(r"[^A-Z0-9]+")
_MA_CHUAN = re.compile(r"^[A-Z0-9_]+$")


def ma_khong_dau(chuoi: Optional[str]) -> str:
    """'Bàn trà 1mx0,5m' → 'BAN_TRA_1MX0_5M'."""
    return _KHONG_HOP_LE.sub("_", bo_dau_py(chuoi).upper()).strip("_")[:DO_DAI_MA].strip("_")


def ma_kieu_cu(ten: Optional[str]) -> str:
    """Mã tự sinh kiểu cũ (còn dấu, nối '-') — chỉ để TÌM sản phẩm đã tạo trước khi đổi quy tắc."""
    out = []
    for ch in (ten or "").strip().upper():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "-", "_"):
            out.append("-")
    return "".join(out)[:DO_DAI_MA].strip("-")


def ma_danh_muc_chung(db: Session, ten: Optional[str]) -> Optional[str]:
    """Mã của sản phẩm cùng tên (so không dấu) trong danh mục chung shared.products, nếu có đúng 1."""
    if not ten:
        return None
    rows = db.execute(
        text("SELECT ma_sp FROM shared.products WHERE ketoan.bo_dau(ten_sp) = ketoan.bo_dau(:t) AND ma_sp IS NOT NULL"),
        {"t": ten},
    ).scalars().all()
    return rows[0] if len(rows) == 1 else None


def ma_moi_cho(db: Session, ten: Optional[str], goc: Optional[str] = None) -> str:
    """Mã chuẩn cho một sản phẩm: ưu tiên mã danh mục chung cùng tên, không thì bỏ dấu từ tên (hoặc mã gốc)."""
    return ma_danh_muc_chung(db, ten) or ma_khong_dau(ten) or ma_khong_dau(goc)


def chuan_hoa_ma_kho(db: Session, *, ghi: bool = False) -> list[dict]:
    """Đổi mọi ma_sp còn dấu / ký tự lạ trong ketoan.product sang mã chuẩn, giữ duy nhất (thêm _2, _3…).

    Chạy một lần khi triển khai (cần duyệt trên production). ghi=False: chỉ trả danh sách dự kiến.
    Liên kết kho/BOM/phiếu kho dùng product_id nên không bị ảnh hưởng.
    """
    ds = db.execute(text("SELECT id, ma_sp, ten_sp FROM ketoan.product ORDER BY id")).all()
    dang_dung = {r.ma_sp for r in ds}
    thay_doi = []
    for r in ds:
        if r.ma_sp and _MA_CHUAN.match(r.ma_sp):
            continue
        goc = ma_moi_cho(db, r.ten_sp, r.ma_sp) or f"SP_{r.id}"
        moi, i = goc, 2
        while moi in dang_dung:
            moi, i = f"{goc}_{i}", i + 1
        dang_dung.discard(r.ma_sp)
        dang_dung.add(moi)
        thay_doi.append({"id": r.id, "cu": r.ma_sp, "moi": moi, "ten": r.ten_sp})
        if ghi:
            db.execute(text("UPDATE ketoan.product SET ma_sp = :m, updated_at = now() WHERE id = :i"), {"m": moi, "i": r.id})
    if ghi:
        db.commit()
    return thay_doi
