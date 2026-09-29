"""TK kế toán chi tiết của từng tài khoản tiền (ketoan.tai_khoan_nh.tk_ke_toan).

Anh Quang 28/09/2026: "tài khoản ngân hàng gắn với tài khoản định khoản". Mỗi tài khoản ngân hàng /
tiền mặt / ví điện tử có một TK con của 111 (tiền mặt) hoặc 112 (còn lại): 1111 Tiền Mặt, 1121 ACB,
1122 BIDV, 1123 VPB. Bút toán tự sinh ghi vào TK con; Sổ cái / Cân đối phát sinh gộp TK con lên 111/112.
Bút toán cũ ghi thẳng 111/112 giữ nguyên — chuyển sang TK con là bước dữ liệu riêng
(`chuyen_but_toan_cu`, cần duyệt khi chạy trên production).
"""
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..models import JournalLine, TaiKhoanNH

TK_TIEN_MAT = "111"
TK_TIEN_GUI = "112"
LOAI_TIEN_MAT = "tien_mat"
SO_CON_TOI_DA = 99            # 1121 … 11299
_MAU_TK_CON = re.compile(r"^\d{4,6}$")
_KHOA_CAP_MA = "ketoan.tai_khoan_nh.tk_ke_toan"

_DDL = (
    "ALTER TABLE ketoan.tai_khoan_nh ADD COLUMN IF NOT EXISTS tk_ke_toan VARCHAR(10)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_tai_khoan_nh_tk_ke_toan ON ketoan.tai_khoan_nh (tk_ke_toan) "
    "WHERE tk_ke_toan IS NOT NULL",
)


def tk_cha(loai: Optional[str]) -> str:
    """111 cho tiền mặt, 112 cho ngân hàng / ví điện tử."""
    return TK_TIEN_MAT if (loai or "").strip() == LOAI_TIEN_MAT else TK_TIEN_GUI


def tk_tien_cua(tk: Optional[TaiKhoanNH]) -> str:
    """TK định khoản của một tài khoản tiền: TK con đã gán, chưa gán thì 111/112 theo loại (không có tài khoản → 112)."""
    if tk is None:
        return TK_TIEN_GUI
    return tk.tk_ke_toan or tk_cha(tk.loai)


def tk_chi_tiet(db: Session) -> dict[str, str]:
    """{mã TK con: tên tài khoản} — kể cả tài khoản ngừng dùng (vẫn còn số dư / lịch sử trên sổ)."""
    rows = db.execute(
        select(TaiKhoanNH.tk_ke_toan, TaiKhoanNH.ten_tk).where(TaiKhoanNH.tk_ke_toan.is_not(None))
    ).all()
    return {ma: ten for ma, ten in rows}


def _ma_dang_dung(db: Session, bo_qua_id: Optional[int] = None) -> set[str]:
    stmt = select(TaiKhoanNH.tk_ke_toan).where(TaiKhoanNH.tk_ke_toan.is_not(None))
    if bo_qua_id is not None:
        stmt = stmt.where(TaiKhoanNH.id != bo_qua_id)
    return set(db.execute(stmt).scalars())


def ma_tiep_theo(db: Session, loai: Optional[str]) -> str:
    """Mã con trống nhỏ nhất dưới 111/112 (1121, 1122…) — gợi ý khi thêm tài khoản."""
    cha, dung = tk_cha(loai), _ma_dang_dung(db)
    for i in range(1, SO_CON_TOI_DA + 1):
        if f"{cha}{i}" not in dung:
            return f"{cha}{i}"
    raise HTTPException(status.HTTP_409_CONFLICT, f"Đã dùng hết mã con của TK {cha}")


def _so_dong_but_toan(db: Session, ma: str) -> int:
    return db.execute(select(func.count(JournalLine.id)).where(JournalLine.account_code == ma)).scalar() or 0


def kiem_tra_tk_ke_toan(db: Session, ma: str, loai: Optional[str], tk_hien_tai: Optional[TaiKhoanNH] = None) -> str:
    """Chuẩn hoá + kiểm mã TK con cho một tài khoản tiền (400/409 nếu sai). Trả mã đã chuẩn hoá.

    - 4–6 chữ số, bắt đầu bằng 111 (tiền mặt) hoặc 112 (ngân hàng / ví), không trùng tài khoản khác;
    - không đổi được mã đã có bút toán (bút toán cũ sẽ mất liên kết với tài khoản).
    """
    ma = (ma or "").strip()
    cha = tk_cha(loai)
    if not _MAU_TK_CON.match(ma) or not ma.startswith(cha) or ma == cha:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"TK kế toán phải là TK con của {cha} (4–6 chữ số, VD {cha}1)",
        )
    bo_qua = tk_hien_tai.id if tk_hien_tai is not None else None
    if ma in _ma_dang_dung(db, bo_qua):
        raise HTTPException(status.HTTP_409_CONFLICT, f"TK {ma} đã gán cho tài khoản khác")
    cu = tk_hien_tai.tk_ke_toan if tk_hien_tai is not None else None
    if cu and cu != ma and _so_dong_but_toan(db, cu):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"TK {cu} đã có bút toán — không đổi sang {ma} được (sổ cái sẽ tách khỏi lịch sử)",
        )
    return ma


