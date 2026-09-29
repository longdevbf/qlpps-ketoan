"""Đồng bộ công nợ từ các phòng (POST /api/cong-no/sync, /import) — bản sửa 28/09/2026.

Hai nguồn:
  * **Báo giá → phải thu KH** (ref_source='baogia_quote', ref_id=quotes.id): mọi báo giá đã duyệt
    có tổng đơn > 0. Số "đã thu" tính ĐÚNG cách màn Đơn hàng tính "Còn thu" (quy tắc anh Quang
    28/07, `conThuDoiChieu` trong static/js/kt-don-hang.js và `loadDonHang` trong index.html):
        Còn thu = Tổng đơn − Đã thu thực − max(0, Cọc hợp đồng − Cọc đã ghi doanh thu)
    trong đó "Đã thu thực" / "Cọc đã ghi" gộp ketoan.doanh_thu theo mã đơn bằng CÙNG câu SQL của
    `/api/external/orders-overview` (`SQL_DOANH_THU_THEO_DON` bên dưới — giữ y hệt CTE
    `doanh_thu_agg` ở app/routers/external.py). Công nợ của đơn = Còn thu (kẹp ≥ 0, < 1 đ coi
    như đã thu đủ — cùng ngưỡng "đã thu đủ" của nút Hoàn thành màn Đơn hàng).
    Dòng đã có được CẬP NHẬT (so_tien / da_tra / trang_thai / ngay_tra), không chỉ tạo mới.
    Bản trước chỉ trừ tiền cọc ghi trên báo giá khi TẠO dòng, không bao giờ cập nhật dòng cũ →
    đơn đã hoàn thành vẫn hiện còn nợ.
  * **Mua hàng → phải trả NCC** (ref_source='muahang'): PO đã có hàng trở đi mà CHƯA có dòng công nợ
    nào — cùng điều kiện + cùng hàm tạo với auto-bridge của app Mua hàng
    (`_auto_bridge_to_ketoan` trong muahang/app/routers/orders.py). PO đã có dòng thì bỏ qua (không
    tạo thêm "NCC mới" chồng lên dòng cũ khi NCC/combo đã đổi — nguồn tạo trùng của bản trước); đơn
    đã có dòng phải trả KT nhập tay (cùng mã báo giá) cũng bỏ qua. Tương tự bên phải thu: đơn chưa có
    dòng tự động mà đã có dòng phải thu KT nhập tay (số tiền > 0, cùng mã đơn) thì không tạo thêm.

KHÔNG còn đồng bộ Sale Admin (vanchuyen):
  * thu hộ KH qua ĐVVC (saleadmin_vc_phai_thu) TRÙNG phải thu của chính đơn báo giá — màn Công nợ KH,
    Tổng quan, Bù trừ đều đã loại nguồn này;
  * cước phải trả ĐVVC (saleadmin_vc_phai_tra) lấy `chi_phi_vc − da_tra_dvvc`, nhưng ĐVVC được trả
    qua Đề nghị thanh toán (chi phí + sổ quỹ) và `da_tra_dvvc` gần như không được cập nhật → sinh
    nợ ĐVVC ảo; lại có `ma_don` nên màn Đơn hàng cộng cước 2 lần vào "Phải trả".

`dry_run=True`: chạy ĐÚNG nhánh ghi thật trong cùng giao dịch rồi rollback — số xem trước = số sẽ ghi.
Cả lần chạy là MỘT giao dịch: lỗi ở bất kỳ dòng nào thì không ghi gì (all-or-nothing).
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable, Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload

from ..models import CongNo
from .cong_no_from_order import (
    CongNoFromOrderError, create_cong_no_list_from_order, find_existing_cong_no_for_order,
)
from .id_gen import next_cong_no_id

NGUON_BAO_GIA = "baogia"
NGUON_MUA_HANG = "muahang"
NGUON_HOP_LE = (NGUON_BAO_GIA, NGUON_MUA_HANG)

REF_BAO_GIA = "baogia_quote"
REF_THU_HO = "saleadmin_vc_phai_thu"   # dòng thu hộ ĐVVC cũ — trùng phải thu đơn, không tính
LOAI_CHI_TIET_BAO_GIA = "bao_gia_da_duyet"
PHAI_THU, PHAI_TRA = "phai_thu", "phai_tra"
DA_TRA, CHUA_TRA = "da_tra", "chua_tra"
MUI_GIO = "Asia/Ho_Chi_Minh"
# Còn thu dưới 1 đ (tổng đơn có số lẻ, vd 18.000.000,58) = đã thu đủ — cùng ngưỡng màn Đơn hàng.
NGUONG_THU_DU = Decimal("1")
# Trạng thái PO mà auto-bridge Mua hàng ghi nợ NCC (muahang/app/routers/orders.py update_status).
PO_TRANG_THAI_GHI_NO = ("Đã có hàng", "Đã lấy hàng", "Đã giao", "Hoàn Thành")
_0 = Decimal("0")

# Gộp doanh thu theo mã đơn — GIỮ Y HỆT CTE `doanh_thu_agg` của /api/external/orders-overview
# (app/routers/external.py). Sửa một bên thì sửa cả bên kia (hoặc cho external import hằng này).
SQL_DOANH_THU_THEO_DON = """
            SELECT ma_don,
                   SUM(so_tien) AS thu_thuc,
                   SUM(CASE WHEN loai_thanh_toan ILIKE '%cọc%'      THEN so_tien ELSE 0 END) AS thu_dat_coc,
                   SUM(CASE WHEN loai_thanh_toan ILIKE 'thanh toán' THEN so_tien ELSE 0 END) AS thu_thanh_toan
            FROM ketoan.doanh_thu
            WHERE ma_don IS NOT NULL
            GROUP BY ma_don
