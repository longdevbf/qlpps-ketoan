"""Số dư đầu kỳ theo hệ thống tài khoản kế toán (GL) — màn /ketoan/so-du-dau-ky.

Journal chưa có khái niệm "bút toán đầu kỳ" nên số dư đầu kỳ được lưu thành
ĐÚNG MỘT bút toán `source_type='so_du_dau_ky'` ghi ngày (ngày bắt đầu − 1):
mọi báo cáo đọc journal (sổ cái, cân đối phát sinh, cân đối kế toán) tự có số
dư nền mà không phải sửa từng báo cáo. Lưu lại = XOÁ bút toán cũ + post bút
toán mới (không dùng bút toán đảo: đảo ghi ngày hôm nay sẽ làm số dư đầu kỳ
biến mất khỏi mọi kỳ sau hôm nay). Chi tiết công nợ theo đối tượng (131/331/141)
nằm ở bảng `ketoan.so_du_dau_ky_doi_tuong`.

Tiền (28/09/2026): nhập theo TK con của từng tài khoản tiền (1111 Tiền Mặt, 1121 ACB…
— ketoan.tai_khoan_nh.tk_ke_toan) thay cho 111/112 cấp 1; sổ cái / cân đối phát sinh
tự gộp TK con lên TK cha.

Khác `ketoan.so_du_dau_ky` (số dư đầu tháng của TK ngân hàng, routers/so_du_dau_ky.py).
"""
import calendar
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from ..models import (
    CaiDatHeThong, JournalEntry, KyKeToan, SoDuDauKy, SoDuDauKyDoiTuong, TaiKhoanNH,
)
from .journal import ACCOUNTS, ASSET_ACCOUNTS, danh_muc_tk, post_journal, tk_cha_cua
from .so_quy_auto import so_du_truoc_ngay
from .tai_khoan_tien import TK_TIEN_GUI, TK_TIEN_MAT, tk_tien_cua
from .tim_kiem import mau_like, sql_khop

SOURCE_TYPE = "so_du_dau_ky"
SOURCE_ID = "GL"
# Giám đốc chốt 01/10/2026: sổ cái bắt đầu dùng từ 01/05/2026, số dư đầu kỳ (ngày hạch toán 30/04/2026)
# do kế toán nhập tay ở màn này. Chỉ là MẶC ĐỊNH khi Cài đặt chưa khai ngày — không ghi gì vào DB.
NGAY_BAT_DAU_MAC_DINH = date(2026, 5, 1)
# Chỉ TK bảng cân đối (loại 1–4) có số dư đầu kỳ; 5–8 đã kết chuyển về 421.
LOAI_TK_CO_SO_DU = ("1", "2", "3", "4")
TK_HAO_MON = "214"                    # TK loại 2 nhưng dư Có (điều chỉnh giảm tài sản)
TK_LUONG_TINH = {"131", "331", "421"}  # có thể dư Nợ hoặc dư Có
TINH_CHAT_NO, TINH_CHAT_CO, TINH_CHAT_LT = "no", "co", "luong_tinh"
CAP_1, CAP_2 = 1, 2

TK_TIEN = (TK_TIEN_MAT, TK_TIEN_GUI)
TK_KHACH_HANG, TK_NCC, TK_NHAN_VIEN = "131", "331", "141"
DOI_TUONG_TK = (TK_KHACH_HANG, TK_NCC, TK_NHAN_VIEN)
GIOI_HAN_TIM = 20

_ZERO = Decimal("0")


# ─── Danh mục TK + tính chất ────────────────────────────────────────────────

def _tinh_chat(tk: str) -> str:
    if tk in TK_LUONG_TINH:
        return TINH_CHAT_LT
    if tk == TK_HAO_MON or tk[0] in ("3", "4"):
        return TINH_CHAT_CO
    return TINH_CHAT_NO if tk in ASSET_ACCOUNTS or tk[0] in ("1", "2") else TINH_CHAT_CO


def tai_khoan_co_so_du(danh_muc: dict[str, str], tk_da_ghi: Iterable[str] = ()) -> dict[str, Optional[str]]:
    """{mã TK: TK cha (None nếu cấp 1)} theo thứ tự hiển thị — các TK loại 1–4 nhận số dư đầu kỳ.

    `danh_muc` = danh_muc_tk(db). TK có TK con (111/112 → 1111, 1121…) nhập theo TK con, đặt ngay
    chỗ TK cha; TK cha chỉ còn khi bút toán đầu kỳ đã lưu có dòng ghi thẳng nó (`tk_da_ghi`, dữ liệu
    cũ — giữ để không mất số). TK chưa có TK con nào vẫn nhập thẳng như cũ."""
    con_theo_cha: dict[str, list[str]] = {}
    for ma in danh_muc:
        cha = tk_cha_cua(ma)
        if cha is not None:
            con_theo_cha.setdefault(cha, []).append(ma)
    da_ghi = set(tk_da_ghi)
    out: dict[str, Optional[str]] = {}
    for tk in sorted(tk for tk in ACCOUNTS if tk[0] in LOAI_TK_CO_SO_DU):
        con = sorted(con_theo_cha.get(tk, ()))
        if not con or tk in da_ghi:
            out[tk] = None
        out.update((ma, tk) for ma in con)
    return out


