"""Chi phí chờ phân bổ (TK 242) — đọc/ghi thật trên `ketoan.chi_phi_co_dinh`.

NGHIỆP VỤ (anh Quang 2026-09-25): một dòng `chi_phi_co_dinh` có `so_thang_phan_bo > 1` là khoản
TRẢ TRƯỚC một lần rồi phân bổ dần (vd "Thuê showroom tháng 6 7 8/2026" 127,5tr / 3 tháng) — đúng
bản chất TK 242. Báo cáo KQKD (`pl_calculator`) đã phân bổ các dòng này vào chi phí hằng tháng
(`_sum_co_dinh_duong_thang_method_only`, `_sum_co_dinh_front_loaded`). Màn này hiển thị CHÍNH các
dòng đó với lịch phân bổ tính theo đúng công thức của pl_calculator:
  - duong_thang : so_tien_thang / so_thang_phan_bo mỗi tháng, từ thang_bat_dau, N tháng liên tiếp
  - front_loaded: 50% tháng đầu, 50% chia đều N−1 tháng còn lại
(so_tien_thang của dòng N>1 là TỔNG số tiền — pl_calculator chia cho N). Để ra số đồng chẵn, mỗi
kỳ làm tròn đồng và kỳ cuối lấy phần lẻ ⇒ tổng lịch = đúng tổng tiền; lệch ≤ 1đ/tháng so với số
thực của pl_calculator. Dòng N>1 phương pháp khác (prorated/seasonal/…) không có lịch N tháng xác
định → không đưa lên màn (hiện không có dòng nào như vậy).

"ĐÃ PHÂN BỔ" = các tháng ≤ tháng hiện tại (KQKD đã tính chi phí các tháng đó, kể cả tháng này).

SỔ CÁI: khoản thêm từ màn này ghi Nợ 242 / Có nguồn (111/112 hoặc TK con 111x/112x, 331) và lưu thêm vào
`ketoan.phan_bo_242`. Nút "Phân bổ tháng" ghi Nợ 641/642 / Có 242 cho phần đã tới hạn mà chưa lên
sổ của các khoản đó (source_type='phan_bo_242', source_id='YYYY-MM'). Khoản nhập từ màn Chi phí
cố định cũ không có bút toán Nợ 242 nên KHÔNG ghi Có 242 cho chúng (tránh âm 242) — chúng chỉ phân
bổ vào KQKD. KQKD đọc chi phí từ `chi_phi_co_dinh`, không đọc 641/642 trên sổ cái ⇒ không đếm 2 lần.
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload

from ..models import ChiPhiCoDinh, JournalEntry, JournalLine
from ..models.phan_bo_242 import PhanBo242
from . import ky_thue
from .journal import ACCOUNTS, post_journal, tk_cha_cua
from .period_close import is_ky_da_chot
from .so_cai_doc import DA_POST, so_du_no
from .tai_khoan_tien import TK_TIEN_GUI, TK_TIEN_MAT, tk_chi_tiet
from .tim_kiem import chua_khong_dau

TK_CHO_PHAN_BO = "242"
# P&L chỉ lấy chi_phi_co_dinh nhóm ban_hang/quan_ly (pl_calculator.calc_pl_for_month) ⇒ chỉ 2 TK này.
TK_CP_THEO_NHOM = {"641": "ban_hang", "642": "quan_ly"}
NHOM_THEO_TK_CP = {v: k for k, v in TK_CP_THEO_NHOM.items()}
TK_NGUON_HOP_LE = ("111", "112", "331")
# Ngoài 3 TK trên: TK con của 111/112 đang gán cho tài khoản tiền (1111, 1121… — tai_khoan_nh.tk_ke_toan).
TK_TIEN_CO_TK_CON = (TK_TIEN_MAT, TK_TIEN_GUI)
LOAI_KHOAN = {"tra_truoc": "Chi phí trả trước", "ccdc": "Công cụ dụng cụ xuất dùng"}
PHUONG_PHAP_CO_LICH = ("duong_thang", "front_loaded")
SO_KY_TOI_THIEU, SO_KY_TOI_DA = 2, 36
TY_LE_THANG_DAU_FRONT_LOADED = Decimal("0.5")
SOURCE_GHI_NHAN = "phan_bo_242_ghi_nhan"
SOURCE_PHAN_BO = "phan_bo_242"
REF_TABLE = "chi_phi_co_dinh"
_DONG = Decimal("1")


def _vnd(x: Decimal) -> Decimal:
    return x.quantize(_DONG, rounding=ROUND_HALF_UP)


def ma_khoan(cpcd_id: int) -> str:
    return f"PB-{cpcd_id:04d}"


def lich_phan_bo(r: ChiPhiCoDinh) -> list[tuple[str, int]]:
    """Lịch [(YYYY-MM, số đồng)] — cùng công thức pl_calculator (xem docstring module)."""
    tong, n = _vnd(Decimal(r.so_tien_thang or 0)), int(r.so_thang_phan_bo or 1)   # VND nguyên — Σ lịch = cột "Tổng tiền"
    y, m = r.thang_bat_dau.year, r.thang_bat_dau.month
    cac_thang = [f"{yy}-{mm:02d}" for yy, mm in (ky_thue.cong_thang(y, m, i) for i in range(n))]
    if r.phuong_phap_phan_bo == "front_loaded":
        dau = _vnd(tong * TY_LE_THANG_DAU_FRONT_LOADED)
        moi = _vnd((tong - dau) / (n - 1))
        so = [dau] + [moi] * (n - 1)
    else:
        moi = _vnd(tong / n)
        so = [moi] * n
    so[-1] = tong - sum(so[:-1])          # kỳ cuối lấy phần lẻ ⇒ tổng lịch = tổng tiền
    return [(t, int(s)) for t, s in zip(cac_thang, so)]


def _cac_khoan(db: Session) -> list[tuple[ChiPhiCoDinh, Optional[PhanBo242]]]:
    return list(db.execute(
        select(ChiPhiCoDinh, PhanBo242)
        .outerjoin(PhanBo242, PhanBo242.cpcd_id == ChiPhiCoDinh.id)
        .where(ChiPhiCoDinh.so_thang_phan_bo > 1,
               ChiPhiCoDinh.so_tien_thang > 0,
               ChiPhiCoDinh.nhom_chi_phi.in_(TK_CP_THEO_NHOM.values()),
               ChiPhiCoDinh.phuong_phap_phan_bo.in_(PHUONG_PHAP_CO_LICH))
        .order_by(ChiPhiCoDinh.thang_bat_dau.desc(), ChiPhiCoDinh.id.desc())
    ).all())


def _da_ghi_so_theo_khoan(db: Session) -> dict[int, int]:
    """Tổng Có 242 đã phân bổ lên sổ cái, theo khoản (ref_id)."""
    rows = db.execute(
        select(JournalLine.ref_id, func.sum(JournalLine.so_tien))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalEntry.source_type == SOURCE_PHAN_BO, JournalEntry.trang_thai == DA_POST,
               JournalLine.account_code == TK_CHO_PHAN_BO, JournalLine.loai == "co",
               JournalLine.ref_table == REF_TABLE)
        .group_by(JournalLine.ref_id)
    ).all()
    return {int(rid): int(s) for rid, s in rows if rid is not None}


def _dong(r: ChiPhiCoDinh, pb: Optional[PhanBo242], thang: str, da_ghi_so: dict[int, int]) -> dict[str, Any]:
    lich = lich_phan_bo(r)
    tong = int(_vnd(Decimal(r.so_tien_thang or 0)))   # làm tròn (không cắt) — khớp Σ lịch phân bổ
    da = [s for t, s in lich if t <= thang]
    da_pb = sum(da)
    tk_cp = pb.tk_cp if pb else NHOM_THEO_TK_CP.get(r.nhom_chi_phi, "")
    tren_so = pb is not None and pb.je_ghi_nhan_id is not None
    ghi_so = da_ghi_so.get(r.id, 0)
    return {
        "id": r.id, "ma": ma_khoan(r.id), "ten": r.ten_khoan or r.loai_chi_phi or "—",
        "loai": pb.loai if pb else "tra_truoc", "bo_phan": pb.bo_phan if pb else None,
        "ngay": (r.ngay_bat_dau or r.thang_bat_dau).isoformat(),
        "thang_bat_dau": r.thang_bat_dau.strftime("%Y-%m"), "phuong_phap": r.phuong_phap_phan_bo,
        "tong": tong, "so_ky": len(lich), "da_ky": len(da), "da_pb": da_pb, "con_lai": tong - da_pb,
        "muc_thang": dict(lich).get(thang, 0),
        "tk_cp": tk_cp, "ten_tk_cp": ACCOUNTS.get(tk_cp, "Chưa xác định"),
        "doi": pb.tk_nguon if pb else None, "nhom_chi_phi": r.nhom_chi_phi,
        "trang_thai": "dang" if lich[-1][0] >= thang else "xong",   # còn phân bổ từ tháng này trở đi
        "tren_so_cai": tren_so, "da_ghi_so": ghi_so, "cho_ghi_so": (da_pb - ghi_so) if tren_so else 0,
        "nguon_nhap": "man_phan_bo" if pb else "chi_phi_co_dinh",
        "lich": [{"thang": t, "so_tien": s, "da": t <= thang} for t, s in lich],
    }


def danh_sach(db: Session, tim: str = "", loai: str = "", trang_thai: str = "") -> dict[str, Any]:
    thang = ky_thue.thang_nay()
    da_ghi = _da_ghi_so_theo_khoan(db)
    tat_ca = [_dong(r, pb, thang, da_ghi) for r, pb in _cac_khoan(db)]
    dang = [x for x in tat_ca if x["trang_thai"] == "dang"]
    dong = [x for x in tat_ca
            if chua_khong_dau(f"{x['ma']} {x['ten']} {x['bo_phan'] or ''}", tim)   # không phân biệt dấu + hoa/thường
            and (not loai or x["loai"] == loai)
            and (not trang_thai or x["trang_thai"] == trang_thai)]
    for x in dong:
        x.pop("lich")
    cho_ghi = sum(x["cho_ghi_so"] for x in tat_ca)
    ct = _but_toan_thang(db, thang)
    return {
        "thang": thang, "dong": dong, "tong_dong": len(dong),
        "tong": {"con_lai": sum(x["con_lai"] for x in tat_ca), "muc_thang": sum(x["muc_thang"] for x in tat_ca),
                 "so_khoan": len(dang), "tong": sum(x["tong"] for x in dang)},
        "so_sach": {"tk242": int(so_du_no(db, TK_CHO_PHAN_BO)),
                    "con_lai_tren_so": sum(x["tong"] - x["da_ghi_so"] for x in tat_ca if x["tren_so_cai"]),
                    "cho_ghi_so": cho_ghi,
                    "so_khoan_ngoai_so": sum(1 for x in tat_ca if not x["tren_so_cai"] and x["trang_thai"] == "dang")},
        "da_phan_bo_thang": cho_ghi == 0, "ct_thang": ct,
    }


def _but_toan_thang(db: Session, thang: str) -> Optional[dict]:
    je = db.execute(select(JournalEntry).where(
        JournalEntry.source_type == SOURCE_PHAN_BO, JournalEntry.source_id == thang,
        JournalEntry.trang_thai == DA_POST).order_by(JournalEntry.id.desc()).limit(1)).scalar_one_or_none()
    return {"so_ct": je.ma_but_toan, "id": je.id} if je else None


def chi_tiet(db: Session, cpcd_id: int) -> dict[str, Any]:
    kq = db.execute(select(ChiPhiCoDinh, PhanBo242).outerjoin(PhanBo242, PhanBo242.cpcd_id == ChiPhiCoDinh.id)
                    .where(ChiPhiCoDinh.id == cpcd_id)).first()
    if kq is None or int(kq[0].so_thang_phan_bo or 1) <= 1:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có khoản chi phí chờ phân bổ này")
    return _dong(kq[0], kq[1], ky_thue.thang_nay(), _da_ghi_so_theo_khoan(db))


def _kiem_khoa(db: Session, ngay: date) -> None:
    if is_ky_da_chot(db, ngay):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Kỳ {ngay:%m/%Y} đã khoá sổ — không ghi được bút toán.")


def _tk_nguon_hop_le(db: Session, doi: str) -> bool:
    """111 / 112 / 331, hoặc TK con của 111/112 đang gán cho một tài khoản tiền."""
    if doi in TK_NGUON_HOP_LE:
        return True
    return doi in tk_chi_tiet(db) and tk_cha_cua(doi) in TK_TIEN_CO_TK_CON


def them_khoan(db: Session, user: JWTPayload, d: dict[str, Any]) -> dict[str, Any]:
    """Tạo dòng chi_phi_co_dinh (KQKD tự phân bổ) + bút toán Nợ 242 / Có nguồn — all-or-nothing."""
    ten = (d.get("ten") or "").strip()
    loai, tk_cp, doi = d.get("loai"), str(d.get("tk_cp") or ""), str(d.get("doi") or "")
    tong, so_ky = int(d.get("tong") or 0), int(d.get("so_ky") or 0)
    ngay = d.get("ngay") or ky_thue.hom_nay()
    bo_phan = (d.get("bo_phan") or "").strip() or None
    if not ten:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nhập tên khoản chi phí.")
    if loai not in LOAI_KHOAN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Loại phải là Chi phí trả trước hoặc Công cụ dụng cụ.")
    if tong <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tổng số tiền phải lớn hơn 0.")
    if not SO_KY_TOI_THIEU <= so_ky <= SO_KY_TOI_DA:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Số tháng phân bổ từ {SO_KY_TOI_THIEU} đến {SO_KY_TOI_DA}.")
    if tk_cp not in TK_CP_THEO_NHOM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "TK chi phí phải là 641 (bán hàng) hoặc 642 (quản lý) — báo cáo KQKD chỉ phân bổ 2 nhóm này.")
    if not _tk_nguon_hop_le(db, doi):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TK nguồn phải là 111, 112 (hoặc TK con của tài khoản tiền) hoặc 331.")
    _kiem_khoa(db, ngay)
    y, m = ky_thue.cong_thang(ngay.year, ngay.month, so_ky - 1)
    cp = ChiPhiCoDinh(
        thang_bat_dau=ngay.replace(day=1), ngay_bat_dau=ngay, ngay_ket_thuc=ky_thue.cuoi_thang(y, m),
        so_tien_thang=Decimal(tong), ten_khoan=ten[:255], nhom_chi_phi=TK_CP_THEO_NHOM[tk_cp],
        mo_ta=f"{LOAI_KHOAN[loai]} — TK 242, phân bổ {so_ky} tháng vào TK {tk_cp}",
        lap_lai=False, so_thang_phan_bo=so_ky, phuong_phap_phan_bo="duong_thang", created_by=user.username,
    )
    db.add(cp)
    db.flush()
    je = post_journal(
        db, ngay=ngay, mo_ta=f"Ghi nhận chi phí chờ phân bổ {ma_khoan(cp.id)}: {ten}",
        source_type=SOURCE_GHI_NHAN, source_id=str(cp.id), by_user=user.username,
        lines=[{"loai": "no", "account_code": TK_CHO_PHAN_BO, "so_tien": tong, "ref_table": REF_TABLE, "ref_id": cp.id},
               {"loai": "co", "account_code": doi, "so_tien": tong, "ref_table": REF_TABLE, "ref_id": cp.id}],
    )
    db.add(PhanBo242(cpcd_id=cp.id, loai=loai, tk_cp=tk_cp, tk_nguon=doi, bo_phan=bo_phan,
                     je_ghi_nhan_id=je.id, created_by=user.username))
    db.commit()
    lich = lich_phan_bo(cp)
    return {"id": cp.id, "ma": ma_khoan(cp.id), "muc_thang": lich[0][1], "so_ct": je.ma_but_toan}


def phan_bo_thang(db: Session, user: JWTPayload, thang: str) -> dict[str, Any]:
    """Ghi Nợ 641/642 / Có 242 cho phần đã tới hạn (≤ tháng) mà chưa lên sổ của các khoản có bút toán 242."""
    thang = ky_thue.kiem_thang(thang)
    if thang != ky_thue.thang_nay():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ phân bổ cho tháng hiện tại.")
    ngay = ky_thue.khoang_ky(thang)[1]
    _kiem_khoa(db, ngay)
    da_ghi = _da_ghi_so_theo_khoan(db)
    lines = []
    for r, pb in _cac_khoan(db):
        x = _dong(r, pb, thang, da_ghi)
        if x["cho_ghi_so"] <= 0:
            continue
        lines += [
            {"loai": "no", "account_code": x["tk_cp"], "so_tien": x["cho_ghi_so"], "ref_table": REF_TABLE,
             "ref_id": r.id, "ghi_chu": f"{x['ma']} {x['ten']}"[:200]},
            {"loai": "co", "account_code": TK_CHO_PHAN_BO, "so_tien": x["cho_ghi_so"], "ref_table": REF_TABLE,
             "ref_id": r.id, "ghi_chu": x["ma"]},
        ]
    if not lines:
        raise HTTPException(status.HTTP_409_CONFLICT, "Không còn khoản nào chờ ghi sổ phân bổ tháng này.")
    je = post_journal(db, ngay=ngay, mo_ta=f"Phân bổ chi phí trả trước (TK 242) tháng {thang[5:]}/{thang[:4]}",
                      source_type=SOURCE_PHAN_BO, source_id=thang, by_user=user.username, lines=lines)
    db.commit()
    return {"so_ct": je.ma_but_toan, "so_tien": int(je.tong_tien), "id": je.id, "so_khoan": len(lines) // 2}
