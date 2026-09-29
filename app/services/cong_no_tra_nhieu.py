"""Ghi nhận thu/trả NHIỀU khoản công nợ trong MỘT giao dịch (POST /api/cong-no/tra-nhieu).

Áp cho từng khoản ĐÚNG cơ chế của `tra_cong_no` (POST /api/cong-no/{id}/tra — không sửa):
    - ketoan.cong_no: da_tra += số trả; trang_thai 'da_tra' + ngay_tra khi trả đủ, ngược lại
      'chua_tra'; ghi_chu nếu có (con_lai là cột GENERATED = so_tien - da_tra).
    - ketoan.so_quy: 1 dòng / khoản — cùng tham số `sync_so_quy_from_cong_no_payment`
      (lien_quan='cong_no', ref_id='<id>-DA<da_tra mới>', thu|chi, phan_loai_cf thu_kh|tra_ncc).
    - shared.audit_log: action 'tra_cong_no' / khoản.
Khác bản 1 khoản: (1) validate HẾT trước khi ghi, (2) chặn chi âm quỹ bằng assert_du_chi trên
TỔNG (bản cũ commit công nợ TRƯỚC khi kiểm số dư), (3) không commit giữa chừng — hai hàm dùng chung
`sync_so_quy_from_cong_no_payment` và `log_action` đều tự commit nên KHÔNG gọi được trong một giao
dịch; ở đây gọi thẳng `_upsert_so_quy` / thêm `AuditLog` với đúng các trường như hai hàm đó.
`dry_run=True` chạy y hệt nhánh ghi thật (cùng hàm `_ap_dung`) rồi rollback.
"""
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.audit.logger import _get_ip
from shared.auth import JWTPayload
from shared.models import AuditLog

from ..models import CongNo
from .so_quy_auto import _upsert_so_quy, assert_du_chi

TRANG_THAI_DA_TRA = "da_tra"
TRANG_THAI_CHUA_TRA = "chua_tra"
_LIEN_QUAN_SO_QUY = "cong_no"


def _validate(rows: dict[str, CongNo], dong: list[tuple[str, Decimal]]) -> str:
    """Trả loai chung; raise 422 kèm danh sách lỗi TỪNG dòng nếu có bất kỳ lỗi nào."""
    loi: list[str] = []
    if not dong:
        loi.append("Chưa chọn khoản nào.")
    ids = [i for i, _ in dong]
    if len(set(ids)) != len(ids):
        loi.append("Một khoản bị chọn hai lần.")
    loai = {rows[i].loai for i in ids if i in rows}
    if len(loai) > 1:
        loi.append("Không trộn khoản phải thu và phải trả trong cùng một lần ghi nhận.")
    for cid, so_tien in dong:
        cn = rows.get(cid)
        if cn is None:
            loi.append(f"{cid}: không tồn tại.")
            continue
        con_lai = Decimal(cn.so_tien or 0) - Decimal(cn.da_tra or 0)
        if so_tien <= 0:
            loi.append(f"{cid}: số tiền phải lớn hơn 0.")
        elif so_tien > con_lai:
            loi.append(f"{cid}: {int(so_tien):,}đ vượt số còn lại {int(con_lai):,}đ.")
    if loi:
        # detail là CHUỖI (KD.api của giao diện chỉ hiển thị được detail dạng chuỗi/danh sách pydantic).
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, " ".join(loi))
    return loai.pop()


