"""Ketoan: Trang Kế Toán phê duyệt cấp 1 các Đề Nghị Thanh Toán từ saleadmin.

Workflow: NV saleadmin tạo (`cho_duyet`) → KT (ở đây) duyệt → `kt_duyet`
                                          → KT từ chối → `kt_tu_choi`
Sau khi `kt_duyet`, CEO duyệt cấp 2 ở app saleadmin để hoàn tất + auto-sync ketoan.

Cùng DB nên đọc/ghi `saleadmin.denghitt` trực tiếp qua ORM (lazy import).
"""
import logging
from datetime import date as date_cls, datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select, text as _text
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, require_app
from shared.db import get_db
from shared.routers.duyet_chi import _ngay_ghi_so

from ..models import ChiPhiPhatSinh, SoQuy
from ..services.ban_sao_de_nghi import tu_choi_de_xuat_kem
from ..services.from_saleadmin import LOAI_CHI_PHI_DVVC
from ._chi_tien import (
    HACH_TOAN_TRA_NCC, chan_doi_loai_tra_ncc, loai_khi_chi, ngay_nhan_hop_le, nguoi_nhan_chuan,
)


logger = logging.getLogger(__name__)

router = APIRouter()
_REQ = require_app("ketoan")
_KT_ROLES = ("manager", "admin")


# ── Schemas (local — không phụ thuộc saleadmin) ─────────────────────


class KTApproveBody(BaseModel):
    kt_ghi_chu: Optional[str] = None


class KTRejectBody(BaseModel):
    ly_do: str = Field(..., min_length=1)


class ChiBody(BaseModel):
    tai_khoan: Optional[str] = None
    ghi_chu: Optional[str] = None
    # Ngày ghi sổ khoản chi (kế toán nhập trong hộp thoại Chi tiền). Bỏ trống = giữ
    # hành vi cũ: lấy ngày CEO duyệt, không có thì ngày đề nghị.
    ngay_chi: Optional[date_cls] = None
    # Việc 3 (08/10/2026) — đều optional, bỏ trống = y hệt trước (màn cũ /chi-tap-trung chỉ gửi {tai_khoan, ghi_chu}).
    nguoi_nhan: Optional[str] = Field(None, max_length=255)   # → so_quy.doi_tuong_ten
    ngay_nhan: Optional[date_cls] = None                      # → so_quy.ngay_nhan (không ràng buộc ngày chi)
    # TÊN loại trong danh mục. Chỉ Đề nghị TT trả ĐVVC đổi được (gợi ý "Vận chuyển"); bản sao đề xuất trả NCC
    # (ref_congno) là Nợ 331 → gửi loại nào cũng 422.
    loai_chi_phi: Optional[str] = Field(None, max_length=128)


_CHI_ROLES = ("manager", "admin", "ceo", "assistant_ceo")