"""

_SQL_DON_DA_DUYET = f"""
    WITH doanh_thu_agg AS ({SQL_DOANH_THU_THEO_DON}),
    ngay_thu AS (
        SELECT ma_don, MAX(ngay) AS ngay_thu_cuoi FROM ketoan.doanh_thu
        WHERE ma_don IS NOT NULL GROUP BY ma_don
    )
    SELECT q.id, q.quote_number, q.customer_name, q.tien_trinh_mh,
           (COALESCE(q.duyet_luc, q.created_at) AT TIME ZONE '{MUI_GIO}')::date AS ngay,
           COALESCE(q.tong_don, 0)       AS tong_don,
           COALESCE(q.deposit, 0)        AS deposit,
           COALESCE(dta.thu_thuc, 0)     AS thu_thuc_te,
           COALESCE(dta.thu_dat_coc, 0)  AS thu_dat_coc,
           nt.ngay_thu_cuoi
    FROM baogia.quotes q
    LEFT JOIN doanh_thu_agg dta ON dta.ma_don = q.quote_number
    LEFT JOIN ngay_thu nt ON nt.ma_don = q.quote_number
    WHERE q.duyet_status = 'approved' AND COALESCE(q.tong_don, 0) > 0
    ORDER BY q.id
"""


def con_thu_don(tong_don: Decimal, thu_thuc_te: Decimal, deposit: Decimal, thu_dat_coc: Decimal) -> Decimal:
    """"Còn thu" của 1 đơn — công thức màn Đơn hàng (anh Quang 28/07). Âm = khách trả thừa.

    Tổng − Đã thu thực (đã gồm cọc đã ghi doanh thu) − phần cọc HỢP ĐỒNG chưa ghi doanh thu
    (không trừ cọc 2 lần). Mirror 1-1 của `conThuDoiChieu` (kt-don-hang.js)."""
    return tong_don - thu_thuc_te - max(_0, deposit - thu_dat_coc)


def cong_no_cua_don(con_thu: Decimal) -> Decimal:
    """Số còn phải thu ghi vào công nợ: Còn thu kẹp ≥ 0 (thu thừa không thành nợ âm), < 1 đ = 0."""
    return con_thu if con_thu >= NGUONG_THU_DU else _0


def _D(v: Any) -> Decimal:
    return Decimal(str(v)) if v is not None else _0


def _anh(cn: CongNo) -> dict[str, Any]:
    return {"so_tien": _D(cn.so_tien), "da_tra": _D(cn.da_tra), "trang_thai": cn.trang_thai,
            "ngay_tra": cn.ngay_tra}


def _dong_thay_doi(hanh_dong: str, cn: CongNo, truoc: Optional[dict], ghi_chu: str = "",
                   **them: Any) -> dict[str, Any]:
    t = truoc or {"so_tien": _0, "da_tra": _0, "trang_thai": None}
    so_tien, da_tra = _D(cn.so_tien), _D(cn.da_tra)
    return {
        "hanh_dong": hanh_dong, "id": cn.id, "loai": cn.loai, "ma_don": cn.ma_don,
        "doi_tac": cn.doi_tac, "ngay": cn.ngay.isoformat() if cn.ngay else None,
        "so_tien_truoc": t["so_tien"], "so_tien_sau": so_tien,
        "da_tra_truoc": t["da_tra"], "da_tra_sau": da_tra,
        "con_lai_truoc": t["so_tien"] - t["da_tra"], "con_lai_sau": so_tien - da_tra,
        "trang_thai_truoc": t["trang_thai"], "trang_thai_sau": cn.trang_thai,
        "ghi_chu": ghi_chu, **them,
    }


def _ids_co_thu_tren_cong_no(db: Session, ids: Iterable[str]) -> set[str]:
    """Dòng công nợ đã có phiếu THU ghi thẳng trên màn Công nợ (so_quy lien_quan='cong_no',
    ref '<id>' / '<id>-DA…') — tiền này KHÔNG vào doanh_thu nên màn Đơn hàng không thấy."""
    ids = list(ids)
    if not ids:
        return set()
    rows = db.execute(text("""
        SELECT DISTINCT cn.id FROM ketoan.cong_no cn
        JOIN ketoan.so_quy sq ON sq.lien_quan = 'cong_no' AND sq.loai = 'thu'
             AND (sq.ref_id = cn.id OR sq.ref_id LIKE cn.id || '-DA%')
        WHERE cn.id = ANY(:ids)
    """), {"ids": ids}).scalars().all()
    return set(rows)


def _ma_don_co_dong_tay(db: Session, loai: str) -> set[str]:
    """Mã báo giá đã có dòng công nợ KT nhập tay (không ref_source, số tiền > 0) — ma_don có thể kèm
    "— Tên KH" (combo) nên lấy phần mã trước dấu gạch dài. Sync không tạo thêm dòng tự động chồng lên."""
    return set(db.execute(text("""
        SELECT DISTINCT TRIM(SPLIT_PART(REPLACE(ma_don, '–', '—'), '—', 1)) FROM ketoan.cong_no
        WHERE loai = :loai AND ref_source IS NULL AND so_tien > 0 AND COALESCE(ma_don, '') <> ''
    """), {"loai": loai}).scalars().all())


def _dong_bo_phai_thu(db: Session, username: str, kq: dict[str, Any]) -> None:
    don = db.execute(text(_SQL_DON_DA_DUYET)).mappings().all()
    co_dong_tay = _ma_don_co_dong_tay(db, PHAI_THU)
    hien_co = {
        cn.ref_id: cn for cn in db.execute(
            select(CongNo).where(CongNo.ref_source == REF_BAO_GIA).with_for_update()
        ).scalars()
    }
    co_thu_cn = _ids_co_thu_tren_cong_no(db, (cn.id for cn in hien_co.values()))
    dem = kq["dem"][NGUON_BAO_GIA]
    ref_con_don: set[str] = set()

    for r in don:
        ref_id = str(r["id"])
        ref_con_don.add(ref_id)
        tong_don = _D(r["tong_don"])
        con_thu = con_thu_don(tong_don, _D(r["thu_thuc_te"]), _D(r["deposit"]), _D(r["thu_dat_coc"]))
        con_lai = cong_no_cua_don(con_thu)
        da_tra_muc_tieu = tong_don - con_lai
        ngay_thu_du = r["ngay_thu_cuoi"] or r["ngay"]
        them = {"con_thu_don_hang": con_thu, "tien_trinh": r["tien_trinh_mh"]}

        cn = hien_co.get(ref_id)
        if cn is None and r["quote_number"] in co_dong_tay:
            dem["bo_qua"] += 1
            kq["don_bo_qua"].append({"ma_don": r["quote_number"], "doi_tac": r["customer_name"], "con_thu_don_hang": con_thu,
                                     "ly_do": "Đơn đã có công nợ phải thu nhập tay — không tạo thêm để tránh trùng"})
            continue
        if cn is None:
            cn = CongNo(
                id=next_cong_no_id(db), ngay=r["ngay"],
                doi_tac=r["customer_name"] or "(KH chưa rõ)",
                so_tien=tong_don, da_tra=da_tra_muc_tieu, loai=PHAI_THU,
                loai_chi_tiet=LOAI_CHI_TIET_BAO_GIA, ma_don=r["quote_number"],
                ref_id=ref_id, ref_source=REF_BAO_GIA,
                trang_thai=DA_TRA if con_lai == _0 else CHUA_TRA,
                ngay_tra=ngay_thu_du if con_lai == _0 else None,
                ghi_chu=f"Báo giá đã duyệt {r['quote_number']}", created_by=username,
            )
            db.add(cn)
            db.flush()
            dem["tao_moi"] += 1
            kq["dong"].append(_dong_thay_doi("tao_moi", cn, None, **them))
            continue

        truoc = _anh(cn)
        da_tra_moi, ghi_chu = da_tra_muc_tieu, ""
        if con_thu <= -NGUONG_THU_DU and truoc["so_tien"] - truoc["da_tra"] >= NGUONG_THU_DU:
            # Đơn hàng báo THU THỪA mà công nợ đang còn nợ → thường là cọc bị trừ 2 lần (cọc HĐ
            # không ghi doanh thu dạng "cọc") hoặc số cọc trên báo giá sai — KT nên kiểm đơn.
            kq["can_kiem"].append({"id": cn.id, "ma_don": cn.ma_don, "doi_tac": cn.doi_tac,
                                   "tien_trinh": r["tien_trinh_mh"], "con_lai_truoc": truoc["so_tien"] - truoc["da_tra"],
                                   "con_thu_don_hang": con_thu, "tong_don": tong_don, "coc_hop_dong": _D(r["deposit"]),
                                   "da_thu_doanh_thu": _D(r["thu_thuc_te"])})
        if cn.id in co_thu_cn and truoc["da_tra"] > da_tra_muc_tieu:
            # KT đã thu thẳng trên Công nợ (có phiếu Sổ quỹ) mà chưa ghi doanh thu → không hạ da_tra.
            da_tra_moi = truoc["da_tra"]
            ghi_chu = "Giữ số đã thu KT ghi trên Công nợ (có phiếu Sổ quỹ, chưa có doanh thu theo mã đơn)"
            kq["giu_so_da_thu"].append({"id": cn.id, "ma_don": cn.ma_don, "doi_tac": cn.doi_tac,
                                        "da_tra": truoc["da_tra"], "da_tra_theo_don_hang": da_tra_muc_tieu})
        trang_thai = DA_TRA if tong_don - da_tra_moi < NGUONG_THU_DU else CHUA_TRA
        if (truoc["so_tien"], truoc["da_tra"], truoc["trang_thai"]) == (tong_don, da_tra_moi, trang_thai):
            dem["bo_qua"] += 1
            continue
        cn.so_tien, cn.da_tra, cn.trang_thai = tong_don, da_tra_moi, trang_thai
        if trang_thai == DA_TRA and cn.ngay_tra is None:
            cn.ngay_tra = ngay_thu_du
        db.flush()
        dem["cap_nhat"] += 1
        kq["dong"].append(_dong_thay_doi("cap_nhat", cn, truoc, ghi_chu, **them))

    # Dòng báo giá cũ mà đơn KHÔNG còn (xoá / huỷ duyệt / tổng 0): không tự sửa, liệt kê để KT xem.
    for ref_id, cn in hien_co.items():
        if ref_id not in ref_con_don:
            kq["khong_con_don"].append({"id": cn.id, "ma_don": cn.ma_don, "doi_tac": cn.doi_tac,
                                        "con_lai": _D(cn.so_tien) - _D(cn.da_tra)})


def _dong_bo_phai_tra(db: Session, username: str, kq: dict[str, Any]) -> None:
    pos = db.execute(text("""
        SELECT id, ref_bao_gia FROM muahang.purchase_orders
        WHERE selected_ncc_id IS NOT NULL AND status = ANY(:tt)
        ORDER BY id
    """), {"tt": list(PO_TRANG_THAI_GHI_NO)}).all()
    dem = kq["dem"][NGUON_MUA_HANG]
    co_dong_tay = _ma_don_co_dong_tay(db, PHAI_TRA)
    for po_id, ma_bao_gia in pos:
        if find_existing_cong_no_for_order(db, str(po_id)) is not None:
            dem["bo_qua"] += 1
            continue
        if ma_bao_gia and ma_bao_gia in co_dong_tay:
            dem["bo_qua"] += 1
            kq["po_bo_qua"].append({"po": str(po_id), "ma_don": ma_bao_gia,
                                    "ly_do": "Đơn đã có công nợ phải trả ghi tay — không tạo thêm để tránh trùng"})
            continue
        try:
            moi = create_cong_no_list_from_order(
                db, str(po_id), created_by=username, require_terminal=False, commit=False,
            )
        except CongNoFromOrderError as ex:   # PO chưa có tổng tiền / không tìm thấy → bỏ qua, ghi lý do
            dem["bo_qua"] += 1
            kq["po_bo_qua"].append({"po": str(po_id), "ma_don": ma_bao_gia, "ly_do": ex.message})
            continue
        dem["tao_moi"] += len(moi)
        kq["dong"].extend(_dong_thay_doi("tao_moi", cn, None, po=str(po_id)) for cn in moi)


def _tong_hop(db: Session) -> dict[str, dict[str, dict[str, Decimal]]]:
    """Số dư theo loại → đối tác (phải thu đã loại dòng thu hộ ĐVVC — cùng định nghĩa màn Công nợ KH)."""
    rows = db.execute(text("""
        SELECT loai, doi_tac, SUM(so_tien) AS so_tien, SUM(da_tra) AS da_tra, COUNT(*) AS so_dong
        FROM ketoan.cong_no
        WHERE NOT (loai = :pt AND COALESCE(ref_source, '') = :thu_ho)
        GROUP BY loai, doi_tac
    """), {"pt": PHAI_THU, "thu_ho": REF_THU_HO}).mappings().all()
    out: dict[str, dict[str, dict[str, Decimal]]] = {PHAI_THU: {}, PHAI_TRA: {}}
    for r in rows:
        out.setdefault(r["loai"], {})[r["doi_tac"]] = {
            "so_tien": _D(r["so_tien"]), "da_tra": _D(r["da_tra"]), "so_dong": int(r["so_dong"])}
    return out


def _cong_loai(theo_dt: dict[str, dict[str, Decimal]]) -> dict[str, Any]:
    so_tien = sum((v["so_tien"] for v in theo_dt.values()), _0)
    da_tra = sum((v["da_tra"] for v in theo_dt.values()), _0)
    con_lai_dt = [v["so_tien"] - v["da_tra"] for v in theo_dt.values()]
    return {
        "so_dong": sum(v["so_dong"] for v in theo_dt.values()),
        "so_tien": so_tien, "da_tra": da_tra, "con_lai_rong": so_tien - da_tra,
        # = thẻ "Còn phải thu/trả" lọc "Còn nợ" (cộng đối tác có số ròng > 0)
        "con_lai_doi_tac_con_no": sum((c for c in con_lai_dt if c > 0), _0),
        "so_doi_tac_con_no": sum(1 for c in con_lai_dt if c > 0),
    }


def _so_sanh(truoc: dict, sau: dict) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tong, doi_tac = {}, []
    for loai in (PHAI_THU, PHAI_TRA):
        t, s = truoc.get(loai, {}), sau.get(loai, {})
        tong[loai] = {"truoc": _cong_loai(t), "sau": _cong_loai(s)}
        for ten in set(t) | set(s):
            a = t.get(ten, {"so_tien": _0, "da_tra": _0})
            b = s.get(ten, {"so_tien": _0, "da_tra": _0})
            cl_a, cl_b = a["so_tien"] - a["da_tra"], b["so_tien"] - b["da_tra"]
            if (a["so_tien"], a["da_tra"]) != (b["so_tien"], b["da_tra"]):
                doi_tac.append({"loai": loai, "doi_tac": ten, "so_tien_truoc": a["so_tien"],
                                "so_tien_sau": b["so_tien"], "con_lai_truoc": cl_a,
                                "con_lai_sau": cl_b, "chenh": cl_b - cl_a})
    doi_tac.sort(key=lambda x: (x["loai"], -abs(x["chenh"]), x["doi_tac"] or ""))
    return tong, doi_tac


def dong_bo_cong_no(
    db: Session, *, nguon: Iterable[str], user: JWTPayload, dry_run: bool,
) -> dict[str, Any]:
    """Chạy đồng bộ trong MỘT giao dịch; dry_run → rollback. Caller ghi audit sau khi commit."""
    chon = [n for n in NGUON_HOP_LE if n in set(nguon)]
    kq: dict[str, Any] = {
        "dem": {n: {"tao_moi": 0, "cap_nhat": 0, "bo_qua": 0} for n in chon},
        "dong": [], "giu_so_da_thu": [], "can_kiem": [], "khong_con_don": [], "don_bo_qua": [], "po_bo_qua": [],
    }
    try:
        truoc = _tong_hop(db)
        if NGUON_BAO_GIA in chon:
            _dong_bo_phai_thu(db, user.username, kq)
        if NGUON_MUA_HANG in chon:
            _dong_bo_phai_tra(db, user.username, kq)
        db.flush()
        sau = _tong_hop(db)
        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    tong, doi_tac = _so_sanh(truoc, sau)
    dem = kq.pop("dem")
    return {
        "ok": True, "dry_run": dry_run, "nguon": chon,
        "summary": {
            "tao_moi": sum(d["tao_moi"] for d in dem.values()),
            "cap_nhat": sum(d["cap_nhat"] for d in dem.values()),
            "bo_qua": sum(d["bo_qua"] for d in dem.values()),
            "loi": 0,
        },
        "detail": dem, "tong": tong, "theo_doi_tac": doi_tac, **kq,
    }
