"""Thuế TNCN (khấu trừ từ lương, theo tháng) + thuế TNDN tạm tính (theo quý).

TNCN — NGUỒN SỐ LIỆU:
  1. Nếu HR đã lập bảng TNCN tháng (`hcns.tncn_data`, màn TNCN của HCNS — có thể đã sửa tay
     `override`) → lấy nguyên số của HR.
  2. Nếu chưa → tạm tính từ BẢNG LƯƠNG LIVE của HCNS (`hcns.app.routers.payroll.bang_luong_thang`
     — cùng nguồn màn Bảng lương Kế toán `/api/external/luong`; `hcns.payroll` không được lưu):
       thu nhập chịu thuế = `tong_cong` (tổng các khoản cộng), trừ BH bắt buộc `bhxh_tru`,
       trừ giảm trừ gia cảnh; thuế tính bằng CHÍNH HÀM + CẤU HÌNH của HR
       (`_load_tncn_config`, `_calc_tncn_progressive`, `_count_npt`, luật khoán 10% cho HĐ
       ngoài `loai_hd_luy_tien` — y hệt `calc_tncn_taxes`). Khoản miễn thuế (ăn trưa, phần
       chênh làm thêm giờ) CHƯA được tách → đang tính là chịu thuế (ghi rõ trên màn).
  Ghi sổ: Nợ 334 / Có 3335, ngày cuối tháng, source_type='thue_tncn', source_id='YYYY-MM'.

TNDN — NGUỒN SỐ LIỆU:
  Lợi nhuận kế toán trước thuế = Σ `ln_truoc_thue` của `pl_calculator.calc_pl_for_month`
  các tháng trong quý (cùng hàm báo cáo KQKD /api/bao-cao/pl, dùng chung cache 'pl:YYYY-MM').
  Thuế suất = `pl_calculator.TAX_RATE_TNDN` (hằng số báo cáo KQKD đang dùng) — KHÔNG tự đặt số khác.
  Thuế quý = thuế suất × max(0, LN + điều chỉnh tăng − điều chỉnh giảm) (tính trên cả quý, như
  /pl/yearly tính trên cả năm để tháng lỗ bù tháng lãi).
  Ghi sổ: Nợ 821 / Có 3334, ngày cuối quý, source_type='thue_tndn_tam_nop', source_id='Qn-YYYY'.
"""
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload

from ..models.cai_dat_he_thong import CaiDatHeThong
from ..models.thue_tndn_dieu_chinh import ThueTndnDieuChinh
from . import ky_thue
from .journal import post_journal
from .period_close import is_ky_da_chot
from .pl_calculator import TAX_RATE_TNDN, _sum_doanh_thu_thuc_hien, calc_pl_for_month
from .so_cai_doc import but_toan_ra_dict, phat_sinh, tim_but_toan
from .thue_gtgt import vnd

SOURCE_TNCN = "thue_tncn"
SOURCE_TNDN = "thue_tndn_tam_nop"
TK_TNCN = "3335"
TK_TNDN = "3334"
TK_PHAI_TRA_NLD = "334"
TK_CP_THUE_TNDN = "821"
TY_LE_TAM_NOP_TOI_THIEU = Decimal("0.8")      # tạm nộp 4 quý ≥ 80% số quyết toán (NĐ 126/2020 Đ.8)
NGUON_HR = "hr_tncn"
NGUON_LUONG_LIVE = "luong_live"
# Biểu thuế suất TNDN theo doanh thu năm (Luật Thuế TNDN 67/2025/QH15 Đ.10) — CHỈ để gợi ý
# trên màn; số tính thuế vẫn dùng TAX_RATE_TNDN của báo cáo KQKD.
BIEU_TNDN_THEO_DOANH_THU: tuple[tuple[Optional[int], int], ...] = (
    (3_000_000_000, 15), (50_000_000_000, 17), (None, 20),
)
_HANG_TRAM = Decimal(100)


def _dec(x: Any) -> Decimal:
    return Decimal(str(x or 0))


def _ky_ke_khai(db: Session) -> str:
    st = db.get(CaiDatHeThong, 1)
    return (st.ky_ke_khai_thue if st else None) or "quy"


