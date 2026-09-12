"""Xin Nghỉ API — cross-app leave request system.

Mounted at /api/xin-nghi in: marketing, muahang, ketoan, saleadmin, ceo
Read-only mount (GET only) in: hcns

11/09/2026: thêm tệp đính kèm cho đơn (`/{rid}/tep`, không đổi bảng DB) và phép năm
của chính người đang đăng nhập (`/phep-nam`) cho màn Xin nghỉ dùng chung 8 app.
"""
import calendar
import logging
import re
import shutil
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as sqlfunc, or_, select, text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models.leave_request import LeaveRequest
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)
log = logging.getLogger(__name__)

_APPROVER_ROLES = {"admin", "ceo", "assistant_ceo", "manager", "leader"}
_SUPER_ROLES = {"admin", "ceo", "assistant_ceo"}
_LOAI_NGHI_LABELS = {
    # 4 loại chính thức (anh Quang 2026-06-06):
    "nghi_khong_luong": "Nghỉ Không Lương",
    "nghi_phep": "Nghỉ Phép Năm",
    "doi_ca": "Nghỉ Đổi Ca",
    "xin_thoi_viec": "Xin Thôi Việc",
    # Legacy — giữ accept để không phá đơn cũ
    "nghi_bu": "Nghỉ Bù",
    "nghi_om": "Nghỉ Ốm",
    "viec_rieng": "Việc Riêng",
    "nghi_le": "Nghỉ Lễ / Tết",
}


# Subdomain -> tên app trong JWT.apps. CHỈ liệt kê chỗ lệch nhau.
# Công Nghệ phục vụ ở itque.qlpps.com (xem deploy-kit/config.json).
_HOST_ALIAS = {"itque": "congnghe"}


def _is_approver(user: JWTPayload) -> bool:
    return (user.role or "").lower() in _APPROVER_ROLES


def _approver_app_scope(user: JWTPayload) -> Optional[set[str]]:
    """(Deprecated — thay bằng _approver_depts) Trả set app_name theo JWT.apps."""
    if (user.role or "").lower() in _SUPER_ROLES:
        return None
    return {(a or "").lower() for a in (user.apps or []) if a}


def _approver_depts(db: Session, user: JWTPayload) -> Optional[list[str]]:
    """Danh sách PHÒNG BAN (lowercase) mà manager/leader được xem/duyệt đơn nghỉ.

    - admin/ceo/assistant_ceo → None (không giới hạn, thấy hết).
    - manager/leader → phòng ban chính + phụ (phong_ban_phu, CSV) của HỌ, tra từ
      hcns.employees. Dùng KHỚP TIỀN TỐ để gồm cả sub-team (vd "Kinh Doanh" bao
      "Kinh Doanh Bán Lẻ Nhóm 1/2"). [] = không xác định → fail-closed (không thấy).

    Sửa 2026-08-26 (anh Quang): TRƯỚC lọc theo app_name → SAI: KD manager thấy đơn
    phòng khác cùng app (vd Vy KD thấy đơn Huy Mua Hàng). Giờ lọc theo PHÒNG BAN.
    """
    if (user.role or "").lower() in _SUPER_ROLES:
        return None
    row = db.execute(text(
        "SELECT phong_ban, phong_ban_phu FROM hcns.employees "
        "WHERE LOWER(username) = LOWER(:u) LIMIT 1"
    ), {"u": user.username or ""}).mappings().first()
    depts: list[str] = []
    if row:
        main = (row.get("phong_ban") or "").strip().lower()
        if main:
            depts.append(main)
        for d in str(row.get("phong_ban_phu") or "").split(","):
            d = d.strip().lower()
            if d and d not in depts:
                depts.append(d)
    return depts


def _dept_where(depts: list[str]):
    """Điều kiện SQL: phong_ban của đơn khớp TIỀN TỐ bất kỳ phòng nào approver quản lý."""
    return or_(*[sqlfunc.lower(sqlfunc.coalesce(LeaveRequest.phong_ban, "")).like(d + "%")
                 for d in depts])


