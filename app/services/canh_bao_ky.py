"""Cảnh báo "kỳ này chưa đủ để tin số" — Đợt 1, 07/10/2026.

CHỈ ĐỌC, không sửa dữ liệu nào. Mỗi hàm trả 0..n cảnh báo dạng dict:
    {ma, muc: 'danger'|'warning'|'info', tieu_de, chi_tiet, so_tien?, lien_ket?, ap_dung: [màn…]}
`ap_dung` là các màn nên hiện cảnh báo đó: 'cdkt' · 'kqkd' · 'lctt' · 'doi_chieu'.

Nguyên tắc: cảnh báo về một con số trên báo cáo phải kết luận từ CHÍNH con số báo cáo đang hiển
thị (truyền vào dưới dạng kết quả bao_cao_can_doi), không từ một bảng nguồn riêng — nếu không, màn
"phơi lỗi" lại tự nói sai (vd báo vốn góp = 0 trong khi Cân đối đang hiện vốn góp từ sổ cái).

Bối cảnh (dữ liệu production 07/10/2026 do người yêu cầu chạy): khấu hao ngừng sau 08/2026,
bảng ky_ke_toan 0 dòng, bảng von_chu_so_huu 0 dòng — ba điều này trước đây không màn nào báo.
"""
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KhauHaoLog, KyKeToan, TaiSanCoDinh
# Hàm "private" của period_close nhưng cố ý dùng lại: cảnh báo phải dùng ĐÚNG định nghĩa "kỳ đầu
# tiên có dữ liệu" mà chot_ky dùng để chặn chốt kỳ — tự viết lại là hai định nghĩa trôi khỏi nhau.
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


_TOI_DA_THANG = 120   # 10 năm — chặn vòng lặp dài bất thường


def _dai_thang(tu: str, den: str) -> list[str]:
    """Các tháng từ `tu` tới `den`. Quá _TOI_DA_THANG thì giữ các tháng GẦN NHẤT (bỏ tháng cũ) —
    tháng gần nhất là tháng người dùng cần thấy; nơi gọi tự so độ dài để biết đã cắt."""
    out, t = [], tu
    while t <= den:
        out.append(t)
        t = _thang_sau(t)
    return out[-_TOI_DA_THANG:]


def _chu_thang(thang: str) -> str:
    return f"{thang[5:7]}/{thang[:4]}"


def _tien(x) -> str:
    # Cùng đơn vị "VND" với thẻ số và bong bóng giải thích trên màn (KD.tienVnd).
    return f"{Decimal(str(x)):,.0f}".replace(",", ".") + " VND"