def _kiem_khoa(db: Session, ngay: date) -> None:
    if is_ky_da_chot(db, ngay):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Kỳ {ngay:%m/%Y} đã khoá sổ — mở khoá sổ tháng này trước khi ghi.")


# ═══════════════════════════ TNCN ═══════════════════════════

def _cfg_hr(db: Session) -> dict:
    from hcns.app.routers.tncn import _load_tncn_config  # nguồn cấu hình thuế TNCN của HR
    return _load_tncn_config(db)


def _bac(tn_tinh_thue: Decimal, bieu: list[dict]) -> Optional[int]:
    if tn_tinh_thue <= 0:
        return None
    for i, b in enumerate(bieu, start=1):
        if b.get("den") is None or tn_tinh_thue <= _dec(b["den"]):
            return i
    return len(bieu)


def _dong_tu_hr(db: Session, thang: str, bieu: list[dict]) -> list[dict]:
    from hcns.app.models import Payroll, TncnData
    bh = dict(db.execute(select(Payroll.ma_nv, Payroll.bhxh_tru)
                         .where(Payroll.thang == thang)).all())
    rows = db.execute(select(TncnData).where(TncnData.thang == thang)
                      .order_by(TncnData.ma_nv)).scalars().all()
    return [{
        "ma_nv": r.ma_nv, "ten": r.ho_ten or r.ma_nv, "phong_ban": r.phong_ban or "—",
        "loai_hop_dong": r.loai_hop_dong,
        "tong_thu_nhap": vnd(r.thu_nhap_ca_nhan), "bh": vnd(bh.get(r.ma_nv)),
        "so_npt": int(r.so_npt or 0), "giam_tru": vnd(_dec(r.giam_tru_bn) + _dec(r.giam_tru_npt)),
        "tn_tinh_thue": vnd(r.tn_tinh_thue), "bac": _bac(_dec(r.tn_tinh_thue), bieu),
        "thue": vnd(r.thue_tncn), "sua_tay": bool(r.override),
    } for r in rows]


def _dong_tu_luong(db: Session, user: JWTPayload, thang: str, cfg: dict) -> list[dict]:
    """Tạm tính từ bảng lương live — cùng công thức/cấu hình với HR `calc_tncn_taxes`."""
    from hcns.app.routers.payroll import bang_luong_thang
    from hcns.app.routers.tncn import _calc_tncn_progressive, _count_npt
    luong = bang_luong_thang(user, db, thang)
    gt_bt, gt_npt = _dec(cfg.get("giam_tru_ban_than")), _dec(cfg.get("giam_tru_npt"))
    flat_min, flat_pct = _dec(cfg.get("flat_tax_min")), _dec(cfg.get("flat_tax_pct"))
    luy_tien = set(cfg.get("loai_hd_luy_tien") or [])
    bieu = cfg.get("bac_thue") or []
    out = []
    for r in luong.get("rows", []):
        tong, bh = _dec(r.get("tong_cong")), _dec(r.get("bhxh_tru"))
        if tong <= 0:      # không trả thu nhập trong tháng (vd dòng trợ lý AI tính bằng USD) → không thuộc diện TNCN
            continue
        loai_hd = r.get("loai_hop_dong") or "Chính thức"
        npt = _count_npt(db, r["ma_nv"])
        giam_tru = gt_bt + gt_npt * npt
        if loai_hd in luy_tien:
            tntt = max(Decimal(0), tong - bh - giam_tru)
            thue = _calc_tncn_progressive(tntt, cfg)
            bac = _bac(tntt, bieu)
        else:   # HĐ thời vụ/không ký: khấu trừ 10% trên thu nhập từ ngưỡng (không giảm trừ)
            tntt, giam_tru, bac = tong, Decimal(0), None
            thue = (tong * flat_pct).quantize(Decimal("1")) if tong >= flat_min else Decimal(0)
        out.append({
            "ma_nv": r["ma_nv"], "ten": r.get("ho_ten") or r["ma_nv"], "phong_ban": r.get("phong_ban") or "—",
            "loai_hop_dong": loai_hd, "tong_thu_nhap": vnd(tong), "bh": vnd(bh), "so_npt": npt,
            "giam_tru": vnd(giam_tru), "tn_tinh_thue": vnd(tntt), "bac": bac, "thue": vnd(thue),
            "sua_tay": False,
        })
    return out


