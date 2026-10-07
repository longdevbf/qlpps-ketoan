"""Schema cho cảnh báo kỳ + đối chiếu sổ cái ↔ bảng nghiệp vụ (Đợt 1, 07/10/2026)."""
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel


class CanhBaoItem(BaseModel):
    ma: str
    muc: Literal["danger", "warning", "info"]
    tieu_de: str
    chi_tiet: str
    nguyen_nhan: list[str] = []
    so_tien: Optional[Decimal] = None
    lien_ket: Optional[str] = None
    ap_dung: list[Literal["cdkt", "kqkd", "lctt", "doi_chieu"]]


class LoiDocItem(BaseModel):
    ham: str          # hàm Python gặp lỗi — cho người sửa code, không hiện cho kế toán
    chi_tiet: str     # thông báo gốc của Postgres
    mo_ta: str = ""   # câu tiếng Việt để hiện trên màn hình


class CanhBaoOut(BaseModel):
    thang: str
    canh_bao: list[CanhBaoItem]
    loi_doc_du_lieu: list[LoiDocItem] = []


class DongDoiChieu(BaseModel):
    khoa: str
    nhan: str
    tk: list[str]
    bang: Optional[str] = None
    # None = nguồn đó không có cho dòng này (vd phải trả NV chỉ có ở sổ cái).
    # Bảng KQKD: `nghiep_vu` là đúng con số đang hiện trên Kết quả kinh doanh.
    so_cai: Optional[Decimal] = None
    nghiep_vu: Optional[Decimal] = None
    chenh: Optional[Decimal] = None
    # Nguồn báo cáo đang dùng. Cân đối: so_cai | nghiep_vu | khop (hai nguồn bằng nhau) | khac.
    # KQKD: nghiep_vu | so_cai | tron (cộng cả hai) | cong_thuc | chua_tinh (gán cứng 0).
    dang_dung: Literal["so_cai", "nghiep_vu", "khop", "khac", "tron", "cong_thuc", "chua_tinh"]


class DoiChieuOut(BaseModel):
    thang: str
    tu_ngay: str
    den_ngay: str
    can_doi: list[DongDoiChieu]
    kqkd: list[DongDoiChieu]
    loi_doc_du_lieu: list[LoiDocItem] = []
