"""Thư viện đào tạo — router DÙNG CHUNG cho cả 8 app (12/09/2026).

Theo ảnh mẫu người dùng gửi: lưới thẻ nội dung (video / tài liệu / đường dẫn) có chủ đề,
thẻ, ảnh đại diện, người chia sẻ, lượt xem, lượt thích, đánh dấu; kèm modal "Tạo tài liệu
đào tạo" cho tải tệp tới 2GB.

Vì sao KHÔNG dùng `/api/dao-tao` sẵn có: endpoint đó là "buổi đào tạo"
(`marketing.dao_tao_sessions`: tên buổi, ngày, giảng viên, tệp) — nghiệp vụ khác hẳn, và
mỗi app tự khai một bản router riêng đã trôi xa nhau. Màn buổi đào tạo cũ giữ nguyên ở
`/buoi-dao-tao`; thư viện nội dung nằm ở đây, prefix `/api/thu-vien`.

Tệp KHÔNG đi qua `shared.utils.uploads.save_upload`: hàm đó đọc cả tệp vào bộ nhớ
(`content = await file.read()`) và chặn video/PowerPoint, trong khi ảnh mẫu cho tải video
tới 2GB. Ở đây ghi theo từng khối 1MB xuống đĩa, và phục vụ lại bằng endpoint riêng có
kiểm quyền — không mở thư mục ra cho `/api/uploads`.
"""
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text as sql_text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models.dao_tao_nd import DaoTaoNoiDung, DaoTaoTuongTac
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)

_SUPER_ROLES = {"admin", "ceo", "assistant_ceo"}
# Ai được đăng nội dung — giữ đúng nhóm mà màn buổi đào tạo cũ đang dùng (_UPLOAD_ROLES).
_TAO_ROLES = _SUPER_ROLES | {"manager", "leader", "hr_manager"}

LOAI_ND = {"video": "Video", "tai_lieu": "Tài liệu", "link": "Link"}
CHU_DE = ["Quy trình", "Kỹ năng", "Sản phẩm", "Văn hóa công ty", "Hệ thống",
          "Kinh doanh", "Thiết kế", "Sản xuất", "Nhân sự", "An toàn lao động"]
PHAM_VI = {"cong_ty": "Toàn công ty", "phong_ban": "Theo phòng ban"}

_DUOI_OK = {"mp4", "mov", "m4v", "webm", "pdf", "doc", "docx", "ppt", "pptx",
            "xls", "xlsx", "png", "jpg", "jpeg", "webp"}
_DUOI_ANH = {"png", "jpg", "jpeg", "webp"}
_TOI_DA = 2 * 1024 * 1024 * 1024   # 2GB, đúng con số ghi trên ảnh mẫu
_KHOI = 1024 * 1024                # ghi từng 1MB, không nạp cả tệp vào RAM


def _thu_muc(nd_id: int) -> Path:
    goc = Path(getattr(settings, "upload_dir", "/var/lib/qlpps/uploads")).expanduser().resolve()
    d = goc / "dao_tao" / str(nd_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _duoi(ten: Optional[str]) -> str:
    t = (ten or "").rsplit(".", 1)
    return t[-1].lower() if len(t) == 2 else ""


async def _ghi_tep(f: UploadFile, nd_id: int, chi_anh: bool = False) -> tuple[str, int]:
    """Ghi tệp theo từng khối. Trả (đường dẫn tuyệt đối, số byte). Quá cỡ → 413 + dọn tệp dở."""
    duoi = _duoi(f.filename)
    hop_le = _DUOI_ANH if chi_anh else _DUOI_OK
    if duoi not in hop_le:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"Định dạng .{duoi or '?'} không hỗ trợ. Nhận: {', '.join(sorted(hop_le))}")
    dich = _thu_muc(nd_id) / f"{uuid.uuid4().hex}.{duoi}"
    n = 0
    try:
        with open(dich, "wb") as ra:
            while True:
                khoi = await f.read(_KHOI)
                if not khoi:
                    break
                n += len(khoi)
                if n > _TOI_DA:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        "Tệp quá lớn — tối đa 2GB")
                ra.write(khoi)
    except Exception:
        try:
            dich.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    if n == 0:
        dich.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tệp rỗng")
    return str(dich), n


