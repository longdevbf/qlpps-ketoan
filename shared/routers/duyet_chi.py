"""Duyệt Chi API — cross-app expense request workflow.

Flow (anh Quang chốt 2026-06-01, manager app-scoped):
  NV đề xuất → Manager app → Kế Toán → Mai (≤ hạn mức) HOẶC CEO (vượt hạn) → done.

  - Manager: bất kỳ manager/leader có app_name của rec trong apps đều duyệt được
    (không strict phong_ban — 1 app có nhiều sub-phong_ban không phải cái nào cũng
    có manager riêng; strict equality làm rec từ sub-phong_ban không có manager
    bị kẹt). NV không có phong_ban → skip thẳng KT.
  - Mai auto-approve khi item ở approval_level='ceo' (sau khi KT đã duyệt)
    + số tiền ≤ duyet_chi.max_amount. Vượt hạn → escalate, CEO duyệt tay.

Reject ở bất kỳ cấp nào → kết thúc.

Mounted at /api/duyet-chi trong: baogia, marketing, muahang, hcns, ketoan,
saleadmin, ceo.
"""
import calendar
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as sqlfunc, select, text as sql_text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models.expense_request import ExpenseRequest
from shared.models.user import User
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)

_CHUNG_TU_SUBDIR = "duyet_chi"
_ALLOWED_EXT = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"}
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

# Role buckets
_CEO_ROLES = {"ceo", "admin", "assistant_ceo"}
_MANAGER_ROLES = {"manager", "leader", "admin", "ceo", "assistant_ceo"}

# Chuỗi cấp duyệt: NV → Manager phòng → KT → CEO
# (Bản 28/05/2026 từng gỡ Manager — khôi phục 30/05 vì manager phòng phải duyệt
# đơn chi của NV phòng mình trước khi sang KT, đúng workflow tài chính nội bộ.)
_LEVELS = ("manager", "ketoan", "ceo")
_NEXT_LEVEL = {"manager": "ketoan", "ketoan": "ceo", "ceo": "done"}

_LOAI_CHI_LABELS = {
    "di_chuyen": "Di Chuyển / Xăng xe",
    "van_phong": "Văn Phòng Phẩm",
    "tiep_thi": "Tiếp Thị / Quảng cáo",
    "dao_tao": "Đào Tạo",
    "khach_hang": "Tiếp Khách",
    "khac": "Chi Phí Khác",
}


# ── Helpers RBAC ──────────────────────────────────────────────────────────────
def _is_ceo(user: JWTPayload) -> bool:
    return (user.role or "").lower() in _CEO_ROLES


def _user_phong_ban(username: str) -> Optional[str]:
    """Lấy phong_ban của user từ hcns.employees (qua _lookup_user_info cache)."""
    if not username:
        return None
    _, pb, _, _, _ = _lookup_user_info(username)
    return pb or None


def _user_apps(db: Session, username: str) -> set[str]:
    """Trả set apps user được phép truy cập (shared.users.apps)."""
    if not username:
        return set()
    row = db.execute(
        select(User.apps).where(User.username == username).limit(1)
    ).first()
    if row and row[0]:
        return {str(a).lower() for a in row[0]}
    return set()


def _dept_has_manager(db: Session, phong_ban: Optional[str]) -> bool:
    """Phòng ban `phong_ban` có manager/leader active không?

    Anh Quang 2026-07-02: nhiều phòng KHÔNG có manager → đề xuất chi kẹt mãi ở
    cấp 'manager'. Dùng hàm này để quyết định: phòng có manager → bắt đầu ở
    'manager'; phòng KHÔNG có manager → skip thẳng lên 'ketoan'.
    """
    if not phong_ban or not phong_ban.strip():
        return False
    pb = phong_ban.strip()
    rows = db.execute(
        select(User.username)
        .where(User.role.in_(("manager", "leader")))
        .where(User.active.is_(True))
    ).all()
    for (uname,) in rows:
        if _user_phong_ban(uname) == pb:
            return True
    return False