def _cac_thang_tncn(db: Session) -> list[str]:
    from hcns.app.models import TncnData
    co_hr = [t for (t,) in db.execute(select(TncnData.thang).distinct()).all()]
    y, m = ky_thue.hom_nay().year, ky_thue.hom_nay().month
    gan_day = [f"{yy}-{mm:02d}" for yy, mm in (ky_thue.cong_thang(y, m, -i) for i in range(12))]
    return sorted(set(co_hr) | set(gan_day), reverse=True)


def _thang_mac_dinh() -> str:
    y, m = ky_thue.cong_thang(ky_thue.hom_nay().year, ky_thue.hom_nay().month, -1)
    return f"{y}-{m:02d}"


def tncn_thang(db: Session, user: JWTPayload, thang: Optional[str]) -> dict[str, Any]:
    thang = ky_thue.kiem_thang(thang) if thang else _thang_mac_dinh()
    tu, den = ky_thue.khoang_ky(thang)
    cfg = _cfg_hr(db)
    bieu_hr = cfg.get("bac_thue") or []
    dong = _dong_tu_hr(db, thang, bieu_hr)
    nguon = NGUON_HR
    if not dong:
        dong, nguon = _dong_tu_luong(db, user, thang, cfg), NGUON_LUONG_LIVE
    from hcns.app.models import PayrollMeta
    meta = db.execute(select(PayrollMeta).where(PayrollMeta.thang == thang)).scalar_one_or_none()
    ky_ke_khai = _ky_ke_khai(db)
    han = ky_thue.han_nop_khai(thang if ky_ke_khai == "thang" else ky_thue.quy_cua(tu))
    je = tim_but_toan(db, SOURCE_TNCN, thang)
    tong = {
        "so_nv": len(dong), "so_nv_nop": sum(1 for x in dong if x["thue"] > 0),
        "tong_thu_nhap": sum(x["tong_thu_nhap"] for x in dong), "bh": sum(x["bh"] for x in dong),
        "tn_tinh_thue": sum(x["tn_tinh_thue"] for x in dong), "thue": sum(x["thue"] for x in dong),
    }
    return {
        "thang": thang, "cac_thang": _cac_thang_tncn(db), "nguon": nguon,
        "trang_thai_luong": "da_chot" if meta and meta.processed_at else "chua_chot",
        "quy_dinh": {
            "giam_tru_ban_than": vnd(cfg.get("giam_tru_ban_than")), "giam_tru_npt": vnd(cfg.get("giam_tru_npt")),
            "bieu": [[b.get("den"), float(_dec(b.get("ts")) * _HANG_TRAM)] for b in bieu_hr],
            "flat_min": vnd(cfg.get("flat_tax_min")), "flat_pct": float(_dec(cfg.get("flat_tax_pct")) * _HANG_TRAM),
            "loai_hd_luy_tien": list(cfg.get("loai_hd_luy_tien") or []),
            "can_cu": "Theo cấu hình thuế TNCN của HCNS",
        },
        "dong": dong, "tong": tong, "ky_ke_khai": ky_ke_khai, "han_nop": han.isoformat(),
        "ket_thuc": ky_thue.hom_nay() > den, "khoa": is_ky_da_chot(db, den),
        "so_sach": {"da_ghi": je is not None, "but_toan": but_toan_ra_dict(je),
                    "ps_3335": vnd(phat_sinh(db, [TK_TNCN], "co", tu, den))},
    }


