"""Thuế GTGT (phương pháp khấu trừ) — bảng kê bán ra / mua vào + tổng hợp số phải nộp theo kỳ.

NGUỒN SỐ LIỆU (anh Quang 2026-09-25 — dữ liệu thật, không bịa):
- ĐẦU RA = đơn báo giá ĐÃ DUYỆT (`baogia.quotes.duyet_status='approved'`) theo NGÀY DUYỆT
  (`duyet_luc`) trong kỳ, cột `tien_thue`/`tong_chua_thue`/`vat_percent`. Đây đúng là quy ước
  "VAT Đầu Ra (đơn duyệt/tháng)" của Tổng quan cũ (`routers/bao_cao.py:_build_dashboard`
  → `vat_dau_ra`) và trang Đơn hàng — số trên màn này phải khớp số đó.
  Hệ thống CHƯA có hoá đơn điện tử (không có số/ký hiệu HĐ) → bảng kê ghi theo số đơn.
  Đơn không tính VAT (`tien_thue = 0`) không lên bảng kê, chỉ đếm riêng.
- ĐẦU VÀO: KHÔNG có nguồn — đơn mua hàng (muahang), công nợ NCC, chi phí phát sinh đều không
  có cột thuế GTGT đầu vào / hoá đơn mua vào. Bảng kê mua vào rỗng, đầu vào = 0, kèm chú thích.
  Vì vậy "Kỳ trước chuyển sang" cũng = 0 (không có đầu vào nào để còn dư khấu trừ).
- SỔ CÁI: phát sinh Có 3331 / Nợ 133 lấy từ journal_line để đối chiếu (hiện chưa có bút toán
  thuế GTGT nào → 0).
"""
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from xml.sax.saxutils import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from baogia.app.models import Quote

from . import ky_thue
from .so_cai_doc import phat_sinh
from .tim_kiem import khop_mot_trong

TRANG_THAI_DUYET = "approved"
TK_THUE_DAU_RA = ("3331", "33311")
TK_THUE_DAU_VAO = ("133", "1331")
SIZE_TOI_DA = 200
_SORT_COT = {"ngay": "ngay", "gia_tri": "gia_tri", "thue": "thue"}
LY_DO_KHONG_CO_DAU_VAO = (
    "Hệ thống chưa lưu hoá đơn mua vào: đơn mua hàng, công nợ nhà cung cấp và chi phí phát "
    "sinh đều chưa có trường thuế GTGT đầu vào."
)