def _can_approve_at(user: JWTPayload, level: str, rec: ExpenseRequest, db: Session) -> bool:
    """Check user có quyền duyệt rec tại level hiện tại không.

    Flow 2026-06-01 (manager app-scoped): NV → Manager app → KT → Mai/CEO → done.
    - level='manager': manager/leader có app_name của rec trong apps.
        Lý do dùng app thay vì phong_ban: 1 app có nhiều sub-phong_ban (vd marketing
        có "Marketing", "Quảng Cáo Ads", "Media", "Tư Vấn"…) nhưng chỉ vài cái có
        manager riêng. Strict phong_ban equality làm rec từ sub-phong_ban không có
        manager bị KẸT mãi. App-scope cho manager bao quát cả app.
    - level='ketoan' : admin/ceo/assistant_ceo OR (apps chứa 'ketoan' + role manager/leader/kt)
    - level='ceo'    : admin/ceo/assistant_ceo (Mai cũng duyệt ở level này nhưng qua execute_override)
    """
    role = (user.role or "").lower()
    if role in _CEO_ROLES:
        return True
    if level == "manager":
        if role not in {"manager", "leader"}:
            return False
        # Dept-scoped (2026-06-16): manager chỉ duyệt đề xuất CÙNG phòng ban mình.
        pb = _user_phong_ban(user.username)
        return bool(pb) and (rec.phong_ban or "") == pb
    if level == "ceo":
        return False  # chỉ CEO mới duyệt cấp CEO
    if level == "ketoan":
        if role not in {"manager", "leader", "kt"}:
            return False
        return "ketoan" in _user_apps(db, user.username)
    return False


def _is_any_approver(user: JWTPayload) -> bool:
    """User có khả năng duyệt tối thiểu 1 cấp (cho list filter).

    - CEO roles: duyệt cấp ceo (cuối)
    - manager/leader: duyệt cấp manager (đầu)
    - kt (kế toán): duyệt cấp ketoan (giữa)
    """
    role = (user.role or "").lower()
    if role in _CEO_ROLES:
        return True
    if role in {"manager", "leader", "kt"}:
        return True
    return False


def _approver_app_scope(user: JWTPayload) -> Optional[set[str]]:
    """Trả set app_name approver được xem.

    - admin/ceo/assistant_ceo                      → `None` (cross-app)
    - kt (kế toán)                                  → `None` (cross-app)
    - manager/leader có 'ketoan' trong JWT.apps    → `None` (KT manager/leader
      quản lý dòng tiền toàn công ty → cross-app, không bị filter theo phòng)
    - manager/leader thường                        → set apps trong JWT.apps
    """
    role = (user.role or "").lower()
    if role in _CEO_ROLES or role == "kt":
        return None
    user_apps = {(a or "").lower() for a in (user.apps or []) if a}
    if role in ("manager", "leader") and "ketoan" in user_apps:
        return None
    return user_apps


def _approver_dept_scope(user: JWTPayload, db: Session) -> Optional[set[str]]:
    """Phạm vi XEM theo PHÒNG BAN (2026-06-16, thay app-scope).

    - admin/ceo/assistant_ceo + kt → None (thấy TOÀN BỘ — phục vụ cấp ketoan/ceo,
      và CEO duyệt được mọi cấp nên đề xuất không bị kẹt).
    - manager/leader CÓ app 'ketoan' → None (kế toán duyệt dòng tiền TOÀN CÔNG TY,
      cross-dept; nếu giới hạn theo phòng riêng sẽ KẸT đơn của phòng khác ở cấp
      'ketoan' — đúng bug 2026-06-19: KT không thấy đơn marketing/saleadmin).
    - manager/leader thường        → chỉ phòng ban của chính mình.
    """
    role = (user.role or "").lower()
    if role in _CEO_ROLES or role == "kt":
        return None
    if role in ("manager", "leader") and "ketoan" in _user_apps(db, user.username):
        return None
    pb = _user_phong_ban(user.username)
    return {pb} if pb else set()


def _duoc_dung_chung_tu(user: JWTPayload, rec: ExpenseRequest, db: Session) -> bool:
    """Người gửi đơn, hoặc người duyệt CÓ đơn này trong phạm vi phòng ban của mình.

    Siết 12/09/2026: trước đó ba chỗ (đính kèm / xoá / tải chứng từ) chỉ hỏi
    `_is_any_approver`, nghĩa là mọi manager, leader hay kế toán của BẤT KỲ phòng nào
    cũng sửa được chứng từ đơn người khác — xoá không kèm tên tệp còn xoá sạch cả list.
    Nay dùng đúng phạm vi xem của `GET /api/duyet-chi` (:361-370).
    """
    if rec.username == user.username:
        return True
    if not _is_any_approver(user):
        return False
    pham_vi = _approver_dept_scope(user, db)
    return pham_vi is None or (rec.phong_ban or "") in pham_vi


# ── Schemas ───────────────────────────────────────────────────────────────────
class ExpenseCreate(BaseModel):
    tieu_de: str
    loai_chi: str
    so_tien: Decimal
    ngay_de_xuat: date
    han_thanh_toan: Optional[date] = None
    muc_dich: str
    ghi_chu: str = ""


class ExpenseReview(BaseModel):
    trang_thai: str  # da_duyet | tu_choi (giữ tương thích UI cũ)
    nhan_xet_duyet: str = ""
    han_thanh_toan: Optional[date] = None


