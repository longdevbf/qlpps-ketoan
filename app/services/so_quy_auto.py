"""Auto-wire SoQuy entries:
- DoanhThu created/updated → tạo SoQuy thu (lien_quan='doanh_thu', ref_id=DT-{id}).
- CongNo có khoản trả → tạo SoQuy chi (lien_quan='cong_no', ref_id=CN-{id}-pay-{seq}).
- ChiPhiPhatSinh created → tạo SoQuy chi (lien_quan='chi_phi', ref_id=CP-{id}).

Idempotent qua (lien_quan, ref_id) — gọi lại update so_tien.
Fail-soft — caller không bị block nếu sync SoQuy fail.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import ChiPhiPhatSinh, CongNo, DoanhThu, SoQuy


def _net_so_quy(db: Session, tai_khoan_ten: str, tu_ngay=None) -> Decimal:
    """SUM(thu − chi) trên ketoan.so_quy của TK; nếu `tu_ngay` → chỉ từ ngày đó."""
    sql = ("SELECT COALESCE(SUM(CASE WHEN loai='thu' THEN so_tien ELSE -so_tien END),0) "
           "FROM ketoan.so_quy WHERE tai_khoan = :tk")
    params = {"tk": tai_khoan_ten}
    if tu_ngay is not None:
        sql += " AND ngay >= :tu"
        params["tu"] = tu_ngay
    return Decimal(str(db.execute(text(sql), params).scalar() or 0))


def so_du_hien_tai(db: Session, tai_khoan_ten: Optional[str]) -> Decimal:
    """Số dư HIỆN TẠI của 1 tài khoản — TÔN TRỌNG snapshot `SoDuDauKy` (đồng bộ với
    màn Sổ Quỹ + báo cáo). Trước đây chỉ dùng `TaiKhoanNH.so_du_dau + net all-time`
    nên guard chặn-chi lệch số dư hiển thị khi có re-baseline đầu kỳ (DUP-01, 2026-08-28).

    Quy tắc: lấy snapshot đầu kỳ GẦN NHẤT có tháng ≤ tháng hiện tại làm mốc, cộng net
    giao dịch từ mốc đó tới nay. Không có snapshot → TaiKhoanNH.so_du_dau + net all-time.
    """
    if not tai_khoan_ten:
        return Decimal("0")
    from datetime import date as _date
    cur_month = _date.today().replace(day=1)
    try:
        from ..models import TaiKhoanNH, SoDuDauKy
        tk = db.execute(
            select(TaiKhoanNH).where(TaiKhoanNH.ten_tk == tai_khoan_ten)
        ).scalar_one_or_none()
        if tk is not None:
            anchor = db.execute(
                select(SoDuDauKy.thang, SoDuDauKy.so_du)
                .where(SoDuDauKy.tai_khoan_id == tk.id, SoDuDauKy.thang <= cur_month)
                .order_by(SoDuDauKy.thang.desc()).limit(1)
            ).first()
            if anchor:  # snapshot đầu kỳ + net từ đầu tháng snapshot tới nay
                return Decimal(str(anchor[1] or 0)) + _net_so_quy(db, tai_khoan_ten, anchor[0])
            # không snapshot → số dư đầu all-time + toàn bộ net
            return Decimal(str(getattr(tk, "so_du_dau", 0) or 0)) + _net_so_quy(db, tai_khoan_ten)
    except Exception:
        db.rollback()
    # TK không có bản ghi danh mục → chỉ net all-time
    return _net_so_quy(db, tai_khoan_ten)


def assert_du_chi(db: Session, tai_khoan_ten: Optional[str], so_tien_chi) -> None:
    """CHẶN lệnh chi làm số dư TK âm (anh Quang 2026-08-27) — raise HTTPException 400.
    Gọi TRƯỚC khi tạo bất kỳ giao dịch chi nào (sổ quỹ / chi phí / chuyển nội bộ / nút Chi)."""
    from fastapi import HTTPException, status
    st = Decimal(str(so_tien_chi or 0))
    if st <= 0:
        return
    # Khoá theo TÀI KHOẢN tới hết transaction → 2 lệnh chi đồng thời cùng TK không
    # cùng đọc số dư cũ rồi cùng qua cửa (DB-07, 2026-08-28).
    if tai_khoan_ten:
        try:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"),
                       {"k": f"soquy_chi:{tai_khoan_ten}"})
        except Exception:
            db.rollback()
    bal = so_du_hien_tai(db, tai_khoan_ten)
    if bal - st < 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Số dư '{tai_khoan_ten or '(chưa chọn tài khoản)'}' chỉ còn "
            f"{int(bal):,}đ — KHÔNG đủ để chi {int(st):,}đ (sẽ âm {int(st - bal):,}đ). "
            f"Vui lòng nạp thêm, chọn tài khoản khác, hoặc kiểm tra lại số dư đầu kỳ.",
        )


def _upsert_so_quy(
    db: Session,
    *,
    lien_quan: str,
    ref_id: str,
    ngay,
    loai: str,            # 'thu' | 'chi'
    so_tien: Decimal,
    tai_khoan: Optional[str] = None,
    noi_dung: Optional[str] = None,
    mo_ta: Optional[str] = None,
    phan_loai_cf: Optional[str] = None,
    ma_don: Optional[str] = None,
    created_by: Optional[str] = "auto-bridge",
) -> SoQuy:
    # Idempotent theo (lien_quan, ref_id) — được bảo vệ bởi partial UNIQUE INDEX
    # uq_sq_lienquan_refid (dedupe + index tạo 2026-08-28, DB-02) nên 2 request
    # đồng thời KHÔNG tạo được 2 dòng (dòng thua vi phạm unique → fail-soft rollback).
    rec = db.execute(
        select(SoQuy).where(
            SoQuy.lien_quan == lien_quan, SoQuy.ref_id == ref_id,
        )
    ).scalar_one_or_none()
    if rec is None:
        rec = SoQuy(
            lien_quan=lien_quan, ref_id=ref_id,
            created_by=created_by,
        )
        db.add(rec)
    rec.ngay = ngay
    rec.loai = loai
    rec.so_tien = so_tien
    if tai_khoan:
        rec.tai_khoan = tai_khoan
    if noi_dung:
        rec.noi_dung = noi_dung
    if mo_ta:
        rec.mo_ta = mo_ta
    if phan_loai_cf:
        rec.phan_loai_cf = phan_loai_cf
    if ma_don:
        rec.ma_don = ma_don
    return rec


def sync_so_quy_from_doanh_thu(db: Session, dt: DoanhThu) -> None:
    """Khi DoanhThu created/updated → tạo SoQuy thu tương ứng. Fail-soft."""
    if dt is None or dt.id is None:
        return
    try:
        _upsert_so_quy(
            db,
            lien_quan="doanh_thu",
            ref_id=f"DT-{dt.id}",
            ngay=dt.ngay,
            loai="thu",
            so_tien=Decimal(dt.so_tien or 0),
            tai_khoan=dt.ngan_hang,
            noi_dung=(dt.mo_ta or f"Thu {dt.loai_thanh_toan or 'doanh thu'} - {dt.ma_don or ''}").strip(),
            mo_ta=dt.mo_ta,
            ma_don=dt.ma_don,  # DB-04: điền ma_don để màn đối chiếu KHÔNG sót giao dịch thu
        )
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.getLogger(__name__).error(
            "sync_so_quy_from_doanh_thu FAILED dt=%s", getattr(dt, "id", None), exc_info=True)


def sync_so_quy_from_chi_phi(db: Session, cp: ChiPhiPhatSinh) -> None:
    """Khi ChiPhi created/updated → tạo SoQuy chi. Fail-soft."""
    if cp is None or cp.id is None:
        return
    try:
        _upsert_so_quy(
            db,
            lien_quan="chi_phi",
            ref_id=f"CP-{cp.id}",
            ngay=cp.ngay,
            loai="chi",
            so_tien=Decimal(cp.so_tien or 0),
            tai_khoan=cp.ngan_hang,
            noi_dung=(cp.mo_ta or f"{cp.loai_chi_phi or 'Chi phí'}").strip(),
            mo_ta=cp.mo_ta,
        )
        db.commit()
    except Exception:
        db.rollback()
        import logging
        logging.getLogger(__name__).error(
            "sync_so_quy_from_chi_phi FAILED cp=%s", getattr(cp, "id", None), exc_info=True)


def sync_so_quy_from_cong_no_payment(
    db: Session, cn: CongNo, paid_delta: Decimal,
    tai_khoan: Optional[str] = None,
    ngay_thanh_toan=None,
) -> None:
    """Khi CongNo da_tra tăng (delta) → tạo SoQuy chi cho khoản trả NCC,
    HOẶC SoQuy thu nếu là CongNo phải thu (loai='phai_thu').

    Idempotent qua ref_id = '{cn.id}-DA{seq}' (không thêm prefix CN- thừa).
    Caller pass `paid_delta` (số tiền vừa trả thêm) và `ngay_thanh_toan` (ngày thực tế trả).
    """
    if cn is None or not cn.id or paid_delta is None or paid_delta == 0:
        return
    try:
        seq = str(cn.da_tra or 0).replace(".", "_")
        sq_loai = "thu" if cn.loai == "phai_thu" else "chi"
        from datetime import date as _date_cls
        # Ưu tiên ngay_thanh_toan (do caller truyền), fallback ngay_tra, fallback today.
        # KHÔNG dùng cn.ngay (ngày phát sinh nợ) — trả tháng 5 mà nợ từ tháng 3
        # sẽ làm entry rơi sai tháng trong sổ quỹ.
        ngay_sq = (
            ngay_thanh_toan
            or getattr(cn, "ngay_tra", None)
            or _date_cls.today()
        )
        # phan_loai_cf để cashflow phân loại đúng:
        # phai_thu → thu từ KH, phai_tra → chi trả NCC/VC
        phan_loai = "thu_kh" if sq_loai == "thu" else "tra_ncc"
        _upsert_so_quy(
            db,
            lien_quan="cong_no",
            ref_id=f"{cn.id}-DA{seq}",
            ngay=ngay_sq,
            loai=sq_loai,
            so_tien=Decimal(paid_delta),
            tai_khoan=tai_khoan,
            noi_dung=f"{'Thu' if sq_loai=='thu' else 'Chi'} công nợ {cn.id} - {cn.doi_tac}",
            mo_ta=f"Trả công nợ — đối tác: {cn.doi_tac}",
            phan_loai_cf=phan_loai,
        )
        db.commit()
    except Exception as ex:
        db.rollback()
        import logging
        logging.getLogger(__name__).error(
            "sync_so_quy_from_cong_no_payment FAILED cn=%s delta=%s: %s",
            cn.id, paid_delta, ex, exc_info=True,
        )
