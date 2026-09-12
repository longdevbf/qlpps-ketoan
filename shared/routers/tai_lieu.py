"""Tài liệu / Văn bản công ty — router DÙNG CHUNG cho cả 8 app (12/09/2026).

Vì sao có router này: văn bản công ty nằm ở `hcns.documents`, nhưng API đọc nó
(`/api/documents` của HCNS) nằm sau `require_app("hcns")` nên 7 app kia gọi là 403.
Trước đây họ phải đi vòng qua `/api/dao-tao/van-ban-cong-ty` — một tab chỉ-đọc nằm nhờ
trong màn Đào tạo. Router này cho cả 8 app cùng một cửa, kèm những thứ màn mới cần mà
bảng gốc không có: danh mục chuẩn, cơ quan ban hành, cờ nổi bật, lượt xem, lượt tải.

Ranh giới đã giữ:
  · `hcns.documents` CHỈ ĐỌC (schema của app khác) — thêm/sửa/xoá văn bản vẫn phải qua
    `POST /api/documents` của HCNS. Màn ẩn nút "Tải lên" ở 7 app còn lại.
  · Phần bổ sung ghi vào `shared.tai_lieu_meta` / `shared.tai_lieu_luot` (bảng mới).
  · Lọc theo `ap_dung_phong_ban` áp cho CẢ đường tải tệp — trước đây tệp văn bản ai có
    app hcns cũng tải được, kể cả văn bản chỉ áp dụng cho phòng khác (uploads.py:366).
"""
from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.db import get_db
from shared.models.tai_lieu import TaiLieuLuot, TaiLieuMeta
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)

# Người xem được MỌI văn bản, không bị lọc theo phòng ban áp dụng.
_MANAGER_ROLES = {"admin", "ceo", "assistant_ceo", "manager", "hr_manager"}
# Người được sửa phần bổ sung (danh mục, cơ quan ban hành, cờ nổi bật).
_SUA_ROLES = _MANAGER_ROLES | {"leader"}

# 7 danh mục theo ảnh mẫu 12/09/2026. Bảng gốc để `loai` là chữ tự do (dev đang có
# "Quyết định", "Quy định"), nên màn không thể lọc theo `loai` thô — suy về danh mục chuẩn.
DANH_MUC = [
    "Quyết định của công ty",
    "Quy chế - Nội quy",
    "Chính sách nhân sự",
    "Luật - Nghị định - Thông tư",
    "Quy trình - Hướng dẫn",
    "Biểu mẫu",
    "Tài liệu khác",
]