def _calc_so_ngay(ngay_bat_dau: date, ngay_ket_thuc: date, buoi: str) -> Decimal:
    if ngay_ket_thuc < ngay_bat_dau:
        return Decimal("0")
    total_days = (ngay_ket_thuc - ngay_bat_dau).days + 1
    if buoi in ("sang", "chieu"):
        return Decimal("0.5")
    return Decimal(str(total_days))


# ── Tệp đính kèm (11/09/2026) ────────────────────────────────────────────────
# KHÔNG thêm cột DB: tệp của đơn #N nằm trong `<upload_dir>/xin_nghi/N/`, danh sách tệp
# = danh sách file trong thư mục đó. Tên trên đĩa `<12 hex>__<tên gốc đã lọc>` — giữ
# được tên gốc để hiện mà không cần bảng phụ. Thư mục uploads dùng chung mọi app (dev:
# `./_storage` gắn vào cả 8 container) nên nộp ở app nào, người duyệt ở app khác vẫn mở.
_TEP_SUBDIR = "xin_nghi"
_TEP_EXT = {".pdf", ".jpg", ".jpeg", ".png"}
_TEP_MAX = 5 * 1024 * 1024   # 5 MB — đúng dòng "tối đa 5MB" trên form
_TEP_TOI_DA = 10             # số tệp tối đa mỗi đơn
_TEP_MA_RE = re.compile(r"^[a-f0-9]{12}__[^/\\]{1,120}$")


def _tep_dir(rid: int) -> Path:
    return Path(settings.upload_dir).expanduser().resolve() / _TEP_SUBDIR / str(int(rid))


def _ds_tep(rid: int) -> list[dict]:
    """Tệp của đơn, cũ trước mới sau. Thư mục chưa có → []."""
    d = _tep_dir(rid)
    if not d.is_dir():
        return []
    files = [f for f in d.iterdir() if f.is_file() and _TEP_MA_RE.match(f.name)]
    files.sort(key=lambda f: f.stat().st_mtime)
    return [{"ma": f.name, "ten": f.name.split("__", 1)[1],
             "url": f"/api/xin-nghi/{int(rid)}/tep/{quote(f.name)}",
             "kich_thuoc": f.stat().st_size} for f in files]


def _ten_goc_an_toan(filename: Optional[str], ext: str) -> str:
    """Tên gốc để hiện lại: bỏ thư mục, ký tự lạ; giữ chữ có dấu. Rỗng → 'tep'."""
    stem = Path((filename or "").replace("\\", "/")).stem
    stem = re.sub(r"[^\w\-. ()]+", "_", stem).strip(" ._") or "tep"
    return stem[:80] + ext


def _la_chu_don(rec: "LeaveRequest", user: JWTPayload) -> bool:
    return (rec.username or "").lower() == (user.username or "").lower()


def _xem_duoc_don(db: Session, user: JWTPayload, rec: "LeaveRequest") -> bool:
    """Người gửi, admin/CEO, hoặc manager/leader của đúng phòng ban đơn — cùng phạm vi
    với danh sách `GET ""` (ai thấy đơn trong danh sách thì mở được tệp của đơn)."""
    if _la_chu_don(rec, user):
        return True
    if not _is_approver(user):
        return False
    depts = _approver_depts(db, user)
    if depts is None:
        return True
    rp = (rec.phong_ban or "").strip().lower()
    return any(rp.startswith(d) for d in depts)


# ── Schemas ───────────────────────────────────────────────────────────────────
class LeaveCreate(BaseModel):
    loai_nghi: str
    ngay_bat_dau: date
    ngay_ket_thuc: date
    buoi: str = "ca_ngay"
    ly_do: str
    ghi_chu: str = ""


class LeaveReview(BaseModel):
    trang_thai: str  # da_duyet | tu_choi
    nhan_xet_duyet: str = ""


