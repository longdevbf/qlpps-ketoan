"""Đối chiếu tồn kho Kế toán (bảng cũ) với Kho mới của Mua hàng — CHỈ ĐỌC.

Hai sổ khác nhau (điều tra 30/09/2026):
  · Kế toán hiện hành đọc `muahang.ton_kho_items` (bảng cũ, mỗi dòng = một lô nhập).
  · Mua hàng đã chuyển sang Kho mới: `muahang.kho_sp` (danh mục SKU + giá nhập) và
    `muahang.kho_movement` (phiếu); tồn = Σ phiếu có dấu, giá trị = tồn × `kho_sp.don_gia_nhap`.

Cách nối: phiếu `kho_movement` có `ref_type='ton_kho_item'` mang `ref_id` = id dòng bảng cũ
(phiếu đầu kỳ, lúc Mua hàng chuyển V1 sang kho mới). KHÔNG nối theo mã hay tên: mã bảng cũ
có dòng để trống / khác mã SKU mới, và có 4 cặp SKU trùng tên khác mã.

Module này chỉ SELECT, không ghi vào schema `muahang`. Không import fastapi (xem
services-nghiepvu.md); lỗi DB nổi lên cho router xử lý, không nuốt thành "rỗng".
"""
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

GHI_CHU = "Chưa kiểm kê — hai số này chưa phải số chốt"

_KHONG = Decimal("0")

# Thứ tự hiện ở bảng tổng theo nhãn. (mã nhãn, chữ hiển thị, mức màu pill)
NHAN: dict[str, tuple[str, str]] = {
    "khop": ("Khớp", "success"),
    "chi_kho_moi": ("Chỉ có ở Kho mới (nhập tay sau {moc})", "warning"),
    "kho_moi_co_nhap_tay": ("Kho mới có thêm nhập tay (sau {moc})", "warning"),
    "ke_toan_da_tru": ("Kế toán đã trừ, Kho mới chưa có phiếu xuất", "danger"),
    "khac_gia": ("Khác giá", "info"),
    "chi_bang_cu": ("Chỉ có ở bảng cũ", "danger"),
    "kho_moi_it_hon": ("Kho mới ít hơn Kế toán", "danger"),
    "lech_sl_chua_ro": ("Lệch số lượng, chưa rõ lý do", "danger"),
}


def _d(v: Any) -> Decimal:
    return Decimal(str(v)) if v is not None else _KHONG


def _chuan_ten(s: Optional[str]) -> str:
    # So tên bằng Python (không dùng ILIKE/collation của DB — production dùng collation C).
    t = unicodedata.normalize("NFC", s or "")
    return re.sub(r"\s+", " ", t).strip().casefold()


def _nhan_chu(ma: str, moc: str) -> str:
    return NHAN[ma][0].format(moc=moc)