# ─── DDL + gán mã cho tài khoản chưa có (lifespan app/main.py) ───────────────

def dam_bao_cot_tk_ke_toan(engine: Engine) -> None:
    """Thêm cột + chỉ mục UNIQUE, rồi gán mã con cho tài khoản chưa có theo thứ tự id
    (dữ liệu 28/09: ACB→1121, BIDV→1122, Tiền Mặt→1111, VPB→1123). Chạy lại nhiều lần vẫn an toàn;
    khoá advisory để nhiều worker khởi động cùng lúc không cấp trùng mã."""
    with engine.begin() as c:
        for sql in _DDL:
            c.execute(text(sql))
        c.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _KHOA_CAP_MA})
        dung = set(c.execute(text(
            "SELECT tk_ke_toan FROM ketoan.tai_khoan_nh WHERE tk_ke_toan IS NOT NULL"
        )).scalars())
        chua_gan = c.execute(text(
            "SELECT id, loai FROM ketoan.tai_khoan_nh WHERE tk_ke_toan IS NULL ORDER BY id"
        )).all()
        for tk_id, loai in chua_gan:
            cha = tk_cha(loai)
            ma = next((f"{cha}{i}" for i in range(1, SO_CON_TOI_DA + 1) if f"{cha}{i}" not in dung), None)
            if ma is None:
                continue
            dung.add(ma)
            c.execute(text("UPDATE ketoan.tai_khoan_nh SET tk_ke_toan = :m WHERE id = :i"), {"m": ma, "i": tk_id})


# ─── Chuyển bút toán cũ 111/112 sang TK con (bước dữ liệu — cần duyệt trên production) ─

_SQL_DONG_CU = text("""
    SELECT l.id, l.account_code AS tk_cu, t.tk_ke_toan AS tk_moi, t.ten_tk, l.loai, l.so_tien,
           e.ma_but_toan, e.ngay, e.source_type
    FROM ketoan.journal_line l
    JOIN ketoan.journal_entry e ON e.id = l.journal_id
    LEFT JOIN ketoan.tam_ung tu ON l.ref_table = 'tam_ung' AND tu.id = l.ref_id
    JOIN ketoan.tai_khoan_nh t ON t.id = CASE WHEN l.ref_table = 'tai_khoan_nh' THEN l.ref_id ELSE tu.tai_khoan_id END
    WHERE l.account_code IN ('111', '112')
      AND l.ref_table IN ('tai_khoan_nh', 'tam_ung')
      AND t.tk_ke_toan IS NOT NULL
      AND left(t.tk_ke_toan, 3) = l.account_code
    ORDER BY e.ngay, l.id
""")


def chuyen_but_toan_cu(db: Session, *, ghi: bool = False) -> list[dict]:
    """Dòng bút toán 111/112 cũ có ghi rõ tài khoản tiền (ref tai_khoan_nh, hoặc tạm ứng có tai_khoan_id)
    → TK con của đúng tài khoản đó. Chỉ đổi trong cùng TK cha nên số dư 111/112 không đổi.
    ghi=False: chỉ trả danh sách dự kiến. Dòng không xác định được tài khoản thì giữ nguyên."""
    ds = [dict(r._mapping) for r in db.execute(_SQL_DONG_CU)]
    if ghi and ds:
        for r in ds:
            db.execute(
                text("UPDATE ketoan.journal_line SET account_code = :m WHERE id = :i AND account_code = :c"),
                {"m": r["tk_moi"], "i": r["id"], "c": r["tk_cu"]},
            )
        db.execute(text("""
            UPDATE ketoan.tam_ung tu SET tk_tien = t.tk_ke_toan
            FROM ketoan.tai_khoan_nh t
            WHERE t.id = tu.tai_khoan_id AND tu.tk_tien IN ('111', '112')
              AND t.tk_ke_toan IS NOT NULL AND left(t.tk_ke_toan, 3) = tu.tk_tien
        """))
        db.commit()
    return ds
