"""Bảng DUY NHẤT các mã "dòng tiền" của sổ quỹ (cột `ketoan.so_quy.phan_loai_cf`).

Mỗi mã gắn với một khoản mục của báo cáo lưu chuyển tiền tệ (LCTT, mẫu B03). Form lập phiếu thu/chi,
schema API (`app/schemas/so_quy.py`), endpoint `GET /api/so-quy/phan-loai-cf` và báo cáo LCTT
(`app/routers/bao_cao_cashflow.py`) đều đọc từ ĐÂY — thêm/sửa mã thì chỉ sửa một chỗ này.

CẦN KẾ TOÁN XÁC NHẬN: cột `ma_so` ghi theo mẫu B03-DN / B03-DNN (hai mẫu giống nhau ở các mã này). Người
viết tra cứu, CHƯA đối chiếu văn bản gốc — xác nhận trước khi dùng báo cáo để nộp cơ quan thuế / ngân hàng.

Quy ước:
- `khoa`  : giá trị lưu trong cột. 'khac' và 'noi_bo' dùng được cho CẢ HAI chiều nên xuất hiện 2 lần
            (nhãn theo từng chiều). API vẫn nhận NULL (nhiều bridge tự sinh không gắn mã) — báo cáo
            tự đoán những dòng NULL bằng heuristic (xem bao_cao_cashflow.py).
- `ma_so` : mã số trên B03; '' = không lên báo cáo (chuyển nội bộ).
- `nhom`  : hdkd = hoạt động kinh doanh · dautu = đầu tư · taichinh = tài chính · noibo = chuyển nội bộ.
- Khoá cũ (9 khoá có từ trước: thu_kh, tra_ncc, nap_ads, tra_luong, mua_ccdc, sua_chua_lon, vay_nh,
  tra_nh, khac) PHẢI còn đủ — dữ liệu đã ghi vẫn dùng chúng.

Service này KHÔNG import fastapi.
"""
from typing import NamedTuple, Optional


class PhanLoaiCf(NamedTuple):
    khoa: str
    ma_so: str
    ten: str      # nhãn đầy đủ (trong ô chọn)
    ngan: str     # nhãn ngắn (trong thẻ nhỏ ở bảng sổ quỹ)
    loai: str     # 'thu' | 'chi'
    nhom: str     # 'hdkd' | 'dautu' | 'taichinh' | 'noibo'


NHOM_TEN = {
    "hdkd": "Hoạt động kinh doanh",
    "dautu": "Hoạt động đầu tư",
    "taichinh": "Hoạt động tài chính",
    "noibo": "Chuyển nội bộ",
}

_NOI_BO_TEN = "Chuyển nội bộ giữa các quỹ (không tính vào lưu chuyển tiền)"

_CHI = (
    PhanLoaiCf("tra_ncc", "02", "Trả tiền cho người cung cấp hàng hoá, dịch vụ", "Trả NCC", "chi", "hdkd"),
    PhanLoaiCf("nap_ads", "02", "Nạp / chi quảng cáo, marketing (tính vào mã 02)", "Quảng cáo", "chi", "hdkd"),
    PhanLoaiCf("tra_luong", "03", "Trả cho người lao động (lương, thưởng, bảo hiểm)", "Trả lương", "chi", "hdkd"),
    PhanLoaiCf("tra_lai_vay", "04", "Trả lãi vay", "Trả lãi vay", "chi", "hdkd"),
    PhanLoaiCf("nop_thue_tndn", "05", "Nộp thuế thu nhập doanh nghiệp", "Thuế TNDN", "chi", "hdkd"),
    PhanLoaiCf("khac", "07", "Chi khác cho hoạt động kinh doanh (kể cả nộp thuế GTGT, TNCN, môn bài…)", "Chi khác", "chi", "hdkd"),
    PhanLoaiCf("mua_ccdc", "21", "Mua sắm tài sản cố định, công cụ dụng cụ", "Mua TSCĐ/CCDC", "chi", "dautu"),
    PhanLoaiCf("sua_chua_lon", "21", "Sửa chữa lớn tài sản cố định", "Sửa chữa lớn", "chi", "dautu"),
    PhanLoaiCf("chi_cho_vay", "23", "Cho vay, mua công cụ nợ của đơn vị khác", "Cho vay", "chi", "dautu"),
    PhanLoaiCf("chi_gop_von", "25", "Đầu tư góp vốn vào đơn vị khác", "Góp vốn", "chi", "dautu"),
    PhanLoaiCf("tra_von", "32", "Trả lại vốn góp cho chủ sở hữu, mua lại cổ phiếu", "Trả vốn góp", "chi", "taichinh"),
    PhanLoaiCf("tra_nh", "34", "Trả nợ gốc vay ngân hàng (lãi vay chọn mã 04)", "Trả nợ gốc vay", "chi", "taichinh"),
    PhanLoaiCf("tra_goc_thue_tc", "35", "Trả nợ gốc thuê tài chính", "Trả gốc thuê TC", "chi", "taichinh"),
    PhanLoaiCf("chia_co_tuc", "36", "Trả cổ tức, lợi nhuận cho chủ sở hữu", "Chia cổ tức", "chi", "taichinh"),
    PhanLoaiCf("noi_bo", "", _NOI_BO_TEN, "Nội bộ", "chi", "noibo"),
)

