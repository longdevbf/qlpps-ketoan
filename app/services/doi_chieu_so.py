"""Đối chiếu hai chiều: số theo SỔ CÁI (journal_line) ↔ số theo BẢNG NGHIỆP VỤ — Đợt 1, 07/10/2026.

CHỈ ĐỌC và HIỆN chênh lệch; không sửa số nào cho khớp (quyết định của người yêu cầu).

Kết quả kinh doanh hiện tính hoàn toàn từ bảng nghiệp vụ (pl_calculator), trong khi các bút toán
doanh thu/chi phí vẫn được ghi vào sổ cái TK 511/632/641/642… — hai nguồn chưa từng được so với
nhau. Module này lấy phát sinh từng TK trong tháng rồi đặt cạnh dòng tương ứng của KQKD.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.orm import Session, aliased

from ..models import JournalEntry, JournalLine
from .journal import tk_cha_cua

# (khoá dòng KQKD trong kết quả calc_pl_for_month, nhãn, TK, chiều số dư tự nhiên,
#  nguồn mà KQKD THẬT SỰ đang dùng cho dòng đó — phải khớp pl_calculator / nguon_bao_cao.NGUON_KQKD)
DONG_KQKD: list[tuple[str, str, str, str, str]] = [
    ("dt_thuan", "Doanh thu thuần", "511", "co", "nghiep_vu"),
    ("dt_tai_chinh", "Doanh thu hoạt động tài chính", "515", "co", "chua_tinh"),   # gán cứng 0
    ("cogs", "Giá vốn hàng bán", "632", "no", "nghiep_vu"),
    ("cp_tai_chinh.tong", "Chi phí tài chính", "635", "no", "nghiep_vu"),
    ("cp_ban_hang.tong", "Chi phí bán hàng", "641", "no", "nghiep_vu"),
    ("cp_quan_ly.tong", "Chi phí quản lý doanh nghiệp", "642", "no", "nghiep_vu"),
    ("thu_nhap_khac", "Thu nhập khác", "711", "co", "so_cai"),                 # đọc sổ cái 711
    ("cp_khac", "Chi phí khác", "811", "no", "tron"),                          # chi phí phát sinh + sổ cái 811
    ("thue_tndn", "Chi phí thuế TNDN", "821", "no", "cong_thuc"),              # LNTT × 20%
]

# Mô tả nguồn cho từng loại dòng — hiện ở bong bóng ⓘ cạnh tên khoản mục.
_MO_TA = {
    "nghiep_vu": "Số trên Kết quả kinh doanh, tính từ bảng nghiệp vụ (đơn hàng, chi phí, công nợ, bảng lương…)",
    "chua_tinh": "Kết quả kinh doanh chưa tính dòng này — đang gán 0",
    "so_cai": "Kết quả kinh doanh đọc thẳng sổ cái cho dòng này",
    "tron": "Kết quả kinh doanh cộng chi phí phát sinh nhóm khác với sổ cái TK 811",
    "cong_thuc": "Kết quả kinh doanh tính bằng công thức lợi nhuận trước thuế × 20%, không đọc sổ cái",
}


def phat_sinh_theo_tk(db: Session, tu: date, den: date) -> dict[str, tuple[Decimal, Decimal]]:
    """Phát sinh (Nợ, Có) từng TK trong [tu, den], chỉ bút toán 'da_post'.

    BỎ các bút toán có dòng TK 911: đó là bút toán kết chuyển cuối kỳ, nó làm TK 5xx-8xx về 0
    nên tính vào thì "phát sinh trong kỳ" của doanh thu/chi phí bị triệt tiêu. TK con (1121…)
    cộng dồn lên TK cha như trial_balance.
    """
    jl911 = aliased(JournalLine)
    co_ket_chuyen = exists().where(and_(jl911.journal_id == JournalEntry.id, jl911.account_code.like("911%")))
    rows = db.execute(
        select(
            JournalLine.account_code,
            func.coalesce(func.sum(case((JournalLine.loai == "no", JournalLine.so_tien), else_=0)), 0),
            func.coalesce(func.sum(case((JournalLine.loai == "co", JournalLine.so_tien), else_=0)), 0),
        )
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.trang_thai == "da_post")
        .where(JournalEntry.ngay >= tu, JournalEntry.ngay <= den)
        .where(~co_ket_chuyen)
        .group_by(JournalLine.account_code)
    ).all()
    out: dict[str, list[Decimal]] = {}
    for code, no, co in rows:
        goc = tk_cha_cua(code) or code
        v = out.setdefault(goc, [Decimal("0"), Decimal("0")])
        v[0] += Decimal(no or 0)
        v[1] += Decimal(co or 0)
    return {k: (v[0], v[1]) for k, v in out.items()}


def _lay(d: dict, duong_dan: str):
    for k in duong_dan.split("."):
        d = d.get(k) if isinstance(d, dict) else None
    return d


def doi_chieu_kqkd(pl: dict, ps: dict[str, tuple[Decimal, Decimal]]) -> list[dict]:
    """Ghép từng dòng KQKD (số đang hiện trên báo cáo) với phát sinh TK tương ứng (sổ cái)."""
    out: list[dict] = []
    for khoa, nhan, tk, chieu, dang_dung in DONG_KQKD:
        no, co = ps.get(tk, (Decimal("0"), Decimal("0")))
        so_cai = (co - no) if chieu == "co" else (no - co)
        # Cột thứ hai là đúng con số đang hiện trên Kết quả kinh doanh, dù dòng đó lấy từ nguồn nào.
        tren_bao_cao = Decimal(str(_lay(pl, khoa) or 0)).quantize(Decimal("0.01"))
        out.append({
            "khoa": khoa, "nhan": nhan, "tk": [tk], "bang": _MO_TA[dang_dung],
            "so_cai": so_cai, "nghiep_vu": tren_bao_cao, "chenh": so_cai - tren_bao_cao,
            "dang_dung": dang_dung,
        })
    return out
