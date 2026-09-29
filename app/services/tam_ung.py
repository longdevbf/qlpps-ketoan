"""Tạm ứng nhân viên (TK 141) — nghiệp vụ cho màn /ketoan/tam-ung.

Hạch toán qua `services/journal.py` (post_journal / void_journal), tiền thật
lên sổ quỹ (`ketoan.so_quy`, nguồn số dư tiền của toàn app) — xem docstring
models/tam_ung.py. Router (routers/tam_ung.py) chỉ gọi các hàm ở đây.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session

from ..models import (
    ChiPhiPhatSinh, JournalEntry, JournalLine, SoQuy, TaiKhoanNH,
    TamUng, TamUngQuyetToan,
)
from .tai_khoan_tien import tk_tien_cua
from .journal import post_journal, void_journal
from .period_close import is_ky_da_chot
from .so_quy_auto import assert_du_chi
from .tim_kiem import chua_khong_dau


# ─── Hằng số tài khoản / nhãn ───────────────────────────────────────────────
TK_TAM_UNG = "141"
TK_PHAI_TRA_NLD = "334"
# TK chi phí được chọn khi quyết toán → nhóm chi phí P&L (khớp
# routers/chi_phi.py:_NHOM_TO_ACCOUNT). Chỉ các TK chi phí CÓ trong CoA.
TK_CHI_PHI_QUYET_TOAN: dict[str, str] = {
    "641": "ban_hang", "642": "quan_ly", "635": "tai_chinh", "811": "khac",
}

SOURCE_UNG = "tam_ung"
SOURCE_QT = "tam_ung_quyet_toan"
REF_TABLE = "tam_ung"
SO_QUY_LIEN_QUAN = "tam_ung"
SO_QUY_CF = "khac"
LOAI_CHI_PHI_QT = "Quyết toán tạm ứng"
PREFIX_UNG = "TU"
PREFIX_QT = "QTTU"

XU_LY_THU_TIEN = "thu_tien"
XU_LY_TRU_LUONG = "tru_luong"

TT_HIEU_LUC = "hieu_luc"
TT_DA_HUY = "da_huy"

# trạng thái hiển thị (khớp nhãn trong static/js/kt-tam-ung.js)
TT_CHUA_QT = "chua_quyet_toan"
TT_MOT_PHAN = "mot_phan"
TT_QUA_HAN = "qua_han"
TT_DA_QT = "da_quyet_toan"
LOC_CON_NO = "con_no"

HAN_HOAN_MAC_DINH = timedelta(days=30)

_ZERO = Decimal("0")


# ─── Tiện ích ───────────────────────────────────────────────────────────────

def _int(v: Decimal) -> int:
    return int(v or 0)


def _next_so_ct(db: Session, model, prefix: str, ngay: date) -> str:
    """Số chứng từ <PREFIX>-YYYY-NNNN, khoá advisory theo (prefix, năm)."""
    head = f"{prefix}-{ngay.year}-"
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"so_ct:{head}"})
    rows = db.execute(select(model.so_ct).where(model.so_ct.like(f"{head}%"))).scalars().all()
    seq = max((int(s[len(head):]) for s in rows if s[len(head):].isdigit()), default=0)
    return f"{head}{seq + 1:04d}"


def _chan_ky_da_khoa(db: Session, ngay: date) -> None:
    if is_ky_da_chot(db, ngay):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Kỳ {ngay:%m/%Y} đã khoá sổ — không ghi/sửa chứng từ ngày {ngay:%d/%m/%Y}.",
        )


def _nhan_vien(db: Session, ma: str) -> tuple[str, str]:
    row = db.execute(
        text("SELECT ma_nv, ho_ten FROM hcns.employees WHERE ma_nv = :ma"), {"ma": ma},
    ).first()
    if not row:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Không tìm thấy nhân viên mã {ma!r}")
    return row[0], row[1]


def list_nhan_vien(db: Session) -> list[dict]:
    """Nhân viên đang làm (hcns.employees) — cho ô chọn khi lập tạm ứng."""
    rows = db.execute(text(
        "SELECT ma_nv, ho_ten, phong_ban FROM hcns.employees "
        "WHERE ngay_nghi_viec IS NULL AND trang_thai <> 'Đã nghỉ' ORDER BY ho_ten"
    )).all()
    return [{"ma": r[0], "ten": r[1], "phong_ban": r[2]} for r in rows]


def _tai_khoan(db: Session, tk_id: int) -> TaiKhoanNH:
    tk = db.get(TaiKhoanNH, tk_id)
    if not tk or not tk.active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tài khoản chi không tồn tại hoặc đã ngừng dùng")
    return tk


def _qt_hieu_luc(tu: TamUng) -> list[TamUngQuyetToan]:
    return [q for q in tu.quyet_toans if q.trang_thai == TT_HIEU_LUC]


def _so_lieu(tu: TamUng, hom_nay: date) -> dict:
    qts = _qt_hieu_luc(tu)
    da_qt = sum((q.giam_tam_ung for q in qts), _ZERO)
    con_lai = tu.so_tien - da_qt
    qua_han = (hom_nay - tu.han_hoan).days if con_lai > 0 and tu.han_hoan < hom_nay else 0
    if con_lai <= 0:
        tt = TT_DA_QT
    elif qua_han:
        tt = TT_QUA_HAN
    elif da_qt > 0:
        tt = TT_MOT_PHAN
    else:
        tt = TT_CHUA_QT
    return {"da_qt": da_qt, "con_lai": con_lai, "qua_han": qua_han, "trang_thai": tt}


def serialize(tu: TamUng, hom_nay: Optional[date] = None, chi_tiet: bool = False) -> dict:
    sl = _so_lieu(tu, hom_nay or date.today())
    out = {
        "id": tu.id,
        "so_ct": tu.so_ct,
        "ung_id": tu.journal_id,
        "ngay": tu.ngay.isoformat(),
        "nhan_vien": {"ma": tu.nhan_vien_ma, "ten": tu.nhan_vien_ten},
        "noi_dung": tu.noi_dung,
        "da_ung": _int(tu.so_tien),
        "da_quyet_toan": _int(sl["da_qt"]),
        "con_lai": _int(sl["con_lai"]),
        "han_hoan": tu.han_hoan.isoformat(),
        "qua_han_ngay": sl["qua_han"],
        "trang_thai": sl["trang_thai"],
        "tai_khoan": {"id": tu.tai_khoan_id, "ten": tu.tai_khoan_ten, "tk": tu.tk_tien},
        "so_lan_quyet_toan": len(_qt_hieu_luc(tu)),
    }
    if chi_tiet:
        out["quyet_toan"] = [
            {
                "id": q.journal_id, "qt_id": q.id, "so_ct": q.so_ct, "ngay": q.ngay.isoformat(),
                "chi_phi": _int(q.chi_phi), "tk_cp": q.tk_cp, "hoan": _int(q.hoan),
                "chi_bu": _int(q.chi_bu), "xu_ly_thua": q.xu_ly_thua, "ghi_chu": q.ghi_chu,
            }
            for q in _qt_hieu_luc(tu)
        ]
    return out


def _so_du_so_cai_141(db: Session) -> Decimal:
    """Số dư Nợ TK 141 trên journal (chỉ bút toán 'da_post')."""
    v = db.execute(
        select(func.coalesce(func.sum(case(
            (JournalLine.loai == "no", JournalLine.so_tien), else_=-JournalLine.so_tien,
        )), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_id)
        .where(JournalLine.account_code == TK_TAM_UNG, JournalEntry.trang_thai == "da_post")
    ).scalar()
    return Decimal(str(v or 0))


# ─── Đọc ────────────────────────────────────────────────────────────────────

def _lay(db: Session, tu_id: int) -> TamUng:
    tu = db.get(TamUng, tu_id)
    if not tu or tu.trang_thai != TT_HIEU_LUC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Khoản tạm ứng không tồn tại")
    return tu


def list_tam_ung(db: Session, tim: str = "", trang_thai: str = "") -> dict:
    hom_nay = date.today()
    dau_thang = hom_nay.replace(day=1)
    rows = db.execute(
        select(TamUng).where(TamUng.trang_thai == TT_HIEU_LUC)
        .order_by(TamUng.ngay.desc(), TamUng.id.desc())
    ).scalars().all()
    tat_ca = [serialize(t, hom_nay) for t in rows]

    con_no = [r for r in tat_ca if r["con_lai"] > 0]
    qua_han = [r for r in con_no if r["trang_thai"] == TT_QUA_HAN]
    tong = {
        "con_lai": sum(r["con_lai"] for r in con_no),
        "qua_han": sum(r["con_lai"] for r in qua_han),
        "so_qua_han": len(qua_han),
        "so_nv": len({r["nhan_vien"]["ma"] for r in con_no}),
        "da_ung_thang": sum(r["da_ung"] for r in tat_ca if r["ngay"] >= dau_thang.isoformat()),
    }

    dong = [
        r for r in tat_ca
        # không phân biệt dấu + hoa/thường ("thinh" ra "Anh THỊNH") — tim_kiem.py
        if chua_khong_dau(f"{r['nhan_vien']['ten']} {r['nhan_vien']['ma']} {r['so_ct']} {r['noi_dung']}", tim)
        and (
            not trang_thai
            or (trang_thai == LOC_CON_NO and r["con_lai"] > 0)
            or r["trang_thai"] == trang_thai
        )
    ]
    return {"dong": dong, "tong": tong, "so_sach": {"tk141": _int(_so_du_so_cai_141(db))}}


def get_tam_ung(db: Session, tu_id: int) -> dict:
    return serialize(_lay(db, tu_id), chi_tiet=True)


# ─── Lập / sửa / xoá khoản tạm ứng ──────────────────────────────────────────

def _post_ung(db: Session, tu: TamUng, by_user: str) -> JournalEntry:
    return post_journal(
        db, ngay=tu.ngay,
        mo_ta=f"Chi tạm ứng {tu.so_ct} — {tu.nhan_vien_ten}: {tu.noi_dung}",
        source_type=SOURCE_UNG, source_id=str(tu.id), by_user=by_user,
        lines=[
            {"loai": "no", "account_code": TK_TAM_UNG, "ref_table": REF_TABLE,
             "ref_id": tu.id, "so_tien": tu.so_tien, "ghi_chu": tu.nhan_vien_ten},
            {"loai": "co", "account_code": tu.tk_tien, "ref_table": "tai_khoan_nh",
             "ref_id": tu.tai_khoan_id, "so_tien": tu.so_tien,
             "ghi_chu": f"Chi từ {tu.tai_khoan_ten}"},
        ],
    )


def _ghi_so_quy_ung(db: Session, tu: TamUng, by_user: str) -> SoQuy:
    sq = db.get(SoQuy, tu.so_quy_id) if tu.so_quy_id else None
    if sq is None:
        sq = SoQuy(lien_quan=SO_QUY_LIEN_QUAN, ref_id=tu.so_ct, created_by=by_user)
        db.add(sq)
    sq.ngay = tu.ngay
    sq.loai = "chi"
    sq.so_tien = tu.so_tien
    sq.tai_khoan = tu.tai_khoan_ten
    sq.noi_dung = f"Chi tạm ứng {tu.so_ct} — {tu.nhan_vien_ten}: {tu.noi_dung}"
    sq.nhan_vien_ten = tu.nhan_vien_ten
    sq.phan_loai_cf = SO_QUY_CF
    db.flush()
    return sq


def _ap_du_lieu(db: Session, tu: TamUng, body) -> None:
    ma, ten = _nhan_vien(db, body.nhan_vien_ma)
    tk = _tai_khoan(db, body.tai_khoan_id)
    tu.nhan_vien_ma, tu.nhan_vien_ten = ma, ten
    tu.ngay = body.ngay
    tu.noi_dung = body.noi_dung.strip()
    tu.so_tien = body.so_tien
    tu.han_hoan = body.han_hoan or (body.ngay + HAN_HOAN_MAC_DINH)
    if tu.han_hoan < tu.ngay:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Hạn hoàn ứng phải từ ngày ứng trở đi")
    tu.tai_khoan_id, tu.tai_khoan_ten, tu.tk_tien = tk.id, tk.ten_tk, tk_tien_cua(tk)


def tao_tam_ung(db: Session, body, by_user: str) -> TamUng:
    _chan_ky_da_khoa(db, body.ngay)
    tu = TamUng(created_by=by_user, updated_by=by_user)
    _ap_du_lieu(db, tu, body)
    assert_du_chi(db, tu.tai_khoan_ten, tu.so_tien)
    tu.so_ct = _next_so_ct(db, TamUng, PREFIX_UNG, tu.ngay)
    db.add(tu)
    db.flush()
    tu.journal_id = _post_ung(db, tu, by_user).id
    tu.so_quy_id = _ghi_so_quy_ung(db, tu, by_user).id
    db.commit()
    db.refresh(tu)
    return tu


def _chan_da_quyet_toan(tu: TamUng, viec: str) -> None:
    if _qt_hieu_luc(tu):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Khoản {tu.so_ct} đã quyết toán — huỷ các lần quyết toán trước khi {viec}.",
        )


def _void_neu_co(db: Session, je_id: Optional[int], by_user: str) -> None:
    je = db.get(JournalEntry, je_id) if je_id else None
    if je is not None and je.trang_thai == "da_post":
        void_journal(db, je_id=je.id, by_user=by_user)


def sua_tam_ung(db: Session, tu_id: int, body, by_user: str) -> TamUng:
    tu = _lay(db, tu_id)
    _chan_da_quyet_toan(tu, "sửa")
    _chan_ky_da_khoa(db, tu.ngay)
    _chan_ky_da_khoa(db, body.ngay)
    tk_cu, tien_cu = tu.tai_khoan_ten, tu.so_tien
    _ap_du_lieu(db, tu, body)
    can_them = tu.so_tien - (tien_cu if tu.tai_khoan_ten == tk_cu else _ZERO)
    if can_them > 0:
        assert_du_chi(db, tu.tai_khoan_ten, can_them)
    tu.updated_by = by_user
    _void_neu_co(db, tu.journal_id, by_user)
    tu.journal_id = _post_ung(db, tu, by_user).id
    tu.so_quy_id = _ghi_so_quy_ung(db, tu, by_user).id
    db.commit()
    db.refresh(tu)
    return tu


def xoa_tam_ung(db: Session, tu_id: int, by_user: str) -> TamUng:
    tu = _lay(db, tu_id)
    _chan_da_quyet_toan(tu, "xoá")
    _chan_ky_da_khoa(db, tu.ngay)
    _void_neu_co(db, tu.journal_id, by_user)
    sq = db.get(SoQuy, tu.so_quy_id) if tu.so_quy_id else None
    if sq is not None:
        db.delete(sq)
    tu.so_quy_id = None
    tu.trang_thai = TT_DA_HUY
    tu.updated_by = by_user
    db.commit()
    return tu


# ─── Quyết toán ─────────────────────────────────────────────────────────────

def quyet_toan(db: Session, body, by_user: str) -> dict:
    tu = _lay(db, body.id)
    _chan_ky_da_khoa(db, body.ngay)
    if body.ngay < tu.ngay:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ngày quyết toán không được trước ngày ứng")
    con = _so_lieu(tu, body.ngay)["con_lai"]
    if con <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Khoản {tu.so_ct} đã quyết toán xong")
    cp = body.chi_phi
    if cp > 0 and body.tk_cp not in TK_CHI_PHI_QUYET_TOAN:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "TK chi phí phải là một trong " + ", ".join(TK_CHI_PHI_QUYET_TOAN),
        )
    if cp == 0 and not body.het:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nhập chi phí thực tế, hoặc chọn kết thúc để ghi nhận nhân viên hoàn lại toàn bộ",
        )
    if body.xu_ly_thua not in (XU_LY_THU_TIEN, XU_LY_TRU_LUONG):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "xu_ly_thua không hợp lệ")

    thua = con - cp
    hoan = chi_bu = _ZERO
    ket_thuc = True
    if thua < 0:
        chi_bu, giam = -thua, con
    elif thua == 0:
        giam = cp
    elif body.het:
        hoan, giam = thua, con
    else:
        giam, ket_thuc = cp, False
    if chi_bu > 0:
        assert_du_chi(db, tu.tai_khoan_ten, chi_bu)

    qt = TamUngQuyetToan(
        tam_ung_id=tu.id, ngay=body.ngay, chi_phi=cp, tk_cp=body.tk_cp if cp > 0 else None,
        hoan=hoan, chi_bu=chi_bu, xu_ly_thua=body.xu_ly_thua if hoan > 0 else None,
        giam_tam_ung=giam, ket_thuc=ket_thuc, ghi_chu=(body.ghi_chu or "").strip() or None,
        created_by=by_user,
    )
    qt.so_ct = _next_so_ct(db, TamUngQuyetToan, PREFIX_QT, body.ngay)
    db.add(qt)
    db.flush()

    nv = tu.nhan_vien_ten
    lines: list[dict] = []
    if cp > 0:
        lines.append({"loai": "no", "account_code": body.tk_cp, "so_tien": cp,
                      "ref_table": REF_TABLE, "ref_id": tu.id, "ghi_chu": f"Chi phí thực tế — {tu.noi_dung}"})
    if hoan > 0:
        tk_hoan = TK_PHAI_TRA_NLD if body.xu_ly_thua == XU_LY_TRU_LUONG else tu.tk_tien
        lines.append({"loai": "no", "account_code": tk_hoan, "so_tien": hoan,
                      "ref_table": REF_TABLE, "ref_id": tu.id,
                      "ghi_chu": f"Trừ lương {nv}" if tk_hoan == TK_PHAI_TRA_NLD else f"{nv} nộp lại {tu.tai_khoan_ten}"})
    lines.append({"loai": "co", "account_code": TK_TAM_UNG, "so_tien": giam,
                  "ref_table": REF_TABLE, "ref_id": tu.id, "ghi_chu": nv})
    if chi_bu > 0:
        lines.append({"loai": "co", "account_code": tu.tk_tien, "so_tien": chi_bu,
                      "ref_table": REF_TABLE, "ref_id": tu.id, "ghi_chu": f"Chi bù cho {nv} từ {tu.tai_khoan_ten}"})
    je = post_journal(
        db, ngay=body.ngay, mo_ta=f"Quyết toán tạm ứng {tu.so_ct} ({qt.so_ct}) — {nv}",
        source_type=SOURCE_QT, source_id=str(qt.id), by_user=by_user, lines=lines,
    )
    qt.journal_id = je.id

    tien_mat = chi_bu if chi_bu > 0 else (hoan if body.xu_ly_thua == XU_LY_THU_TIEN else _ZERO)
    if tien_mat > 0:
        sq = SoQuy(
            ngay=body.ngay, loai="chi" if chi_bu > 0 else "thu", so_tien=tien_mat,
            tai_khoan=tu.tai_khoan_ten, lien_quan=SO_QUY_LIEN_QUAN, ref_id=qt.so_ct,
            noi_dung=(f"Chi bù tạm ứng {tu.so_ct} cho {nv}" if chi_bu > 0
                      else f"{nv} hoàn tạm ứng {tu.so_ct}"),
            nhan_vien_ten=nv, phan_loai_cf=SO_QUY_CF, created_by=by_user,
        )
        db.add(sq)
        db.flush()
        qt.so_quy_id = sq.id

    if cp > 0:
        # Chi phí thực tế lên P&L (pl_calculator đọc chi_phi_phat_sinh). Không
        # tạo sổ quỹ: tiền đã ra ở lúc chi tạm ứng.
        cpps = ChiPhiPhatSinh(
            ngay=body.ngay, so_tien=cp, loai_chi_phi=LOAI_CHI_PHI_QT,
            ten_khoan=tu.noi_dung[:255], nhom_chi_phi=TK_CHI_PHI_QUYET_TOAN[body.tk_cp],
            nguoi_chi=nv[:128], mo_ta=f"Quyết toán tạm ứng {tu.so_ct} ({qt.so_ct})",
            ghi_chu=qt.ghi_chu, created_by=by_user,
        )
        db.add(cpps)
        db.flush()
        qt.chi_phi_id = cpps.id

    db.commit()
    return {"so_ct": qt.so_ct, "con_lai": _int(con - giam), "journal_id": qt.journal_id}


def huy_quyet_toan(db: Session, qt_id: int, by_user: str) -> TamUng:
    """Huỷ LẦN QUYẾT TOÁN GẦN NHẤT (đảo bút toán, xoá sổ quỹ + chi phí đã sinh)."""
    qt = db.get(TamUngQuyetToan, qt_id)
    if not qt or qt.trang_thai != TT_HIEU_LUC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Lần quyết toán không tồn tại")
    tu = _lay(db, qt.tam_ung_id)
    if _qt_hieu_luc(tu)[-1].id != qt.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Chỉ huỷ được lần quyết toán gần nhất")
    _chan_ky_da_khoa(db, qt.ngay)
    _void_neu_co(db, qt.journal_id, by_user)
    for model, rid in ((SoQuy, qt.so_quy_id), (ChiPhiPhatSinh, qt.chi_phi_id)):
        obj = db.get(model, rid) if rid else None
        if obj is not None:
            db.delete(obj)
    qt.so_quy_id = qt.chi_phi_id = None
    qt.trang_thai = TT_DA_HUY
    db.commit()
    db.refresh(tu)
    return tu