def _phong_ban_cua(username: str) -> Optional[str]:
    try:
        _, pb, _, _, _ = _lookup_user_info(username)
        return pb or None
    except Exception:
        return None


def _xem_duoc(user: JWTPayload, nd: DaoTaoNoiDung, pb_minh: Optional[str]) -> bool:
    if nd.pham_vi != "phong_ban":
        return True
    if (user.role or "").lower() in _SUPER_ROLES:
        return True
    return bool(pb_minh) and (nd.phong_ban or "") == pb_minh


def _dem_tuong_tac(db: Session, ids: list[int], username: str) -> dict:
    """Đếm xem/thích cho từng nội dung + đánh dấu của CHÍNH người đang xem, 2 truy vấn."""
    if not ids:
        return {}
    ra = {i: {"xem": 0, "thich": 0, "da_thich": False, "da_danh_dau": False} for i in ids}
    for r in db.execute(sql_text("""
        SELECT noi_dung_id, hanh_dong, COUNT(*) AS n FROM shared.dao_tao_tuong_tac
        WHERE noi_dung_id = ANY(:ids) GROUP BY noi_dung_id, hanh_dong
    """), {"ids": ids}).mappings().all():
        if r["hanh_dong"] in ("xem", "thich"):
            ra[r["noi_dung_id"]][r["hanh_dong"]] = r["n"]
    for r in db.execute(sql_text("""
        SELECT noi_dung_id, hanh_dong FROM shared.dao_tao_tuong_tac
        WHERE noi_dung_id = ANY(:ids) AND username = :u AND hanh_dong IN ('thich', 'danh_dau')
    """), {"ids": ids, "u": username}).mappings().all():
        ra[r["noi_dung_id"]]["da_" + r["hanh_dong"]] = True
    return ra


def _ra_dict(nd: DaoTaoNoiDung, d: dict) -> dict:
    return {
        "id": nd.id, "tieu_de": nd.tieu_de, "mo_ta": nd.mo_ta or "",
        "loai_nd": nd.loai_nd, "loai_nhan": LOAI_ND.get(nd.loai_nd, nd.loai_nd),
        "chu_de": nd.chu_de or "", "pham_vi": nd.pham_vi, "phong_ban": nd.phong_ban or "",
        "ten_tep": nd.ten_tep or "", "kich_thuoc": nd.kich_thuoc or 0,
        "thoi_luong": nd.thoi_luong or 0, "the": nd.the or [], "lien_quan": nd.lien_quan or [],
        "link_url": nd.link_url or "",
        "co_tep": bool(nd.duong_dan_tep),
        "url_tep": f"/api/thu-vien/{nd.id}/tep" if nd.duong_dan_tep else "",
        "url_anh": f"/api/thu-vien/{nd.id}/anh" if nd.anh_dai_dien else "",
        "nguoi_chia_se": nd.nguoi_chia_se or "", "nguoi_chia_se_ten": nd.nguoi_chia_se_ten or nd.created_by or "",
        "created_by": nd.created_by or "", "created_at": nd.created_at,
        "luot_xem": d.get("xem", 0), "luot_thich": d.get("thich", 0),
        "da_thich": d.get("da_thich", False), "da_danh_dau": d.get("da_danh_dau", False),
    }


# ── Đọc ───────────────────────────────────────────────────────────────────────
@router.get("/meta")
def meta(user: Annotated[JWTPayload, _AUTH]):
    """Nguồn cho các ô chọn trong modal + quyền tạo (màn ẩn nút nếu không có quyền)."""
    return {
        "loai_nd": [{"ma": k, "ten": v} for k, v in LOAI_ND.items()],
        "chu_de": CHU_DE,
        "pham_vi": [{"ma": k, "ten": v} for k, v in PHAM_VI.items()],
        "toi_da_mb": _TOI_DA // (1024 * 1024),
        "duoi_ho_tro": sorted(_DUOI_OK),
        "duoc_tao": (user.role or "").lower() in _TAO_ROLES,
    }


