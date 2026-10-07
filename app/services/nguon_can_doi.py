"""Khai nguồn từng dòng Cân đối kế toán + nguyên nhân lệch Tài sản ≠ Nguồn vốn — Đợt 1, 07/10/2026.

Tách khỏi app/routers/bao_cao_can_doi.py (luật repo: tính toán nghiệp vụ nằm ở services/). Router
gom ba bộ số của chính nó rồi gọi hai hàm dưới:
  gia_tri   — số báo cáo đang hiển thị cho từng dòng
  so_cai    — số theo sổ cái (journal_line, theo mã TK); rỗng ở chế độ source='legacy'
  nghiep_vu — số theo bảng nghiệp vụ; tiền luôn có, các dòng khác rỗng ở chế độ source='journal'
CHỈ MÔ TẢ, không đổi con số nào của báo cáo.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import KyKeToan
from .nguon_bao_cao import NGUON_CDKT, NHAN_CDKT

# Chênh giữa hai nguồn từ mức này trở lên mới đưa vào "nguyên nhân lệch" — dưới đó thường chỉ là
# làm tròn/thời điểm ghi sổ, nêu ra chỉ làm loãng danh sách.
_NGUONG_CHENH = 1_000_000


def _vnd(x: float) -> str:
    return f"{x:,.0f}".replace(",", ".") + " VND"   # cùng đơn vị với thẻ số trên màn


def ghep_nguon_can_doi(gia_tri: dict[str, float], so_cai: dict[str, float],
                       nghiep_vu: dict[str, float]) -> dict[str, dict]:
    """Mỗi dòng: mô tả nguồn (NGUON_CDKT) + số sổ cái, số nghiệp vụ, chênh, và nguồn đang dùng.

    `dang_dung`: 'khop' (hai nguồn bằng nhau) · 'so_cai' / 'nghiep_vu' (báo cáo đang lấy số đó) ·
    'khac' (không bằng nguồn nào — vd ln_giu_lai lấy kỳ đã chốt).
    """
    nguon: dict[str, dict] = {}
    for khoa_dong, mo_ta in NGUON_CDKT.items():
        muc = dict(mo_ta)
        if khoa_dong in gia_tri:
            sc: Optional[float] = so_cai.get(khoa_dong)
            nv: Optional[float] = nghiep_vu.get(khoa_dong)
            gt = gia_tri[khoa_dong]
            if sc is not None and nv is not None and abs(sc - nv) < 1:
                dang_dung = "khop"
            elif sc is not None and abs(gt - sc) < 1:
                dang_dung = "so_cai"
            elif nv is not None and abs(gt - nv) < 1:
                dang_dung = "nghiep_vu"
            else:
                dang_dung = "khac"
            muc.update({
                "so_cai": sc, "nghiep_vu": nv, "dang_dung": dang_dung,
                "chenh": (sc - nv) if sc is not None and nv is not None else None,
            })
        nguon[khoa_dong] = muc
    return nguon


def nguyen_nhan_lech(db: Session, *, thang: str, von_csh_tong: float, von_gop: float,
                     ln_giu_lai: float, quy_dn: float, nguon: dict[str, dict]) -> list[dict]:
    """Nguyên nhân lệch có khả năng nhất, xếp theo mức chắc chắn — chỉ nêu điều đo được từ số liệu.

    Mỗi mục có `ma` để nơi hiển thị bỏ được ý đã có cảnh báo riêng (canh_bao_ky.lech_can_doi).
    Gọi khi Tài sản ≠ Nguồn vốn.
    """
    out: list[dict] = []
    if abs(von_csh_tong) < 1:
        out.append({"ma": "von_csh_bang_0", "thong_bao":
                    "Toàn bộ vốn chủ sở hữu = 0 — nguồn vốn hiện chỉ gồm nợ phải trả."})
    if abs(von_gop) < 1:
        out.append({"ma": "von_gop_chua_khai", "thong_bao": "Vốn góp (411) trên Cân đối = 0."})
    if abs(ln_giu_lai) < 1:
        da_chot = db.execute(
            select(func.count()).select_from(KyKeToan)
            .where(KyKeToan.trang_thai == "da_chot").where(KyKeToan.thang <= thang)
        ).scalar() or 0
        if da_chot == 0:
            out.append({"ma": "chua_chot_ky", "thong_bao":
                        "Chưa kỳ kế toán nào được chốt → Lợi nhuận chưa phân phối (421) = 0, "
                        "lãi/lỗ luỹ kế chưa vào nguồn vốn."})
    if abs(quy_dn) < 1:
        out.append({"ma": "quy_bang_0", "thong_bao": "Các quỹ (414/415/353) đang bằng 0."})
    lech_nguon = sorted(
        ((k, v) for k, v in nguon.items() if v.get("chenh") is not None and abs(v["chenh"]) >= _NGUONG_CHENH),
        key=lambda kv: -abs(kv[1]["chenh"]),
    )
    for k, v in lech_nguon[:3]:
        out.append({"ma": "so_cai_khac_nghiep_vu", "khoa": k, "thong_bao":
                    f"{NHAN_CDKT.get(k, k)}: sổ cái {_vnd(v['so_cai'])}, bảng nghiệp vụ {_vnd(v['nghiep_vu'])} — "
                    + ("báo cáo đang lấy số sổ cái." if v["dang_dung"] == "so_cai"
                       else "báo cáo đang lấy số bảng nghiệp vụ." if v["dang_dung"] == "nghiep_vu"
                       else "hai nguồn đang khác nhau.")})
    return out