class HistoryEntry(BaseModel):
    level: str
    # username + ho_ten optional vì có entry migration (vd flow_change 2026-05-28)
    # không có actor cụ thể — chỉ ghi system message.
    username: Optional[str] = None
    ho_ten: Optional[str] = None
    action: str  # approve | reject | migrated_to_ketoan | ...
    comment: str = ""
    at: str  # ISO datetime


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    ho_ten: str
    phong_ban: Optional[str]
    app_name: str
    tieu_de: str
    loai_chi: str
    so_tien: Decimal
    ngay_de_xuat: date
    han_thanh_toan: Optional[date] = None
    muc_dich: str
    ghi_chu: Optional[str]
    chung_tu_url: Optional[str] = None
    chung_tu_urls: List[str] = []
    trang_thai: str
    approval_level: str
    approval_history: List[HistoryEntry] = []
    nguoi_duyet: Optional[str]
    ho_ten_nguoi_duyet: Optional[str]
    nhan_xet_duyet: Optional[str]
    ngay_duyet: Optional[datetime]
    da_chi: bool = False
    chi_phi_id: Optional[int] = None
    tai_khoan_chi: Optional[str] = None
    ngay_chi: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


def _chung_tu_dir() -> Path:
    base = Path(settings.upload_dir).expanduser().resolve()
    sub = base / _CHUNG_TU_SUBDIR
    sub.mkdir(parents=True, exist_ok=True)
    return sub


def _safe_ext(filename: Optional[str]) -> str:
    if not filename:
        return ""
    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_EXT else ""


