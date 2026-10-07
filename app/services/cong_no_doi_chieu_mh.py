"""Đối chiếu công nợ phải trả NCC giữa 2 sổ độc lập — `muahang.congno` (nguồn nghiệp vụ mua
hàng, tính lại mỗi lần PO đổi) và `ketoan.cong_no` (sổ CHUẨN của Kế toán, không tự động đổi
theo). Quyết định người dùng 30/09/2026 (phương án B): hệ thống chỉ ĐỀ XUẤT, Kế toán DUYỆT
TỪNG DÒNG — không có đường tự động ghi đè. Xem memory so-no-ncc-quyet-dinh-29-09.md phần
"TRẠNG THÁI SAU KIỂM ẢNH THẬT" (bảng cầu nối chênh 30/09 09:45) để biết bối cảnh đầy đủ.

Phạm vi: CHỈ PO ở 4 trạng thái Kế toán ghi nợ (`PO_TRANG_THAI_GHI_NO` — Đã có hàng, Đã lấy
hàng, Đã giao, Hoàn Thành). PO còn "Đặt hàng"/"Đang SX" CỐ Ý không đề xuất — đó là nợ dự kiến,
Kế toán chưa ghi dòng cho các đơn này, không phải thiếu sót cần vá.

Khớp 1 dòng MH ↔ 1 dòng KT theo (po_id, ncc_id): `ketoan.cong_no.ref_id` LUÔN kết thúc bằng
đúng `ncc_id` khi dòng đó gắn 1 NCC cụ thể — cả 2 định dạng đang tồn tại:
  - đơn không combo, tạo qua create_cong_no_list_from_order: 'MH-{po}-NCC{ncc_id}'
  - đơn combo (nhiều NCC/PO), tách theo phần:      'MH-{po}-NCCCOMBO{combo_id}-PART{ncc_id}'
Cả 2 dạng đều LIKE '%' || ncc_id ở cuối chuỗi — dùng chung 1 điều kiện khớp.
Dòng KT kiểu CŨ 'MH-{po}' (không hậu tố, một NCC/đơn, sinh trước khi có per-NCC) khớp theo
PO + KHÔNG còn dòng MH nào khác cho PO đó (đơn 1-NCC, không combo).

Idempotent qua chính `ref_id` (giống create_cong_no_list_from_order) — bấm áp dụng 2 lần
không tạo trùng, vì lần 2 dòng KT đã tồn tại nên rơi vào nhánh cap_nhat_so_tien (số bằng nhau
→ không có gì để áp) thay vì tao_dong.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date as date_cls
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload

from ..models import CongNo
from .cong_no_dong_bo import PO_TRANG_THAI_GHI_NO, _ma_don_co_dong_tay
from .id_gen import next_cong_no_id

logger = logging.getLogger(__name__)

REF_SOURCE_MUAHANG = "muahang"
LOAI_CHI_TIET = "Công Nợ NCC"
NGUONG_LECH = Decimal("1")   # < 1đ coi như làm tròn, bỏ qua — cùng ngưỡng NGUONG_THU_DU chỗ khác


def _vnd(v: Decimal) -> str:
    """Định dạng số tiền kiểu Việt Nam (dấu chấm ngăn hàng nghìn) cho câu `ly_do` hiển thị
    thẳng ra UI — SỬA lỗi 6 (kiểm chứng độc lập 30/09/2026): trước in số thô Decimal
    ('8600000.00') giữa câu tiếng Việt, không nhất quán với KD.tienVnd() ở mọi cột số khác."""
    return f"{int(v):,}".replace(",", ".")


@dataclass
class DeXuat:
    """Một dòng đề xuất đối chiếu — 1 cặp (PO, NCC)."""

    po_id: str
    ma_don: Optional[str]
    ncc_id: Optional[str]
    ncc_ten: str
    loai: str                       # 'cap_nhat_so_tien' | 'tao_dong' | 'khong_ap_dung_duoc'
    po_ngay: Optional[date_cls] = None  # ngày tạo PO — dùng làm `ngay` khi tao_dong (SỬA lỗi 1
                                         # kiểm chứng độc lập 30/09: date.today() làm sai lệch số
                                         # theo tháng ở Cân đối; cùng quy ước cong_no_from_order.py:251).
    mh_so_tien: Optional[Decimal] = None
    kt_id: Optional[str] = None
    kt_so_tien: Optional[Decimal] = None
    kt_da_tra: Optional[Decimal] = None
    chenh_lech: Optional[Decimal] = None
    ap_dung_duoc: bool = False
    ly_do: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "po_id": self.po_id, "ma_don": self.ma_don, "ncc_id": self.ncc_id, "ncc_ten": self.ncc_ten,
            "loai": self.loai,
            "mh_so_tien": str(self.mh_so_tien) if self.mh_so_tien is not None else None,
            "kt_id": self.kt_id,
            "kt_so_tien": str(self.kt_so_tien) if self.kt_so_tien is not None else None,
            "kt_da_tra": str(self.kt_da_tra) if self.kt_da_tra is not None else None,
            "chenh_lech": str(self.chenh_lech) if self.chenh_lech is not None else None,
            "ap_dung_duoc": self.ap_dung_duoc, "ly_do": self.ly_do,
        }


_SQL_MH_ROWS = """
    SELECT c.id, c.ncc_id, c.ncc_name, c.so_tien, c.ref_order_id, po.ref_bao_gia AS ma_don,
           po.created_at AS po_ngay
    FROM muahang.congno c
    JOIN muahang.purchase_orders po ON po.id = c.ref_order_id
    WHERE c.loai = 'no_phai_tra' AND po.status = ANY(:tt)
    ORDER BY c.ref_order_id, c.id
