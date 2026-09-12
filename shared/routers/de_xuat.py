"""Đề Xuất API — nhân viên đề xuất công việc lên cấp trên, duyệt xong thành việc thật.

Luồng (anh Quang chốt 28/08/2026):
    NV gửi → Manager cùng phòng → [CEO nếu cần] → done → sinh Giao Việc

Khác Duyệt Chi ở hai chỗ:
  1. KHÔNG luôn qua CEO. Manager chốt là xong, trừ khi có một trong ba dấu
     hiệu: có ngân sách dự kiến, ảnh hưởng nhiều phòng, hoặc người gửi tick
     xin ý kiến CEO. Bắt mọi đề xuất qua CEO thì hộp thư CEO ngập và việc nhỏ
     chạy chậm.
  2. Duyệt xong SINH RA `Directive` (Giao Việc) giao cho chính người đề xuất.
     Không có bước này thì đề xuất được duyệt chỉ nằm im, không ai biết có làm
     hay không.

## Chống kẹt — đọc trước khi sửa

`duyet_chi.py` từng để đề xuất kẹt vĩnh viễn ở cấp 'manager' vì nhiều phòng
không có manager (anh Quang 2026-07-02). Bốn luật dưới đây sinh ra để chuyện
đó không lặp lại; bỏ luật nào cũng mở lại đúng cái lỗ đó:

  a. Phòng không có manager active  → bắt đầu thẳng ở cấp cần thiết kế tiếp.
  b. Người gửi CHÍNH LÀ manager      → bỏ qua cấp manager (không ai tự duyệt).
  c. CEO duyệt được ở MỌI cấp        → cửa thoát cuối, không gì kẹt vĩnh viễn.
  d. Không có cấp nào khả dụng       → rơi về 'ceo', vì luôn tồn tại super-role.

## Tự duyệt

Chặn, TRỪ super-role (admin/ceo/assistant_ceo) — theo đúng tiền lệ
`xin_nghi.py`: họ không có cấp trên nên chặn là kẹt. Hệ quả: super-role tự
duyệt đề xuất của mình thì người giao trùng người nhận, mà `giao_viec.py` cấm
"tự giao task cho mình" → BỎ QUA bước sinh việc và ghi rõ vào lịch sử, không
nuốt lỗi im lặng.

Mounted at /api/de-xuat trong cả 8 app.
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models.de_xuat import DeXuat
from shared.models.user import User
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)

_TEP_SUBDIR = "de_xuat"
_ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif",
                ".doc", ".docx", ".xls", ".xlsx"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

_SUPER_ROLES = {"admin", "ceo", "assistant_ceo"}
_MANAGER_ROLES = {"manager", "leader"}

_LEVELS = ("manager", "ceo")
_NHAC_SAU_NGAY = 7   # quá ngần này ngày chưa ai đụng → nhắc người duyệt

_LOAI_LABELS = {
    "cai_tien": "Cải tiến cách làm",
    "viec_moi": "Việc mới / Sáng kiến",
    "van_de": "Vấn đề cần xử lý",
    "khac": "Khác",
}
_MUC_DO = ("thap", "trung", "cao")
# Đề xuất dùng thang thấp/trung/cao; Directive dùng low/med/high.
_MUC_DO_SANG_PRIORITY = {"thap": "low", "trung": "med", "cao": "high"}


# ── Helpers: ai là cấp trên ───────────────────────────────────────────────────
def _user_phong_ban(username: str) -> Optional[str]:
    try:
        _, pb, _, _, _ = _lookup_user_info(username)
        return (pb or "").strip() or None
    except Exception:
        return None


def _dept_has_manager(db: Session, phong_ban: Optional[str], *, tru: str = "") -> bool:
    """Phòng `phong_ban` có manager/leader active nào KHÁC `tru` không?

    `tru` = username người gửi: manager tự đề xuất thì chính họ không tính là
    người duyệt được, nếu không đề xuất sẽ kẹt chờ chính mình.
    """
    if not phong_ban or not phong_ban.strip():
        return False
    pb = phong_ban.strip()
    rows = db.execute(
        select(User.username)
        .where(User.role.in_(tuple(_MANAGER_ROLES)))
        .where(User.active.is_(True))
    ).all()
    for (uname,) in rows:
        if uname and uname != tru and _user_phong_ban(uname) == pb:
            return True
    return False


def _can_ceo(rec: DeXuat) -> bool:
    """Đề xuất này có phải lên CEO không? Ba dấu hiệu, chỉ cần một."""
    return bool(
        (rec.ngan_sach_du_kien or 0) > 0
        or rec.lien_phong_ban
        or rec.xin_y_kien_ceo
    )


def _cap_bat_dau(db: Session, rec: DeXuat) -> str:
    """Cấp duyệt đầu tiên — đã áp luật chống kẹt (a), (b), (d)."""
    co_manager = _dept_has_manager(db, rec.phong_ban, tru=rec.username)
    if co_manager:
        return "manager"
    # Không có manager duyệt được → nhảy thẳng lên CEO. Kể cả khi đề xuất
    # không cần CEO: thà CEO duyệt một việc nhỏ còn hơn để nó kẹt mãi.
    return "ceo"


def _cap_ke_tiep(rec: DeXuat, cap_hien_tai: str) -> str:
    """Sau khi duyệt ở `cap_hien_tai` thì đi đâu."""
    if cap_hien_tai == "manager":
        return "ceo" if _can_ceo(rec) else "done"
    return "done"   # ceo là cấp cuối


def _can_approve_at(user: JWTPayload, level: str, rec: DeXuat, db: Session) -> bool:
    """User có quyền duyệt `rec` tại `level` không.

    - super-role: duyệt được MỌI cấp (luật chống kẹt (c)).
    - manager/leader: chỉ cấp 'manager', và chỉ ĐÚNG phòng ban của đề xuất.
      Dùng phòng ban chứ không dùng app như Duyệt Chi từng làm: đề xuất công
      việc thuộc về phòng, không thuộc về app.
    """
    role = (user.role or "").lower()
    if role in _SUPER_ROLES:
        return True
    if level == "manager" and role in _MANAGER_ROLES:
        pb = _user_phong_ban(user.username)
        return bool(pb) and (rec.phong_ban or "") == pb
    return False


def _is_any_approver(user: JWTPayload) -> bool:
    role = (user.role or "").lower()
    return role in _SUPER_ROLES or role in _MANAGER_ROLES


# ── Thông báo ─────────────────────────────────────────────────────────────────
def _notify_next_tier(db: Session, rec: DeXuat, *, by: str) -> None:
    """Báo cấp duyệt kế tiếp, hoặc báo người gửi khi đã có kết quả.

    Toàn bộ fail-soft: thông báo hỏng không được làm hỏng việc gửi/duyệt —
    bản ghi đã nằm trong DB rồi, ném lỗi ra chỉ khiến người dùng gửi lại lần nữa.
    """
    try:
        from shared.services.notify import notify, notify_many
    except Exception:
        return
    tien_to = f"[Đề Xuất #{rec.id}]"
    url = f"/de-xuat#id={rec.id}"
    lvl = rec.approval_level

    if lvl == "done":
        them = " — đã tạo việc để theo dõi" if rec.directive_id else ""
        try:
            notify(
                db, target=rec.username, source_app=rec.app_name,
                event_type="de_xuat:approved",
                title=f"{tien_to} Đã được duyệt{them}",
                message=rec.tieu_de, ref_type="de_xuat", ref_id=rec.id,
                url=url, severity="success", created_by=by,
            )
        except Exception:
            pass
        return

    if lvl == "rejected":
        cuoi = (rec.approval_history or [])[-1] if rec.approval_history else {}
        ai = cuoi.get("ho_ten") or cuoi.get("username") or by
        try:
            notify(
                db, target=rec.username, source_app=rec.app_name,
                event_type="de_xuat:rejected",
                title=f"{tien_to} Bị từ chối bởi {ai}",
                message=cuoi.get("comment") or rec.tieu_de,
                ref_type="de_xuat", ref_id=rec.id,
                url=url, severity="warning", created_by=by,
            )
        except Exception:
            pass
        return

    # Còn chờ duyệt → tìm người của cấp hiện tại
    targets: list[str] = []
    try:
        if lvl == "manager" and rec.phong_ban:
            rows = db.execute(
                select(User.username)
                .where(User.role.in_(tuple(_MANAGER_ROLES)))
                .where(User.active.is_(True))
            ).all()
            targets = [r[0] for r in rows
                       if r[0] and r[0] != rec.username
                       and _user_phong_ban(r[0]) == rec.phong_ban]
        elif lvl == "ceo":
            rows = db.execute(
                select(User.username)
                .where(User.role.in_(tuple(_SUPER_ROLES)))
                .where(User.active.is_(True))
            ).all()
            targets = [r[0] for r in rows if r[0]]
    except Exception:
        return
    if not targets:
        return

    nhan = {"manager": f"Manager phòng {rec.phong_ban or ''}".strip(), "ceo": "CEO"}
    try:
        notify_many(
            db, targets, exclude=[by], source_app=rec.app_name,
            event_type=f"de_xuat:pending_{lvl}",
            title=f"{tien_to} Chờ {nhan.get(lvl, lvl)} duyệt",
            message=f"{rec.ho_ten} • {rec.tieu_de}",
            ref_type="de_xuat", ref_id=rec.id, url=url,
            severity="info", created_by=by,
        )
    except Exception:
        pass


# ── Khép vòng: duyệt xong → sinh Giao Việc ────────────────────────────────────
def _sinh_giao_viec(db: Session, rec: DeXuat, *, nguoi_duyet: str) -> Optional[str]:
    """Tạo Directive giao cho người đề xuất. Trả lời vì sao KHÔNG tạo (nếu không).

    Trả None = đã tạo xong, `rec.directive_id` đã gán.

    Không gọi HTTP sang /api/giao-viec mà dựng thẳng row trong CÙNG transaction:
    duyệt và sinh việc phải cùng sống hoặc cùng chết, không được nửa vời.
    """
    if rec.directive_id:
        return None
    if nguoi_duyet == rec.username:
        # giao_viec.py cấm "tự giao task cho mình". Xảy ra khi super-role tự
        # đề xuất rồi tự duyệt. Duyệt vẫn ghi nhận, chỉ bỏ bước sinh việc.
        return "Người duyệt trùng người đề xuất nên không tạo việc — tự giao task cho mình."
    try:
        from shared.models.directive import Directive
    except Exception as e:
        return f"Không nạp được module Giao Việc: {e}"

    try:
        than = (rec.noi_dung or "").strip()
        if rec.ket_qua_ky_vong:
            than += f"\n\n— Kết quả kỳ vọng —\n{rec.ket_qua_ky_vong.strip()}"
        than += f"\n\n(Sinh từ Đề Xuất #{rec.id})"

        d = Directive(
            from_user=nguoi_duyet,
            to_user=rec.username,
            app=rec.app_name,
            title=rec.tieu_de[:255],
            body=than,
            priority=_MUC_DO_SANG_PRIORITY.get(rec.muc_do, "med"),
            due_date=rec.han_mong_muon,
            status="assigned",
            last_activity_at=datetime.now(timezone.utc),
        )
        # from_user_id / to_user_id chỉ để tiện join, thiếu không sao
        try:
            for cot, uname in (("from_user_id", nguoi_duyet), ("to_user_id", rec.username)):
                uid = db.execute(
                    select(User.id).where(User.username == uname)
                ).scalar_one_or_none()
                if uid:
                    setattr(d, cot, uid)
        except Exception:
            pass

        db.add(d)
        db.flush()
        rec.directive_id = d.id
    except Exception as e:
        return f"Tạo việc thất bại: {e}"

    # Báo người nhận + đẩy lên lịch — cả hai fail-soft, việc đã tạo rồi
    try:
        from shared.routers.giao_viec import _notify_assignee
        _notify_assignee(db, d, by=nguoi_duyet)
    except Exception:
        pass
    if rec.han_mong_muon:
        try:
            from shared.services.calendar_sync import upsert_event_from_directive
            upsert_event_from_directive(db, d)
        except Exception:
            pass
    return None


# ── Schemas ───────────────────────────────────────────────────────────────────
class DeXuatCreate(BaseModel):
    tieu_de: str
    loai: str = "cai_tien"
    noi_dung: str
    ket_qua_ky_vong: str
    muc_do: str = "trung"
    han_mong_muon: Optional[date] = None
    ngan_sach_du_kien: Optional[Decimal] = None
    lien_phong_ban: bool = False
    xin_y_kien_ceo: bool = False


class DeXuatReview(BaseModel):
    trang_thai: str            # da_duyet | tu_choi
    nhan_xet_duyet: str = ""
    # Manager thấy việc lớn hơn tưởng → đẩy lên CEO thay vì tự chốt
    day_len_ceo: bool = False


class HistoryEntry(BaseModel):
    level: str
    username: Optional[str] = None
    ho_ten: Optional[str] = None
    action: str                # approve | reject | escalate | cancel
    comment: str = ""
    at: str


class DeXuatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    ho_ten: str
    phong_ban: Optional[str]
    app_name: str
    tieu_de: str
    loai: str
    noi_dung: str
    ket_qua_ky_vong: str
    muc_do: str
    han_mong_muon: Optional[date] = None
    ngan_sach_du_kien: Optional[Decimal] = None
    lien_phong_ban: bool = False
    xin_y_kien_ceo: bool = False
    tep_dinh_kem: List[str] = []
    trang_thai: str
    approval_level: str
    approval_history: List[HistoryEntry] = []
    nguoi_duyet: Optional[str]
    ho_ten_nguoi_duyet: Optional[str]
    nhan_xet_duyet: Optional[str]
    ngay_duyet: Optional[datetime]
    directive_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime


def _tep_dir() -> Path:
    base = Path(settings.upload_dir).expanduser().resolve()
    sub = base / _TEP_SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def _safe_ext(filename: Optional[str]) -> str:
    if not filename:
        return ""
    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_EXT else ""


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/meta")
def meta(user: Annotated[JWTPayload, _AUTH]):
    """Nhãn cho dropdown + user này có duyệt được gì không (để ẩn/hiện tab)."""
    return {
        "loai": [{"ma": k, "ten": v} for k, v in _LOAI_LABELS.items()],
        "muc_do": [{"ma": "thap", "ten": "Thấp"},
                   {"ma": "trung", "ten": "Trung bình"},
                   {"ma": "cao", "ten": "Cao"}],
        "la_nguoi_duyet": _is_any_approver(user),
    }


@router.get("", response_model=List[DeXuatOut])
def list_de_xuat(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = None,
    limit: int = 200,
):
    """Đề xuất CỦA TÔI (mọi trạng thái), mới nhất trước."""
    stmt = select(DeXuat).where(DeXuat.username == user.username)
    if trang_thai:
        stmt = stmt.where(DeXuat.trang_thai == trang_thai)
    stmt = stmt.order_by(DeXuat.id.desc()).limit(max(1, min(limit, 500)))
    return db.execute(stmt).scalars().all()


@router.get("/queue/me", response_model=List[DeXuatOut])
def hang_cho_duyet_cua_toi(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Đề xuất ĐANG CHỜ CHÍNH USER NÀY duyệt — nguồn cho trang Phê Duyệt."""
    if not _is_any_approver(user):
        return []
    rows = db.execute(
        select(DeXuat)
        .where(DeXuat.trang_thai == "cho_duyet")
        .order_by(DeXuat.id.desc())
        .limit(500)
    ).scalars().all()
    return [r for r in rows if _can_approve_at(user, r.approval_level, r, db)]