def _tk_da_ghi(je: Optional[JournalEntry]) -> set[str]:
    return {ln.account_code for ln in je.lines} if je is not None else set()


# ─── Ngày số dư + khoá sổ ───────────────────────────────────────────────────

def _but_toan_dau_ky(db: Session) -> Optional[JournalEntry]:
    return db.execute(
        select(JournalEntry)
        .where(JournalEntry.source_type == SOURCE_TYPE, JournalEntry.trang_thai == "da_post")
        .order_by(JournalEntry.id.desc()).limit(1)
    ).scalar_one_or_none()


def ngay_so_du(db: Session, je: Optional[JournalEntry]) -> date:
    """Ngày bắt đầu dùng sổ cái: Cài đặt → bút toán đầu kỳ đã lưu (ngày hạch toán + 1) → NGAY_BAT_DAU_MAC_DINH.

    Bỏ hai nấc cuối cũ ("chứng từ sớm nhất" rồi "1/1 năm nay"): khi Cài đặt để trống chúng rơi về
    30/11/2024 (khấu hao cũ nhất) — sớm hơn ngày sổ cái thật sự bắt đầu 19 tháng.
    """
    st = db.get(CaiDatHeThong, 1)
    if st is not None and st.ngay_bat_dau_dung:
        return st.ngay_bat_dau_dung
    if je is not None:
        return je.ngay + timedelta(days=1)
    return NGAY_BAT_DAU_MAC_DINH


def khoa_so_den(db: Session) -> Optional[date]:
    thang = db.execute(
        select(KyKeToan.thang).where(KyKeToan.trang_thai == "da_chot")
        .order_by(KyKeToan.thang.desc()).limit(1)
    ).scalar()
    if not thang:
        return None
    y, m = int(thang[:4]), int(thang[5:7])
    return date(y, m, calendar.monthrange(y, m)[1])


# ─── Đối tượng (khách hàng / NCC / nhân viên) ───────────────────────────────

_SQL_DT = {
    TK_NHAN_VIEN: "SELECT ma_nv AS id, ma_nv AS ma, ho_ten AS ten FROM hcns.employees",
    TK_NCC: "SELECT id, COALESCE(NULLIF(short_code, ''), id) AS ma, name AS ten FROM muahang.suppliers",
    TK_KHACH_HANG: "SELECT CAST(id AS VARCHAR) AS id, COALESCE(sdt, '') AS ma, ho_ten AS ten FROM baogia.customers",
}
_SQL_DT_MAC_DINH = {
    # 131 (hàng chục nghìn khách) KHÔNG liệt kê sẵn — thêm qua ô tìm.
    TK_NHAN_VIEN: " WHERE ngay_nghi_viec IS NULL ORDER BY ho_ten",
    TK_NCC: " ORDER BY name",
}


def _dt_theo_id(db: Session, tk: str, ids: list[str]) -> dict[str, tuple[str, str]]:
    if not ids:
        return {}
    cot_id = "CAST(id AS VARCHAR)" if tk == TK_KHACH_HANG else ("ma_nv" if tk == TK_NHAN_VIEN else "id")
    rows = db.execute(text(_SQL_DT[tk] + f" WHERE {cot_id} = ANY(:ids)"), {"ids": ids}).all()
    return {r.id: (r.ma, r.ten) for r in rows}


def tim_doi_tuong(db: Session, tk: str, q: str) -> list[dict]:
    if tk not in DOI_TUONG_TK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "tk phải là 131, 331 hoặc 141")
    q = (q or "").strip()
    if not q:
        return []
    # Không phân biệt dấu + hoa/thường ("chien" ra "CHIẾN PHƯƠNG") — tim_kiem.py.
    sql = f"SELECT * FROM ({_SQL_DT[tk]}) d WHERE {sql_khop(('d.ten', 'd.ma'), 'q')} ORDER BY d.ten LIMIT :n"
    rows = db.execute(text(sql), {"q": mau_like(q), "n": GIOI_HAN_TIM}).all()
    return [{"tk": tk, "id": r.id, "ma": r.ma, "ten": r.ten, "du_no": 0, "du_co": 0} for r in rows]


# ─── Đối chiếu tiền với Sổ quỹ / Ngân hàng ──────────────────────────────────

