"""Cảnh báo "kỳ này chưa đủ để tin số" — Đợt 1, 07/10/2026.

CHỈ ĐỌC, không sửa dữ liệu nào. Mỗi hàm trả 0..n cảnh báo dạng dict:
    {ma, muc: 'danger'|'warning'|'info', tieu_de, chi_tiet, so_tien?, lien_ket?, ap_dung: [màn…]}
`ap_dung` là các màn nên hiện cảnh báo đó: 'cdkt' · 'kqkd' · 'lctt' · 'doi_chieu'.

Bối cảnh (dữ liệu production 07/10/2026 do người yêu cầu chạy): khấu hao ngừng sau 08/2026,
bảng ky_ke_toan 0 dòng, bảng von_chu_so_huu 0 dòng — ba điều này trước đây không màn nào báo.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KhauHaoLog, KyKeToan, TaiSanCoDinh, VonCSH
from .period_close import _ky_dau_tien_co_data

_TAT_CA = ["cdkt", "kqkd", "lctt", "doi_chieu"]


def _thang_sau(thang: str) -> str:
    y, m = int(thang[:4]), int(thang[5:7])
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def _thang_truoc(thang: str) -> str:
    y, m = int(thang[:4]), int(thang[5:7])
    return f"{y - 1:04d}-12" if m == 1 else f"{y:04d}-{m - 1:02d}"


def _cuoi_thang(thang: str) -> date:
    y, m = int(thang[:4]), int(thang[5:7])
    return date(y, m, monthrange(y, m)[1])


def _dai_thang(tu: str, den: str) -> list[str]:
    out, t = [], tu
    while t <= den and len(out) < 120:   # chặn trên 10 năm cho chắc, tránh vòng lặp dài bất thường
        out.append(t)
        t = _thang_sau(t)
    return out


def _chu_thang(thang: str) -> str:
    return f"{thang[5:7]}/{thang[:4]}"


def _tien(x: Decimal) -> str:
    return f"{x:,.0f}".replace(",", ".") + " đ"


def thieu_khau_hao(db: Session, thang: str, thang_hien_tai: str) -> list[dict]:
    """Tháng đã có tài sản phải khấu hao nhưng `khau_hao_log` không có dòng nào.

    Xét từ tháng liền sau tháng khấu hao gần nhất tới `thang`. Số tiền là ƯỚC TÍNH theo trạng thái
    tài sản HIỆN TẠI (nguyên giá / số tháng, không vượt phần còn lại) — đủ để biết thiếu cỡ nào,
    không dùng để ghi sổ. Ghi sổ thật vẫn chạy ở màn TSCĐ (POST /api/tai-san/khau-hao/{thang}).
    """
    gan_nhat: Optional[str] = db.execute(select(func.max(KhauHaoLog.thang))).scalar()
    tu = _thang_sau(gan_nhat) if gan_nhat else None
    if tu is None:
        dau = db.execute(
            select(func.min(TaiSanCoDinh.ngay_su_dung)).where(TaiSanCoDinh.trang_thai == "dang_su_dung")
        ).scalar()
        if dau is None:
            return []
        tu = dau.strftime("%Y-%m")
    can_xet = _dai_thang(tu, thang)
    if not can_xet:
        return []

    thieu: list[tuple[str, Decimal, int]] = []
    for m in can_xet:
        rows = db.execute(
            select(TaiSanCoDinh.nguyen_gia, TaiSanCoDinh.hao_mon_luy_ke, TaiSanCoDinh.so_thang_kh)
            .where(TaiSanCoDinh.trang_thai == "dang_su_dung")
            .where(TaiSanCoDinh.ngay_su_dung <= _cuoi_thang(m))
            .where(TaiSanCoDinh.hao_mon_luy_ke < TaiSanCoDinh.nguyen_gia)
        ).all()
        if not rows:
            continue
        uoc = sum((min(ng / so_thang, ng - hm) for ng, hm, so_thang in rows), Decimal("0"))
        thieu.append((m, uoc.quantize(Decimal("1")), len(rows)))
    if not thieu:
        return []

    da_qua = [x for x in thieu if x[0] < thang_hien_tai]
    tong = sum((x[1] for x in thieu), Decimal("0"))
    ds_thang = ", ".join(_chu_thang(x[0]) for x in thieu)
    chi_tiet = (
        f"Khấu hao ghi gần nhất: {_chu_thang(gan_nhat) if gan_nhat else 'chưa có'}. "
        f"Ước tính thiếu khoảng {_tien(thieu[-1][1])}/tháng cho {thieu[-1][2]} tài sản "
        f"(tổng {_tien(tong)}) — chi phí khấu hao trên Kết quả kinh doanh và hao mòn trên Cân đối "
        "đang thiếu phần này. Không có lịch chạy tự động: phải bấm chạy ở màn Tài sản cố định."
    )
    if not da_qua:
        return [{
            "ma": "chua_khau_hao_thang_nay", "muc": "info",
            "tieu_de": f"Tháng {_chu_thang(thieu[-1][0])} chưa chạy khấu hao",
            "chi_tiet": chi_tiet, "so_tien": tong, "lien_ket": "/ketoan/tscd", "ap_dung": _TAT_CA,
        }]
    return [{
        "ma": "thieu_khau_hao", "muc": "warning",
        "tieu_de": f"Chưa chạy khấu hao {len(thieu)} tháng: {ds_thang}",
        "chi_tiet": chi_tiet, "so_tien": tong, "lien_ket": "/ketoan/tscd", "ap_dung": _TAT_CA,
    }]


def ky_chua_chot(db: Session, thang: str, thang_hien_tai: str) -> list[dict]:
    """Các kỳ đã qua (từ kỳ đầu tiên có dữ liệu tới trước `thang_hien_tai`, không quá `thang`) chưa chốt.

    Chốt kỳ phải đi lần lượt (period_close.chot_ky từ chối 409 `ky_truoc_chua_chot` nếu kỳ trước chưa
    chốt) nên kỳ đầu tiên chưa chốt là chỗ phải bắt đầu — ghi rõ trong thông báo.
    """
    dau = _ky_dau_tien_co_data(db)
    if dau is None:
        return []
    cuoi = min(thang, _thang_truoc(thang_hien_tai))
    can_xet = _dai_thang(dau, cuoi)
    if not can_xet:
        return []
    da_chot = set(db.execute(
        select(KyKeToan.thang).where(KyKeToan.trang_thai == "da_chot").where(KyKeToan.thang.in_(can_xet))
    ).scalars().all())
    chua = [m for m in can_xet if m not in da_chot]
    if not chua:
        return []
    tong_da_chot = db.execute(
        select(func.count()).select_from(KyKeToan).where(KyKeToan.trang_thai == "da_chot")
    ).scalar() or 0
    return [{
        "ma": "ky_chua_chot", "muc": "warning",
        "tieu_de": (f"{len(chua)} kỳ kế toán chưa chốt ({_chu_thang(chua[0])} – {_chu_thang(chua[-1])})"
                    if len(chua) > 1 else f"Kỳ {_chu_thang(chua[0])} chưa chốt"),
        "chi_tiet": (
            ("Chưa kỳ nào được chốt" if tong_da_chot == 0 else f"Đã chốt {tong_da_chot} kỳ")
            + " → Lợi nhuận chưa phân phối (421) trên Cân đối chỉ lấy tới kỳ chốt gần nhất. "
            f"Phải chốt lần lượt từ kỳ {_chu_thang(chua[0])}: hệ thống không cho chốt một kỳ khi kỳ "
            "trước đó chưa chốt."
        ),
        "so_tien": None, "lien_ket": "/ketoan/khoa-so", "ap_dung": ["cdkt", "kqkd", "doi_chieu"],
    }]


def von_gop_chua_khai(db: Session, den: date) -> list[dict]:
    """Bảng vốn chủ sở hữu không có giao dịch nào tới ngày `den`."""
    so_dong = db.execute(
        select(func.count()).select_from(VonCSH).where(VonCSH.ngay <= den)
    ).scalar() or 0
    if so_dong:
        return []
    return [{
        "ma": "von_gop_chua_khai", "muc": "warning",
        "tieu_de": "Vốn góp chủ sở hữu chưa được khai",
        "chi_tiet": ("Bảng vốn chủ sở hữu chưa có giao dịch nào tới ngày này → Vốn góp (411) = 0 trên "
                     "Cân đối kế toán. Hệ thống đã có API ghi vốn góp nhưng chưa có màn nhập."),
        "so_tien": None, "lien_ket": None, "ap_dung": ["cdkt", "doi_chieu"],
    }]


def lech_can_doi(bc: dict) -> list[dict]:
    """Từ kết quả bao_cao_can_doi(): Tài sản ≠ Nguồn vốn → cảnh báo đỏ kèm nguyên nhân đo được."""
    ck = bc.get("check") or {}
    if ck.get("can_bang", True):
        return []
    lech = Decimal(str(ck.get("lech") or 0)).quantize(Decimal("1"))
    ts = Decimal(str(bc["tai_san"]["tong_tai_san"] or 0))
    pt = f" ({abs(lech) / ts * 100:.1f}% tổng tài sản)".replace(".", ",") if ts else ""
    nn = [x["thong_bao"] for x in ck.get("nguyen_nhan") or []]
    return [{
        "ma": "lech_can_doi", "muc": "danger",
        "tieu_de": f"Tổng tài sản ≠ Tổng nguồn vốn — lệch {_tien(lech)}{pt}",
        "chi_tiet": " ".join(nn) if nn else "Chưa xác định được nguyên nhân từ số liệu — kiểm tra bút toán thiếu vế ở Sổ kế toán.",
        "nguyen_nhan": nn,
        "so_tien": lech, "lien_ket": "/ketoan/doi-chieu", "ap_dung": ["cdkt", "doi_chieu"],
    }]