@router.post("", response_model=DeXuatOut, status_code=status.HTTP_201_CREATED)
def tao_de_xuat(
    body: DeXuatCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    if body.loai not in _LOAI_LABELS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Loại đề xuất không hợp lệ: {body.loai}")
    if body.muc_do not in _MUC_DO:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Mức độ không hợp lệ: {body.muc_do}")
    if not body.tieu_de.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tiêu đề không được để trống")
    if not body.noi_dung.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Nội dung không được để trống")
    if not body.ket_qua_ky_vong.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Kết quả kỳ vọng không được để trống — "
                            "người duyệt cần biết duyệt xong thì đạt được gì")
    if body.ngan_sach_du_kien is not None and body.ngan_sach_du_kien < 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ngân sách không được âm")

    ho_ten, phong_ban, _, _, _ = _lookup_user_info(user.username)
    host = request.headers.get("host", "")
    app_name = host.split(".")[0] if "." in host else (host or "internal")

    rec = DeXuat(
        username=user.username,
        ho_ten=ho_ten or user.username,
        phong_ban=phong_ban,
        app_name=app_name[:32],
        tieu_de=body.tieu_de.strip()[:256],
        loai=body.loai,
        noi_dung=body.noi_dung.strip(),
        ket_qua_ky_vong=body.ket_qua_ky_vong.strip(),
        muc_do=body.muc_do,
        han_mong_muon=body.han_mong_muon,
        ngan_sach_du_kien=body.ngan_sach_du_kien,
        lien_phong_ban=bool(body.lien_phong_ban),
        xin_y_kien_ceo=bool(body.xin_y_kien_ceo),
        tep_dinh_kem=[],
        trang_thai="cho_duyet",
        approval_history=[],
    )
    rec.approval_level = _cap_bat_dau(db, rec)
    db.add(rec)
    db.flush()
    _notify_next_tier(db, rec, by=user.username)
    db.commit()
    db.refresh(rec)
    try:
        from shared.services.activity_logger import log_activity
        log_activity(db, user.username, action="de_xuat_submit", app="shared",
                     ref_type="de_xuat", ref_id=rec.id,
                     metadata={"loai": rec.loai, "muc_do": rec.muc_do})
    except Exception:
        pass
    return rec