def so_du_tien_theo_so_quy(db: Session, ngay: date) -> dict:
    """Tồn ĐẦU ngày `ngay` của từng tài khoản tiền theo Sổ quỹ + mốc "Chốt số dư đầu kỳ" TK ngân
    hàng (cùng thuật toán neo với màn Sổ quỹ/Ngân hàng — so_quy_auto.so_du_truoc_ngay), gắn vào
    TK con của tài khoản đó (1111, 1121…); 111/112 = tổng các tài khoản chưa có TK con (thường 0).
    Chỉ để THAM CHIẾU cạnh ô nhập, không tự ghi: bảng cân đối lấy tiền từ sổ quỹ, còn sổ
    cái/cân đối phát sinh lấy từ journal — nhập khớp số này thì hai nơi không mâu thuẫn.

    Ngày trước mốc chốt sớm nhất thì Sổ quỹ chỉ có số "trừ ngược" từ mốc tương lai
    (thường âm, không có ý nghĩa) → không đưa số, chỉ báo mốc sớm nhất."""
    moc = db.execute(select(func.min(SoDuDauKy.thang))).scalar()
    out = {"moc_som_nhat": moc.isoformat() if moc else None, "co_so": bool(moc and ngay >= moc)}
    if out["co_so"]:
        tien = dict.fromkeys(TK_TIEN, _ZERO)
        for tk in db.execute(select(TaiKhoanNH)).scalars():
            ma = tk_tien_cua(tk)
            tien[ma] = tien.get(ma, _ZERO) + so_du_truoc_ngay(db, tk.id, tk.ten_tk, ngay)
        out.update({k: int(v) for k, v in tien.items()})
    return out


# ─── GET ────────────────────────────────────────────────────────────────────

def doc_so_du(db: Session, quyen_sua: bool) -> dict:
    je = _but_toan_dau_ky(db)
    ngay = ngay_so_du(db, je)
    khoa_den = khoa_so_den(db)
    khoa = bool(khoa_den and khoa_den >= ngay - timedelta(days=1))

    net: dict[str, Decimal] = {}
    for ln in (je.lines if je else []):
        net[ln.account_code] = net.get(ln.account_code, _ZERO) + (ln.so_tien if ln.loai == "no" else -ln.so_tien)
    tham_chieu = so_du_tien_theo_so_quy(db, ngay)
    danh_muc = danh_muc_tk(db)
    tai_khoan = []
    # Mỗi dòng chỉ mang số ghi đúng mã của nó (TK cha không gộp TK con) → cộng mọi dòng không trùng.
    for tk, cha in tai_khoan_co_so_du(danh_muc, _tk_da_ghi(je)).items():
        goc = cha or tk
        n = net.get(tk, _ZERO)
        tai_khoan.append({
            "tk": tk, "ten": danh_muc[tk], "loai": int(goc[0]), "tinh_chat": _tinh_chat(goc),
            "cap": CAP_2 if cha else CAP_1, "tk_cha": cha,
            "du_no": int(n) if n > 0 else 0, "du_co": int(-n) if n < 0 else 0,
            "doi_tuong": tk if tk in DOI_TUONG_TK else None,
            "so_quy": tham_chieu.get(tk, 0) if goc in TK_TIEN and tham_chieu["co_so"] else None,
        })

    da_luu = db.execute(select(SoDuDauKyDoiTuong).order_by(SoDuDauKyDoiTuong.tk, SoDuDauKyDoiTuong.ten)).scalars().all()
    doi_tuong = [
        {"tk": d.tk, "id": d.doi_tuong_id, "ma": d.ma, "ten": d.ten, "du_no": int(d.du_no), "du_co": int(d.du_co)}
        for d in da_luu
    ]
    co = {(d["tk"], d["id"]) for d in doi_tuong}
    for tk, where in _SQL_DT_MAC_DINH.items():
        for r in db.execute(text(_SQL_DT[tk] + where)).all():
            if (tk, r.id) not in co:
                doi_tuong.append({"tk": tk, "id": r.id, "ma": r.ma, "ten": r.ten, "du_no": 0, "du_co": 0})

    return {
        "ngay": ngay.isoformat(),
        "ngay_hach_toan": (ngay - timedelta(days=1)).isoformat(),
        "khoa": khoa,
        "khoa_den": khoa_den.isoformat() if khoa_den else None,
        "quyen_sua": quyen_sua,
        "but_toan_id": je.id if je else None,
        "tien_so_quy": tham_chieu,
        "tai_khoan": tai_khoan,
        "doi_tuong": doi_tuong,
    }


# ─── PUT ────────────────────────────────────────────────────────────────────

def _mot_ben(tk: str, no: Decimal, co: Decimal) -> None:
    if no > 0 and co > 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"TK {tk}: mỗi dòng chỉ nhập một bên Nợ hoặc Có")