def _ap_dung(
    db: Session, cn: CongNo, so_tien: Decimal, *, tai_khoan: str, ngay_tra: Optional[date],
    ghi_chu: Optional[str], user: JWTPayload, request: Optional[Request], dry_run: bool,
) -> dict[str, Any]:
    """Áp 1 khoản — chỉ flush, KHÔNG commit (caller quyết commit hay rollback).

    dry_run: chạy y hệt, chỉ khác là dòng so_quy/audit_log MỚI được gỡ khỏi phiên (expunge) thay vì
    INSERT — rollback không trả lại được giá trị sequence đã cấp, nên nếu INSERT thì mỗi lần "Xem
    trước" sẽ làm nhảy id so_quy/audit_log dù không ghi dòng nào."""
    da_tra_cu = Decimal(cn.da_tra or 0)
    cn.da_tra = da_tra_cu + so_tien
    if Decimal(cn.da_tra) >= Decimal(cn.so_tien):
        cn.trang_thai = TRANG_THAI_DA_TRA
        cn.ngay_tra = ngay_tra or date.today()
    else:
        cn.trang_thai = TRANG_THAI_CHUA_TRA
    if ghi_chu:
        cn.ghi_chu = ghi_chu
    db.flush()
    db.refresh(cn)  # lấy con_lai (GENERATED) + da_tra đúng định dạng DB cho ref_id như bản cũ

    sq_loai = "thu" if cn.loai == "phai_thu" else "chi"
    ngay_sq = ngay_tra or cn.ngay_tra or date.today()
    ref_id = f"{cn.id}-DA{str(cn.da_tra or 0).replace('.', '_')}"
    sq = _upsert_so_quy(
        db, lien_quan=_LIEN_QUAN_SO_QUY, ref_id=ref_id, ngay=ngay_sq, loai=sq_loai,
        so_tien=so_tien, tai_khoan=tai_khoan,
        noi_dung=f"{'Thu' if sq_loai == 'thu' else 'Chi'} công nợ {cn.id} - {cn.doi_tac}",
        mo_ta=f"Trả công nợ — đối tác: {cn.doi_tac}",
        phan_loai_cf="thu_kh" if sq_loai == "thu" else "tra_ncc",
    )
    audit = AuditLog(
        app="ketoan", user_id=user.sub if user else None, username=user.username if user else None,
        action="tra_cong_no", resource=f"cong_no:{cn.id}",
        ip=_get_ip(request) if request else None,
        ua=request.headers.get("user-agent") if request else None,
        payload={"da_tra": str(cn.da_tra), "trang_thai": cn.trang_thai, "tra_nhieu": True},
        status="ok",
    )
    db.add(audit)
    if dry_run:
        for moi in (sq, audit):
            if moi in db.new:
                db.expunge(moi)
    db.flush()
    return {
        "id": cn.id, "doi_tac": cn.doi_tac, "ma_don": cn.ma_don, "loai": cn.loai,
        "so_tien_tra": str(so_tien), "da_tra_cu": str(da_tra_cu), "da_tra_moi": str(cn.da_tra),
        "con_lai_moi": str(cn.con_lai), "trang_thai_moi": cn.trang_thai,
        "so_quy": {"loai": sq_loai, "ref_id": ref_id, "so_tien": str(so_tien),
                   "tai_khoan": tai_khoan, "ngay": ngay_sq.isoformat()},
    }


def tra_nhieu(
    db: Session, *, dong: list[tuple[str, Decimal]], tai_khoan: str, ngay_tra: Optional[date],
    ghi_chu: Optional[str], user: JWTPayload, request: Optional[Request], dry_run: bool,
) -> dict[str, Any]:
    """Validate hết → kiểm quỹ (phải trả) → áp từng khoản → commit (hoặc rollback nếu dry_run/lỗi)."""
    try:
        ids = sorted({i for i, _ in dong})
        rows = {
            r.id: r for r in db.execute(
                select(CongNo).where(CongNo.id.in_(ids)).order_by(CongNo.id).with_for_update()
            ).scalars()
        }
        loai = _validate(rows, dong)
        tong = sum((s for _, s in dong), Decimal("0"))
        if loai == "phai_tra":
            assert_du_chi(db, tai_khoan, tong)
        ket_qua = [
            _ap_dung(db, rows[cid], so_tien, tai_khoan=tai_khoan, ngay_tra=ngay_tra,
                     ghi_chu=ghi_chu, user=user, request=request, dry_run=dry_run)
            for cid, so_tien in dong
        ]
        if dry_run:
            db.rollback()
        else:
            db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "dry_run": dry_run, "loai": loai, "tai_khoan": tai_khoan,
        "tong": str(tong), "so_khoan": len(ket_qua),
        "so_doi_tuong": len({k["doi_tac"] for k in ket_qua}),
        "dong": ket_qua,
    }
