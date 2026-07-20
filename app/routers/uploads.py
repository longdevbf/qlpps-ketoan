"""Local file upload endpoints — Kế Toán V2.

Endpoints (mọi route đều require_ketoan_user):

    POST   /api/chi-phi/{cp_id}/upload-hoa-don       (multipart `file`)
    POST   /api/doanh-thu/{dt_id}/upload-chung-tu
    POST   /api/cong-no/{cn_id}/upload-chung-tu
    POST   /api/so-quy/{sq_id}/upload-chung-tu

    GET    /api/uploads/{scope}/{filename}           (serve file, login-required)
    DELETE /api/uploads/{scope}/{filename}           (manager+ only, nullify *_url)

Storage layout (helper `shared.utils.uploads`):
    /var/lib/qlpps/uploads/ketoan/<scope>/<uuid>.<ext>

Scopes:
    chi_phi_<id>, doanh_thu_<id>, cong_no_<id>, so_quy_<id>

URL trả về dạng `/api/uploads/<scope>/<filename>` — match GET endpoint trong file này.
"""
from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload
from shared.db import get_db
from shared.utils.uploads import delete_file, resolve_path, resolve_path_cross_app, save_upload

from shared.models import Product

from ..models import ChiPhiPhatSinh, CongNo, DoanhThu, SoQuy
from ._deps import require_ketoan_user


router = APIRouter()
_AUTH = Depends(require_ketoan_user)
_APP = "ketoan"

# Roles được phép DELETE (admin/ceo/manager).
_MANAGER_ROLES = ("admin", "ceo", "manager")