def luu_so_du(db: Session, body, by_user: str) -> dict:
    je_cu = _but_toan_dau_ky(db)
    ngay = ngay_so_du(db, je_cu)
    khoa_den = khoa_so_den(db)
    ngay_ht = ngay - timedelta(days=1)
    if khoa_den and khoa_den >= ngay_ht:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Sổ đã khoá đến {khoa_den:%d/%m/%Y} — mở khoá sổ trước khi sửa số dư đầu kỳ.",
        )

    # Cùng danh sách với màn GET: TK tiền nhập theo TK con, TK cha chỉ nhận khi bản đã lưu có dòng ghi thẳng nó.
    hop_le = tai_khoan_co_so_du(danh_muc_tk(db), _tk_da_ghi(je_cu))
    tk_net: dict[str, Decimal] = {}
    for x in body.tai_khoan:
        if x.tk not in hop_le:
            con = [ma for ma, cha in hop_le.items() if cha == x.tk]
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"TK {x.tk} nhập số dư theo TK con: {', '.join(con)}" if con
                else f"TK {x.tk} không nhận số dư đầu kỳ",
            )
        if x.tk in tk_net:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"TK {x.tk} bị gửi hai lần")
        _mot_ben(x.tk, x.du_no, x.du_co)
        tk_net[x.tk] = x.du_no - x.du_co
    tong_no = sum((v for v in tk_net.values() if v > 0), _ZERO)
    tong_co = sum((-v for v in tk_net.values() if v < 0), _ZERO)
    if tong_no != tong_co:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Tổng dư Nợ {int(tong_no):,} khác tổng dư Có {int(tong_co):,} — chưa cân.",
        )

    theo_tk: dict[str, list] = {tk: [] for tk in DOI_TUONG_TK}
    for d in body.doi_tuong:
        if d.tk not in theo_tk:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"TK {d.tk} không có chi tiết đối tượng")
        _mot_ben(d.tk, d.du_no, d.du_co)
        if d.du_no or d.du_co:
            theo_tk[d.tk].append(d)
    moi_dt: list[SoDuDauKyDoiTuong] = []
    for tk, ds in theo_tk.items():
        if not ds:
            continue
        ids = [d.id for d in ds]
        if len(set(ids)) != len(ids):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"TK {tk}: một đối tượng bị gửi hai lần")
        tra = _dt_theo_id(db, tk, ids)
        thieu = [i for i in ids if i not in tra]
        if thieu:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"TK {tk}: không tìm thấy đối tượng {', '.join(thieu[:5])}")
        tong_ct = sum((d.du_no - d.du_co for d in ds), _ZERO)
        if tong_ct != tk_net.get(tk, _ZERO):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Chi tiết đối tượng TK {tk} ({int(tong_ct):,}) chưa khớp số dư tài khoản ({int(tk_net.get(tk, _ZERO)):,}).",
            )
        moi_dt += [
            SoDuDauKyDoiTuong(tk=tk, doi_tuong_id=d.id, ma=tra[d.id][0], ten=tra[d.id][1],
                              du_no=d.du_no, du_co=d.du_co, updated_by=by_user)
            for d in ds
        ]

    # Thay toàn bộ: bút toán đầu kỳ cũ (kể cả bản đã huỷ) + chi tiết đối tượng.
    for je in db.execute(select(JournalEntry).where(JournalEntry.source_type == SOURCE_TYPE)).scalars():
        db.delete(je)
    db.execute(delete(SoDuDauKyDoiTuong))
    db.flush()

    je_moi = None
    lines = [
        {"loai": "no" if v > 0 else "co", "account_code": tk, "so_tien": abs(v),
         "ghi_chu": "Số dư đầu kỳ"}
        for tk, v in sorted(tk_net.items()) if v != 0
    ]
    if lines:
        je_moi = post_journal(
            db, ngay=ngay_ht, mo_ta=f"Số dư đầu kỳ tại ngày {ngay:%d/%m/%Y}",
            source_type=SOURCE_TYPE, source_id=SOURCE_ID, by_user=by_user, lines=lines,
        )
    db.add_all(moi_dt)

    st = db.get(CaiDatHeThong, 1)
    if st is not None and st.ngay_bat_dau_dung is None:
        # Cố định ngày bắt đầu: nếu không, mặc định "chứng từ sớm nhất" của màn
        # Cài đặt sẽ trôi sang ngày của chính bút toán đầu kỳ vừa ghi.
        st.ngay_bat_dau_dung = ngay
    db.commit()
    return {
        "ngay": ngay.isoformat(), "but_toan_id": je_moi.id if je_moi else None,
        "tong_no": int(tong_no), "tong_co": int(tong_co), "so_doi_tuong": len(moi_dt),
    }