def _denghitt_to_dict(e, name_map: Optional[dict] = None) -> dict:
    """Convert saleadmin.DeNghiTT ORM → dict.

    `name_map` (username → full_name) dùng để gắn thêm `*_ten` cho UI hiển thị
    tên thay vì mã. Caller (`list_denghitt`) batch query một lần để tránh N+1.
    """
    nm = name_map or {}
    return {
        "id": e.id,
        "ngay_de_nghi": e.ngay_de_nghi.isoformat() if e.ngay_de_nghi else None,
        "ma_don": e.ma_don,
        "don_vi_vc": e.don_vi_vc,
        "dvvc_id": e.dvvc_id,
        "so_tien": float(e.so_tien) if e.so_tien else 0,
        "ngay_giao": e.ngay_giao.isoformat() if e.ngay_giao else None,
        "ly_do": e.ly_do,
        "ghi_chu": e.ghi_chu,
        "trang_thai": e.trang_thai,
        "nguoi_tao": e.nguoi_tao,
        "nguoi_tao_ten": nm.get(e.nguoi_tao) if e.nguoi_tao else None,
        "kt_duyet_boi": e.kt_duyet_boi,
        "kt_duyet_boi_ten": nm.get(e.kt_duyet_boi) if e.kt_duyet_boi else None,
        "kt_duyet_luc": e.kt_duyet_luc.isoformat() if e.kt_duyet_luc else None,
        "kt_ghi_chu": e.kt_ghi_chu,
        "nguoi_duyet": e.nguoi_duyet,
        "nguoi_duyet_ten": nm.get(e.nguoi_duyet) if e.nguoi_duyet else None,
        "ngay_duyet": e.ngay_duyet.isoformat() if e.ngay_duyet else None,
        "chung_tu_url": e.chung_tu_url,
        "ref_congno": getattr(e, "ref_congno", None),
        "da_chi": bool(getattr(e, "da_chi", False)),
        "da_chi_ngoai": bool(getattr(e, "da_chi_ngoai", False)),
        "tai_khoan_chi": getattr(e, "tai_khoan_chi", None),
        "ngay_chi": e.ngay_chi.isoformat() if getattr(e, "ngay_chi", None) else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _build_name_map(db: Session, rows: list) -> dict:
    """Batch query shared.users để map username → full_name cho cả nguoi_tao/kt_duyet_boi/nguoi_duyet."""
    from shared.models import User  # lazy
    usernames = {
        u for e in rows
        for u in (e.nguoi_tao, e.kt_duyet_boi, e.nguoi_duyet)
        if u
    }
    if not usernames:
        return {}
    users = db.execute(
        select(User.username, User.full_name).where(User.username.in_(usernames))
    ).all()
    return {u: n for u, n in users}


def _get_or_404(db: Session, did: str):
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    e = db.get(DeNghiTT, did)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"DNTT {did} không tồn tại")
    return e


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("/api/de-nghi-tt")
def list_denghitt(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = Query(None, description="lọc theo trang_thai; rỗng = tất cả"),
    limit: int = Query(200, le=500),
    offset: int = 0,
):
    """List denghitt cho trang Kế Toán phê duyệt. Default trả tất cả status mới nhất."""
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    stmt = select(DeNghiTT).order_by(DeNghiTT.created_at.desc())
    if trang_thai:
        stmt = stmt.where(DeNghiTT.trang_thai == trang_thai)
    stmt = stmt.limit(limit).offset(offset)
    rows = list(db.execute(stmt).scalars())
    name_map = _build_name_map(db, rows)
    return [_denghitt_to_dict(e, name_map) for e in rows]


@router.get("/api/de-nghi-tt/summary")
def summary_denghitt(
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Đếm theo trạng thái — dùng cho badge UI."""
    from sqlalchemy import func
    from saleadmin.app.models import DeNghiTT  # lazy cross-app
    rows = db.execute(
        select(DeNghiTT.trang_thai, func.count(DeNghiTT.id))
        .group_by(DeNghiTT.trang_thai)
    ).all()
    return {tt: n for tt, n in rows}


@router.get("/api/de-nghi-tt/{did}/detail")
def detail_denghitt(
    did: str,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Chi tiết 1 DNTT kèm danh sách chứng từ — dùng cho modal KT xem trước khi duyệt."""
    e = _get_or_404(db, did)
    name_map = _build_name_map(db, [e])
    data = _denghitt_to_dict(e, name_map)
    # Lấy danh sách chứng từ
    try:
        from saleadmin.app.models.dntt_attachment import DeNghiTTAttachment
        atts = db.execute(
            select(DeNghiTTAttachment)
            .where(DeNghiTTAttachment.dntt_id == did)
            .order_by(DeNghiTTAttachment.uploaded_at.asc())
        ).scalars().all()
        data["attachments"] = [
            {
                "id": a.id,
                "loai": a.loai,
                "filename": a.filename,
                "url": a.url,
                "size": a.size,
                "ghi_chu": a.ghi_chu,
                "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
                "uploaded_by": a.uploaded_by,
            }
            for a in atts
        ]
    except Exception:
        data["attachments"] = []
    return data


@router.post("/api/de-nghi-tt/{did}/kt-approve")
def kt_approve(
    did: str,
    body: KTApproveBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế toán duyệt cấp 1 — cho_duyet → kt_duyet."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được duyệt cấp 1")
    e = _get_or_404(db, did)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r}, KT chỉ duyệt khi cho_duyet",
        )
    e.trang_thai = "kt_duyet"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    if body.kt_ghi_chu:
        e.kt_ghi_chu = body.kt_ghi_chu
    db.commit()
    db.refresh(e)
    log_action(
        db, app="ketoan", action="kt_approve_denghitt", user=user, request=request,
        resource=f"denghitt:{did}", payload={"kt_ghi_chu": body.kt_ghi_chu},
    )
    return _denghitt_to_dict(e, _build_name_map(db, [e]))


