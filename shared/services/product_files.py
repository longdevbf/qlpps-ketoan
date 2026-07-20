"""Shared route serve ảnh sản phẩm cho mọi app.

Ảnh được upload qua `POST /api/products/{pid}/upload-image` của Kế Toán và
lưu tại `{UPLOAD_DIR}/ketoan/product_{pid}/<uuid>.<ext>`. URL trả về sang FE
là `/api/files/products/{pid}/{filename}`.

Mỗi app (ketoan/marketing/saleadmin/muahang/baogia) mount router này để FE
của app đó tải được ảnh:

    from shared.services.product_files import router as product_files_router
    app.include_router(product_files_router, tags=["product_files"])

Auth: yêu cầu JWT (login bất kỳ app nào đều OK), không kiểm tra role/app cụ thể.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from shared.auth import JWTPayload, current_user
from shared.utils.uploads import resolve_path


router = APIRouter()


@router.get("/api/files/products/{pid}/{filename}")
def serve_product_image(
    pid: int,
    filename: str,
    user: Annotated[JWTPayload, Depends(current_user)],
):
    """Serve ảnh master Sản Phẩm. File vật lý lưu tại Kế Toán scope product_<pid>."""
    p = resolve_path("ketoan", f"product_{pid}", filename)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ảnh không tồn tại")
    return FileResponse(str(p), filename=filename)