def thieu_khau_hao(db: Session, thang: str, thang_hien_tai: str) -> list[dict]:
    """Tháng đã có tài sản phải khấu hao nhưng `khau_hao_log` không có dòng nào.

    Xét từ tháng liền sau tháng khấu hao gần nhất tới `thang` — nhưng không quá tháng hiện tại (tháng
    tương lai chưa tới hạn khấu hao). Số tiền là ƯỚC TÍNH theo trạng thái tài sản HIỆN TẠI (nguyên
    giá / số tháng, không vượt phần còn lại) — đủ để biết thiếu cỡ nào, không dùng để ghi sổ. Ghi sổ
    thật vẫn chạy ở màn TSCĐ (POST /api/tai-san/khau-hao/{thang}).
    """
    thang = min(thang, thang_hien_tai)
    gan_nhat: Optional[str] = db.execute(select(func.max(KhauHaoLog.thang))).scalar()
    # Một lần đọc danh sách tài sản còn phải khấu hao, rồi xét từng tháng trong Python — không truy
    # vấn lại DB trong vòng lặp tháng.
    tai_san = db.execute(
        select(TaiSanCoDinh.ngay_su_dung, TaiSanCoDinh.nguyen_gia, TaiSanCoDinh.hao_mon_luy_ke,
               TaiSanCoDinh.so_thang_kh)
        .where(TaiSanCoDinh.trang_thai == "dang_su_dung")
        .where(TaiSanCoDinh.hao_mon_luy_ke < TaiSanCoDinh.nguyen_gia)
    ).all()
    if not tai_san:
        return []
    tu = _thang_sau(gan_nhat) if gan_nhat else min(ts.ngay_su_dung for ts in tai_san).strftime("%Y-%m")

    can_xet = _dai_thang(tu, thang)
    bi_cat = len(can_xet) == _TOI_DA_THANG and can_xet[0] != tu
    thieu = [m for m in can_xet if any(ts.ngay_su_dung <= _cuoi_thang(m) for ts in tai_san)]
    if not thieu:
        return []
    # Tháng hiện tại chưa tới hạn khấu hao (chạy vào cuối tháng): đã có tháng cũ bị thiếu thì chỉ tính các
    # tháng cũ vào số tiền thiếu; chỉ còn tháng hiện tại thì là nhắc nhở (info), không phải thiếu.
    qua_han = [m for m in thieu if m < thang_hien_tai]
    if qua_han:
        thieu = qua_han
    # Ước tính theo TỪNG tài sản: số tháng thiếu × mức tháng, nhưng không vượt phần còn lại phải
    # khấu hao của chính tài sản đó (cộng nhiều tháng không được vượt nguyên giá − hao mòn).
    tong = Decimal("0")
    thang_cuoi = Decimal("0")
    so_ts = 0
    for ts in tai_san:
        muc_thang = ts.nguyen_gia / ts.so_thang_kh
        con_lai = ts.nguyen_gia - ts.hao_mon_luy_ke
        n = sum(1 for m in thieu if ts.ngay_su_dung <= _cuoi_thang(m))
        if n:
            tong += min(muc_thang * n, con_lai)
            thang_cuoi += min(muc_thang, con_lai)
            so_ts += 1
    tong, thang_cuoi = tong.quantize(Decimal("1")), thang_cuoi.quantize(Decimal("1"))
    khoang = (f"{len(thieu)} tháng ({_chu_thang(thieu[0])} – {_chu_thang(thieu[-1])})" if len(thieu) > 1
              else f"tháng {_chu_thang(thieu[0])}")
    chi_tiet = (
        f"Khấu hao ghi gần nhất: {_chu_thang(gan_nhat) if gan_nhat else 'chưa có'}. "
        f"Ước tính thiếu khoảng {_tien(thang_cuoi)}/tháng cho {so_ts} tài sản (tổng {_tien(tong)}, không vượt "
        "phần còn lại phải khấu hao) — chi phí khấu hao trên Kết quả kinh doanh và hao mòn trên Cân đối đang "
        "thiếu phần này. Không có lịch chạy tự động: phải bấm chạy ở màn Tài sản cố định."
        + (f" Chỉ xét {_TOI_DA_THANG} tháng gần nhất." if bi_cat else "")
        + (f" Tháng {_chu_thang(thang_hien_tai)} chưa tới hạn nên chưa tính." if qua_han and thang >= thang_hien_tai else "")
    )
    if all(m >= thang_hien_tai for m in thieu):
        return [{
            "ma": "chua_khau_hao_thang_nay", "muc": "info",
            "tieu_de": f"Tháng {_chu_thang(thieu[-1])} chưa chạy khấu hao",
            "chi_tiet": chi_tiet, "so_tien": tong, "lien_ket": "/ketoan/tscd", "ap_dung": _TAT_CA,
        }]
    return [{
        "ma": "thieu_khau_hao", "muc": "warning",
        "tieu_de": f"Chưa chạy khấu hao {khoang}",
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
    can_xet = _dai_thang(dau, min(thang, _thang_truoc(thang_hien_tai)))
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


def von_gop_chua_khai(bc: dict) -> list[dict]:
    """Vốn góp trên Cân đối (số đang hiển thị) bằng 0 — và cả sổ cái TK 411 lẫn sổ vốn chủ sở hữu đều 0.

    Đọc từ kết quả bao_cao_can_doi (`nguon` của dòng vốn góp), không đếm bảng riêng: số dư đầu kỳ có
    thể đã khai Có 411 trên sổ cái trong khi sổ vốn chủ sở hữu trống — khi đó báo cáo hiện vốn góp
    đúng và không được cảnh báo.
    """
    if abs(float(bc["nguon_von"]["von_csh"]["von_gop"] or 0)) >= 1:
        return []
    return [{
        "ma": "von_gop_chua_khai", "muc": "warning",
        "tieu_de": "Vốn góp chủ sở hữu chưa được khai",
        "chi_tiet": ("Vốn góp (411) trên Cân đối = 0: sổ vốn chủ sở hữu chưa có giao dịch và sổ cái TK 411 "
                     "chưa có số dư. Chưa có màn hình nhập vốn góp — sẽ bổ sung ở đợt sau."),
        "so_tien": None, "lien_ket": None, "ap_dung": ["cdkt", "doi_chieu"],
    }]


def lech_can_doi(bc: dict, bo_ma: frozenset[str] = frozenset()) -> list[dict]:
    """Từ kết quả bao_cao_can_doi(): Tài sản ≠ Nguồn vốn → cảnh báo đỏ kèm nguyên nhân đo được.

    `bo_ma`: mã nguyên nhân đã có cảnh báo riêng đứng cạnh (vd kỳ chưa chốt, vốn góp chưa khai) —
    bỏ khỏi danh sách để cùng một ý không bị nói hai lần trên một màn.
    """
    ck = bc.get("check") or {}
    if ck.get("can_bang", True):
        return []
    lech = Decimal(str(ck.get("lech") or 0)).quantize(Decimal("1"))
    ts = Decimal(str(bc["tai_san"]["tong_tai_san"] or 0))
    pt = f" ({abs(lech) / ts * 100:.1f}% tổng tài sản)".replace(".", ",") if ts else ""
    goc = ck.get("nguyen_nhan") or []
    nn = [x["thong_bao"] for x in goc if x.get("ma") not in bo_ma]
    # "Chưa xác định" chỉ khi danh sách GỐC rỗng. Rỗng vì mọi ý đã có cảnh báo riêng thì chỉ sang đó.
    du_phong = ("Nguyên nhân đo được nằm ở các cảnh báo bên dưới." if goc
                else "Chưa xác định được nguyên nhân từ số liệu — kiểm tra bút toán thiếu vế ở Sổ kế toán.")
    return [{
        "ma": "lech_can_doi", "muc": "danger",
        "tieu_de": f"Tổng tài sản ≠ Tổng nguồn vốn — lệch {_tien(lech)}{pt}",
        "chi_tiet": " ".join(nn) if nn else du_phong,
        "nguyen_nhan": nn,
        "so_tien": lech, "lien_ket": "/ketoan/doi-chieu", "ap_dung": ["cdkt", "doi_chieu"],
    }]