@router.get("")
def danh_sach(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    q: Optional[str] = None,
    chu_de: Optional[str] = None,
    loai_nd: Optional[str] = None,
    pham_vi: Optional[str] = None,
    phong_ban: Optional[str] = None,
    the: Optional[str] = None,
    danh_dau: bool = False,
    sap_xep: str = Query("moi_nhat", description="moi_nhat|xem_nhieu|thich_nhieu|ten"),
    trang: int = Query(1, ge=1),
    so_dong: int = Query(12, ge=1, le=60),
):
    pb_minh = _phong_ban_cua(user.username)
    rows = db.execute(select(DaoTaoNoiDung).order_by(DaoTaoNoiDung.id.desc())).scalars().all()
    rows = [r for r in rows if _xem_duoc(user, r, pb_minh)]

    dem = _dem_tuong_tac(db, [r.id for r in rows], user.username)
    ds = [_ra_dict(r, dem.get(r.id, {})) for r in rows]

    # Chủ đề phổ biến + người chia sẻ nổi bật tính trên TOÀN BỘ phần người này xem được,
    # không theo bộ lọc — nếu không thì bấm lọc xong hai khối đó rỗng, trông như hỏng.
    dem_cd, dem_ng = {}, {}
    for r in ds:
        if r["chu_de"]:
            dem_cd[r["chu_de"]] = dem_cd.get(r["chu_de"], 0) + 1
        k = r["nguoi_chia_se"] or r["created_by"]
        if k:
            dem_ng.setdefault(k, {"username": k, "ten": r["nguoi_chia_se_ten"], "so": 0})["so"] += 1

    if chu_de:
        ds = [r for r in ds if r["chu_de"] == chu_de]
    if loai_nd:
        ds = [r for r in ds if r["loai_nd"] == loai_nd]
    if pham_vi:
        ds = [r for r in ds if r["pham_vi"] == pham_vi]
    if phong_ban:
        ds = [r for r in ds if r["phong_ban"] == phong_ban]
    if the:
        ds = [r for r in ds if the in (r["the"] or [])]
    if danh_dau:
        ds = [r for r in ds if r["da_danh_dau"]]
    if q:
        k = q.strip().lower()
        ds = [r for r in ds
              if k in r["tieu_de"].lower() or k in r["mo_ta"].lower()
              or k in (r["nguoi_chia_se_ten"] or "").lower()
              or any(k in str(t).lower() for t in (r["the"] or []))]

    if sap_xep == "xem_nhieu":
        ds.sort(key=lambda r: r["luot_xem"], reverse=True)
    elif sap_xep == "thich_nhieu":
        ds.sort(key=lambda r: r["luot_thich"], reverse=True)
    elif sap_xep == "ten":
        ds.sort(key=lambda r: r["tieu_de"].lower())

    tong = len(ds)
    dau = (trang - 1) * so_dong
    ds_ng = sorted(dem_ng.values(), key=lambda x: x["so"], reverse=True)[:5]
    for n in ds_ng:
        try:
            # Thứ tự trả về: (ho_ten, phong_ban, email, chuc_vu, phong_ban_phu) —
            # lấy nhầm phần tử thứ 3 là in email lên màn (thấy trên ảnh thật 12/09/2026).
            _, _, _, cv, _ = _lookup_user_info(n["username"])
            n["chuc_vu"] = cv or ""
        except Exception:
            n["chuc_vu"] = ""
    return {
        "total": tong,
        "items": ds[dau:dau + so_dong],
        "chu_de_pho_bien": sorted(
            [{"ten": t, "so": s} for t, s in dem_cd.items()], key=lambda x: x["so"], reverse=True),
        "nguoi_chia_se": ds_ng,
        "duoc_tao": (user.role or "").lower() in _TAO_ROLES,
    }