@router.get("/{rid}", response_model=DeXuatOut)
def xem_de_xuat(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    rec = db.get(DeXuat, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if rec.username != user.username and not _is_any_approver(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền xem đề xuất này")
    return rec


@router.put("/{rid}/duyet", response_model=DeXuatOut)
def duyet_de_xuat(
    rid: int,
    body: DeXuatReview,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Duyệt / từ chối tại cấp hiện tại. Backend tự suy cấp, client không truyền."""
    if body.trang_thai not in ("da_duyet", "tu_choi"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Trạng thái không hợp lệ")
    rec = db.get(DeXuat, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if rec.trang_thai != "cho_duyet":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Đề xuất đã kết thúc ({rec.trang_thai}), không duyệt thêm được")

    # Tự duyệt: chặn, trừ super-role (họ không có cấp trên) — theo xin_nghi.py
    role = (user.role or "").lower()
    if rec.username == user.username and role not in _SUPER_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Không được tự duyệt đề xuất của mình — để cấp trên duyệt.")

    cap = rec.approval_level
    if cap not in _LEVELS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Cấp duyệt không hợp lệ: {cap}")
    if not _can_approve_at(user, cap, rec, db):
        nhan = {"manager": f"Manager phòng {rec.phong_ban or ''}".strip(), "ceo": "CEO"}
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Bạn không có quyền duyệt ở cấp này — cần {nhan.get(cap, cap)}")

    ho_ten_duyet, _, _, _, _ = _lookup_user_info(user.username)
    ho_ten_duyet = ho_ten_duyet or user.username
    now = datetime.now(timezone.utc)
    tu_choi = body.trang_thai == "tu_choi"
    day_len = bool(body.day_len_ceo) and cap == "manager" and not tu_choi

    entry = {
        "level": cap,
        "username": user.username,
        "ho_ten": ho_ten_duyet,
        "action": "reject" if tu_choi else ("escalate" if day_len else "approve"),
        "comment": (body.nhan_xet_duyet or "").strip(),
        "at": now.isoformat(),
    }
    rec.approval_history = list(rec.approval_history or []) + [entry]

    ghi_chu_viec: Optional[str] = None
    if tu_choi:
        rec.trang_thai = "tu_choi"
        rec.approval_level = "rejected"
    else:
        ke_tiep = "ceo" if day_len else _cap_ke_tiep(rec, cap)
        if ke_tiep == "done":
            rec.trang_thai = "da_duyet"
            rec.approval_level = "done"
            ghi_chu_viec = _sinh_giao_viec(db, rec, nguoi_duyet=user.username)
            if ghi_chu_viec:
                rec.approval_history = list(rec.approval_history) + [{
                    "level": "done", "username": None, "ho_ten": None,
                    "action": "no_task", "comment": ghi_chu_viec,
                    "at": datetime.now(timezone.utc).isoformat(),
                }]
        else:
            rec.approval_level = ke_tiep   # giữ trang_thai='cho_duyet'

    rec.nguoi_duyet = user.username
    rec.ho_ten_nguoi_duyet = ho_ten_duyet
    rec.nhan_xet_duyet = entry["comment"]
    rec.ngay_duyet = now

    db.flush()
    _notify_next_tier(db, rec, by=user.username)
    db.commit()
    db.refresh(rec)
    try:
        from shared.services.activity_logger import log_activity
        log_activity(db, user.username,
                     action=("de_xuat_reject" if tu_choi else "de_xuat_approve"),
                     app="shared", ref_type="de_xuat", ref_id=rec.id,
                     metadata={"at_level": cap, "directive_id": rec.directive_id})
    except Exception:
        pass
    return rec


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def huy_de_xuat(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Người gửi tự rút lại đề xuất khi CHƯA ai duyệt."""
    rec = db.get(DeXuat, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if rec.username != user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ người gửi mới rút được đề xuất")
    if rec.trang_thai != "cho_duyet":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Đề xuất đã kết thúc ({rec.trang_thai}), không rút được")
    rec.trang_thai = "huy"
    rec.approval_level = "rejected"
    rec.approval_history = list(rec.approval_history or []) + [{
        "level": rec.approval_level, "username": user.username,
        "ho_ten": rec.ho_ten, "action": "cancel", "comment": "Người gửi tự rút",
        "at": datetime.now(timezone.utc).isoformat(),
    }]
    db.commit()
    return None


# ── Tệp đính kèm ──────────────────────────────────────────────────────────────
@router.post("/{rid}/tep", response_model=DeXuatOut)
async def upload_tep(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    rec = db.get(DeXuat, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if rec.username != user.username and not _is_any_approver(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền đính kèm tệp")

    ext = _safe_ext(file.filename)
    if not ext:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Định dạng không hỗ trợ. Chỉ nhận: {sorted(_ALLOWED_EXT)}")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tệp trống")
    if len(data) > _MAX_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Tệp quá lớn — tối đa {_MAX_BYTES // (1024*1024)}MB")

    fname = f"{rid}_{uuid.uuid4().hex[:12]}{ext}"
    (_tep_dir() / fname).write_bytes(data)
    rec.tep_dinh_kem = list(rec.tep_dinh_kem or []) + [f"/api/de-xuat/tep/{fname}"]
    db.commit()
    db.refresh(rec)
    return rec


@router.get("/tep/{fname}")
def tai_tep(
    fname: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Phục vụ tệp đính kèm — cùng luật xem với `GET /api/de-xuat/{id}` (:497).

    Siết 12/09/2026: trước đó chỉ cần đăng nhập là tải được tệp của đề xuất người khác —
    đã thử thật ở dev, nv26018 lấy được tệp của đề xuất #13. Tên tệp có dạng
    `<id đề xuất>_<12hex>.<ext>` (xem upload :639) nên tra ngược id để áp đúng luật đó.
    """
    if "/" in fname or "\\" in fname or ".." in fname:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên tệp không hợp lệ")
    so = fname.split("_", 1)[0]
    if not so.isdigit():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên tệp không hợp lệ")
    rec = db.get(DeXuat, int(so))
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tệp không tồn tại")
    if rec.username != user.username and not _is_any_approver(user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Không có quyền xem tệp của đề xuất này"
        )
    p = _tep_dir() / fname
    if not p.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tệp không tồn tại")
    return FileResponse(p, headers={"X-Content-Type-Options": "nosniff"})
