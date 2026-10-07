"""Pydantic schemas — đối chiếu tồn kho Kế toán ↔ Kho mới Mua hàng (chỉ đọc)."""
from datetime import date
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, PlainSerializer

# Tính bằng Decimal, ra JSON là SỐ (như các endpoint external khác) — Pydantic v2 mặc định
# in Decimal thành chuỗi, sẽ làm vỡ phép cộng ở trình duyệt.
Tien = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class TongKeToan(BaseModel):
    nguon: str
    so_dong: int
    so_dong_con_ton: int
    so_mat_hang_con_ton: int
    sl: Tien
    gt: Tien
    dong_het_hang_chua_chuyen: int


class TongMuaHang(BaseModel):
    nguon: str
    so_sku: int
    so_sku_con_ton: int
    sl: Tien
    gt: Tien


class Chenh(BaseModel):
    sl: Tien
    gt: Tien


class PhanRa(BaseModel):
    da_tru_bang_cu: Chenh
    nhap_tay: Chenh
    khac: Chenh
    lech_gia: Chenh


class ThanhPhan(BaseModel):
    da_tru_bang_cu: Tien
    nhap_tay: Tien
    khac: Tien


class DongDoiChieu(BaseModel):
    ma_sp: str
    ten_sp: str
    nhom: Optional[str] = None
    ma_bang_cu: list[str]
    so_dong_bang_cu: int
    kt_sl: Tien
    kt_gt: Tien
    mh_sl: Tien
    mh_gia: Tien
    mh_gt: Tien
    chenh_sl: Tien
    chenh_gt: Tien
    nhan_ma: str
    nhan: str
    nhan_mau: str
    thanh_phan: ThanhPhan
    khac_gia: bool
    canh_bao: list[str]
    trung_ten_voi: list[str]


class TheoNhan(BaseModel):
    nhan_ma: str
    nhan: str
    nhan_mau: str
    so_dong: int
    chenh_sl: Tien
    chenh_gt: Tien


class TonKhoDoiChieuOut(BaseModel):
    ghi_chu: str
    ke_toan: TongKeToan
    mua_hang: TongMuaHang
    chenh: Chenh
    phan_ra: PhanRa
    ngay_chuyen_kho_moi: Optional[date] = None
    so_cap_trung_ten: int
    so_sku_gia_0: int
    theo_nhan: list[TheoNhan]
    dong: list[DongDoiChieu]
