"""Local file upload helpers — dùng chung cho 6 app V2.

Layout:
    /var/lib/qlpps/uploads/{app}/{scope}/<uuid>.<ext>

Trong đó:
    - app: tên app (baogia/marketing/muahang/hcns/ketoan/saleadmin)
    - scope: tên thư mục con tự đặt (vd: 'lead_id', 'cmt_<id>', 'po_<id>', 'hoso_NV001', 'hoa_don_2026-04')

URL trả về dùng pattern `/api/uploads/{scope}/{filename}` — mỗi app tự mount route serve.

Override base path qua env `UPLOAD_DIR` (default `/var/lib/qlpps/uploads`).
"""
from __future__ import annotations

import mimetypes
import os
import uuid
from pathlib import Path
from typing import Final, Optional

from fastapi import HTTPException, UploadFile, status


# 20 MB (đủ cho ảnh hồ sơ + hợp đồng PDF; image upload tự dùng 10MB)
MAX_UPLOAD_BYTES: Final[int] = 20 * 1024 * 1024
MAX_IMAGE_BYTES: Final[int] = 10 * 1024 * 1024

ALLOWED_IMAGE_TYPES: Final[set[str]] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
}

ALLOWED_DOC_TYPES: Final[set[str]] = ALLOWED_IMAGE_TYPES | {
    "application/pdf",
    "application/x-pdf",          # PDF variant một số tool tạo ra
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/csv",
}

_EXT_BY_CT: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "application/pdf": "pdf",
    "application/x-pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/csv": "csv",
    "application/csv": "csv",
}

# Extension → MIME type chuẩn để fallback khi browser gửi application/octet-stream
# (xảy ra khi Foxit PDF Reader / một số tool trên Windows ghi đè Windows Registry)
_EXT_TO_CT: Final[dict[str, str]] = {
    ".pdf":  "application/pdf",
    ".doc":  "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls":  "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv":  "text/csv",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
}


def _resolve_content_type(file: UploadFile) -> str:
    """Trả MIME type thực tế của file.

    Foxit PDF Reader (và một số app Windows khác) ghi đè registry khiến browser
    gửi 'application/octet-stream' thay vì 'application/pdf'. Khi gặp trường hợp
    này, đoán lại từ extension của filename — đủ an toàn vì backend vẫn
    validate extension trước khi lưu.
    """
    ct = (file.content_type or "").strip().lower()
    if ct and ct != "application/octet-stream":
        return ct
    # Fallback: đoán từ extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext in _EXT_TO_CT:
            return _EXT_TO_CT[ext]
        # Thử mimetypes stdlib làm lớp cuối
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            return guessed
    return ct or "application/octet-stream"


def _base_dir() -> Path:
    """Root upload dir cho mọi app. Đọc từ pydantic settings (load .env), fallback env, fallback default."""
    try:
        from shared.config import settings
        path = settings.upload_dir
    except Exception:
        path = os.getenv("UPLOAD_DIR", "/var/lib/qlpps/uploads")
    return Path(path).expanduser().resolve()


def _app_dir(app: str) -> Path:
    """Sub-dir per app."""
    if "/" in app or "\\" in app or app.startswith("."):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid app name: {app}")
    return _base_dir() / app


def _scope_dir(app: str, scope: str) -> Path:
    if "/" in scope or "\\" in scope or scope.startswith(".") or not scope.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid scope: {scope}")
    d = _app_dir(app) / scope
    d.mkdir(parents=True, exist_ok=True)
    return d