def ghi_so_tncn(db: Session, user: JWTPayload, thang: str) -> dict[str, Any]:
    d = tncn_thang(db, user, ky_thue.kiem_thang(thang))
    _, den = ky_thue.khoang_ky(thang)
    if d["so_sach"]["da_ghi"]:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tháng {thang} đã ghi sổ thuế TNCN ({d['so_sach']['but_toan']['so_ct']}).")
    if not d["ket_thuc"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tháng chưa kết thúc — lương còn thay đổi, chưa ghi sổ thuế TNCN.")
    so_tien = d["tong"]["thue"]
    if so_tien <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tháng này không có thuế TNCN phải khấu trừ.")
    _kiem_khoa(db, den)
    je = post_journal(
        db, ngay=den, mo_ta=f"Khấu trừ thuế TNCN từ lương tháng {thang[5:]}/{thang[:4]} ({d['tong']['so_nv_nop']} NV)",
        source_type=SOURCE_TNCN, source_id=thang, by_user=user.username,
        lines=[{"loai": "no", "account_code": TK_PHAI_TRA_NLD, "so_tien": so_tien},
               {"loai": "co", "account_code": TK_TNCN, "so_tien": so_tien}],
    )
    db.commit()
    return {"so_ct": je.ma_but_toan, "so_tien": so_tien, "id": je.id}


_COT_XUAT_TNCN = ("STT", "Mã NV", "Họ tên", "Phòng ban", "Loại hợp đồng", "Tổng thu nhập chịu thuế",
                  "BH bắt buộc", "Số NPT", "Giảm trừ gia cảnh", "Thu nhập tính thuế", "Bậc", "Thuế TNCN khấu trừ")


def xuat_tncn_csv(db: Session, user: JWTPayload, thang: str) -> tuple[str, bytes]:
    """CSV số liệu cho tờ khai 05/KK-TNCN: tổng hợp + chi tiết từng người (không kèm CCCD)."""
    d = tncn_thang(db, user, ky_thue.kiem_thang(thang))
    t = d["tong"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([f"Số liệu tờ khai 05/KK-TNCN tháng {thang} — nguồn: "
                + ("bảng TNCN của HCNS" if d["nguon"] == NGUON_HR else "tạm tính từ bảng lương live HCNS")])
    w.writerow(["Tổng số người lao động", t["so_nv"]])
    w.writerow(["Số cá nhân bị khấu trừ thuế", t["so_nv_nop"]])
    w.writerow(["Tổng thu nhập chịu thuế trả cho cá nhân", t["tong_thu_nhap"]])
    w.writerow(["Tổng thuế TNCN đã khấu trừ", t["thue"]])
    w.writerow(["Hạn nộp", d["han_nop"]])
    w.writerow([])
    w.writerow(_COT_XUAT_TNCN)
    for i, x in enumerate(d["dong"], start=1):
        w.writerow([i, x["ma_nv"], x["ten"], x["phong_ban"], x["loai_hop_dong"] or "", x["tong_thu_nhap"],
                    x["bh"], x["so_npt"], x["giam_tru"], x["tn_tinh_thue"], x["bac"] or "", x["thue"]])
    return f"05KK_TNCN_{thang}.csv", ("﻿" + buf.getvalue()).encode("utf-8")


# ═══════════════════════════ TNDN ═══════════════════════════

def _pl_thang(db: Session, thang: str) -> dict:
    """calc_pl_for_month qua cache chung của báo cáo KQKD (key 'pl:YYYY-MM', TTL 30s)."""
    from ..routers.bao_cao_pnl import _cache_get, _cache_set
    kq = _cache_get(f"pl:{thang}")
    if kq is None:
        kq = calc_pl_for_month(db, thang)
        _cache_set(f"pl:{thang}", kq)
    return kq


def _tong_dict(v: Any) -> Decimal:
    return _dec(v.get("tong") if isinstance(v, dict) else v)


# (mã TK, tên, bên, hàm lấy số từ kết quả calc_pl_for_month)
_DONG_KQKD = (
    ("511", "Doanh thu thuần bán hàng (đã trừ hoàn tiền khách)", "doanh_thu", lambda p: _dec(p["dt_thuan"])),
    ("515", "Doanh thu hoạt động tài chính", "doanh_thu", lambda p: _dec(p["dt_tai_chinh"])),
    ("711", "Thu nhập khác", "doanh_thu", lambda p: _dec(p["thu_nhap_khac"])),
    ("632", "Giá vốn hàng bán", "chi_phi", lambda p: _dec(p["cogs"])),
    ("635", "Chi phí tài chính", "chi_phi", lambda p: _tong_dict(p["cp_tai_chinh"])),
    ("641", "Chi phí bán hàng", "chi_phi", lambda p: _tong_dict(p["cp_ban_hang"])),
    ("642", "Chi phí quản lý doanh nghiệp", "chi_phi", lambda p: _tong_dict(p["cp_quan_ly"])),
    ("811", "Chi phí khác", "chi_phi", lambda p: _dec(p["cp_khac"])),
)


def _dieu_chinh(db: Session, quy: str) -> list[ThueTndnDieuChinh]:
    return list(db.execute(select(ThueTndnDieuChinh).where(ThueTndnDieuChinh.quy == quy)
                           .order_by(ThueTndnDieuChinh.thu_tu, ThueTndnDieuChinh.id)).scalars())


def _so_lieu_quy(db: Session, quy: str) -> dict[str, Any]:
    """LN kế toán + điều chỉnh + thuế của 1 quý (chỉ các tháng đã bắt đầu)."""
    tu, den = ky_thue.khoang_ky(quy)
    nay = ky_thue.thang_nay()
    thang = [t for t in ky_thue.cac_thang_cua_quy(quy) if t <= nay]
    pls = [_pl_thang(db, t) for t in thang]
    chi_tiet = []
    for tk, ten, ben, lay in _DONG_KQKD:
        so = sum((lay(p) for p in pls), Decimal(0))
        if so or tk == "511":
            chi_tiet.append({"tk": tk, "ten": ten, "ben": ben, "so_tien": vnd(so)})
    doanh_thu = sum(x["so_tien"] for x in chi_tiet if x["ben"] == "doanh_thu")
    chi_phi = sum(x["so_tien"] for x in chi_tiet if x["ben"] == "chi_phi")
    # LN = Σ dòng doanh thu − Σ dòng chi phí ĐÃ làm tròn (đúng các số in trong bảng KQKD quý của màn)
    # — không làm tròn riêng Σ ln_truoc_thue (có thể lệch 1đ so với dòng "Lợi nhuận" cộng tay).
    loi_nhuan = doanh_thu - chi_phi
    dc = _dieu_chinh(db, quy)
    tang = sum(int(x.so_tien) for x in dc if x.loai == "tang")
    giam = sum(int(x.so_tien) for x in dc if x.loai == "giam")
    tntt = max(0, loi_nhuan + tang - giam)
    ts = _dec(TAX_RATE_TNDN)
    thue = vnd(Decimal(tntt) * ts)
    return {
        "quy": quy, "khoang": {"tu": tu.isoformat(), "den": den.isoformat()},
        "cac_thang": thang, "ket_thuc": ky_thue.hom_nay() > den, "chua_toi": ky_thue.hom_nay() < tu,
        "doanh_thu": doanh_thu,
        "chi_phi": chi_phi,
        "chi_tiet": chi_tiet, "loi_nhuan": loi_nhuan,
        "dieu_chinh": [{"loai": x.loai, "noi_dung": x.noi_dung, "so_tien": int(x.so_tien)} for x in dc],
        "tang": tang, "giam": giam, "tn_tinh_thue": tntt,
        "thue_suat": float(ts * _HANG_TRAM), "thue": thue,
        "han_nop": ky_thue.han_tam_nop_tndn(quy).isoformat(),
    }


def _thue_suat_theo_luat(doanh_thu_nam_truoc: int) -> int:
    for tran, ts in BIEU_TNDN_THEO_DOANH_THU:
        if tran is None or doanh_thu_nam_truoc <= tran:
            return ts
    return BIEU_TNDN_THEO_DOANH_THU[-1][1]


def tndn_quy(db: Session, quy: Optional[str]) -> dict[str, Any]:
    quy = ky_thue.kiem_quy(quy) if quy else ky_thue.quy_cua(ky_thue.hom_nay())
    nam = int(quy[3:])
    d = _so_lieu_quy(db, quy)
    je = tim_but_toan(db, SOURCE_TNDN, quy)
    d.update({"da_ghi": je is not None, "but_toan": but_toan_ra_dict(je)})
    hom_nay = ky_thue.hom_nay()
    cac_quy, tntt_nam, tam_nop = [], 0, 0
    for n in range(1, 5):
        q = f"Q{n}-{nam}"
        x = d if q == quy else _so_lieu_quy(db, q)
        jq = je if q == quy else tim_but_toan(db, SOURCE_TNDN, q)
        han = ky_thue.han_tam_nop_tndn(q)
        if not x["chua_toi"]:
            tntt_nam += x["loi_nhuan"] + x["tang"] - x["giam"]
        if jq is not None:
            tam_nop += int(jq.tong_tien)
        cac_quy.append({"quy": q, "han": han.isoformat(), "chua_toi": x["chua_toi"],
                        "da_ghi": jq is not None, "thue": None if x["chua_toi"] else x["thue"],
                        "qua_han": jq is None and x["thue"] > 0 and hom_nay > han})
    dt_nam_truoc = vnd(_sum_doanh_thu_thuc_hien(db, date(nam - 1, 1, 1), date(nam - 1, 12, 31)))
    ts_luat = _thue_suat_theo_luat(dt_nam_truoc) if dt_nam_truoc > 0 else None   # không có dữ liệu năm trước → không gợi ý
    d.update({
        "cac_quy": cac_quy,
        "luy_ke": {"tam_nop": tam_nop, "thue_uoc": vnd(Decimal(max(0, tntt_nam)) * _dec(TAX_RATE_TNDN)),
                   "ty_le_toi_thieu": float(TY_LE_TAM_NOP_TOI_THIEU)},
        "doanh_thu_nam_truoc": dt_nam_truoc, "thue_suat_luat": ts_luat,
        "bieu": [[tran, ts] for tran, ts in BIEU_TNDN_THEO_DOANH_THU],
        "can_cu": ("Lợi nhuận lấy từ báo cáo kết quả kinh doanh các tháng đã qua của quý, cùng thuế suất "
                   "báo cáo đó dùng. Tạm nộp 4 quý không thấp hơn 80% số thuế quyết toán năm"),
    })
    return d


def luu_dieu_chinh(db: Session, user: JWTPayload, quy: str, dong: list[dict]) -> dict[str, Any]:
    quy = ky_thue.kiem_quy(quy)
    if tim_but_toan(db, SOURCE_TNDN, quy) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Quý đã ghi sổ tạm nộp — không sửa điều chỉnh được.")
    moi = []
    for i, x in enumerate(dong):
        loai, nd = (x.get("loai") or "").strip(), (x.get("noi_dung") or "").strip()
        so_tien = _dec(x.get("so_tien"))
        if loai not in ("tang", "giam"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Dòng {i + 1}: loại phải là Tăng hoặc Giảm.")
        if not nd:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Dòng {i + 1}: nhập nội dung điều chỉnh.")
        if so_tien <= 0 or so_tien != so_tien.to_integral_value():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Dòng {i + 1}: số tiền phải là số đồng dương.")
        moi.append(ThueTndnDieuChinh(quy=quy, thu_tu=i, loai=loai, noi_dung=nd[:200],
                                     so_tien=so_tien, created_by=user.username))
    db.execute(delete(ThueTndnDieuChinh).where(ThueTndnDieuChinh.quy == quy))
    db.add_all(moi)
    db.commit()
    return {"quy": quy, "so_dong": len(moi)}


def ghi_so_tndn(db: Session, user: JWTPayload, quy: str) -> dict[str, Any]:
    quy = ky_thue.kiem_quy(quy)
    d = _so_lieu_quy(db, quy)
    den = date.fromisoformat(d["khoang"]["den"])
    je = tim_but_toan(db, SOURCE_TNDN, quy)
    if je is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Quý đã ghi sổ tạm nộp ({je.ma_but_toan}).")
    if not d["ket_thuc"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quý chưa kết thúc — số liệu còn tạm tính, chưa ghi sổ.")
    if d["thue"] <= 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Quý này không phát sinh thuế TNDN tạm nộp.")
    _kiem_khoa(db, den)
    je = post_journal(
        db, ngay=den, mo_ta=f"Thuế TNDN tạm nộp quý {quy[1]}/{quy[3:]} ({d['thue_suat']:g}% × {d['tn_tinh_thue']:,} đ)".replace(",", "."),
        source_type=SOURCE_TNDN, source_id=quy, by_user=user.username,
        lines=[{"loai": "no", "account_code": TK_CP_THUE_TNDN, "so_tien": d["thue"]},
               {"loai": "co", "account_code": TK_TNDN, "so_tien": d["thue"]}],
    )
    db.commit()
    return {"so_ct": je.ma_but_toan, "so_tien": d["thue"], "id": je.id}