@router.post("/api/de-nghi-tt/{did}/kt-reject")
def kt_reject(
    did: str,
    body: KTRejectBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Kế toán từ chối cấp 1 — cho_duyet → kt_tu_choi."""
    if user.role not in _KT_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ kế toán (manager)/admin được từ chối cấp 1")
    e = _get_or_404(db, did)
    if e.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r}, KT chỉ từ chối khi cho_duyet",
        )
    e.trang_thai = "kt_tu_choi"
    e.kt_duyet_boi = user.username
    e.kt_duyet_luc = datetime.now(tz=timezone.utc)
    e.kt_ghi_chu = body.ly_do
    # Đề nghị TT này là bản sao của đề xuất trả NCC bên Mua Hàng (ref_congno) thì từ chối luôn, cùng giao dịch.
    kem = tu_choi_de_xuat_kem(db, congno_id=getattr(e, "ref_congno", None), ly_do=body.ly_do, username=user.username)
    db.commit()
    db.refresh(e)
    log_action(
        db, app="ketoan", action="kt_reject_denghitt", user=user, request=request,
        resource=f"denghitt:{did}", payload={"ly_do": body.ly_do, "tu_choi_kem": kem},
    )
    return {**_denghitt_to_dict(e, _build_name_map(db, [e])), "tu_choi_kem": kem}


@router.post("/api/de-nghi-tt/{did}/tu-choi-truoc-chi")
def tu_choi_truoc_chi(
    did: str,
    body: KTRejectBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """Từ chối DNTT ĐÃ DUYỆT XONG (trang_thai='duyet', CEO đã duyệt cấp 2 ở Sale
    Admin) NHƯNG CHƯA CHI — giám đốc yêu cầu 30/09/2026 (màn Duyệt chi tab "Chờ
    chi" thiếu nút Từ chối). Trước đây chỉ từ chối được ở cấp 1 (cho_duyet →
    kt_tu_choi, kt_reject phía trên) hoặc cấp 2 bên Sale Admin (kt_duyet → tu_choi,
    saleadmin/app/routers/denghitt.py:292 reject_denghitt — CHỈ ĐỌC, không sửa).

    duyet → tu_choi — CÙNG trạng thái cuối 'tu_choi' đã có sẵn trong pipeline DNTT
    (models/denghitt.py:68: cho_duyet → kt_duyet → duyet | kt_tu_choi | tu_choi),
    không phải trạng thái mới. Ghi field GIỐNG HỆT reject_denghitt bên Sale Admin
    (nguoi_duyet/ngay_duyet/ly_do) để nếu sau này Sale Admin có màn "sửa & gửi
    lại" cho tu_choi, dữ liệu đã đúng khuôn — không cần chờ họ đổi gì.
    """
    if user.role not in _CHI_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được từ chối")
    e = _get_or_404(db, did)
    if (e.trang_thai or "") != "duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r} — chỉ từ chối khi ĐÃ DUYỆT XONG, chưa chi",
        )
    if getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề nghị này đã chi rồi — không thể từ chối")
    if getattr(e, "da_chi_ngoai", False):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Khoản này đã được chi ở trang Duyệt ĐX Trả NCC — không từ chối được nữa",
        )
    e.trang_thai = "tu_choi"
    e.nguoi_duyet = user.username
    e.ngay_duyet = datetime.now(tz=timezone.utc)
    e.ly_do = body.ly_do
    # Bản sao của đề xuất trả NCC (ref_congno) → từ chối luôn đề xuất Mua Hàng, không thì nó vẫn chi được.
    kem = tu_choi_de_xuat_kem(db, congno_id=getattr(e, "ref_congno", None), ly_do=body.ly_do, username=user.username)
    db.commit()
    db.refresh(e)
    log_action(
        db, app="ketoan", action="tu_choi_truoc_chi_denghitt", user=user, request=request,
        resource=f"denghitt:{did}", payload={"ly_do": body.ly_do, "tu_choi_kem": kem},
    )
    return {**_denghitt_to_dict(e, _build_name_map(db, [e])), "tu_choi_kem": kem}


@router.post("/api/de-nghi-tt/{did}/chi")
def chi_denghitt(
    did: str,
    body: ChiBody,
    request: Request,
    user: Annotated[JWTPayload, Depends(_REQ)],
    db: Annotated[Session, Depends(get_db)],
):
    """KT bấm CHI 1 Đề Nghị TT đã CEO duyệt → tạo sổ quỹ chi + ChiPhí + đánh dấu
    da_chi (đồng nhất với Đề xuất chi + Trả NCC). Idempotent: chỉ chi khi
    trang_thai='duyet' + chưa da_chi + chưa da_chi_ngoai (chưa chi ở trang NCC).
    Nếu DNTT nối từ đề xuất NCC (ref_congno) → giảm công nợ NCC luôn.
    """
    if user.role not in _CHI_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán/CEO được chi")
    e = _get_or_404(db, did)
    if (e.trang_thai or "") != "duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"DNTT trạng thái {e.trang_thai!r} — chỉ chi khi CEO đã duyệt cuối (duyet).",
        )
    if getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề nghị này đã được chi rồi.")
    if getattr(e, "da_chi_ngoai", False):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Khoản này đã được chi ở trang Duyệt ĐX Trả NCC — không chi lại.",
        )

    tk = (body.tai_khoan or "").strip() or None
    # BẮT BUỘC chọn tài khoản (LOG-04, 2026-08-28): trước đây không chọn TK thì sổ quỹ
    # tạo với tai_khoan=None → LỌT guard chặn số dư âm + tiền chi "treo" TK NULL.
    if not tk:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Vui lòng chọn tài khoản chi (Tiền Mặt / ngân hàng) trước khi Chi.",
        )
    # Việc 3 — ô mới kiểm TRƯỚC mọi thao tác ghi; client cũ không gửi thì các bước này không làm gì.
    nguoi_nhan = nguoi_nhan_chuan(body.nguoi_nhan)
    ngay_nhan = ngay_nhan_hop_le(body.ngay_nhan)
    tra_ncc = bool(getattr(e, "ref_congno", None))
    if tra_ncc:   # bản sao đề xuất trả NCC: tiền trả nợ (Nợ 331), không có dòng chi phí để đổi loại
        chan_doi_loai_tra_ncc(body.loai_chi_phi)
        goi_y_loai, loai_doi = HACH_TOAN_TRA_NCC, None
    else:
        goi_y_loai = LOAI_CHI_PHI_DVVC
        # Nhóm của gợi ý để None: cầu nối chưa bao giờ ghi nhóm cho dòng "Vận chuyển" (cột tự về 'khac') —
        # giữ nguyên khi kế toán không đổi; đổi loại thì nhóm theo danh mục.
        chon = loai_khi_chi(db, (LOAI_CHI_PHI_DVVC, None), body.loai_chi_phi)
        loai_doi = chon if chon[0] != LOAI_CHI_PHI_DVVC else None
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    from ketoan.app.services.so_quy_auto import assert_du_chi
    assert_du_chi(db, tk, e.so_tien)

    # Tạo sổ quỹ chi + ChiPhí phai_tra ĐVVC (idempotent qua ref_dntt), rồi đánh dấu.
    try:
        from ketoan.app.services.from_saleadmin import sync_so_quy_chi_phi_from_denghitt
        sync_so_quy_chi_phi_from_denghitt(
            db, e, tai_khoan=tk, doi_tuong_ten=nguoi_nhan, ngay_nhan=ngay_nhan,
            loai_chi_phi=loai_doi[0] if loai_doi else None, nhom_chi_phi=loai_doi[1] if loai_doi else None,
        )
        e.da_chi = True
        e.tai_khoan_chi = tk
        e.ngay_chi = datetime.now(tz=timezone.utc)
        e.chi_boi = user.username
        db.commit()
        db.refresh(e)
    except Exception as ex:
        db.rollback()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Chi thất bại — sổ quỹ lỗi: {ex}"
        )
    if not getattr(e, "da_chi", False):
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Chi chưa ghi được")

    # Nối NCC: DNTT từ đề xuất trả NCC → giảm công nợ NCC ở CẢ HAI sổ.
    #
    # BỔ SUNG 02/10/2026 — `ketoan.cong_no`. Trước đây khối này chỉ đặt
    # `muahang.congno.da_chi = TRUE`, mà `da_chi` chỉ làm giảm công nợ bên MUA HÀNG
    # (muahang/app/routers/congno.py ~435). Sổ CHUẨN là `ketoan.cong_no` và nó
    # KHÔNG hề giảm — đúng điều docstring hàm này hứa ("giảm công nợ NCC luôn") mà
    # chưa làm, và đúng điều comment trong from_saleadmin.py:99-101 đã ghi nhận
    # ("nợ NCC không giảm") nhưng lần vá 30/09 chỉ xử phần chi phí trùng.
    #
    # Ca thật: DNTT-2026-0042 → phiếu quỹ #859, CHIẾN PHƯƠNG 70.000.000đ ngày
    # 16/09 — tiền ra khỏi quỹ, công nợ Kế toán đứng im, phải vá tay bằng bút toán
    # V04 ngày 01/10. Và vì `da_chi` đã TRUE, trang "Duyệt ĐX Trả NCC" sau đó trả
    # 409 "Đề xuất này đã chi rồi" → KHÔNG bù lại được bằng giao diện.
    #
    # Dùng CHUNG service với cửa chi kia (ncc_de_xuat.py::chi_ncc), khoá idempotent
    # `ref_id='mh-dexuat-{ref_congno}'` → trả bằng cửa nào thì cửa còn lại cũng
    # không ghi trùng. Ghi trong CÙNG transaction với lệnh UPDATE Mua hàng: hai sổ
    # cùng giảm hoặc cùng không, không bao giờ lệch nhau nửa bước.
    _ref_cn = getattr(e, "ref_congno", None)
    if _ref_cn:
        try:
            db.execute(
                _text("""UPDATE muahang.congno
                         SET da_chi = TRUE, tai_khoan_chi = :tk, ngay_chi = now()
                         WHERE id = :c AND da_chi = FALSE"""),
                {"tk": tk, "c": _ref_cn},
            )
            from ketoan.app.services.giam_cong_no_ncc import ghi_giam_cong_no_ncc
            ghi_giam_cong_no_ncc(
                db,
                ma_de_xuat_mh=_ref_cn,
                ncc_ten=(e.don_vi_vc or ""),
                so_tien=e.so_tien,
                by=user.username,
                # Ngày phiếu quỹ, KHÔNG phải ngày bấm — sync_so_quy_chi_phi_from_denghitt
                # lấy `ngay_duyet` làm ngày phiếu, nếu đây dùng today() thì khoản của
                # tháng trước rơi sang tháng này và lệch báo cáo theo tháng.
                ngay=_ngay_ghi_so(
                    body.ngay_chi,
                    (e.ngay_duyet.date() if getattr(e, "ngay_duyet", None)
                     else getattr(e, "ngay_de_nghi", None)),
                ),
                nguon=f"nút Chi trang Đề nghị TT {e.id}",
            )
            db.commit()
        except Exception:
            db.rollback()
            logger.exception(
                "chi_denghitt: giam cong no NCC that bai (dntt=%s, de_xuat=%s) — "
                "TIEN DA RA KHOI QUY, can vao Cong no NCC ghi tay dong giam no",
                did, _ref_cn,
            )

    # Việc 3: đọc lại từ DB đúng thứ ĐÃ LƯU (không phải thứ client gửi) — giao diện đối chiếu với lựa chọn của
    # kế toán; cầu nối sổ quỹ là fail-soft nên "đã gửi" chưa chắc là "đã ghi".
    _ref = f"DNTT-{e.id}"
    sq_luu = db.execute(
        select(SoQuy.doi_tuong_ten, SoQuy.ngay_nhan, SoQuy.ngay).where(SoQuy.ref_dntt == _ref)
    ).first()
    loai_luu = None if tra_ncc else db.execute(
        select(ChiPhiPhatSinh.loai_chi_phi).where(ChiPhiPhatSinh.ref_dntt == _ref)
    ).scalar_one_or_none()
    luu = {
        "nguoi_nhan": sq_luu.doi_tuong_ten if sq_luu else None,
        "ngay_nhan": sq_luu.ngay_nhan.isoformat() if sq_luu and sq_luu.ngay_nhan else None,
        "loai_chi_phi_hach_toan": loai_luu,
    }

    log_action(
        db, app="ketoan", action="chi_denghitt", user=user, request=request,
        resource=f"denghitt:{did}",
        payload={
            "tai_khoan": tk, "so_tien": float(e.so_tien or 0),
            # Việc 3: ngày kế toán nhập + ngày phiếu quỹ thật (DNTT ghi phiếu theo ngày CEO duyệt).
            "ngay_chi": body.ngay_chi.isoformat() if body.ngay_chi else None,
            "ngay_so_quy": sq_luu.ngay.isoformat() if sq_luu and sq_luu.ngay else None,
            "loai_chi_phi_goi_y": goi_y_loai, "loai_chi_phi_chon": HACH_TOAN_TRA_NCC if tra_ncc else loai_luu,
            "nguoi_nhan": luu["nguoi_nhan"], "ngay_nhan": luu["ngay_nhan"],
        },
    )
    return {**_denghitt_to_dict(e, _build_name_map(db, [e])), **luu}