"""

_SQL_KT_ROWS = """
    SELECT id, doi_tac, so_tien, da_tra, ref_id, ma_don
    FROM ketoan.cong_no
    WHERE loai = 'phai_tra' AND COALESCE(ref_id, '') LIKE 'MH-%'
"""


import re

_RE_PO = re.compile(r"^MH-(ORD-\d+-\d+)")


def _po_id_tu_ref(ref_id: str) -> Optional[str]:
    """Trích po_id từ ref_id KT dạng 'MH-ORD-2026-042[...]' → 'ORD-2026-042'."""
    m = _RE_PO.match(ref_id or "")
    return m.group(1) if m else None


def _ref_id_khop_ncc(ref_id: str, ncc_id: str) -> bool:
    """True nếu ref_id KT là dòng của đúng ncc_id này — khớp theo RANH GIỚI rõ (chữ 'NCC' hoặc
    'PART' ngay trước ncc_id), không chỉ endswith thô (một ncc_id lý thuyết có thể là hậu tố
    tình cờ của chuỗi khác — đã kiểm dev không có ca này, nhưng ranh giới rõ vẫn an toàn hơn)."""
    if not ref_id or not ncc_id:
        return False
    return ref_id.endswith("NCC" + ncc_id) or ref_id.endswith("PART" + ncc_id)


def tinh_de_xuat(db: Session) -> list[DeXuat]:
    """Tính danh sách đề xuất đối chiếu — CHỈ ĐỌC, không ghi gì.

    Gom theo po_id: với mỗi PO, khớp từng dòng MH với dòng KT có ref_id kết thúc bằng đúng
    ncc_id đó; dòng MH không khớp được dòng KT nào → tao_dong (nếu PO/ma_don chưa có dòng nhập
    tay — dùng lại _ma_don_co_dong_tay để không tạo trùng như bài học đơn 057); dòng KT không
    khớp được dòng MH nào (cùng PO) → khong_ap_dung_duoc, liệt kê kèm lý do, không có nút áp.
    """
    mh_rows = db.execute(text(_SQL_MH_ROWS), {"tt": list(PO_TRANG_THAI_GHI_NO)}).mappings().all()
    kt_rows = db.execute(text(_SQL_KT_ROWS)).mappings().all()
    co_dong_tay = _ma_don_co_dong_tay(db, "phai_tra")

    kt_theo_po: dict[str, list[dict]] = {}
    for r in kt_rows:
        po_id = _po_id_tu_ref(r["ref_id"])
        if po_id:
            kt_theo_po.setdefault(po_id, []).append(dict(r))

    mh_theo_po: dict[str, list[dict]] = {}
    for r in mh_rows:
        mh_theo_po.setdefault(r["ref_order_id"], []).append(dict(r))

    ket_qua: list[DeXuat] = []
    tat_ca_po = set(mh_theo_po) | set(kt_theo_po)

    for po_id in sorted(tat_ca_po):
        mh_list = mh_theo_po.get(po_id, [])
        kt_list = list(kt_theo_po.get(po_id, []))
        # ma_don LUÔN lấy từ nguồn PO (mh_list[0], hoặc kt_list nếu PO không còn dòng MH nào) —
        # BUG ĐÃ SỬA: lấy từ kt_list[0] trước đây làm ma_don=None khi kt_list rỗng nhưng PO có
        # dòng nhập tay KHÔNG qua auto-bridge (ref_id rỗng, không nằm trong _SQL_KT_ROWS vì lọc
        # LIKE 'MH-%') — khiến check co_dong_tay không bao giờ đúng, đơn 057 (2 dòng nhập tay,
        # NAM NGỌC 21.800.000) bị đề xuất tao_dong thay vì khong_ap_dung_duoc.
        ma_don = (mh_list[0]["ma_don"] if mh_list else (kt_list[0]["ma_don"] if kt_list else None))

        kt_da_dung: set[str] = set()
        for mh in mh_list:
            ncc_id = mh["ncc_id"] or ""
            # Khớp theo hậu tố ncc_id trong ref_id (cả 2 định dạng per-NCC/combo).
            kt_khop = next(
                (k for k in kt_list if k["id"] not in kt_da_dung and ncc_id and _ref_id_khop_ncc(k["ref_id"] or "", ncc_id)),
                None,
            )
            # Đơn 1-NCC kiểu cũ 'MH-{po}' không hậu tố — chỉ khớp khi PO này CHỈ có 1 dòng MH
            # (không combo/nhiều NCC) và còn đúng 1 dòng KT chưa dùng.
            if kt_khop is None and len(mh_list) == 1:
                kt_khop = next(
                    (k for k in kt_list if k["id"] not in kt_da_dung and (k["ref_id"] or "") == f"MH-{po_id}"),
                    None,
                )
            if kt_khop is not None:
                kt_da_dung.add(kt_khop["id"])
                mh_tien = Decimal(str(mh["so_tien"] or 0))
                kt_tien = Decimal(str(kt_khop["so_tien"] or 0))
                kt_da_tra = Decimal(str(kt_khop["da_tra"] or 0))
                chenh = mh_tien - kt_tien
                if abs(chenh) < NGUONG_LECH:
                    continue  # khớp rồi, không có gì đề xuất
                ap_duoc = mh_tien >= kt_da_tra
                dx = DeXuat(
                    po_id=po_id, ma_don=ma_don, ncc_id=ncc_id, ncc_ten=mh["ncc_name"] or "",
                    loai="cap_nhat_so_tien", mh_so_tien=mh_tien,
                    kt_id=kt_khop["id"], kt_so_tien=kt_tien, kt_da_tra=kt_da_tra, chenh_lech=chenh,
                    ap_dung_duoc=ap_duoc,
                    ly_do="" if ap_duoc else f"Đã trả {_vnd(kt_da_tra)} đ nhiều hơn số mới {_vnd(mh_tien)} đ — cần KT xem",
                )
                ket_qua.append(dx)
            else:
                # MH có, KT chưa có dòng cho NCC này — đề xuất tạo mới, trừ khi PO/đơn đã có
                # dòng nhập tay (tránh tạo trùng, bài học đơn 057).
                if ma_don and ma_don in co_dong_tay:
                    ket_qua.append(DeXuat(
                        po_id=po_id, ma_don=ma_don, ncc_id=ncc_id, ncc_ten=mh["ncc_name"] or "",
                        loai="khong_ap_dung_duoc", mh_so_tien=Decimal(str(mh["so_tien"] or 0)),
                        ap_dung_duoc=False,
                        ly_do="Đơn đã có dòng công nợ nhập tay — không tự tạo thêm để tránh trùng",
                    ))
                    continue
                po_ngay = mh["po_ngay"].date() if mh.get("po_ngay") else None
                ket_qua.append(DeXuat(
                    po_id=po_id, ma_don=ma_don, ncc_id=ncc_id, ncc_ten=mh["ncc_name"] or "",
                    loai="tao_dong", po_ngay=po_ngay, mh_so_tien=Decimal(str(mh["so_tien"] or 0)),
                    ap_dung_duoc=True,
                ))

        # Dòng KT còn lại (cùng PO) không khớp được dòng MH nào → không áp dụng được.
        for kt in kt_list:
            if kt["id"] in kt_da_dung:
                continue
            ket_qua.append(DeXuat(
                po_id=po_id, ma_don=kt["ma_don"], ncc_id=None, ncc_ten=kt["doi_tac"] or "",
                loai="khong_ap_dung_duoc", kt_id=kt["id"],
                kt_so_tien=Decimal(str(kt["so_tien"] or 0)), kt_da_tra=Decimal(str(kt["da_tra"] or 0)),
                ap_dung_duoc=False,
                ly_do="Kế toán có dòng nhưng Mua hàng không còn (PO đổi/không còn NCC này) — cần KT xem, hệ thống không tự xoá",
            ))

    return ket_qua


@dataclass
class KetQuaApDung:
    da_ap_dung: list[dict[str, Any]] = field(default_factory=list)
    loi: list[dict[str, Any]] = field(default_factory=list)


def ap_dung_de_xuat(
    db: Session, *, chon: list[dict[str, Any]], user: JWTPayload,
) -> KetQuaApDung:
    """Áp dụng CÁC DÒNG ĐÃ CHỌN (KT duyệt từng dòng, không tự động toàn bộ).

    `chon`: list các dict {po_id, ncc_id, loai} — xác định lại đúng dòng đề xuất bằng cách tính
    lại tinh_de_xuat() rồi lọc theo khoá này, KHÔNG tin số tiền client gửi lên (chống lệch giữa
    lúc mở hộp thoại và lúc bấm áp dụng — đơn 042/087/190/016 đang audit combo nên đổi liên tục).

    Mỗi dòng một giao dịch riêng (lỗi dòng nào chỉ dòng đó thất bại). KHÔNG tự log_action ở đây
    — audit nằm ở tầng router theo quy ước repo (coding-style.md/routers-api.md); mỗi entry
    trong kq.da_ap_dung mang đủ payload (ref_id, ma_don, ngay, so_tien_cu/moi, da_tra) để router
    tự ghi log kèm `request` (IP/User-Agent). KHÔNG xoá dòng nào. Chốt chặn: không đặt so_tien <
    da_tra hiện có.
    """
    tat_ca = tinh_de_xuat(db)
    khoa_chon = {(c.get("po_id"), c.get("ncc_id"), c.get("loai")) for c in chon}
    can_ap = [
        dx for dx in tat_ca
        if (dx.po_id, dx.ncc_id, dx.loai) in khoa_chon and dx.ap_dung_duoc and dx.loai != "khong_ap_dung_duoc"
    ]

    kq = KetQuaApDung()
    for dx in can_ap:
        try:
            if dx.loai == "cap_nhat_so_tien":
                cn = db.get(CongNo, dx.kt_id)
                if cn is None:
                    kq.loi.append({**dx.to_dict(), "ly_do_loi": "Dòng công nợ không còn tồn tại"})
                    continue
                so_tien_hien_tai = Decimal(str(cn.so_tien))
                da_tra_hien_tai = Decimal(str(cn.da_tra))
                if dx.mh_so_tien is None or dx.mh_so_tien < da_tra_hien_tai:
                    kq.loi.append({**dx.to_dict(), "ly_do_loi": "Đã trả nhiều hơn số mới, cần KT xem"})
                    continue
                if abs(so_tien_hien_tai - dx.mh_so_tien) < NGUONG_LECH:
                    continue  # đã khớp từ lúc tính đề xuất tới lúc áp dụng — bỏ qua, không log rác
                so_cu = so_tien_hien_tai
                cn.so_tien = dx.mh_so_tien
                cn.trang_thai = "da_tra" if cn.so_tien - da_tra_hien_tai <= 0 else "chua_tra"
                db.commit()
                kq.da_ap_dung.append({
                    **dx.to_dict(), "ket_qua": "cap_nhat",
                    "action": "doi_chieu_mh_cap_nhat", "resource": f"cong_no:{cn.id}",
                    "log_payload": {
                        "po_id": dx.po_id, "ncc": dx.ncc_ten, "ref_id": cn.ref_id, "ma_don": cn.ma_don,
                        "so_tien_cu": str(so_cu), "so_tien_moi": str(dx.mh_so_tien), "da_tra": str(da_tra_hien_tai),
                    },
                })

            elif dx.loai == "tao_dong":
                # Idempotent: tinh_de_xuat() tính SỐNG mỗi lần gọi — nếu dòng đã tồn tại cho
                # đúng (po, ncc_id) này, nó tự rơi vào nhánh 'cap_nhat_so_tien' ở trên (không
                # phải 'tao_dong' nữa), nên KHÔNG cần tự kiểm existing ở đây nữa.
                cid = next_cong_no_id(db)
                ref_id_val = f"MH-{dx.po_id}-NCC{dx.ncc_id}"
                # SỬA lỗi 1 (kiểm chứng độc lập 30/09/2026): ngay PHẢI là ngày tạo PO, không phải
                # ngày bấm áp dụng — cùng quy ước cong_no_from_order.py:251 (po.created_at.date()).
                # date.today() làm Cân đối các tháng trước bị THIẾU đúng số tiền vừa tạo (nó rơi
                # vào tháng hiện tại thay vì tháng PO phát sinh thật).
                ngay_dong = dx.po_ngay or date_cls.today()
                cn = CongNo(
                    id=cid, ngay=ngay_dong, doi_tac=dx.ncc_ten,
                    so_tien=dx.mh_so_tien, da_tra=Decimal("0"), loai="phai_tra",
                    loai_chi_tiet=LOAI_CHI_TIET, ma_don=dx.ma_don, ref_id=ref_id_val,
                    ref_source=REF_SOURCE_MUAHANG, trang_thai="chua_tra",
                    ghi_chu=f"Đối chiếu Mua hàng: tạo từ PO {dx.po_id} | NCC: {dx.ncc_ten}",
                    created_by=user.username,
                )
                db.add(cn)
                db.commit()
                kq.da_ap_dung.append({
                    **dx.to_dict(), "kt_id": cid, "ket_qua": "tao_moi",
                    "action": "doi_chieu_mh_tao_dong", "resource": f"cong_no:{cid}",
                    "log_payload": {
                        "po_id": dx.po_id, "ncc": dx.ncc_ten, "ref_id": ref_id_val, "ma_don": dx.ma_don,
                        "ngay": str(ngay_dong), "so_tien": str(dx.mh_so_tien),
                    },
                })
        except Exception:  # fail-hard nghiệp vụ nhưng KHÔNG chặn các dòng khác
            # SỬA (bản vá 30/09/2026 mục 6): str(ex) có thể lộ nguyên câu SQL (IntegrityError/
            # OperationalError in kèm statement) ra client — log chi tiết phía server, trả thông
            # báo chung tiếng Việt cho client.
            db.rollback()
            logger.exception(
                "doi_chieu_mh: ap dung that bai po_id=%s ncc_id=%s loai=%s",
                dx.po_id, dx.ncc_id, dx.loai,
            )
            kq.loi.append({**dx.to_dict(), "ly_do_loi": "Không áp dụng được, đã ghi log — báo quản trị"})

    return kq