def vnd(x: Any) -> int:
    """Làm tròn về đồng (VND không có số lẻ)."""
    return int(Decimal(str(x or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _tong_dong(cot):
    """Σ số đã làm tròn TỪNG ĐƠN (đúng số in trên từng dòng bảng kê) — để dòng Cộng, thẻ tổng hợp và
    tổng quý = Σ các dòng / Σ các tháng tới từng đồng. Làm tròn tổng một lần (bản trước) lệch 1đ
    so với cộng tay các dòng (QA 25/09/2026: 09/2026 dòng cộng 28.378.294 − thẻ 28.378.293)."""
    return func.coalesce(func.sum(func.round(cot)), 0)


def _ngay_duyet():
    return func.date(Quote.duyet_luc)


def _dieu_kien_ky(tu: date, den: date) -> list:
    """Cùng điều kiện với `bao_cao.py:_build_dashboard` (VAT đầu ra Tổng quan cũ)."""
    return [
        Quote.duyet_status == TRANG_THAI_DUYET,
        Quote.duyet_luc.isnot(None),
        _ngay_duyet() >= tu,
        _ngay_duyet() <= den,
    ]


def tong_hop_ky(db: Session, ky: str) -> dict[str, Any]:
    """Các thẻ tổng hợp + đối chiếu sổ cái của 1 kỳ kê khai."""
    tu, den = ky_thue.khoang_ky(ky)
    dk = _dieu_kien_ky(tu, den)
    co_thue = Quote.tien_thue > 0
    r = db.execute(
        select(
            func.count(Quote.id).filter(co_thue),
            func.coalesce(func.sum(func.round(Quote.tong_chua_thue)).filter(co_thue), 0),
            _tong_dong(Quote.tien_thue),
            func.count(Quote.id).filter(~co_thue | Quote.tien_thue.is_(None)),
            func.coalesce(func.sum(func.round(Quote.tong_chua_thue)).filter(~co_thue | Quote.tien_thue.is_(None)), 0),
        ).where(*dk)
    ).one()
    dau_ra = vnd(r[2])
    dau_vao, chuyen_sang = 0, 0
    return {
        "tong_hop": {
            "dau_ra": dau_ra,
            "so_ban": int(r[0] or 0),
            "doanh_thu": vnd(r[1]),
            "dau_vao": dau_vao,
            "so_mua": 0,
            "so_khong": 0,
            "khong_khau_tru": 0,
            "chuyen_sang": chuyen_sang,
            "phai_nop": dau_ra - dau_vao - chuyen_sang,
        },
        "khong_vat": {"so_don": int(r[3] or 0), "doanh_thu": vnd(r[4])},
        "so_sach": {
            "ps_3331": vnd(phat_sinh(db, TK_THUE_DAU_RA, "co", tu, den)),
            "ps_1331": vnd(phat_sinh(db, TK_THUE_DAU_VAO, "no", tu, den)),
        },
        "khoang": {"tu": tu.isoformat(), "den": den.isoformat()},
        "han_nop": ky_thue.han_nop_khai(ky).isoformat(),
        "nguon": {
            "dau_ra": "Đơn báo giá đã duyệt theo ngày duyệt (cùng số \"VAT đầu ra\" của Tổng quan cũ)",
            "dau_vao": LY_DO_KHONG_CO_DAU_VAO,
        },
    }


def _ten_doi_tac(q: Quote) -> dict:
    ten = (q.ten_cong_ty or "").strip() or (q.customer_name or "").strip() or "Khách lẻ"
    return {"ten": ten, "mst": (q.ma_so_thue or "").strip() or None}


def bang_ke_ban(
    db: Session, ky: str, tim: str = "", page: int = 1, size: int = 20, sort: str = "ngay_asc",
) -> dict[str, Any]:
    tu, den = ky_thue.khoang_ky(ky)
    dk = _dieu_kien_ky(tu, den) + [Quote.tien_thue > 0]
    tim = (tim or "").strip()
    if tim:
        # Không phân biệt dấu + hoa/thường — tim_kiem.py.
        dk.append(khop_mot_trong((Quote.quote_number, Quote.customer_name, Quote.ten_cong_ty, Quote.ma_so_thue), tim))
    tong_dong, gia_tri, thue = db.execute(
        select(func.count(Quote.id), _tong_dong(Quote.tong_chua_thue), _tong_dong(Quote.tien_thue)).where(*dk)
    ).one()
    cot, _, chieu = (sort or "ngay_asc").rpartition("_")
    cot_sql = {"ngay": Quote.duyet_luc, "gia_tri": Quote.tong_chua_thue, "thue": Quote.tien_thue}.get(
        _SORT_COT.get(cot, "ngay"), Quote.duyet_luc)
    thu_tu = cot_sql.desc() if chieu == "desc" else cot_sql.asc()
    size = max(1, min(int(size or 20), SIZE_TOI_DA))
    so_trang = max(1, -(-int(tong_dong or 0) // size))
    page = max(1, min(int(page or 1), so_trang))
    rows = db.execute(
        select(Quote).where(*dk).order_by(thu_tu, Quote.id).offset((page - 1) * size).limit(size)
    ).scalars().all()
    dong = [{
        "id": q.id,
        "ngay": q.duyet_luc.astimezone(ky_thue.MUI_GIO).date().isoformat(),
        "so_hd": q.quote_number,
        "doi_tac": _ten_doi_tac(q),
        "gia_tri": vnd(q.tong_chua_thue),
        "thue_suat": float(q.vat_percent or 0),
        "thue": vnd(q.tien_thue),
    } for q in rows]
    return {"dong": dong, "tong_dong": int(tong_dong or 0), "trang": page, "so_trang": so_trang,
            "cong": {"gia_tri": vnd(gia_tri), "thue": vnd(thue)}}


def bang_ke_mua(db: Session, ky: str) -> dict[str, Any]:
    """Không có nguồn hoá đơn mua vào (xem docstring module) → luôn rỗng, kèm lý do."""
    return {"dong": [], "tong_dong": 0, "trang": 1, "so_trang": 1,
            "cong": {"gia_tri": 0, "thue": 0}, "ly_do_rong": LY_DO_KHONG_CO_DAU_VAO}


def danh_sach(db: Session, ky: str, chieu: str, **loc) -> dict[str, Any]:
    ds = bang_ke_mua(db, ky) if chieu == "mua" else bang_ke_ban(db, ky, **loc)
    return {**tong_hop_ky(db, ky), **ds, "ky": ky, "chieu": chieu}


def _nhom_theo_thue_suat(db: Session, ky: str) -> list[tuple[Decimal, int, int]]:
    tu, den = ky_thue.khoang_ky(ky)
    rows = db.execute(
        select(Quote.vat_percent, _tong_dong(Quote.tong_chua_thue), _tong_dong(Quote.tien_thue))
        .where(*_dieu_kien_ky(tu, den), Quote.tien_thue > 0)
        .group_by(Quote.vat_percent).order_by(Quote.vat_percent)
    ).all()
    return [(Decimal(ts or 0), vnd(gt), vnd(t)) for ts, gt, t in rows]


def to_khai_xml(db: Session, ky: str, mst: Optional[str], ten_don_vi: Optional[str]) -> dict[str, str]:
    """Bảng số liệu chỉ tiêu tờ khai 01/GTGT dạng XML để ĐỐI CHIẾU khi lập tờ khai trên HTKK.

    KHÔNG phải tệp XML nộp thuế theo chuẩn của Tổng cục Thuế (hệ thống không có HĐĐT,
    không có đầu vào) — ghi rõ trong tệp.
    """
    th = tong_hop_ky(db, ky)
    t, kv = th["tong_hop"], th["khong_vat"]
    nhom = _nhom_theo_thue_suat(db, ky)
    dong_ts = "".join(
        f'    <NhomThueSuat thueSuat="{ts.normalize()}" giaTriChuaThue="{gt}" thueGTGT="{thue}"/>\n'
        for ts, gt, thue in nhom)
    noi_dung = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Số liệu tham khảo tờ khai 01/GTGT (khấu trừ) do phần mềm kế toán nội bộ tổng hợp.\n"
        "     Đầu ra: đơn báo giá đã duyệt trong kỳ. Đầu vào: hệ thống chưa có dữ liệu hoá đơn mua vào.\n"
        "     Không phải tệp nộp thuế — lập và kiểm tra tờ khai trên HTKK/eTax. -->\n"
        f'<ToKhai01GTGT ky="{escape(ky)}" tuNgay="{th["khoang"]["tu"]}" denNgay="{th["khoang"]["den"]}"'
        f' mst="{escape(mst or "")}" tenNguoiNopThue="{escape(ten_don_vi or "")}">\n'
        f'  <CT21 moTa="Không phát sinh hoạt động mua bán">{0 if t["so_ban"] else 1}</CT21>\n'
        f'  <CT22 moTa="Thuế GTGT còn được khấu trừ kỳ trước chuyển sang">{t["chuyen_sang"]}</CT22>\n'
        '  <CT23 moTa="Giá trị HHDV mua vào">0</CT23>\n'
        f'  <CT24 moTa="Thuế GTGT của HHDV mua vào">{t["dau_vao"]}</CT24>\n'
        f'  <CT25 moTa="Thuế GTGT được khấu trừ kỳ này">{t["dau_vao"]}</CT25>\n'
        f'  <BanRaTheoThueSuat moTa="HHDV bán ra chịu thuế, theo thuế suất">\n{dong_ts}  </BanRaTheoThueSuat>\n'
        f'  <DonKhongTinhVAT soDon="{kv["so_don"]}" doanhThu="{kv["doanh_thu"]}"'
        ' moTa="Đơn đã duyệt không tính thuế GTGT — không lên bảng kê, kế toán tự xác định cách khai"/>\n'
        f'  <CT34 moTa="Tổng doanh thu HHDV bán ra chịu thuế">{t["doanh_thu"]}</CT34>\n'
        f'  <CT35 moTa="Tổng thuế GTGT của HHDV bán ra">{t["dau_ra"]}</CT35>\n'
        f'  <CT36 moTa="Thuế GTGT phát sinh trong kỳ">{t["dau_ra"] - t["dau_vao"]}</CT36>\n'
        f'  <CT40 moTa="Thuế GTGT còn phải nộp trong kỳ">{max(0, t["phai_nop"])}</CT40>\n'
        f'  <CT43 moTa="Thuế GTGT còn được khấu trừ chuyển kỳ sau">{max(0, -t["phai_nop"])}</CT43>\n'
        f'  <HanNop>{th["han_nop"]}</HanNop>\n'
        "</ToKhai01GTGT>\n"
    )
    return {"ten_tep": f"01GTGT_{ky}.xml", "noi_dung": noi_dung}