class TepOut(BaseModel):
    ma: str          # tên trên đĩa — dùng để mở / xoá
    ten: str         # tên gốc để hiện
    url: str
    kich_thuoc: int


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    ho_ten: str
    phong_ban: Optional[str]
    app_name: str
    loai_nghi: str
    ngay_bat_dau: date
    ngay_ket_thuc: date
    buoi: str
    so_ngay: Decimal
    ly_do: str
    ghi_chu: Optional[str]
    trang_thai: str
    nguoi_duyet: Optional[str]
    ho_ten_nguoi_duyet: Optional[str]
    nhan_xet_duyet: Optional[str]
    ngay_duyet: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    # Không phải cột DB — gắn tay từ thư mục tệp (`_ds_tep`) trước khi trả về.
    tep_dinh_kem: List[TepOut] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("", response_model=List[LeaveOut])
def list_leave_requests(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = None,
    phong_ban: Optional[str] = None,
    username: Optional[str] = None,
    thang: Optional[str] = None,  # "YYYY-MM"
):
    stmt = select(LeaveRequest).order_by(LeaveRequest.created_at.desc())
    if not _is_approver(user):
        stmt = stmt.where(LeaveRequest.username == user.username)
    else:
        # Manager/leader chỉ thấy đơn của PHÒNG BAN mình (chính + phụ). Admin/CEO thấy hết.
        depts = _approver_depts(db, user)
        if depts is not None:
            if not depts:
                return []  # không xác định phòng ban → không thấy đơn nào
            stmt = stmt.where(_dept_where(depts))
        if username:
            stmt = stmt.where(LeaveRequest.username == username)
        if phong_ban:
            stmt = stmt.where(LeaveRequest.phong_ban == phong_ban)
    if trang_thai:
        # `da_duyet` gồm CẢ trạng thái cũ `duyet` (28 đơn legacy) — nếu không
        # gộp, tab "Đã duyệt" sẽ thiếu đơn. Vá 2026-08-31.
        if trang_thai == "da_duyet":
            stmt = stmt.where(LeaveRequest.trang_thai.in_(("da_duyet", "duyet")))
        else:
            stmt = stmt.where(LeaveRequest.trang_thai == trang_thai)
    if thang:
        try:
            y, m = thang.split("-")
            last_day = calendar.monthrange(int(y), int(m))[1]
            stmt = stmt.where(
                LeaveRequest.ngay_bat_dau >= date(int(y), int(m), 1)
            ).where(
                LeaveRequest.ngay_bat_dau <= date(int(y), int(m), last_day)
            )
        except Exception:
            pass
    recs = db.execute(stmt).scalars().all()
    for r in recs:
        r.tep_dinh_kem = _ds_tep(r.id)
    return recs