@router.get("/{nd_id}")
def xem_mot(
    nd_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    nd = db.get(DaoTaoNoiDung, nd_id)
    if not nd:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nội dung")
    if not _xem_duoc(user, nd, _phong_ban_cua(user.username)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nội dung này chỉ dành cho phòng ban khác")
    return _ra_dict(nd, _dem_tuong_tac(db, [nd.id], user.username).get(nd.id, {}))


def _lay_hoac_403(db: Session, user: JWTPayload, nd_id: int) -> DaoTaoNoiDung:
    nd = db.get(DaoTaoNoiDung, nd_id)
    if not nd:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nội dung")
    if not _xem_duoc(user, nd, _phong_ban_cua(user.username)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Nội dung này chỉ dành cho phòng ban khác")
    return nd


@router.get("/{nd_id}/tep")
def tai_tep(
    nd_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Phục vụ tệp nội dung. Thư mục `dao_tao/` KHÔNG mở qua `/api/uploads` của app nào —
    chỉ đường này, và đường này có kiểm phạm vi hiển thị."""
    nd = _lay_hoac_403(db, user, nd_id)
    if not nd.duong_dan_tep or not os.path.isfile(nd.duong_dan_tep):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nội dung này không có tệp")
    return FileResponse(nd.duong_dan_tep, filename=nd.ten_tep or Path(nd.duong_dan_tep).name,
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})


@router.get("/{nd_id}/anh")
def tai_anh(
    nd_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    nd = _lay_hoac_403(db, user, nd_id)
    if not nd.anh_dai_dien or not os.path.isfile(nd.anh_dai_dien):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có ảnh đại diện")
    return FileResponse(nd.anh_dai_dien, headers={"X-Content-Type-Options": "nosniff",
                                                  "Cache-Control": "private, max-age=86400"})


# ── Tương tác ─────────────────────────────────────────────────────────────────
@router.post("/{nd_id}/xem")
def ghi_xem(
    nd_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    _lay_hoac_403(db, user, nd_id)
    db.add(DaoTaoTuongTac(noi_dung_id=nd_id, username=user.username, hanh_dong="xem"))
    db.commit()
    return {"ok": True}


def _bat_tat(db: Session, user: JWTPayload, nd_id: int, hanh_dong: str) -> dict:
    """Thích / đánh dấu là BẬT-TẮT: có dòng thì xoá, chưa có thì thêm."""
    cu = db.execute(select(DaoTaoTuongTac).where(
        DaoTaoTuongTac.noi_dung_id == nd_id,
        DaoTaoTuongTac.username == user.username,
        DaoTaoTuongTac.hanh_dong == hanh_dong,
    )).scalars().first()
    if cu:
        db.delete(cu)
        db.commit()
        return {"bat": False}
    db.add(DaoTaoTuongTac(noi_dung_id=nd_id, username=user.username, hanh_dong=hanh_dong))
    db.commit()
    return {"bat": True}


@router.post("/{nd_id}/thich")
def thich(nd_id: int, user: Annotated[JWTPayload, _AUTH], db: Annotated[Session, Depends(get_db)]):
    _lay_hoac_403(db, user, nd_id)
    return _bat_tat(db, user, nd_id, "thich")


@router.post("/{nd_id}/danh-dau")
def danh_dau(nd_id: int, user: Annotated[JWTPayload, _AUTH], db: Annotated[Session, Depends(get_db)]):
    _lay_hoac_403(db, user, nd_id)
    return _bat_tat(db, user, nd_id, "danh_dau")


# ── Tạo / xoá ─────────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED)
async def tao_noi_dung(
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    tieu_de: str = Form(...),
    mo_ta: str = Form(""),
    loai_nd: str = Form(...),
    chu_de: str = Form(""),
    pham_vi: str = Form("cong_ty"),
    phong_ban: str = Form(""),
    link_url: str = Form(""),
    the: str = Form(""),                 # các thẻ, ngăn bởi dấu phẩy
    lien_quan: str = Form(""),           # id nội dung liên quan, ngăn bởi dấu phẩy
    nguoi_chia_se: str = Form(""),
    thoi_luong: int = Form(0),
    gui_thong_bao: bool = Form(False),
    tep: Optional[UploadFile] = File(None),
    anh: Optional[UploadFile] = File(None),
):
    """Tạo một nội dung trong thư viện. Tệp ghi theo khối nên video lớn không nổ bộ nhớ."""
    if (user.role or "").lower() not in _TAO_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Chỉ trưởng nhóm trở lên mới đăng nội dung đào tạo")
    if loai_nd not in LOAI_ND:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Loại nội dung không hợp lệ: {loai_nd}")
    if pham_vi not in PHAM_VI:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Phạm vi không hợp lệ: {pham_vi}")
    if not tieu_de.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tiêu đề không được để trống")
    if loai_nd == "link":
        if not re.match(r"^https?://", link_url.strip()):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Loại Link cần một đường dẫn bắt đầu bằng http:// hoặc https://")
    elif tep is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chọn tệp để tải lên")
    if pham_vi == "phong_ban" and not phong_ban.strip():
        phong_ban = _phong_ban_cua(user.username) or ""
        if not phong_ban:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Không xác định được phòng ban — chọn phạm vi Toàn công ty")

    ten_nguoi = ""
    if nguoi_chia_se.strip():
        try:
            ten_nguoi, _, _, _, _ = _lookup_user_info(nguoi_chia_se.strip())
        except Exception:
            ten_nguoi = ""
    else:
        nguoi_chia_se = user.username
        try:
            ten_nguoi, _, _, _, _ = _lookup_user_info(user.username)
        except Exception:
            ten_nguoi = user.username

    nd = DaoTaoNoiDung(
        tieu_de=tieu_de.strip()[:255], mo_ta=mo_ta.strip() or None, loai_nd=loai_nd,
        chu_de=(chu_de.strip() or None), pham_vi=pham_vi,
        phong_ban=(phong_ban.strip() or None) if pham_vi == "phong_ban" else None,
        link_url=link_url.strip() or None,
        the=[t.strip() for t in the.split(",") if t.strip()][:12],
        lien_quan=[int(x) for x in re.findall(r"\d+", lien_quan)][:12],
        thoi_luong=int(thoi_luong or 0) or None,
        nguoi_chia_se=nguoi_chia_se.strip() or user.username,
        nguoi_chia_se_ten=ten_nguoi or nguoi_chia_se or user.username,
        created_by=user.username,
    )
    db.add(nd)
    db.flush()          # cần id để đặt tên thư mục tệp

    if tep is not None and loai_nd != "link":
        duong, co = await _ghi_tep(tep, nd.id)
        nd.duong_dan_tep, nd.ten_tep, nd.kich_thuoc = duong, (tep.filename or "")[:255], co
    if anh is not None:
        duong_anh, _ = await _ghi_tep(anh, nd.id, chi_anh=True)
        nd.anh_dai_dien = duong_anh
    db.commit()
    db.refresh(nd)

    if gui_thong_bao:
        _bao_nhan_vien(db, nd, boi=user.username)
    try:
        from shared.audit import log_action
        log_action(db, app="shared", action="tao_noi_dung_dao_tao", user=user, request=request,
                   resource=f"dao_tao_noi_dung:{nd.id}",
                   payload={"loai": nd.loai_nd, "pham_vi": nd.pham_vi, "kich_thuoc": nd.kich_thuoc})
    except Exception:
        db.rollback()
    return _ra_dict(nd, {})


def _bao_nhan_vien(db: Session, nd: DaoTaoNoiDung, *, boi: str) -> None:
    """Báo cho người trong phạm vi hiển thị. Fail-soft và CHẶN TRẦN 200 người —
    nội dung toàn công ty mà bắn cho tất cả thì hộp thư ai cũng ngập."""
    try:
        from shared.services.notify import notify_many
        if nd.pham_vi == "phong_ban" and nd.phong_ban:
            rows = db.execute(sql_text("""
                SELECT username FROM hcns.employees
                WHERE phong_ban = :pb AND username IS NOT NULL AND username <> ''
                  AND (trang_thai IS NULL OR trang_thai <> 'Nghỉ việc') LIMIT 200
            """), {"pb": nd.phong_ban}).scalars().all()
        else:
            rows = db.execute(sql_text("""
                SELECT username FROM shared.users WHERE active LIMIT 200
            """)).scalars().all()
        notify_many(
            db, rows, exclude=[boi], source_app="shared", event_type="dao_tao_moi",
            title=f"Tài liệu đào tạo mới: {nd.tieu_de}",
            message=(nd.mo_ta or "")[:200], url="/dao-tao",
            ref_type="dao_tao_noi_dung", ref_id=str(nd.id), created_by=boi,
        )
    except Exception:
        db.rollback()


@router.delete("/{nd_id}", status_code=status.HTTP_204_NO_CONTENT)
def xoa_noi_dung(
    nd_id: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    nd = db.get(DaoTaoNoiDung, nd_id)
    if not nd:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy nội dung")
    if nd.created_by != user.username and (user.role or "").lower() not in _SUPER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ người đăng hoặc ban giám đốc xoá được")
    import shutil
    try:
        shutil.rmtree(_thu_muc(nd_id), ignore_errors=True)
    except Exception:
        pass
    db.execute(sql_text("DELETE FROM shared.dao_tao_tuong_tac WHERE noi_dung_id = :i"), {"i": nd_id})
    db.delete(nd)
    db.commit()
    return None