def doi_chieu_kho_moi(db: Session) -> dict[str, Any]:
    # ── 1. Bảng cũ + phiếu đầu kỳ nối tới nó (nếu có) ────────────────────────
    cu = db.execute(text("""
        SELECT t.id, t.ma_sp, t.ten_sp, t.so_luong, t.thanh_tien,
               (SELECT m.ma_sp FROM muahang.kho_movement m
                 WHERE m.ref_type = 'ton_kho_item' AND m.ref_id = CAST(t.id AS text)
                 ORDER BY m.id LIMIT 1) AS sku
        FROM muahang.ton_kho_items t
        ORDER BY t.id
    """)).mappings().all()

    # ── 2. Kho mới: mỗi SKU đang hoạt động, tồn tổng + phần tồn đến từ phiếu đầu kỳ ──
    # Công thức tồn đúng như qlpps-muahang/app/routers/kho.py (_TON_EXPR, GET /api/kho/ton).
    moi = db.execute(text("""
        SELECT s.ma_sp, s.ten_sp, s.nhom, s.don_gia_nhap,
               COALESCE(SUM(CASE m.loai WHEN 'nhap' THEN m.so_luong
                                        WHEN 'xuat' THEN -m.so_luong
                                        ELSE m.so_luong END), 0) AS ton,
               COALESCE(SUM(CASE WHEN m.ref_type = 'ton_kho_item' THEN
                              (CASE m.loai WHEN 'nhap' THEN m.so_luong
                                           WHEN 'xuat' THEN -m.so_luong
                                           ELSE m.so_luong END)
                            ELSE 0 END), 0) AS dau_ky
        FROM muahang.kho_sp s
        LEFT JOIN muahang.kho_movement m ON m.ma_sp = s.ma_sp
        WHERE s.active IS TRUE
        GROUP BY s.id, s.ma_sp, s.ten_sp, s.nhom, s.don_gia_nhap
        ORDER BY s.ma_sp
    """)).mappings().all()

    # Ngày Mua hàng chuyển bảng cũ sang kho mới (để ghi trong nhãn, không gõ cứng).
    ngay_chuyen = db.execute(text("""
        SELECT MAX(created_at) FROM muahang.kho_movement WHERE ref_type = 'ton_kho_item'
    """)).scalar()
    moc = ngay_chuyen.strftime("%d/%m") if ngay_chuyen else "khi chuyển kho"

    # ── 3. Gom bảng cũ theo SKU kho mới ─────────────────────────────────────
    cu_theo_sku: dict[str, dict[str, Any]] = {}
    cu_roi: list[dict[str, Any]] = []        # dòng bảng cũ không nối tới SKU nào
    cu_het_hang_khong_noi = 0
    tong_cu = {"so_dong": 0, "so_dong_con_ton": 0, "sl": _KHONG, "gt": _KHONG}
    for r in cu:
        sl, gt = _d(r["so_luong"]), _d(r["thanh_tien"])
        tong_cu["so_dong"] += 1
        tong_cu["sl"] += sl
        tong_cu["gt"] += gt
        if sl > 0:
            tong_cu["so_dong_con_ton"] += 1
        ma_cu = (r["ma_sp"] or "").strip()
        if r["sku"]:
            g = cu_theo_sku.setdefault(
                r["sku"], {"sl": _KHONG, "gt": _KHONG, "so_dong": 0, "ma_cu": []})
            g["sl"] += sl
            g["gt"] += gt
            g["so_dong"] += 1
            if ma_cu and ma_cu != r["sku"] and ma_cu not in g["ma_cu"]:
                g["ma_cu"].append(ma_cu)
        elif sl == 0 and gt == 0:
            cu_het_hang_khong_noi += 1          # lô đã hết, chưa từng chuyển — không ảnh hưởng số
        else:
            cu_roi.append({"id": r["id"], "ma": ma_cu, "ten": r["ten_sp"], "sl": sl, "gt": gt})

    # ── 4. Dựng từng dòng đối chiếu ─────────────────────────────────────────
    dong: list[dict[str, Any]] = []
    sku_co_mat = set()
    for s in moi:
        ma = s["ma_sp"]
        sku_co_mat.add(ma)
        gia_mh = _d(s["don_gia_nhap"])
        mh_sl = _d(s["ton"])
        mh_gt = mh_sl * gia_mh
        dau_ky = _d(s["dau_ky"])
        c = cu_theo_sku.get(ma)
        kt_sl = c["sl"] if c else _KHONG
        kt_gt = c["gt"] if c else _KHONG
        nhap_tay = mh_sl - dau_ky                # phiếu không nối bảng cũ (nhập tay, kiểm kê…)
        da_tru = max(dau_ky - kt_sl, _KHONG) if c else _KHONG
        khac = (mh_sl - kt_sl) - da_tru - nhap_tay
        if not c:
            ma_nhan = "khop" if mh_sl == 0 else "chi_kho_moi"
        elif kt_sl == mh_sl:
            ma_nhan = "khop" if kt_gt == mh_gt else "khac_gia"
        elif kt_sl < mh_sl:
            if da_tru == 0 and nhap_tay == 0:
                ma_nhan = "lech_sl_chua_ro"
            else:
                ma_nhan = "ke_toan_da_tru" if da_tru >= nhap_tay else "kho_moi_co_nhap_tay"
        else:
            ma_nhan = "kho_moi_it_hon"
        # Khác giá đi kèm khi lệch số lượng: giá bình quân lô Kế toán ≠ giá nhập SKU.
        khac_gia_kem = bool(c and kt_sl > 0 and mh_sl > 0 and ma_nhan != "khac_gia"
                            and (kt_gt / kt_sl) != gia_mh)
        canh_bao = []
        if gia_mh == 0:
            canh_bao.append("gia_0")
        dong.append({
            "ma_sp": ma, "ten_sp": s["ten_sp"], "nhom": s["nhom"],
            "ma_bang_cu": c["ma_cu"] if c else [],
            "so_dong_bang_cu": c["so_dong"] if c else 0,
            "kt_sl": kt_sl, "kt_gt": kt_gt,
            "mh_sl": mh_sl, "mh_gia": gia_mh, "mh_gt": mh_gt,
            "chenh_sl": mh_sl - kt_sl, "chenh_gt": mh_gt - kt_gt,
            "nhan_ma": ma_nhan, "nhan": _nhan_chu(ma_nhan, moc), "nhan_mau": NHAN[ma_nhan][1],
            "thanh_phan": {"da_tru_bang_cu": da_tru, "nhap_tay": nhap_tay, "khac": khac},
            "khac_gia": khac_gia_kem or ma_nhan == "khac_gia",
            "canh_bao": canh_bao, "trung_ten_voi": [],
        })

    # SKU đã nối nhưng không còn trong danh sách SKU hoạt động → coi như dòng chỉ ở bảng cũ.
    for sku, c in cu_theo_sku.items():
        if sku not in sku_co_mat:
            cu_roi.append({"id": None, "ma": sku, "ten": None, "sl": c["sl"], "gt": c["gt"],
                           "ghi_chu": "SKU không còn hoạt động ở Kho mới"})
    for r in cu_roi:
        dong.append({
            "ma_sp": r["ma"] or "(chưa có mã)", "ten_sp": r["ten"] or "—", "nhom": None,
            "ma_bang_cu": [], "so_dong_bang_cu": 1,
            "kt_sl": r["sl"], "kt_gt": r["gt"],
            "mh_sl": _KHONG, "mh_gia": _KHONG, "mh_gt": _KHONG,
            "chenh_sl": -r["sl"], "chenh_gt": -r["gt"],
            "nhan_ma": "chi_bang_cu", "nhan": _nhan_chu("chi_bang_cu", moc), "nhan_mau": NHAN["chi_bang_cu"][1],
            "thanh_phan": {"da_tru_bang_cu": _KHONG, "nhap_tay": _KHONG, "khac": -r["sl"]},
            "khac_gia": False, "canh_bao": [], "trung_ten_voi": [],
        })

    # ── 5. SKU trùng tên khác mã — chỉ liệt kê, KHÔNG tự nối ─────────────────
    theo_ten: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in dong:
        k = _chuan_ten(r["ten_sp"])
        if k and k != "—":
            theo_ten[k].append(r)
    cap_trung = 0
    for nhom in theo_ten.values():
        ma_khac = {r["ma_sp"] for r in nhom}
        if len(ma_khac) > 1:
            cap_trung += 1
            for r in nhom:
                r["trung_ten_voi"] = sorted(ma_khac - {r["ma_sp"]})
                r["canh_bao"].append("trung_ten")

    dong.sort(key=lambda r: (-abs(r["chenh_gt"]), -abs(r["chenh_sl"]), r["ma_sp"]))

    # ── 6. Tổng ─────────────────────────────────────────────────────────────
    mh_sl_tong = sum((r["mh_sl"] for r in dong), _KHONG)
    mh_gt_tong = sum((r["mh_gt"] for r in dong), _KHONG)
    theo_nhan = []
    for ma, (_, mau) in NHAN.items():
        rs = [r for r in dong if r["nhan_ma"] == ma]
        if rs:
            theo_nhan.append({
                "nhan_ma": ma, "nhan": _nhan_chu(ma, moc), "nhan_mau": mau, "so_dong": len(rs),
                "chenh_sl": sum((r["chenh_sl"] for r in rs), _KHONG),
                "chenh_gt": sum((r["chenh_gt"] for r in rs), _KHONG),
            })

    # Phân rã chênh giá trị theo NGUYÊN NHÂN (cộng đúng bằng chênh tổng): phần số lượng KT đã trừ,
    # phần nhập tay, phần lệch chưa rõ — mỗi phần nhân giá nhập SKU; còn lại là chênh giá/gộp lô.
    pr_tru_sl = sum((r["thanh_phan"]["da_tru_bang_cu"] for r in dong), _KHONG)
    pr_tay_sl = sum((r["thanh_phan"]["nhap_tay"] for r in dong), _KHONG)
    pr_khac_sl = sum((r["thanh_phan"]["khac"] for r in dong), _KHONG)
    pr_tru_gt = sum((r["thanh_phan"]["da_tru_bang_cu"] * r["mh_gia"] for r in dong), _KHONG)
    pr_tay_gt = sum((r["thanh_phan"]["nhap_tay"] * r["mh_gia"] for r in dong), _KHONG)
    pr_khac_gt = sum((r["thanh_phan"]["khac"] * r["mh_gia"] for r in dong), _KHONG)
    chenh_gt_tong = mh_gt_tong - tong_cu["gt"]

    return {
        "ghi_chu": GHI_CHU,
        "ke_toan": {
            "nguon": "muahang.ton_kho_items",
            "so_dong": tong_cu["so_dong"], "so_dong_con_ton": tong_cu["so_dong_con_ton"],
            "so_mat_hang_con_ton": sum(1 for r in dong if r["kt_sl"] > 0),
            "sl": tong_cu["sl"], "gt": tong_cu["gt"],
            "dong_het_hang_chua_chuyen": cu_het_hang_khong_noi,
        },
        "mua_hang": {
            "nguon": "muahang.kho_sp + muahang.kho_movement",
            "so_sku": len(moi), "so_sku_con_ton": sum(1 for r in moi if _d(r["ton"]) > 0),
            "sl": mh_sl_tong, "gt": mh_gt_tong,
        },
        "chenh": {"sl": mh_sl_tong - tong_cu["sl"], "gt": chenh_gt_tong},
        "phan_ra": {
            "da_tru_bang_cu": {"sl": pr_tru_sl, "gt": pr_tru_gt},
            "nhap_tay": {"sl": pr_tay_sl, "gt": pr_tay_gt},
            "khac": {"sl": pr_khac_sl, "gt": pr_khac_gt},
            "lech_gia": {"sl": _KHONG, "gt": chenh_gt_tong - pr_tru_gt - pr_tay_gt - pr_khac_gt},
        },
        "ngay_chuyen_kho_moi": ngay_chuyen.date() if ngay_chuyen else None,
        "so_cap_trung_ten": cap_trung,
        "so_sku_gia_0": sum(1 for r in dong if "gia_0" in r["canh_bao"]),
        "theo_nhan": theo_nhan,
        "dong": dong,
    }