@router.post("", response_model=LeaveOut, status_code=status.HTTP_201_CREATED)
def create_leave_request(
    body: LeaveCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    if body.loai_nghi not in _LOAI_NGHI_LABELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Loại nghỉ không hợp lệ: {body.loai_nghi}",
        )
    if body.ngay_ket_thuc < body.ngay_bat_dau:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Ngày kết thúc phải >= ngày bắt đầu",
        )
    if not body.ly_do.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Lý do không được để trống",
        )

    ho_ten, phong_ban, _, _, _ = _lookup_user_info(user.username)
    so_ngay = _calc_so_ngay(body.ngay_bat_dau, body.ngay_ket_thuc, body.buoi)

    # `app_name` KHÔNG phải nhãn trang trí — nó là thứ `_approver_app_scope()`
    # đem so với JWT.apps để quyết định manager/leader nào được XEM và DUYỆT đơn.
    # Ghi sai một chữ là đơn tàng hình với mọi quản lý, chỉ admin/CEO thấy.
    #
    # Bản cũ suy tên app từ subdomain của Host. Sai vì tên miền KHÔNG luôn trùng
    # tên app: Công Nghệ chạy ở itque.qlpps.com → ghi 'itque', mà JWT.apps chỉ
    # có 'congnghe' → 14 đơn không quản lý nào duyệt được.
    #
    # Nguồn chuẩn: `app.state.app_name` — cả 8 app đều khai, và khai đúng bộ từ
    # vựng của JWT.apps (đã đối chiếu với `SELECT DISTINCT unnest(apps)`).
    app_name = getattr(request.app.state, "app_name", None)
    if not app_name:
        # Đường lui cho ASGI app phụ không khai state — hiện có
        # `shared/services/chat_internal_main.py` cũng mount router này.
        host = (request.headers.get("host") or "").split(":")[0]
        sub = host.split(".")[0] if "." in host else host
        app_name = _HOST_ALIAS.get(sub.lower(), sub.lower()) or "internal"
    # Cột là varchar(32): Host lạ mà dài hơn sẽ làm INSERT nổ giữa lúc nộp đơn.
    app_name = str(app_name)[:32]

    rec = LeaveRequest(
        username=user.username,
        ho_ten=ho_ten or user.username,
        phong_ban=phong_ban,
        app_name=app_name,
        loai_nghi=body.loai_nghi,
        ngay_bat_dau=body.ngay_bat_dau,
        ngay_ket_thuc=body.ngay_ket_thuc,
        buoi=body.buoi,
        so_ngay=so_ngay,
        ly_do=body.ly_do.strip(),
        ghi_chu=(body.ghi_chu or "").strip(),
        trang_thai="cho_duyet",
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    try:
        from shared.services.activity_logger import log_activity
        log_activity(db, user.username, action="leave_submit", app="shared",
                     ref_type="leave_request", ref_id=rec.id,
                     metadata={"so_ngay": float(so_ngay or 0),
                               "loai_nghi": getattr(rec, "loai_nghi", None)})
    except Exception:
        pass
    return rec


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_leave_request(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    rec = db.get(LeaveRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn")
    if rec.username != user.username and not _is_approver(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền hủy đơn này")
    if rec.trang_thai != "cho_duyet":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chỉ có thể hủy đơn đang chờ duyệt")
    db.delete(rec)
    db.commit()
    # Đơn đã xoá khỏi DB thì tệp của nó không còn đường nào mở được — dọn luôn.
    shutil.rmtree(_tep_dir(rid), ignore_errors=True)


@router.put("/{rid}/duyet", response_model=LeaveOut)
def duyet_leave_request(
    rid: int,
    body: LeaveReview,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    if not _is_approver(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ manager/leader/admin được duyệt")
    if body.trang_thai not in ("da_duyet", "tu_choi"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Trạng thái không hợp lệ",
        )
    rec = db.get(LeaveRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn")
    # KHÔNG tự duyệt đơn của CHÍNH MÌNH (anh Quang 2026-08-05): manager/leader duyệt
    # đơn của chính họ = xung đột lợi ích → chặn, để Mai hoặc cấp trên duyệt. Super-role
    # (admin/ceo/assistant_ceo) vẫn được (không có cấp trên). VD: NV26006 nv26006 (manager
    # Kế Toán) tự duyệt phép của mình → chặn.
    if (rec.username or "").lower() == (user.username or "").lower() \
            and (user.role or "").lower() not in _SUPER_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Không được tự duyệt đơn nghỉ của chính mình — để Mai hoặc cấp trên duyệt.",
        )
    # Manager/leader chỉ duyệt được đơn của PHÒNG BAN mình (chính + phụ). Admin/CEO bypass.
    depts = _approver_depts(db, user)
    if depts is not None:
        rp = (rec.phong_ban or "").strip().lower()
        if not any(rp.startswith(d) for d in depts):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Bạn không có quyền duyệt đơn của phòng '{rec.phong_ban}' — khác phòng bạn quản lý.",
            )

    ho_ten_duyet, _, _, _, _ = _lookup_user_info(user.username)
    rec.trang_thai = body.trang_thai
    rec.nguoi_duyet = user.username
    rec.ho_ten_nguoi_duyet = ho_ten_duyet or user.username
    rec.nhan_xet_duyet = body.nhan_xet_duyet
    rec.ngay_duyet = datetime.now(timezone.utc)
    db.commit()
    db.refresh(rec)

    # Auto-sync CalendarEvent (idempotent, fail-soft)
    try:
        from shared.services.calendar_sync import (
            upsert_event_from_leave, delete_event_by_source,
        )
        if rec.trang_thai == "da_duyet":
            upsert_event_from_leave(db, rec)
            db.commit()
        elif rec.trang_thai == "tu_choi":
            if delete_event_by_source(db, "leave_request", str(rec.id)):
                db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # Auto-sync hcns.cham_cong: nghi_phep được duyệt → ghi công vào bảng chấm
    # công để báo cáo công + bảng lương phản ánh đúng (VN Labor Law Đ.113).
    # Chỉ áp dụng nghi_phep (có lương). Loại không-lương/thôi-việc/đổi-ca
    # không tạo record. Idempotent: re-duyệt cùng đơn không nhân đôi.
    _sync_cham_cong_from_leave(db, rec)

    rec.tep_dinh_kem = _ds_tep(rec.id)
    return rec


def _sync_cham_cong_from_leave(db: Session, rec: "LeaveRequest") -> None:
    """Upsert/delete cham_cong cho đơn nghi_phep đã duyệt / từ chối.

    - da_duyet + nghi_phep → upsert cham_cong (loai='nghi_phep', tong_gio=8
      cả ngày / 4 nửa buổi). Không đè record do NV tự chấm.
    - tu_choi + nghi_phep → xoá các cham_cong auto sinh từ đơn này.
    - Loại nghỉ khác: bỏ qua hoàn toàn.

    Fail-soft: lỗi sync KHÔNG làm fail toàn bộ duyệt đơn.
    """
    from datetime import timedelta
    try:
        if (rec.loai_nghi or "").lower() != "nghi_phep":
            return
        username = (rec.username or "").strip()
        if not username:
            return
        from hcns.app.models.cham_cong import ChamCong  # lazy
        from hcns.app.models.employee import Employee  # lazy
        # Resolve username → ma_nv qua employees. Nếu không có employee record
        # thì fallback UPPER(username) — nhưng thường username `_N` (nv26007_3,
        # nv26019_5, ...) đều đã map tới ma_nv gốc (NV26007/NV26019) trong
        # employees, nên fallback này chủ yếu cho edge case dev/test.
        emp = db.execute(
            select(Employee).where(Employee.username == username)
        ).scalar_one_or_none()
        ma_nv = emp.ma_nv if emp else username.upper()
        marker = f"leave_auto:{rec.id}"

        if rec.trang_thai == "tu_choi":
            db.query(ChamCong).filter(
                ChamCong.ma_nv == ma_nv,
                ChamCong.created_by == marker,
            ).delete(synchronize_session=False)
            db.commit()
            return

        if rec.trang_thai != "da_duyet":
            return

        tong_gio_per_day = Decimal("8") if (rec.buoi or "") == "ca_ngay" else Decimal("4")
        d = rec.ngay_bat_dau
        while d <= rec.ngay_ket_thuc:
            existing = db.execute(
                select(ChamCong).where(
                    ChamCong.ma_nv == ma_nv,
                    ChamCong.ngay == d,
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(ChamCong(
                    ma_nv=ma_nv,
                    ngay=d,
                    tong_gio=tong_gio_per_day,
                    loai="nghi_phep",
                    ghi_chu=f"Nghỉ phép — đơn #{rec.id}",
                    created_by=marker,
                    updated_by=marker,
                ))
            elif (existing.created_by or "").startswith("leave_auto:"):
                existing.tong_gio = tong_gio_per_day
                existing.loai = "nghi_phep"
                existing.ghi_chu = f"Nghỉ phép — đơn #{rec.id}"
                existing.created_by = marker
                existing.updated_by = marker
            # else: NV đã chấm thật ngày đó → giữ nguyên, không đè
            d += timedelta(days=1)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


# ── Tệp đính kèm: tải lên · mở · xoá ────────────────────────────────────────
@router.post("/{rid}/tep", response_model=LeaveOut)
async def upload_tep(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Tải một tệp lên đơn. Người gửi đơn (hoặc admin/CEO) mới được."""
    rec = db.get(LeaveRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn")
    if not _la_chu_don(rec, user) and (user.role or "").lower() not in _SUPER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ người gửi đơn mới tải tài liệu lên được")
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _TEP_EXT:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chỉ nhận tệp PDF, JPG, PNG")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tệp trống")
    if len(data) > _TEP_MAX:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tệp quá lớn — tối đa 5MB")
    if len(_ds_tep(rid)) >= _TEP_TOI_DA:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Mỗi đơn tối đa {_TEP_TOI_DA} tệp")
    d = _tep_dir(rid)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{uuid.uuid4().hex[:12]}__{_ten_goc_an_toan(file.filename, ext)}").write_bytes(data)
    rec.tep_dinh_kem = _ds_tep(rid)
    return rec


@router.get("/{rid}/tep/{ma}")
def xem_tep(
    rid: int,
    ma: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Mở tệp — ai thấy đơn trong danh sách thì mở được (`_xem_duoc_don`)."""
    if not _TEP_MA_RE.match(ma):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên tệp không hợp lệ")
    rec = db.get(LeaveRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn")
    if not _xem_duoc_don(db, user, rec):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền xem tài liệu của đơn này")
    d = _tep_dir(rid)
    f = (d / ma).resolve()
    if f.parent != d or not f.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tệp không tồn tại")
    return FileResponse(str(f), filename=ma.split("__", 1)[1], content_disposition_type="inline")


@router.delete("/{rid}/tep", response_model=LeaveOut)
def xoa_tep(
    rid: int,
    ma: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Xoá một tệp. Người gửi khi đơn còn chờ duyệt, hoặc admin/CEO."""
    if not _TEP_MA_RE.match(ma or ""):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên tệp không hợp lệ")
    rec = db.get(LeaveRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đơn")
    la_super = (user.role or "").lower() in _SUPER_ROLES
    if not ((_la_chu_don(rec, user) and rec.trang_thai == "cho_duyet") or la_super):
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Chỉ xoá được tài liệu của đơn đang chờ duyệt do chính bạn gửi")
    d = _tep_dir(rid)
    f = (d / ma).resolve()
    if f.parent == d and f.is_file():
        f.unlink()
    rec.tep_dinh_kem = _ds_tep(rid)
    return rec


# ── Phép năm của CHÍNH người đang đăng nhập ──────────────────────────────────
@router.get("/phep-nam")
def phep_nam_cua_toi(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    nam: Optional[int] = None,
):
    """Phép năm của người đang đăng nhập — CÙNG con số màn Quota phép năm của HCNS.

    Gọi thẳng `quota_phep_summary` của HCNS rồi lấy đúng dòng của người này, KHÔNG chép
    lại công thức (1 ngày cho mỗi tháng chính thức, chốt sổ khi thôi việc). Endpoint gốc
    `/api/quota-phep` chỉ mount ở HCNS, đòi quyền app hcns và trả cả công ty — không dùng
    được cho màn Xin nghỉ ở 8 app.

    - tong_ca_nam: số ngày được cấp cả năm (tháng chính thức trong năm, trừ sau thôi việc)
    - da_cap: cấp đến tháng hiện tại · da_dung: đã duyệt · con_lai = da_cap - da_dung
    """
    nam = nam if (nam and 2020 <= nam <= 2099) else date.today().year
    kq = {"nam": nam, "co_quota": False, "ly_do": "", "tong_ca_nam": 0, "da_cap": 0,
          "da_dung": 0, "con_lai": 0, "cho_duyet": 0.0, "thang_hien_tai": None,
          "het_han": f"{nam}-12-31"}
    cho = db.execute(text(
        "SELECT COALESCE(SUM(so_ngay), 0) FROM shared.leave_requests "
        "WHERE LOWER(username) = LOWER(:u) AND loai_nghi = 'nghi_phep' "
        "AND trang_thai = 'cho_duyet' AND EXTRACT(YEAR FROM ngay_bat_dau) = :nam"
    ), {"u": user.username or "", "nam": nam}).scalar()
    kq["cho_duyet"] = float(cho or 0)

    emp = db.execute(text(
        "SELECT ma_nv, trang_thai, loai_hop_dong FROM hcns.employees "
        "WHERE LOWER(username) = LOWER(:u) LIMIT 1"
    ), {"u": user.username or ""}).mappings().first()
    if not emp:
        kq["ly_do"] = "Tài khoản chưa gắn hồ sơ nhân viên"
        return kq
    # Cùng điều kiện lọc với quota_phep_summary: chỉ NV CHÍNH THỨC đang làm.
    if emp["trang_thai"] != "Đang làm" or emp["loai_hop_dong"] != "Chính thức":
        kq["ly_do"] = "Phép năm chỉ cấp cho nhân viên chính thức đang làm"
        return kq
    try:
        from hcns.app.routers.quota_phep import quota_phep_summary  # lazy — shared không phụ thuộc hcns lúc import
        tong = quota_phep_summary(user=user, db=db, nam=nam)
    except Exception:
        log.exception("phep-nam: không tính được quota cho %s", user.username)
        kq["ly_do"] = "Máy chủ chưa tính được phép năm"
        return kq
    ma = (emp["ma_nv"] or "").upper()
    row = next((r for r in tong.get("rows", []) if (r.get("ma_nv") or "").upper() == ma), None)
    if not row:
        kq["ly_do"] = "Không tìm thấy dòng phép năm của nhân viên"
        return kq
    moi_thang = tong.get("phep_cap_per_month", 1)
    kq.update({
        "co_quota": True,
        "tong_ca_nam": sum(moi_thang for m in (row.get("monthly") or [])
                           if not m.get("before_official") and not m.get("after_resign")),
        "da_cap": row.get("tong_cap_nam", 0),
        "da_dung": row.get("tong_dung_nam", 0),
        "con_lai": row.get("tong_con_nam", 0),
        "thang_hien_tai": tong.get("current_month"),
    })
    return kq


@router.get("/stats")
def leave_stats(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Số liệu đơn nghỉ.

    - NV thường: đếm đơn CỦA CHÍNH MÌNH (cho_duyet / da_duyet / tu_choi).
    - Người DUYỆT (manager/leader/CEO): trả thêm `all_*` = đếm TOÀN PHẠM VI
      họ quản (lọc theo phòng ban; CEO/admin thấy tất cả).

    Vá 2026-08-31 (anh Quang): trước đây 3 thẻ số liệu chỉ đếm đơn của chính
    mình, nên CEO (không tự nộp đơn) luôn thấy 0/0/0 và tưởng hệ thống trống
    dù đang có 215 đơn đã xử lý.
    """
    own = db.execute(
        select(LeaveRequest.trang_thai, sqlfunc.count().label("cnt"))
        .where(LeaveRequest.username == user.username)
        .group_by(LeaveRequest.trang_thai)
    ).all()
    result: dict = {"cho_duyet": 0, "da_duyet": 0, "tu_choi": 0}
    for row in own:
        if row.trang_thai in result:
            result[row.trang_thai] = row.cnt
    if not _is_approver(user):
        return result

    depts = _approver_depts(db, user)
    if depts is not None and not depts:
        result.update({"pending_all": 0, "all_cho_duyet": 0,
                       "all_da_duyet": 0, "all_tu_choi": 0})
        return result

    q = select(LeaveRequest.trang_thai, sqlfunc.count().label("cnt"))
    if depts is not None:
        q = q.where(_dept_where(depts))
    rows = db.execute(q.group_by(LeaveRequest.trang_thai)).all()
    # Gộp trạng thái cũ `duyet` vào `da_duyet` cho khớp bộ lọc trên giao diện.
    agg = {"cho_duyet": 0, "da_duyet": 0, "tu_choi": 0}
    for r in rows:
        k = "da_duyet" if r.trang_thai in ("da_duyet", "duyet") else r.trang_thai
        if k in agg:
            agg[k] += r.cnt
    result["all_cho_duyet"] = agg["cho_duyet"]
    result["all_da_duyet"] = agg["da_duyet"]
    result["all_tu_choi"] = agg["tu_choi"]
    result["pending_all"] = agg["cho_duyet"]
    return result