def _bo_dau(s: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp loại văn bản gõ tay kiểu 'Quyet dinh' lẫn 'Quyết định'."""
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower())
                   if unicodedata.category(c) != "Mn").replace("đ", "d")


def _suy_danh_muc(loai: Optional[str]) -> str:
    l = _bo_dau(loai)
    if "quyet dinh" in l:
        return DANH_MUC[0]
    if "quy che" in l or "noi quy" in l or "quy dinh" in l:
        return DANH_MUC[1]
    if "chinh sach" in l or "nhan su" in l:
        return DANH_MUC[2]
    if "luat" in l or "nghi dinh" in l or "thong tu" in l or "van ban phap" in l:
        return DANH_MUC[3]
    if "quy trinh" in l or "huong dan" in l or "sop" in l:
        return DANH_MUC[4]
    if "bieu mau" in l or "mau" in l or "form" in l:
        return DANH_MUC[5]
    return DANH_MUC[6]


def _phong_ban_cua(username: str) -> Optional[str]:
    try:
        _, pb, _, _, _ = _lookup_user_info(username)
        return pb or None
    except Exception:
        return None


def _xem_het(user: JWTPayload) -> bool:
    return (user.role or "").lower() in _MANAGER_ROLES


def _loc_phong_ban(rows: list[dict], user: JWTPayload) -> list[dict]:
    """Giữ đúng luật của HCNS: rỗng = toàn công ty, có giá trị = chỉ phòng đó."""
    if _xem_het(user):
        return rows
    pb = _phong_ban_cua(user.username)
    ra = []
    for r in rows:
        ds = r.get("ap_dung_phong_ban") or []
        if not ds or (pb and pb in ds):
            ra.append(r)
    return ra


def _doc_tat_ca(db: Session) -> list[dict]:
    """Toàn bộ văn bản (bảng chỉ vài trăm dòng nên đọc hết rồi lọc trong bộ nhớ là đủ).

    Fail-soft: app chạy trên DB không có schema hcns → trả rỗng, màn hiện "chưa có".
    """
    try:
        rows = db.execute(sql_text("""
            SELECT id, loai, tieu_de, noi_dung, file_url, so_hieu, ngay_ban_hanh,
                   ap_dung_phong_ban, created_by, created_at
            FROM hcns.documents ORDER BY ngay_ban_hanh DESC NULLS LAST, created_at DESC
        """)).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        db.rollback()
        return []


def _dinh_dang(file_url: Optional[str]) -> str:
    ten = (file_url or "").split("?")[0].rstrip("/").split("/")[-1]
    duoi = ten.rsplit(".", 1)[-1].lower() if "." in ten else ""
    return {"pdf": "pdf", "doc": "word", "docx": "word", "xls": "excel", "xlsx": "excel",
            "ppt": "ppt", "pptx": "ppt", "png": "anh", "jpg": "anh", "jpeg": "anh"}.get(duoi, "khac")


def _gop(db: Session, rows: list[dict]) -> list[dict]:
    """Gắn phần bổ sung + số đếm cho từng văn bản bằng 2 truy vấn, không phải 2×N."""
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    meta = {m.doc_id: m for m in db.execute(
        sql_text("SELECT * FROM shared.tai_lieu_meta WHERE doc_id = ANY(:ids)"), {"ids": ids}
    ).mappings().all()} if ids else {}
    dem = {}
    for r in db.execute(sql_text("""
        SELECT doc_id, hanh_dong, COUNT(*) AS n FROM shared.tai_lieu_luot
        WHERE doc_id = ANY(:ids) GROUP BY doc_id, hanh_dong
    """), {"ids": ids}).mappings().all():
        dem.setdefault(r["doc_id"], {})[r["hanh_dong"]] = r["n"]
    ra = []
    for r in rows:
        m = meta.get(r["id"]) or {}
        d = dem.get(r["id"], {})
        ra.append({
            "id": r["id"],
            "ten": r["tieu_de"],
            "so_hieu": r["so_hieu"] or "",
            "loai": r["loai"],
            "danh_muc": (m.get("danh_muc") if m else None) or _suy_danh_muc(r["loai"]),
            "ngay_ban_hanh": r["ngay_ban_hanh"],
            "co_quan_ban_hanh": (m.get("co_quan_ban_hanh") if m else None) or "",
            "nguoi_tao": r["created_by"] or "",
            "ap_dung_phong_ban": r["ap_dung_phong_ban"] or [],
            "file_url": r["file_url"] or "",
            "dinh_dang": _dinh_dang(r["file_url"]),
            "mo_ta": r["noi_dung"] or "",
            "noi_bat": bool(m.get("noi_bat")) if m else False,
            "luot_xem": d.get("xem", 0),
            "luot_tai": d.get("tai", 0),
            "created_at": r["created_at"],
        })
    return ra


def _thay_duoc(db: Session, user: JWTPayload, doc_id: int) -> dict:
    """Trả về văn bản nếu người gọi được xem, ngược lại 403/404."""
    rows = [r for r in _doc_tat_ca(db) if r["id"] == doc_id]
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy văn bản")
    if not _loc_phong_ban(rows, user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Văn bản này không áp dụng cho phòng ban của bạn")
    return rows[0]


def _ghi_luot(db: Session, doc_id: int, username: str, hanh_dong: str) -> None:
    """Fail-soft: ghi nhận lượt hỏng thì vẫn phải mở/tải được tệp."""
    try:
        db.add(TaiLieuLuot(doc_id=doc_id, username=username, hanh_dong=hanh_dong))
        db.commit()
    except Exception:
        db.rollback()


# ── Đọc ───────────────────────────────────────────────────────────────────────
@router.get("")
def danh_sach(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    q: Optional[str] = None,
    danh_muc: Optional[str] = None,
    phong_ban: Optional[str] = None,
    sap_xep: str = Query("moi_nhat", description="moi_nhat|cu_nhat|xem_nhieu|ten"),
    trang: int = Query(1, ge=1),
    so_dong: int = Query(10, ge=1, le=100),
):
    """Danh sách văn bản + số đếm theo danh mục + thống kê chung (một lượt gọi cho cả màn)."""
    ds = _gop(db, _loc_phong_ban(_doc_tat_ca(db), user))

    dem_dm = {ten: 0 for ten in DANH_MUC}
    for r in ds:
        dem_dm[r["danh_muc"]] = dem_dm.get(r["danh_muc"], 0) + 1

    loc = ds
    if danh_muc:
        loc = [r for r in loc if r["danh_muc"] == danh_muc]
    if phong_ban:
        loc = [r for r in loc if phong_ban in (r["ap_dung_phong_ban"] or [])]
    if q:
        k = _bo_dau(q)
        loc = [r for r in loc
               if k in _bo_dau(r["ten"]) or k in _bo_dau(r["so_hieu"]) or k in _bo_dau(r["mo_ta"])]

    if sap_xep == "cu_nhat":
        loc.sort(key=lambda r: (r["ngay_ban_hanh"] or r["created_at"].date()))
    elif sap_xep == "xem_nhieu":
        loc.sort(key=lambda r: r["luot_xem"], reverse=True)
    elif sap_xep == "ten":
        loc.sort(key=lambda r: _bo_dau(r["ten"]))
    # moi_nhat = giữ nguyên thứ tự SQL (ngày ban hành mới trước)

    tong = len(loc)
    dau = (trang - 1) * so_dong
    return {
        "total": tong,
        "items": loc[dau:dau + so_dong],
        "danh_muc": [{"ten": t, "so": dem_dm.get(t, 0)} for t in DANH_MUC],
        "thong_ke": _thong_ke_dict(db, ds),
        "co_tai_len": (user.role or "").lower() in _SUA_ROLES,
    }


def _thong_ke_dict(db: Session, ds: list[dict]) -> dict:
    """Tổng tài liệu (theo quyền của người gọi) + lượt xem/tải + số người đã truy cập."""
    try:
        r = db.execute(sql_text("""
            SELECT COUNT(*) FILTER (WHERE hanh_dong = 'xem')  AS xem,
                   COUNT(*) FILTER (WHERE hanh_dong = 'tai')  AS tai,
                   COUNT(DISTINCT username)                    AS nguoi
            FROM shared.tai_lieu_luot
        """)).mappings().first() or {}
    except Exception:
        db.rollback()
        r = {}
    return {
        "tong_tai_lieu": len(ds),
        "luot_xem": int(r.get("xem") or 0),
        "luot_tai": int(r.get("tai") or 0),
        "nguoi_truy_cap": int(r.get("nguoi") or 0),
    }


@router.get("/noi-bat")
def noi_bat(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(5, ge=1, le=20),
):
    """Văn bản nổi bật: ưu tiên cờ `noi_bat`, thiếu thì lấy văn bản được xem nhiều nhất."""
    ds = _gop(db, _loc_phong_ban(_doc_tat_ca(db), user))
    danh_dau = [r for r in ds if r["noi_bat"]]
    if len(danh_dau) < limit:
        con_lai = sorted([r for r in ds if not r["noi_bat"]],
                         key=lambda r: (r["luot_xem"], r["luot_tai"]), reverse=True)
        danh_dau += con_lai[:limit - len(danh_dau)]
    return {"items": danh_dau[:limit], "tu_dong": not any(r["noi_bat"] for r in ds)}


@router.get("/moi-cap-nhat")
def moi_cap_nhat(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(5, ge=1, le=20),
):
    ds = _gop(db, _loc_phong_ban(_doc_tat_ca(db), user))
    ds.sort(key=lambda r: r["created_at"], reverse=True)
    return {"items": ds[:limit]}


@router.get("/{doc_id}")
def xem_mot(
    doc_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    r = _thay_duoc(db, user, doc_id)
    _ghi_luot(db, doc_id, user.username, "xem")
    return _gop(db, [r])[0]


@router.get("/{doc_id}/tai")
def tai_ve(
    doc_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Tải tệp văn bản — CÓ kiểm phòng ban áp dụng, khác đường `/api/uploads` của HCNS.

    Đường cũ (`hcns/app/routers/uploads.py:366`) coi scope `document_*` là công khai với
    mọi người có app hcns, nên văn bản chỉ áp dụng cho một phòng vẫn tải được từ phòng
    khác. Ở đây lọc trước rồi mới trả tệp, và ghi lại lượt tải.
    """
    r = _thay_duoc(db, user, doc_id)
    duong = (r.get("file_url") or "").split("?")[0]
    phan = [x for x in duong.split("/") if x]
    if len(phan) < 2:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Văn bản chưa có tệp đính kèm")
    scope, ten_tep = phan[-2], phan[-1]
    from shared.utils.uploads import resolve_path
    p = resolve_path("hcns", scope, ten_tep)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tệp không còn trên máy chủ")
    _ghi_luot(db, doc_id, user.username, "tai")
    return FileResponse(str(p), filename=f"{(r.get('so_hieu') or r.get('tieu_de') or 'van-ban')}{p.suffix}",
                        headers={"X-Content-Type-Options": "nosniff"})


# ── Ghi phần bổ sung ──────────────────────────────────────────────────────────
class MetaIn(BaseModel):
    danh_muc: Optional[str] = None
    co_quan_ban_hanh: Optional[str] = None
    noi_bat: Optional[bool] = None
    ghi_chu: Optional[str] = None


@router.put("/{doc_id}/meta")
def sua_meta(
    doc_id: int,
    body: MetaIn,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Đặt danh mục chuẩn / cơ quan ban hành / cờ nổi bật. Không đụng `hcns.documents`."""
    if (user.role or "").lower() not in _SUA_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ quản lý trở lên sửa được thông tin này")
    if body.danh_muc and body.danh_muc not in DANH_MUC:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Danh mục không hợp lệ: {body.danh_muc}")
    _thay_duoc(db, user, doc_id)
    m = db.execute(
        sql_text("SELECT id FROM shared.tai_lieu_meta WHERE doc_id = :d"), {"d": doc_id}
    ).mappings().first()
    if m:
        rec = db.get(TaiLieuMeta, m["id"])
    else:
        rec = TaiLieuMeta(doc_id=doc_id)
        db.add(rec)
    if body.danh_muc is not None:
        rec.danh_muc = body.danh_muc
    if body.co_quan_ban_hanh is not None:
        rec.co_quan_ban_hanh = body.co_quan_ban_hanh[:128]
    if body.noi_bat is not None:
        rec.noi_bat = bool(body.noi_bat)
    if body.ghi_chu is not None:
        rec.ghi_chu = body.ghi_chu
    db.commit()
    try:
        from shared.audit import log_action
        log_action(db, app="shared", action="tai_lieu_meta", user=user, request=request,
                   resource=f"document:{doc_id}", payload=body.model_dump(exclude_none=True))
    except Exception:
        db.rollback()
    return _gop(db, [_thay_duoc(db, user, doc_id)])[0]
