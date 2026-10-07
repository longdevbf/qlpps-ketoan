"""Pydantic schemas — SoQuy."""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from ..services.phan_loai_cf import KHOA_HOP_LE


# Phân loại dòng tiền (LCTT, mẫu B03) — danh sách khoá suy ra từ bảng duy nhất
# app/services/phan_loai_cf.py (form, API, báo cáo đều đọc ở đó). Thêm mã mới thì sửa ở đó, không sửa ở đây.
PHAN_LOAI_CF_VALUES = KHOA_HOP_LE
_PCF_PATTERN = "^(" + "|".join(PHAN_LOAI_CF_VALUES) + ")$"


class PhanLoaiCfOut(BaseModel):
    """Một mã dòng tiền trả cho ô chọn ở hộp "Lập phiếu thu / chi" (GET /api/so-quy/phan-loai-cf)."""
    khoa: str          # giá trị lưu vào so_quy.phan_loai_cf
    ma_so: str         # mã số B03 ('' = chuyển nội bộ, không lên báo cáo)
    ten: str           # nhãn đầy đủ
    ngan: str          # nhãn ngắn cho thẻ nhỏ ở bảng sổ quỹ
    loai: str          # 'thu' | 'chi'
    nhom: str          # hdkd | dautu | taichinh | noibo
    nhom_ten: str      # tên nhóm để gom <optgroup>


class SoQuyBase(BaseModel):
    ngay: date
    loai: str = Field(..., pattern="^(thu|chi)$")
    so_tien: Decimal = Decimal("0")
    tai_khoan: Optional[str] = None
    noi_dung: Optional[str] = None
    lien_quan: Optional[str] = None
    phan_loai_cf: Optional[str] = Field(default=None, pattern=_PCF_PATTERN)
    ref_id: Optional[str] = None
    ref_vc: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    nhan_vien_id: Optional[int] = None
    nhan_vien_ten: Optional[str] = None
    # Anh Quang 2026-06-06: Mã đơn báo giá liên kết (multi-cọc)
    ma_don: Optional[str] = None
    # Nghiệp vụ (q14, 01/10/2026). Có ma_dinh_khoan → máy chủ kiểm theo app/services/nghiep_vu_so_quy.py và TỰ
    # suy phan_loai_cf; không có → hành vi cũ (màn /app cũ, cầu nối). Kiểm định dạng ở service để báo lỗi tiếng Việt.
    ma_dinh_khoan: Optional[str] = Field(default=None, max_length=40)
    doi_tuong_loai: Optional[str] = Field(default=None, max_length=20)
    doi_tuong_ma: Optional[str] = Field(default=None, max_length=64)
    doi_tuong_ten: Optional[str] = Field(default=None, max_length=255)
    ky: Optional[str] = Field(default=None, max_length=7)


class SoQuyCreate(SoQuyBase):
    # Chỉ dùng khi có ma_dinh_khoan; không phải cột DB (router bỏ ra trước khi ghi).
    ly_do: Optional[str] = None             # hoan_tien_khach: 'tra_thua' | 'huy_coc' → ghi vào mo_ta
    xac_nhan_trung: Optional[bool] = None   # True = người dùng đã thấy cảnh báo "có thể đã ghi rồi" và vẫn lưu


class SoQuyUpdate(BaseModel):
    ngay: Optional[date] = None
    loai: Optional[str] = Field(default=None, pattern="^(thu|chi)$")
    so_tien: Optional[Decimal] = None
    tai_khoan: Optional[str] = None
    noi_dung: Optional[str] = None
    lien_quan: Optional[str] = None
    phan_loai_cf: Optional[str] = Field(default=None, pattern=_PCF_PATTERN)
    ref_id: Optional[str] = None
    mo_ta: Optional[str] = None
    ghi_chu: Optional[str] = None
    nhan_vien_id: Optional[int] = None
    nhan_vien_ten: Optional[str] = None
    ma_don: Optional[str] = None
    # Chỉ để router nhận ra và CHẶN đổi nghiệp vụ qua PUT (422) — gắn nghiệp vụ cho dòng có sẵn chưa hỗ trợ.
    ma_dinh_khoan: Optional[str] = None


class SoQuyOut(SoQuyBase):
    id: int
    tk_doi_ung: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DinhKhoanXemTruoc(BaseModel):
    """Cặp Nợ/Có của phiếu vừa lưu — CHỈ để hiển thị, chưa ghi sổ kế toán (không gọi post_journal)."""
    no_tk: str
    ten_no: str
    co_tk: str
    ten_co: str
    so_tien: Decimal
    che_do: str
    che_do_ten: str


class SoQuyTaoOut(SoQuyOut):
    """POST /api/so-quy: dòng vừa ghi + (khi có ma_dinh_khoan) định khoản xem trước và cảnh báo mềm."""
    dinh_khoan: Optional[DinhKhoanXemTruoc] = None
    canh_bao: list[str] = []


class ManRiengOut(BaseModel):
    ten: str
    url: str
    ly_do: str


class CanTruongOut(BaseModel):
    ten: str          # tên ô: ma_don | noi_dung | ncc | nhan_vien | ky | ly_do | quy_doi_ung …
    nhan: str         # nhãn tiếng Việt
    bat_buoc: bool


class NghiepVuOut(BaseModel):
    """Một việc trong ô "Việc gì?" (GET /api/so-quy/nghiep-vu). Tài khoản đã chọn theo chế độ TT133/TT99;
    'TIEN' / 'TIEN_DOI_UNG' = tài khoản tiền của quỹ đang chọn / quỹ đối ứng — trình duyệt tự thay."""
    khoa: str
    ten: str
    nhom: str
    loai: str
    thu_tu: int
    cho_phep: str                       # 'co' lập tay được · 'chuyen' lập ở màn khác
    man_rieng: Optional[ManRiengOut] = None
    tk_no: str
    tk_co: str
    ten_tk_no: str
    ten_tk_co: str
    b03_khoa: str
    b03_ma_so: str
    b03_ten: str
    can_truong: list[CanTruongOut]
    trang_thai_luat: str
    cho_xac_nhan: bool                  # luật chưa chốt → nhãn "Chờ kế toán xác nhận"
    canh_bao: Optional[str] = None
    ky_mac_dinh: Optional[str] = None   # 'thang_truoc' | 'thang_nay'


class NhomNghiepVuOut(BaseModel):
    ten: str
    thu_tu: int


class HayDungOut(BaseModel):
    khoa: str
    nhan: str


class LyDoHoanOut(BaseModel):
    ma: str
    nhan: str


class NghiepVuDsOut(BaseModel):
    che_do: str
    che_do_ten: str
    loai: str
    nhom: list[NhomNghiepVuOut]
    hay_dung: list[HayDungOut]
    ly_do_hoan: list[LyDoHoanOut]
    nghiep_vu: list[NghiepVuOut]


class TheoDonOut(BaseModel):
    """GET /api/so-quy/theo-don/{ma_don}: tên khách + đã thu / đã hoàn / còn lại của một mã đơn."""
    ma_don: str
    co_bao_gia: bool
    doc_duoc_bao_gia: bool
    khach: Optional[str] = None
    khach_id: Optional[str] = None
    tong_don: Optional[Decimal] = None
    da_thu: Decimal
    da_hoan: Decimal
    con_lai: Optional[Decimal] = None
    so_phieu: int