async def save_upload(
    file: UploadFile,
    app: str,
    scope: str,
    *,
    allow_docs: bool = False,
    max_bytes: Optional[int] = None,
) -> tuple[str, str, int]:
    """Validate + lưu file. Trả `(filename, relative_url, size_bytes)`.

    `relative_url` dạng `/api/uploads/{scope}/{filename}` — caller tự prefix
    nếu cần absolute URL. App mount route GET serve nội dung qua `resolve_path`.

    Args:
        allow_docs: True cho phép PDF/Word/Excel; False chỉ image.
        max_bytes: override limit (default 10MB image / 20MB doc).
    """
    allowed = ALLOWED_DOC_TYPES if allow_docs else ALLOWED_IMAGE_TYPES
    limit = max_bytes or (MAX_UPLOAD_BYTES if allow_docs else MAX_IMAGE_BYTES)

    content_type = _resolve_content_type(file)

    if content_type not in allowed:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Định dạng không hỗ trợ: {content_type}. "
            f"Chấp nhận: PDF, Word, Excel, CSV, ảnh (JPG/PNG/WebP/GIF)",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "File rỗng")
    if len(content) > limit:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File quá lớn ({len(content) // 1024 // 1024}MB), tối đa {limit // 1024 // 1024}MB",
        )

    ext = _EXT_BY_CT.get(content_type, "bin")
    fname = f"{uuid.uuid4().hex}.{ext}"
    save_path = _scope_dir(app, scope) / fname
    with open(save_path, "wb") as f:
        f.write(content)

    url = f"/api/uploads/{scope}/{fname}"
    return fname, url, len(content)


def resolve_path(app: str, scope: str, filename: str) -> Optional[Path]:
    """Trả Path nếu file tồn tại + nằm dưới base_dir (chống path traversal)."""
    if not filename or "/" in filename or "\\" in filename or filename.startswith("."):
        return None
    if not scope or "/" in scope or "\\" in scope or scope.startswith("."):
        return None
    try:
        p = (_app_dir(app) / scope / filename).resolve()
        base = _app_dir(app).resolve()
        p.relative_to(base)
    except (ValueError, HTTPException):
        return None
    if not p.exists() or not p.is_file():
        return None
    return p


# Tài liệu buổi đào tạo: một bảng dùng chung, nhưng tệp nằm ở thư mục của app đã tải lên —
# cả 5 app này đều có route `POST /api/dao-tao/sessions/{sid}/upload`.
DAO_TAO_APPS = ("baogia", "ketoan", "marketing", "muahang", "saleadmin")


def tim_tep_theo_app(
    app: str,
    scope: str,
    filename: str,
    app_khac: tuple[str, ...] = (),
) -> Optional[Path]:
    """Tìm tệp trong thư mục CỦA APP MÌNH trước, rồi chỉ trong những app KHAI TƯỜNG MINH.

    Dùng thay `resolve_path_cross_app` ở mọi endpoint nhận `scope` thẳng từ URL:

        p = tim_tep_theo_app("marketing", scope, filename,
                             app_khac=DAO_TAO_APPS if scope.startswith("dao_tao_") else ())

    Vì sao cần (12/09/2026): quét mù cả 7 thư mục app khiến `GET /api/uploads/hoso_<ma_nv>/
    <tệp>` ở marketing và baogia trả về hồ sơ nhân sự của app HCNS — đã khai thác thật ở dev
    bằng tài khoản nhân viên thường, lấy được cả tệp phòng chat và chứng từ Mua Hàng.
    Hàm này KHÔNG kiểm chủ sở hữu: endpoint vẫn phải tự hỏi "người gọi có quyền với bản ghi
    gắn scope này không" (mẫu đúng: qlpps-hcns/app/routers/uploads.py:346-372).
    """
    p = resolve_path(app, scope, filename)
    if p is not None:
        return p
    for khac in app_khac:
        if khac == app:
            continue
        p = resolve_path(khac, scope, filename)
        if p is not None:
            return p
    return None


def resolve_path_cross_app(scope: str, filename: str, prefer: str = "") -> Optional[Path]:
    """Tìm file trong tất cả app dirs (cross-app fallback).

    Dùng khi file có thể nằm ở app khác (vd: dao_tao upload từ marketing, đọc từ ketoan).
    prefer = app ưu tiên tìm trước, sau đó mới scan các app còn lại.

    CẢNH BÁO: KHÔNG gọi hàm này với `scope` lấy thẳng từ URL — nó đọc được thư mục của mọi
    app, đó chính là lỗ đã khai thác được ngày 12/09/2026. Endpoint kiểu đó dùng
    `tim_tep_theo_app` ở trên và khai rõ app được phép.
    """
    _APPS = ["marketing", "ketoan", "baogia", "muahang", "hcns", "saleadmin", "ceo"]
    order = [prefer] + [a for a in _APPS if a != prefer] if prefer else _APPS
    for app in order:
        p = resolve_path(app, scope, filename)
        if p is not None:
            return p
    return None


def delete_file(app: str, scope: str, filename: str) -> bool:
    """Xóa file vật lý. True nếu xóa OK, False nếu không tìm thấy."""
    p = resolve_path(app, scope, filename)
    if p is None:
        return False
    try:
        p.unlink()
        return True
    except OSError:
        return False


def list_scope(app: str, scope: str) -> list[dict]:
    """List file trong scope. Trả `[{filename, url, size, mtime}]`."""
    try:
        d = _app_dir(app) / scope
    except HTTPException:
        return []
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            stat = p.stat()
            out.append({
                "filename": p.name,
                "url": f"/api/uploads/{scope}/{p.name}",
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            })
    return out