_THU = (
    PhanLoaiCf("thu_kh", "01", "Thu tiền bán hàng, cung cấp dịch vụ", "Thu KH", "thu", "hdkd"),
    PhanLoaiCf("khac", "06", "Thu khác từ hoạt động kinh doanh", "Thu khác", "thu", "hdkd"),
    PhanLoaiCf("thanh_ly_tscd", "22", "Thu từ thanh lý, nhượng bán tài sản cố định", "Thanh lý TSCĐ", "thu", "dautu"),
    PhanLoaiCf("thu_hoi_cho_vay", "24", "Thu hồi cho vay, bán lại công cụ nợ", "Thu hồi cho vay", "thu", "dautu"),
    PhanLoaiCf("thu_hoi_gop_von", "26", "Thu hồi đầu tư góp vốn vào đơn vị khác", "Thu hồi góp vốn", "thu", "dautu"),
    PhanLoaiCf("thu_lai", "27", "Thu lãi cho vay, cổ tức, lợi nhuận được chia", "Thu lãi, cổ tức", "thu", "dautu"),
    PhanLoaiCf("nhan_von", "31", "Nhận vốn góp của chủ sở hữu", "Nhận vốn góp", "thu", "taichinh"),
    PhanLoaiCf("vay_nh", "33", "Thu từ đi vay ngân hàng", "Vay NH", "thu", "taichinh"),
    PhanLoaiCf("noi_bo", "", _NOI_BO_TEN, "Nội bộ", "thu", "noibo"),
)

BANG: tuple[PhanLoaiCf, ...] = _CHI + _THU

# Khoá hợp lệ (duy nhất, giữ thứ tự khai báo) — schema API dùng làm danh sách cho phép.
KHOA_HOP_LE: tuple[str, ...] = tuple(dict.fromkeys(x.khoa for x in BANG))

_KHOA_CU = ("thu_kh", "tra_ncc", "nap_ads", "tra_luong", "mua_ccdc", "sua_chua_lon", "vay_nh", "tra_nh", "khac")
assert set(_KHOA_CU) <= set(KHOA_HOP_LE), "Thiếu khoá cũ — dữ liệu sổ quỹ đã ghi sẽ không còn hợp lệ"

_LOAI_CUA_KHOA: dict[str, frozenset[str]] = {
    k: frozenset(x.loai for x in BANG if x.khoa == k) for k in KHOA_HOP_LE
}


def danh_sach(loai: Optional[str] = None) -> list[PhanLoaiCf]:
    """Các mã dòng tiền, theo thứ tự mã số B03 (chuyển nội bộ — không mã số — ở cuối).

    loai='thu'|'chi' → chỉ các mã dùng được cho chiều đó; None → tất cả (khoá 'khac', 'noi_bo' xuất hiện 2 lần).
    `sorted` ổn định nên cùng mã số (vd 02: Trả NCC, Quảng cáo) giữ thứ tự khai báo ở trên.
    """
    ds = [x for x in BANG if loai is None or x.loai == loai]
    return sorted(ds, key=lambda x: int(x.ma_so) if x.ma_so else 999)


def khoa_dung_cho_loai(khoa: str, loai: str) -> bool:
    """True nếu mã `khoa` dùng được cho phiếu `loai` ('thu'|'chi'). Khoá lạ → False."""
    return loai in _LOAI_CUA_KHOA.get(khoa, frozenset())