# ── Notify helpers ────────────────────────────────────────────────────────────
def _notify_next_tier(db: Session, rec: ExpenseRequest, *, by: str):
    """Tạo noti cho cấp duyệt tiếp theo, hoặc cho requester nếu đã done/rejected."""
    try:
        from shared.services.notify import notify, notify_many
    except Exception:
        return
    title_prefix = f"[Duyệt Chi #{rec.id}]"
    url = f"/duyet-chi#id={rec.id}"

    lvl = rec.approval_level
    if lvl == "done":
        notify(
            db, target=rec.username, source_app=rec.app_name,
            event_type="expense:approved",
            title=f"{title_prefix} CEO đã duyệt — đề xuất hoàn tất",
            message=f"{rec.tieu_de} • {int(rec.so_tien):,}đ",
            ref_type="expense_request", ref_id=rec.id, url=url, severity="success",
            created_by=by,
        )
        return
    if lvl == "rejected":
        last = (rec.approval_history or [])[-1] if rec.approval_history else {}
        rejecter = last.get("ho_ten") or last.get("username") or by
        notify(
            db, target=rec.username, source_app=rec.app_name,
            event_type="expense:rejected",
            title=f"{title_prefix} Bị từ chối bởi {rejecter}",
            message=last.get("comment", ""),
            ref_type="expense_request", ref_id=rec.id, url=url, severity="warning",
            created_by=by,
        )
        return

    # lvl ∈ {manager, ketoan, ceo} → tìm target tier
    targets: list[str] = []
    if lvl == "manager" and rec.phong_ban:
        # Dept-scoped (2026-06-16): notify manager/leader CÙNG phòng ban với rec.
        rows = db.execute(
            select(User.username)
            .where(User.role.in_(("manager", "leader")))
            .where(User.active.is_(True))
        ).all()
        for r in rows:
            uname = r[0]
            if _user_phong_ban(uname) == rec.phong_ban:
                targets.append(uname)
    elif lvl == "ketoan":
        rows = db.execute(
            select(User.username)
            .where(User.role.in_(("manager", "leader", "admin", "ceo", "assistant_ceo")))
            .where(User.active.is_(True))
        ).all()
        # Filter có apps chứa 'ketoan'
        for r in rows:
            uname = r[0]
            apps = _user_apps(db, uname)
            if "ketoan" in apps:
                targets.append(uname)
    elif lvl == "ceo":
        rows = db.execute(
            select(User.username)
            .where(User.role.in_(tuple(_CEO_ROLES)))
            .where(User.active.is_(True))
        ).all()
        targets = [r[0] for r in rows if r[0]]

    if not targets:
        return
    label = {"manager": "Manager phòng", "ketoan": "Kế Toán", "ceo": "CEO"}.get(lvl, lvl)
    notify_many(
        db, targets, exclude=[by],
        source_app=rec.app_name,
        event_type=f"expense:pending_{lvl}",
        title=f"{title_prefix} Chờ {label} duyệt",
        message=f"{rec.ho_ten} • {rec.tieu_de} • {int(rec.so_tien):,}đ",
        ref_type="expense_request", ref_id=rec.id, url=url, severity="info",
        created_by=by,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("", response_model=List[ExpenseOut])
def list_expense_requests(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = None,
    approval_level: Optional[str] = None,
    phong_ban: Optional[str] = None,
    username: Optional[str] = None,
    thang: Optional[str] = None,  # "YYYY-MM"
    loai_chi: Optional[str] = None,
):
    stmt = select(ExpenseRequest).order_by(ExpenseRequest.created_at.desc())
    if not _is_any_approver(user):
        stmt = stmt.where(ExpenseRequest.username == user.username)
    else:
        # Dept-scoped (2026-06-16): manager/leader chỉ thấy đề xuất CÙNG phòng ban.
        # Admin/CEO/Assistant CEO + KT thấy hết (duyệt cấp ketoan/ceo, không kẹt).
        scope = _approver_dept_scope(user, db)
        if scope is not None:
            if not scope:
                return []
            stmt = stmt.where(ExpenseRequest.phong_ban.in_(scope))
        if username:
            stmt = stmt.where(ExpenseRequest.username == username)
        if phong_ban:
            stmt = stmt.where(ExpenseRequest.phong_ban == phong_ban)
    if trang_thai:
        stmt = stmt.where(ExpenseRequest.trang_thai == trang_thai)
    if approval_level:
        stmt = stmt.where(ExpenseRequest.approval_level == approval_level)
    if loai_chi:
        stmt = stmt.where(ExpenseRequest.loai_chi == loai_chi)
    if thang:
        try:
            y, m = thang.split("-")
            last_day = calendar.monthrange(int(y), int(m))[1]
            stmt = stmt.where(
                ExpenseRequest.ngay_de_xuat >= date(int(y), int(m), 1)
            ).where(
                ExpenseRequest.ngay_de_xuat <= date(int(y), int(m), last_day)
            )
        except Exception:
            pass
    return db.execute(stmt).scalars().all()


@router.get("/queue/me", response_model=List[ExpenseOut])
def my_approval_queue(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Đơn user hiện tại cần duyệt (theo cấp + role + phòng/apps)."""
    queue: list[ExpenseRequest] = []
    all_pending = db.execute(
        select(ExpenseRequest)
        .where(ExpenseRequest.trang_thai == "cho_duyet")
        .order_by(ExpenseRequest.created_at.desc())
    ).scalars().all()
    for rec in all_pending:
        if rec.username == user.username:
            continue  # không tự duyệt
        if _can_approve_at(user, rec.approval_level, rec, db):
            queue.append(rec)
    return queue


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def create_expense_request(
    body: ExpenseCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    if body.loai_chi not in _LOAI_CHI_LABELS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Loại chi không hợp lệ: {body.loai_chi}",
        )
    if not body.tieu_de.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Tiêu đề không được để trống")
    if not body.muc_dich.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Mục đích không được để trống")
    if body.so_tien <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Số tiền phải > 0")

    ho_ten, phong_ban, _, _, _ = _lookup_user_info(user.username)
    host = request.headers.get("host", "")
    app_name = host.split(".")[0] if "." in host else (host or "internal")

    # Start at 'manager' CHỈ khi phòng ban có manager/leader thật; nếu phòng
    # KHÔNG có manager (hoặc user không gắn phòng) → skip thẳng lên 'ketoan'
    # (anh Quang 2026-07-02 — tránh kẹt đề xuất ở phòng không có manager).
    initial_level = "manager" if _dept_has_manager(db, phong_ban) else "ketoan"
    rec = ExpenseRequest(
        username=user.username,
        ho_ten=ho_ten or user.username,
        phong_ban=phong_ban,
        app_name=app_name,
        tieu_de=body.tieu_de.strip(),
        loai_chi=body.loai_chi,
        so_tien=body.so_tien,
        ngay_de_xuat=body.ngay_de_xuat,
        han_thanh_toan=body.han_thanh_toan,
        muc_dich=body.muc_dich.strip(),
        ghi_chu=(body.ghi_chu or "").strip(),
        trang_thai="cho_duyet",
        approval_level=initial_level,
        approval_history=[],
    )
    db.add(rec)
    db.flush()
    _notify_next_tier(db, rec, by=user.username)
    db.commit()
    db.refresh(rec)
    try:
        from shared.services.activity_logger import log_activity
        log_activity(db, user.username, action="expense_submit", app="shared",
                     ref_type="expense_request", ref_id=rec.id,
                     metadata={"so_tien": float(rec.so_tien or 0),
                               "loai_chi": rec.loai_chi})
    except Exception:
        pass
    return rec


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_expense_request(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    rec = db.get(ExpenseRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    # Chỉ owner mới cancel; CEO/admin có thể force cancel
    if rec.username != user.username and not _is_ceo(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền hủy đề xuất này")
    # Flow 2026-05-30: NV → Manager phòng → KT → CEO. Cho hủy khi đơn còn ở
    # cấp đầu tiên (manager hoặc ketoan nếu user không có phong_ban) và chưa
    # có ai duyệt thật (approval_history rỗng kiểm tiếp ở dưới).
    if rec.trang_thai != "cho_duyet" or rec.approval_level not in ("manager", "ketoan"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Chỉ có thể hủy đề xuất chưa qua duyệt",
        )
    if rec.approval_history:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Đề xuất đã có lịch sử duyệt, không thể hủy",
        )
    db.delete(rec)
    db.commit()


@router.put("/{rid}/duyet", response_model=ExpenseOut)
def duyet_expense_request(
    rid: int,
    body: ExpenseReview,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Duyệt/từ chối tại cấp hiện tại của rec. Tự động chuyển cấp tiếp theo.

    User KHÔNG cần chỉ định level — backend tự suy từ rec.approval_level và
    enforce quyền theo `_can_approve_at`.
    """
    if body.trang_thai not in ("da_duyet", "tu_choi"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Trạng thái không hợp lệ")
    rec = db.get(ExpenseRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if rec.trang_thai != "cho_duyet":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Đề xuất đã kết thúc ({rec.trang_thai}), không thể duyệt thêm",
        )
    if rec.username == user.username:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không thể tự duyệt đề xuất của mình")

    curr_level = rec.approval_level  # manager | ketoan | ceo
    if curr_level not in _LEVELS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Cấp duyệt hiện tại không hợp lệ: {curr_level}",
        )
    if not _can_approve_at(user, curr_level, rec, db):
        label = {"manager": "Manager phòng " + (rec.phong_ban or ""),
                 "ketoan": "Kế Toán", "ceo": "CEO"}.get(curr_level, curr_level)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Bạn không có quyền duyệt ở cấp này — cần {label}",
        )

    ho_ten_duyet, _, _, _, _ = _lookup_user_info(user.username)
    ho_ten_duyet = ho_ten_duyet or user.username
    now = datetime.now(timezone.utc)
    action = "approve" if body.trang_thai == "da_duyet" else "reject"
    entry = {
        "level": curr_level,
        "username": user.username,
        "ho_ten": ho_ten_duyet,
        "action": action,
        "comment": (body.nhan_xet_duyet or "").strip(),
        "at": now.isoformat(),
    }
    # Append history (immutable list assignment để SQLAlchemy detect)
    rec.approval_history = list(rec.approval_history or []) + [entry]

    if action == "reject":
        rec.trang_thai = "tu_choi"
        rec.approval_level = "rejected"
    else:
        nxt = _NEXT_LEVEL[curr_level]
        if nxt == "done":
            rec.trang_thai = "da_duyet"
            rec.approval_level = "done"
        else:
            rec.approval_level = nxt
            # giữ trang_thai='cho_duyet' đi tiếp

    # Backward-compat fields (UI cũ đọc) — luôn lưu approver gần nhất
    rec.nguoi_duyet = user.username
    rec.ho_ten_nguoi_duyet = ho_ten_duyet
    rec.nhan_xet_duyet = entry["comment"]
    rec.ngay_duyet = now
    if body.han_thanh_toan is not None:
        rec.han_thanh_toan = body.han_thanh_toan

    db.flush()
    _notify_next_tier(db, rec, by=user.username)
    db.commit()
    db.refresh(rec)
    try:
        from shared.services.activity_logger import log_activity
        log_activity(db, user.username,
                     action=("expense_approve" if action == "approve" else "expense_reject"),
                     app="shared", ref_type="expense_request", ref_id=rec.id,
                     metadata={"at_level": curr_level,
                               "so_tien": float(rec.so_tien or 0)})
    except Exception:
        pass
    return rec


# ── Chứng từ thanh toán: upload + serve ──────────────────────────────────────
@router.post("/{rid}/chung-tu", response_model=ExpenseOut)
async def upload_chung_tu(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    file: UploadFile = File(...),
):
    """Upload file chứng từ thanh toán (PDF/ảnh). Owner hoặc approver mới được."""
    rec = db.get(ExpenseRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if not _duoc_dung_chung_tu(user, rec, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền upload chứng từ")

    ext = _safe_ext(file.filename)
    if not ext:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Định dạng file không hỗ trợ. Chỉ chấp nhận: {sorted(_ALLOWED_EXT)}",
        )
    data = await file.read()
    if len(data) > _MAX_BYTES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"File quá lớn — tối đa {_MAX_BYTES // (1024*1024)}MB",
        )
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File trống")

    fname = f"{rid}_{uuid.uuid4().hex[:12]}{ext}"
    dest = _chung_tu_dir() / fname
    dest.write_bytes(data)

    # Append vào list (không xoá file cũ — multi-upload)
    new_url = f"/api/duyet-chi/chung-tu/{fname}"
    existing = list(rec.chung_tu_urls or [])
    if new_url not in existing:
        existing.append(new_url)
    rec.chung_tu_urls = existing
    # Legacy field — giữ là url đầu tiên cho FE cũ chưa update
    if not rec.chung_tu_url:
        rec.chung_tu_url = new_url

    # SQLAlchemy mutable tracking trên JSONB cần flag
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(rec, "chung_tu_urls")

    db.commit()
    db.refresh(rec)
    return rec


@router.delete("/{rid}/chung-tu", response_model=ExpenseOut)
def delete_chung_tu(
    rid: int,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    filename: Optional[str] = None,
):
    """Xoá chứng từ. Không có `filename` query → xoá HẾT (legacy).
    Có `filename` → chỉ xoá file cụ thể trong list (multi-upload).
    """
    rec = db.get(ExpenseRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if not _duoc_dung_chung_tu(user, rec, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không có quyền")

    def _unlink_url(u: str) -> None:
        old_name = u.rsplit("/", 1)[-1]
        old_path = _chung_tu_dir() / old_name
        if old_path.exists():
            try:
                old_path.unlink()
            except OSError:
                pass

    urls = list(rec.chung_tu_urls or [])
    if filename:
        # Xoá 1 file cụ thể
        target = next((u for u in urls if u.endswith(f"/{filename}")), None)
        if not target:
            # Có thể legacy chỉ ở chung_tu_url
            if rec.chung_tu_url and rec.chung_tu_url.endswith(f"/{filename}"):
                _unlink_url(rec.chung_tu_url)
                rec.chung_tu_url = None
        else:
            _unlink_url(target)
            urls = [u for u in urls if u != target]
            rec.chung_tu_urls = urls
            if rec.chung_tu_url == target:
                rec.chung_tu_url = urls[0] if urls else None
    else:
        # Xoá hết
        for u in urls:
            _unlink_url(u)
        if rec.chung_tu_url and rec.chung_tu_url not in urls:
            _unlink_url(rec.chung_tu_url)
        rec.chung_tu_urls = []
        rec.chung_tu_url = None

    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(rec, "chung_tu_urls")

    db.commit()
    db.refresh(rec)
    return rec


@router.get("/chung-tu/{filename}")
def serve_chung_tu(
    filename: str,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Serve file chứng từ — chỉ người gửi đơn, hoặc người duyệt trong phạm vi phòng ban.

    Siết 12/09/2026: trước đó hàm chỉ hỏi "đã đăng nhập chưa", nên một nhân viên bất kỳ
    tải được chứng từ thanh toán của đơn người khác chỉ cần biết tên tệp — đã thử thật ở
    dev, nv26018 (Nhân Sự) lấy được tệp của đơn #168 phòng Mua Hàng. Tên tệp có dạng
    `<id đơn>_<12hex>.<ext>` (xem upload :623) nên tra ngược id rồi áp ĐÚNG luật xem của
    `GET /api/duyet-chi` (:361-370) thay vì nghĩ ra luật mới.
    """
    khop = re.fullmatch(r"([0-9]+)_[a-f0-9]{6,32}\.[a-z0-9]{2,5}", filename)
    if not khop:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tên file không hợp lệ")
    rec = db.get(ExpenseRequest, int(khop.group(1)))
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File không tồn tại")
    if rec.username != user.username:
        # `_approver_dept_scope` trả None = xem được tất cả (admin/ceo/kt), set rỗng = không
        # phòng nào. Người không duyệt được cấp nào thì chặn thẳng.
        pham_vi = _approver_dept_scope(user, db) if _is_any_approver(user) else set()
        if pham_vi is not None and (rec.phong_ban or "") not in pham_vi:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Không có quyền xem chứng từ của đơn này"
            )
    fpath = _chung_tu_dir() / filename
    if not fpath.exists() or not fpath.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File không tồn tại")
    return FileResponse(str(fpath), headers={"X-Content-Type-Options": "nosniff"})


@router.get("/stats")
def expense_stats(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    """Stats cá nhân + pending count theo cấp (cho approver)."""
    own = db.execute(
        select(ExpenseRequest.trang_thai, sqlfunc.count().label("cnt"))
        .where(ExpenseRequest.username == user.username)
        .group_by(ExpenseRequest.trang_thai)
    ).all()
    result: dict = {"cho_duyet": 0, "da_duyet": 0, "tu_choi": 0}
    for row in own:
        result[row.trang_thai] = row.cnt
    if _is_any_approver(user):
        # Pending toàn hệ thống theo cấp
        rows = db.execute(
            select(ExpenseRequest.approval_level, sqlfunc.count())
            .where(ExpenseRequest.trang_thai == "cho_duyet")
            .group_by(ExpenseRequest.approval_level)
        ).all()
        by_level = {r[0]: r[1] for r in rows}
        result["pending_manager"] = by_level.get("manager", 0)
        result["pending_ketoan"] = by_level.get("ketoan", 0)
        result["pending_ceo"] = by_level.get("ceo", 0)
        result["pending_all"] = sum(by_level.values())
        # Pending của user (đơn user phải duyệt)
        try:
            queue = my_approval_queue.__wrapped__(user, db)  # type: ignore[attr-defined]
        except Exception:
            queue = []
        result["pending_for_me"] = len(queue) if isinstance(queue, list) else 0
    return result


@router.get("/report")
def expense_report(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    thang: Optional[str] = None,
    phong_ban: Optional[str] = None,
    approval_level: Optional[str] = None,
    trang_thai: Optional[str] = None,
):
    """Báo cáo tổng hợp duyệt chi — cho KT & CEO dashboard.

    Trả về:
    - summary: tổng số đơn, tổng tiền theo trạng thái + cấp
    - by_phong_ban: breakdown theo phòng (tổng, đã duyệt, đang chờ, từ chối, sum tiền)
    - by_loai_chi: breakdown theo loại chi
    - sla: thời gian trung bình từ create→done (giờ)
    """
    if not _is_any_approver(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ approver được xem báo cáo")

    stmt = select(ExpenseRequest)
    if phong_ban:
        stmt = stmt.where(ExpenseRequest.phong_ban == phong_ban)
    if approval_level:
        stmt = stmt.where(ExpenseRequest.approval_level == approval_level)
    if trang_thai:
        stmt = stmt.where(ExpenseRequest.trang_thai == trang_thai)
    if thang:
        try:
            y, m = thang.split("-")
            last_day = calendar.monthrange(int(y), int(m))[1]
            stmt = stmt.where(
                ExpenseRequest.ngay_de_xuat >= date(int(y), int(m), 1)
            ).where(
                ExpenseRequest.ngay_de_xuat <= date(int(y), int(m), last_day)
            )
        except Exception:
            pass
    rows = db.execute(stmt).scalars().all()

    summary = {
        "total": len(rows),
        "total_amount": int(sum(int(r.so_tien) for r in rows)),
        "by_trang_thai": {},
        "by_level": {},
    }
    by_pb: dict = {}
    by_loai: dict = {}
    sla_hours: list[float] = []
    for r in rows:
        ts = r.trang_thai
        summary["by_trang_thai"][ts] = summary["by_trang_thai"].get(ts, 0) + 1
        lv = r.approval_level
        summary["by_level"][lv] = summary["by_level"].get(lv, 0) + 1
        pb = r.phong_ban or "(Không rõ)"
        if pb not in by_pb:
            by_pb[pb] = {"total": 0, "amount": 0, "da_duyet": 0, "tu_choi": 0, "cho_duyet": 0}
        by_pb[pb]["total"] += 1
        by_pb[pb]["amount"] += int(r.so_tien)
        by_pb[pb][r.trang_thai] = by_pb[pb].get(r.trang_thai, 0) + 1
        lc = r.loai_chi
        if lc not in by_loai:
            by_loai[lc] = {"total": 0, "amount": 0, "label": _LOAI_CHI_LABELS.get(lc, lc)}
        by_loai[lc]["total"] += 1
        by_loai[lc]["amount"] += int(r.so_tien)
        # SLA: chỉ tính khi đã done
        if r.trang_thai == "da_duyet" and r.ngay_duyet and r.created_at:
            try:
                delta = (r.ngay_duyet - r.created_at).total_seconds() / 3600.0
                if delta > 0:
                    sla_hours.append(delta)
            except Exception:
                pass

    sla_avg = round(sum(sla_hours) / len(sla_hours), 1) if sla_hours else None

    return {
        "summary": summary,
        "by_phong_ban": by_pb,
        "by_loai_chi": by_loai,
        "sla_hours_avg": sla_avg,
        "sla_sample_size": len(sla_hours),
    }


# ── CHI (Kế Toán chi đề xuất đã duyệt xong → sổ quỹ) ─────────────────────────
# anh Quang 2026-08-11: sau khi CEO duyệt (approval_level='done'), KT bấm "Chi"
# tại đề xuất → tạo ketoan.chi_phi_phat_sinh (→ tự sinh SoQuy chi, trừ tài khoản)
# + đánh dấu da_chi. Idempotent (không chi 2 lần).
_LOAI_CHI_MAP = {
    "di_chuyen":  ("Chi phí đi lại", "quan_ly"),
    "van_phong":  ("Chi phí văn phòng", "quan_ly"),
    "tiep_thi":   ("Chi phí tiếp thị", "ban_hang"),
    "dao_tao":    ("Chi phí đào tạo", "quan_ly"),
    "khach_hang": ("Chi phí khách hàng", "ban_hang"),
    "khac":       ("Chi phí khác", "khac"),
}


class ChiBody(BaseModel):
    tai_khoan: str
    ghi_chu: Optional[str] = None


def _can_chi(user: JWTPayload, db: Session) -> bool:
    """Được bấm Chi: CEO/admin, HOẶC người duyệt cấp Kế toán (manager/leader/kt CÓ app 'ketoan').

    Vá 16/09/2026: trước chỉ cần có app 'ketoan' là chi được — nhân viên thường được cấp app
    Kế toán để xem cũng bấm chi được tiền (lỗ tái hiện 12/09). Nay đúng cổng cấp Kế toán của
    `_can_approve_at` (role + app). Kiểm prod 14/09: người có app ketoan chỉ là ceo/manager/admin,
    120 ngày qua người tạo phiếu chi = manager 199, ceo 1 → không chặn nhầm ai.
    """
    role = (user.role or "").lower()
    if role in _CEO_ROLES:
        return True
    return role in {"manager", "leader", "kt"} and "ketoan" in _user_apps(db, user.username)


@router.post("/{rid}/chi", response_model=ExpenseOut)
def chi_expense(
    rid: int,
    body: ChiBody,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[JWTPayload, _AUTH],
):
    if not _can_chi(user, db):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ Kế Toán được chi đề xuất")
    rec = db.get(ExpenseRequest, rid)
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if (rec.approval_level or "") != "done":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Đề xuất chưa duyệt xong (cần CEO duyệt) — chưa thể chi")
    if getattr(rec, "da_chi", False):
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề xuất này đã chi rồi")
    tk = (body.tai_khoan or "").strip()
    if not tk:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Vui lòng chọn tài khoản chi")

    try:
        from ketoan.app.models import ChiPhiPhatSinh
        from ketoan.app.services.so_quy_auto import sync_so_quy_from_chi_phi, assert_du_chi
    except Exception as e:  # pragma: no cover
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            f"Không nạp được module Kế Toán: {e}")
    # CHẶN chi làm số dư TK âm (anh Quang 2026-08-27)
    assert_du_chi(db, tk, rec.so_tien)

    loai_ten, nhom = _LOAI_CHI_MAP.get((rec.loai_chi or "").strip(),
                                       ("Chi phí khác", "khac"))
    _gc = f"Chi đề xuất #{rec.id} • {rec.username}"
    if body.ghi_chu:
        _gc += f" • {body.ghi_chu.strip()}"
    cp = ChiPhiPhatSinh(
        ngay=date.today(),
        so_tien=rec.so_tien,
        loai_chi_phi=loai_ten,
        ten_khoan=(rec.tieu_de or "")[:255],
        nhom_chi_phi=nhom,
        phong_ban=rec.phong_ban,
        nguoi_chi=rec.ho_ten,
        ngan_hang=tk,
        mo_ta=rec.muc_dich,
        ghi_chu=_gc,
        created_by=user.username,
    )
    db.add(cp)
    db.flush()  # cần cp.id để đánh dấu + sync sổ quỹ
    # Đánh dấu đã chi TRƯỚC sync để cùng 1 transaction: sync commit hết, hoặc lỗi
    # thì rollback hết (nguyên tử — không có chuyện da_chi=True mà không ra sổ quỹ).
    rec.da_chi = True
    rec.chi_phi_id = cp.id
    rec.tai_khoan_chi = tk
    rec.ngay_chi = datetime.now(tz=timezone.utc)
    sync_so_quy_from_chi_phi(db, cp)   # _upsert SoQuy chi + db.commit() (hoặc rollback)
    db.refresh(rec)
    if not rec.da_chi:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "Chi thất bại — không ghi được sổ quỹ, vui lòng thử lại")

    # Báo người đề xuất: đã được chi
    try:
        from shared.services.notify import notify
        notify(
            db, target=rec.username, source_app="ketoan",
            event_type="expense:da_chi",
            title=f"💸 Đề xuất '{rec.tieu_de}' đã được chi",
            message=f"{int(rec.so_tien):,}đ • qua {tk}",
            ref_type="expense_request", ref_id=rec.id, severity="success",
            created_by=user.username,
        )
        db.commit()
    except Exception:
        db.rollback()
    return rec