# ---------------------------------------------------------------------------
# 1. Upload hóa đơn cho chi phí phát sinh (int ID)
# ---------------------------------------------------------------------------
@router.post("/api/chi-phi/{cp_id}/upload-hoa-don")
async def upload_hoa_don_chi_phi(
    cp_id: int,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(ChiPhiPhatSinh, cp_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ChiPhi không tồn tại")

    scope = f"chi_phi_{cp_id}"
    fname, url, size = await save_upload(file, _APP, scope, allow_docs=True)

    obj.hoa_don_url = url
    db.commit()
    db.refresh(obj)

    log_action(
        db, app=_APP, action="upload_hoa_don_chi_phi", user=user, request=request,
        resource=f"chi_phi:{cp_id}",
        payload={"filename": fname, "size": size, "url": url},
    )
    return {"id": obj.id, "hoa_don_url": obj.hoa_don_url, "filename": fname, "size": size}


# ---------------------------------------------------------------------------
# 2. Upload chứng từ cho doanh thu (int ID)
# ---------------------------------------------------------------------------
@router.post("/api/doanh-thu/{dt_id}/upload-chung-tu")
async def upload_chung_tu_doanh_thu(
    dt_id: int,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(DoanhThu, dt_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "DoanhThu không tồn tại")

    scope = f"doanh_thu_{dt_id}"
    fname, url, size = await save_upload(file, _APP, scope, allow_docs=True)

    obj.chung_tu_url = url
    db.commit()
    db.refresh(obj)

    log_action(
        db, app=_APP, action="upload_chung_tu_doanh_thu", user=user, request=request,
        resource=f"doanh_thu:{dt_id}",
        payload={"filename": fname, "size": size, "url": url},
    )
    return {"id": obj.id, "chung_tu_url": obj.chung_tu_url, "filename": fname, "size": size}


# ---------------------------------------------------------------------------
# 3. Upload chứng từ cho công nợ (str ID 'CN-2026-0001')
# ---------------------------------------------------------------------------
@router.post("/api/cong-no/{cn_id}/upload-chung-tu")
async def upload_chung_tu_cong_no(
    cn_id: str,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(CongNo, cn_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "CongNo không tồn tại")

    scope = f"cong_no_{cn_id}"
    fname, url, size = await save_upload(file, _APP, scope, allow_docs=True)

    obj.chung_tu_url = url
    db.commit()
    db.refresh(obj)

    log_action(
        db, app=_APP, action="upload_chung_tu_cong_no", user=user, request=request,
        resource=f"cong_no:{cn_id}",
        payload={"filename": fname, "size": size, "url": url},
    )
    return {"id": obj.id, "chung_tu_url": obj.chung_tu_url, "filename": fname, "size": size}


# ---------------------------------------------------------------------------
# 4. Upload chứng từ cho sổ quỹ (int ID)
# ---------------------------------------------------------------------------
@router.post("/api/so-quy/{sq_id}/upload-chung-tu")
async def upload_chung_tu_so_quy(
    sq_id: int,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(SoQuy, sq_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SoQuy không tồn tại")

    scope = f"so_quy_{sq_id}"
    fname, url, size = await save_upload(file, _APP, scope, allow_docs=True)

    obj.chung_tu_url = url
    db.commit()
    db.refresh(obj)

    log_action(
        db, app=_APP, action="upload_chung_tu_so_quy", user=user, request=request,
        resource=f"so_quy:{sq_id}",
        payload={"filename": fname, "size": size, "url": url},
    )
    return {"id": obj.id, "chung_tu_url": obj.chung_tu_url, "filename": fname, "size": size}


# ---------------------------------------------------------------------------
# 5. Upload ảnh sản phẩm (master catalog — chỉ Kế Toán có quyền sửa)
# ---------------------------------------------------------------------------
@router.post("/api/products/{pid}/upload-image")
async def upload_product_image(
    pid: int,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(Product, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")

    # Xoá ảnh cũ nếu có (tránh rác file orphan trên đĩa)
    if obj.hinh_anh and obj.hinh_anh.startswith("/api/files/products/"):
        parts = obj.hinh_anh.split("/")
        if len(parts) >= 6:
            old_fname = parts[5]
            delete_file(_APP, f"product_{pid}", old_fname)

    scope = f"product_{pid}"
    fname, _legacy_url, size = await save_upload(file, _APP, scope, allow_docs=False)

    # URL phải dùng được cross-app — mount qua shared.services.product_files trong mọi app
    url = f"/api/files/products/{pid}/{fname}"
    obj.hinh_anh = url
    db.commit()
    db.refresh(obj)

    log_action(
        db, app=_APP, action="upload_product_image", user=user, request=request,
        resource=f"product:{pid}",
        payload={"filename": fname, "size": size, "url": url},
    )
    return {"id": obj.id, "hinh_anh": obj.hinh_anh, "filename": fname, "size": size}


@router.delete("/api/products/{pid}/image", status_code=status.HTTP_204_NO_CONTENT)
def delete_product_image(
    pid: int,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    obj = db.get(Product, pid)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sản phẩm không tồn tại")
    if not obj.hinh_anh:
        return

    if obj.hinh_anh.startswith("/api/files/products/"):
        parts = obj.hinh_anh.split("/")
        if len(parts) >= 6:
            delete_file(_APP, f"product_{pid}", parts[5])

    old_url = obj.hinh_anh
    obj.hinh_anh = None
    db.commit()
    log_action(
        db, app=_APP, action="delete_product_image", user=user, request=request,
        resource=f"product:{pid}", payload={"url": old_url},
    )


# ---------------------------------------------------------------------------
# 6. Upload tài liệu buổi đào tạo (scope dao_tao_<sid>, allow_docs=True)
# ---------------------------------------------------------------------------
@router.post(
    "/api/dao-tao/sessions/{sid}/upload",
    status_code=status.HTTP_201_CREATED,
)
async def upload_dao_tao_file(
    sid: str,
    file: UploadFile,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Upload file kèm session đào tạo (PDF/Word/Excel/ảnh).

    KHÔNG lưu DB Kế Toán (chia sẻ bảng `marketing.dao_tao_sessions`); FE
    nhận `{url, filename, size}` rồi gọi `POST /api/dao-tao/sessions/{sid}/files`
    để lưu metadata vào session.
    """
    sid_norm = (sid or "").strip()
    if not sid_norm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Thiếu session id")
    scope = f"dao_tao_{sid_norm}"

    fname, url, size = await save_upload(
        file, app=_APP, scope=scope, allow_docs=True,
    )

    log_action(
        db, app=_APP, action="upload_dao_tao_file",
        user=user, request=request, resource=f"dao_tao:{sid_norm}",
        payload={"filename": fname, "size": size, "scope": scope},
    )
    return {"url": url, "filename": fname, "size": size}


# ---------------------------------------------------------------------------
# 6a. Serve file (login-required)
# ---------------------------------------------------------------------------
@router.get("/api/uploads/{scope}/{filename}")
def serve_upload(
    scope: str,
    filename: str,
    user: Annotated[JWTPayload, _AUTH],
):
    """Stream file local. 404 nếu path không hợp lệ / không tồn tại."""
    p = resolve_path(_APP, scope, filename)
    # dao_tao cross-app: file có thể ở app dir khác → fallback
    if p is None and scope.startswith("dao_tao_"):
        p = resolve_path_cross_app(scope, filename, prefer=_APP)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File không tồn tại")
    return FileResponse(str(p), filename=filename)


# ---------------------------------------------------------------------------
# 5b. Delete file (manager+ only) + nullify *_url field
# ---------------------------------------------------------------------------
def _nullify_url_for_scope(db: Session, scope: str, expected_url: str) -> Optional[str]:
    """Match scope -> entity, nullify *_url field nếu hiện tại = expected_url.

    Trả về resource id đã update (string) hoặc None nếu không khớp entity nào.
    """
    # chi_phi_<int>  -> ChiPhiPhatSinh.hoa_don_url
    if scope.startswith("chi_phi_"):
        try:
            rid = int(scope.removeprefix("chi_phi_"))
        except ValueError:
            return None
        obj = db.get(ChiPhiPhatSinh, rid)
        if obj and obj.hoa_don_url == expected_url:
            obj.hoa_don_url = None
            db.commit()
        return f"chi_phi:{rid}" if obj else None

    # doanh_thu_<int> -> DoanhThu.chung_tu_url
    if scope.startswith("doanh_thu_"):
        try:
            rid = int(scope.removeprefix("doanh_thu_"))
        except ValueError:
            return None
        obj = db.get(DoanhThu, rid)
        if obj and obj.chung_tu_url == expected_url:
            obj.chung_tu_url = None
            db.commit()
        return f"doanh_thu:{rid}" if obj else None

    # cong_no_<str> -> CongNo.chung_tu_url
    if scope.startswith("cong_no_"):
        rid = scope.removeprefix("cong_no_")
        obj = db.get(CongNo, rid)
        if obj and obj.chung_tu_url == expected_url:
            obj.chung_tu_url = None
            db.commit()
        return f"cong_no:{rid}" if obj else None

    # so_quy_<int> -> SoQuy.chung_tu_url
    if scope.startswith("so_quy_"):
        try:
            rid = int(scope.removeprefix("so_quy_"))
        except ValueError:
            return None
        obj = db.get(SoQuy, rid)
        if obj and obj.chung_tu_url == expected_url:
            obj.chung_tu_url = None
            db.commit()
        return f"so_quy:{rid}" if obj else None

    # product_<int> -> Product.hinh_anh
    if scope.startswith("product_"):
        try:
            rid = int(scope.removeprefix("product_"))
        except ValueError:
            return None
        obj = db.get(Product, rid)
        if obj and obj.hinh_anh == expected_url:
            obj.hinh_anh = None
            db.commit()
        return f"product:{rid}" if obj else None

    return None


@router.delete("/api/uploads/{scope}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    scope: str,
    filename: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    """Xóa file vật lý + nullify *_url field tương ứng. Manager+ only."""
    if user.role not in _MANAGER_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Role {user.role!r} không có quyền xóa upload",
        )

    p = resolve_path(_APP, scope, filename)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File không tồn tại")

    expected_url = f"/api/uploads/{scope}/{filename}"
    resource = _nullify_url_for_scope(db, scope, expected_url) or f"upload:{scope}/{filename}"

    ok = delete_file(_APP, scope, filename)
    if not ok:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Xóa file thất bại")

    log_action(
        db, app=_APP, action="delete_upload", user=user, request=request,
        resource=resource,
        payload={"scope": scope, "filename": filename, "url": expected_url},
    )
