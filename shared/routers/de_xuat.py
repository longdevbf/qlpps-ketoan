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

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, or_, select, text as sql_text
from sqlalchemy.orm import Session

from shared.auth import JWTPayload, current_user
from shared.config import settings
from shared.db import get_db
from shared.models.de_xuat import DeXuat
from shared.models.de_xuat_chi_tiet import DeXuatChiTiet
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
    # 5 loại theo ảnh mẫu người dùng gửi 12/09/2026 — mỗi loại là một tab ở màn Đề xuất.
    # Thêm mã mới KHÔNG phải migrate: `loai` là varchar tự do, ràng buộc chỉ nằm ở đây.
    "len_chinh_thuc": "Lên chính thức",
    "tuyen_dung": "Tuyển dụng",
    "tang_luong": "Tăng lương",
    "mua_thiet_bi": "Mua thiết bị",
    "thay_doi_quy_trinh": "Thay đổi quy trình",
    # 4 loại cũ — GIỮ LẠI, 6 dòng dữ liệu đang có dùng chúng; bỏ đi là mất nhãn hiển thị.
    "cai_tien": "Cải tiến cách làm",
    "viec_moi": "Việc mới / Sáng kiến",
    "van_de": "Vấn đề cần xử lý",
    "khac": "Khác",
}
# Loại cần chọn NHÂN VIÊN được đề xuất (khác người gửi đơn) — dùng cho cả kiểm ở API
# lẫn việc bật/tắt phần "Thông tin nhân viên" trên màn.
_LOAI_CAN_NV = {"len_chinh_thuc", "tang_luong"}
_MUC_DO = ("thap", "trung", "cao")
# Đề xuất dùng thang thấp/trung/cao; Directive dùng low/med/high.
_MUC_DO_SANG_PRIORITY = {"thap": "low", "trung": "med", "cao": "high"}

# Đề xuất "lên chính thức" CHỈ dành cho nhân viên ĐANG THỬ VIỆC (người dùng chốt 03/10/2026).
_LOAI_CHI_THU_VIEC = "len_chinh_thuc"
_HOP_DONG_THU_VIEC = "Thử việc"
# Dữ liệu thật ghi "Đã nghỉ" (11 người), code cũ chỉ loại "Nghỉ việc" nên người đã nghỉ vẫn hiện ra.
_TRANG_THAI_DA_NGHI = ("Nghỉ việc", "Đã nghỉ")


def _loc_thu_viec(loai: Optional[str], alias: str = "") -> str:
    """Mảnh SQL lọc 'đang thử việc' khi `loai` là lên chính thức; loại khác trả chuỗi rỗng.

    Chỉ ghép HẰNG CHUỖI của file này vào câu SQL (không có dữ liệu người dùng) nên không
    có nguy cơ SQL injection; `alias` là "" hoặc "e.".
    """
    if loai != _LOAI_CHI_THU_VIEC:
        return ""
    return (f"AND TRIM(COALESCE({alias}loai_hop_dong, '')) = '{_HOP_DONG_THU_VIEC}' "
            f"AND COALESCE({alias}trang_thai, '') NOT IN "
            f"({', '.join(repr(t) for t in _TRANG_THAI_DA_NGHI)})")


def _nv_dang_thu_viec(nv: dict) -> bool:
    return ((nv.get("loai_hop_dong") or "").strip() == _HOP_DONG_THU_VIEC
            and (nv.get("trang_thai") or "") not in _TRANG_THAI_DA_NGHI)


def _mau_nhom_con(pb: Optional[str]) -> str:
    """Mẫu LIKE (dùng với ESCAPE '!') khớp mọi nhóm con của phòng `pb`: tên bắt đầu bằng "<pb> ".

    Người dùng chốt 03/10/2026: quản lý phòng "Kinh Doanh" có quyền cả "Kinh Doanh Bán Lẻ Nhóm 1/2".
    Dấu cách sau tên phòng là bắt buộc để "Kinh Doanh" không nuốt nhầm "Kinh DoanhX".
    """
    if not pb:
        return "~~khong~~"
    return pb.replace("!", "!!").replace("%", "!%").replace("_", "!_") + " %"


def _trong_pham_vi_phong(pb_minh: Optional[str], pb_nv: Optional[str]) -> bool:
    """`pb_nv` là chính phòng của mình hoặc một nhóm con của nó (cùng luật với `_mau_nhom_con`)."""
    pb_minh, pb_nv = (pb_minh or "").strip(), (pb_nv or "").strip()
    return bool(pb_minh) and (pb_nv == pb_minh or pb_nv.startswith(pb_minh + " "))


# ── Helpers: ai là cấp trên ───────────────────────────────────────────────────
def _user_phong_ban(username: str) -> Optional[str]:
    try:
        _, pb, _, _, _ = _lookup_user_info(username)
        return (pb or "").strip() or None
    except Exception:
        return None


def _dept_has_manager(db: Session, phong_ban: Optional[str], *, tru: str = "") -> bool:
    """Phòng `phong_ban` (hoặc phòng MẸ của nó) có manager/leader active nào KHÁC `tru` không?

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
        if uname and uname != tru and _trong_pham_vi_phong(_user_phong_ban(uname), pb):
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
    - manager/leader: chỉ cấp 'manager', và chỉ phòng ban của đề xuất HOẶC phòng MẸ của nó
      (nhóm thuộc ban — người dùng chốt 03/10/2026: "Kinh Doanh" duyệt được "Kinh Doanh Bán Lẻ Nhóm 1").
      Dùng phòng ban chứ không dùng app như Duyệt Chi từng làm: đề xuất công
      việc thuộc về phòng, không thuộc về app.
    """
    role = (user.role or "").lower()
    if role in _SUPER_ROLES:
        return True
    if level == "manager" and role in _MANAGER_ROLES:
        return _trong_pham_vi_phong(_user_phong_ban(user.username), rec.phong_ban)
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
                       and _trong_pham_vi_phong(_user_phong_ban(r[0]), rec.phong_ban)]
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
class ChiTietIn(BaseModel):
    """Phần bổ sung của đề xuất — lưu ở bảng RIÊNG `shared.de_xuat_chi_tiet`.

    Người dùng chốt 12/09/2026 "thêm bảng mới, không sửa bảng cũ", nên nhân viên được
    đề xuất và các mốc ngày không nằm trong `shared.de_xuat`. Mọi trường đều tuỳ chọn:
    đề xuất kiểu cũ (cải tiến, việc mới…) không cần phần này.
    """
    nv_username: Optional[str] = None
    nv_ma_nv: Optional[str] = None
    ngay_ket_thuc_thu_viec: Optional[date] = None
    ngay_hieu_luc: Optional[date] = None
    du_lieu: Optional[dict] = None


class ChiTietOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ma: Optional[str] = None
    nv_username: Optional[str] = None
    nv_ma_nv: Optional[str] = None
    nv_ho_ten: Optional[str] = None
    nv_phong_ban: Optional[str] = None
    nv_chuc_vu: Optional[str] = None
    nv_ngay_vao: Optional[date] = None
    ngay_ket_thuc_thu_viec: Optional[date] = None
    ngay_hieu_luc: Optional[date] = None
    du_lieu: Optional[dict] = None


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
    chi_tiet: Optional[ChiTietIn] = None


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
    # Gắn tay từ bảng phụ trước khi trả về (`_gan_chi_tiet`), không phải cột của bảng cũ.
    chi_tiet: Optional[ChiTietOut] = None


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
# ── Bảng phụ `shared.de_xuat_chi_tiet` (12/09/2026) ──────────────────────────
def _ma_de_xuat(db: Session, hom_nay: date) -> str:
    """Mã hiển thị dạng DX260920-01 = DX + yymmdd + số thứ tự trong ngày.

    Bảng cũ chỉ có `id` số nên không có gì để in lên màn theo ảnh mẫu. Đếm theo tiền tố
    ngày của chính bảng phụ; trùng mã không gây hỏng dữ liệu vì mã chỉ để hiển thị.
    """
    dau = f"DX{hom_nay.strftime('%y%m%d')}-"
    n = db.execute(
        select(func.count()).select_from(DeXuatChiTiet).where(DeXuatChiTiet.ma.like(dau + "%"))
    ).scalar() or 0
    return f"{dau}{n + 1:02d}"


def _ct_dict(row) -> Optional[dict]:
    if row is None:
        return None
    return {
        "ma": row.ma, "nv_username": row.nv_username, "nv_ma_nv": row.nv_ma_nv,
        "nv_ho_ten": row.nv_ho_ten, "nv_phong_ban": row.nv_phong_ban,
        "nv_chuc_vu": row.nv_chuc_vu, "nv_ngay_vao": row.nv_ngay_vao,
        "ngay_ket_thuc_thu_viec": row.ngay_ket_thuc_thu_viec,
        "ngay_hieu_luc": row.ngay_hieu_luc, "du_lieu": row.du_lieu,
    }


def _gan_chi_tiet(db: Session, recs) -> None:
    """Gắn `chi_tiet` cho cả danh sách bằng MỘT truy vấn (tránh N+1)."""
    ds = [r.id for r in recs]
    if not ds:
        return
    rows = db.execute(
        select(DeXuatChiTiet).where(DeXuatChiTiet.de_xuat_id.in_(ds))
    ).scalars().all()
    theo_id = {r.de_xuat_id: r for r in rows}
    for r in recs:
        r.chi_tiet = _ct_dict(theo_id.get(r.id))


def _nv_theo_username(db: Session, username: str) -> dict:
    """Hồ sơ nhân viên đọc từ schema `hcns` — liên app CHỈ ĐỌC, đúng luật erp-architecture.

    Fail-soft: app nào chạy trên DB không có schema hcns thì trả rỗng, đề xuất vẫn gửi được.
    """
    if not username:
        return {}
    try:
        r = db.execute(sql_text("""
            SELECT ma_nv, ho_ten, phong_ban, chuc_vu, ngay_vao, ngay_len_chinh_thuc,
                   loai_hop_dong, trang_thai
            FROM hcns.employees WHERE username = :u LIMIT 1
        """), {"u": username}).mappings().first()
        return dict(r) if r else {}
    except Exception:
        db.rollback()
        return {}


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


_PHAM_VI = {"toi", "phong_ban", "tat_ca"}


@router.get("")
def list_de_xuat(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    trang_thai: Optional[str] = None,
    limit: int = 200,
    pham_vi: Optional[str] = Query(None, description="toi|phong_ban|tat_ca — bỏ trống = hành vi cũ"),
    loai: Optional[str] = None,
    tu: Optional[date] = None,
    den: Optional[date] = None,
    trang: int = Query(1, ge=1),
    so_dong: int = Query(0, ge=0, le=200, description="0 = không phân trang (hành vi cũ)"),
):
    """Danh sách đề xuất.

    KHÔNG truyền `pham_vi` và `so_dong` → trả về MẢNG đề xuất của chính mình, y như
    trước 12/09/2026 (bản màn cũ ở 8 app đang đọc kiểu đó, đổi shape là vỡ im lặng).
    Có truyền → trả `{"total", "items", "pham_vi"}` cho màn mới có phân trang.

    Phạm vi (siết theo cùng nguyên tắc đã chốt cho Giao việc 12/09/2026):
      · toi       — đề xuất mình gửi, ai cũng xem được
      · phong_ban — CHỈ quản lý (manager/leader) và super; đề xuất của phòng mình
      · tat_ca    — CHỈ super (admin/ceo/assistant_ceo)
    """
    pv = (pham_vi or "").strip().lower()
    if pv and pv not in _PHAM_VI:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "pham_vi phải thuộc {toi, phong_ban, tat_ca}")
    role = (user.role or "").lower()
    la_super = role in _SUPER_ROLES
    stmt = select(DeXuat)
    if not pv or pv == "toi":
        stmt = stmt.where(DeXuat.username == user.username)
    elif pv == "phong_ban":
        if not (la_super or role in _MANAGER_ROLES):
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Chỉ quản lý và ban giám đốc xem được đề xuất cả phòng")
        pb = _user_phong_ban(user.username)
        stmt = (stmt.where(or_(DeXuat.phong_ban == pb,
                               DeXuat.phong_ban.like(_mau_nhom_con(pb), escape="!")))
                if pb else stmt.where(DeXuat.id < 0))
    else:  # tat_ca
        if not la_super:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ ban giám đốc xem được tất cả")

    if trang_thai:
        stmt = stmt.where(DeXuat.trang_thai == trang_thai)
    if loai:
        stmt = stmt.where(DeXuat.loai == loai)
    if tu:
        stmt = stmt.where(func.date(DeXuat.created_at) >= tu)
    if den:
        stmt = stmt.where(func.date(DeXuat.created_at) <= den)

    if not pv and not so_dong:
        rows = db.execute(
            stmt.order_by(DeXuat.id.desc()).limit(max(1, min(limit, 500)))
        ).scalars().all()
        _gan_chi_tiet(db, rows)
        return [DeXuatOut.model_validate(r).model_dump() for r in rows]

    tong = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
    co = so_dong or 10
    rows = db.execute(
        stmt.order_by(DeXuat.id.desc()).limit(co).offset((trang - 1) * co)
    ).scalars().all()
    _gan_chi_tiet(db, rows)
    return {
        "total": tong,
        "pham_vi": pv or "toi",
        "items": [DeXuatOut.model_validate(r).model_dump() for r in rows],
    }


@router.get("/phong-ban")
def ds_phong_ban(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    loai: Optional[str] = None,
):
    """Danh sách phòng ban ĐANG CÓ nhân sự — cho ô chọn ở form đề xuất.

    Đọc thẳng `hcns.employees` thay vì gọi `/api/departments` của HCNS: endpoint đó
    nằm sau `require_app("hcns")` nên 7 app kia gọi sẽ bị 403 (khảo sát 12/09/2026).
    """
    try:
        rows = db.execute(sql_text(f"""
            SELECT phong_ban, COUNT(*) AS so_nv
            FROM hcns.employees
            WHERE phong_ban IS NOT NULL AND phong_ban <> ''
              AND (trang_thai IS NULL OR trang_thai <> 'Nghỉ việc')
              {_loc_thu_viec(loai)}
            GROUP BY phong_ban ORDER BY phong_ban
        """)).mappings().all()
        return [{"ten": r["phong_ban"], "so_nv": r["so_nv"]} for r in rows]
    except Exception:
        db.rollback()
        return []


@router.get("/nhan-vien")
def ds_nhan_vien(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    phong_ban: Optional[str] = None,
    q: Optional[str] = None,
    loai: Optional[str] = None,
):
    """Nhân viên để chọn trong form (mã NV, chức vụ, ngày vào, ngày lên chính thức).

    Nhân viên thường chỉ thấy CHÍNH MÌNH — đề xuất lên chính thức / tăng lương là việc
    của quản lý. Quản lý thấy phòng mình, super thấy tất cả.

    `loai=len_chinh_thuc` → chỉ người ĐANG THỬ VIỆC (03/10/2026). Không truyền `loai` thì giữ
    hành vi cũ — màn Đào tạo dùng endpoint này để chọn "Người chia sẻ".
    """
    role = (user.role or "").lower()
    dieu_kien, tham_so = ["1=1"], {}
    if role in _SUPER_ROLES:
        pass
    elif role in _MANAGER_ROLES:
        pb = _user_phong_ban(user.username)
        # Quản lý một phòng có quyền cả các nhóm con của phòng đó (03/10/2026, xem _mau_nhom_con).
        dieu_kien.append("(e.phong_ban = :pb_minh OR e.phong_ban LIKE :pb_con ESCAPE '!')")
        tham_so["pb_minh"] = pb or "~~khong~~"
        tham_so["pb_con"] = _mau_nhom_con(pb)
    else:
        dieu_kien.append("e.username = :toi")
        tham_so["toi"] = user.username
    if phong_ban:
        dieu_kien.append("e.phong_ban = :pb")
        tham_so["pb"] = phong_ban
    if q:
        dieu_kien.append("(e.ho_ten ILIKE :q OR e.ma_nv ILIKE :q OR e.username ILIKE :q)")
        tham_so["q"] = f"%{q.strip()}%"
    try:
        rows = db.execute(sql_text(f"""
            SELECT e.username, e.ma_nv, e.ho_ten, e.phong_ban, e.chuc_vu,
                   e.ngay_vao, e.ngay_len_chinh_thuc, e.loai_hop_dong, e.trang_thai
            FROM hcns.employees e
            WHERE {' AND '.join(dieu_kien)}
              AND (e.trang_thai IS NULL OR e.trang_thai <> 'Nghỉ việc')
              {_loc_thu_viec(loai, "e.")}
            ORDER BY e.ho_ten LIMIT 300
        """), tham_so).mappings().all()
        return [dict(r) for r in rows]
    except Exception:
        db.rollback()
        return []


@router.get("/nguoi-duyet")
def ds_nguoi_duyet(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    phong_ban: Optional[str] = None,
    can_ceo: bool = False,
):
    """Chuỗi người sẽ duyệt, xem TRƯỚC khi gửi (ảnh mẫu vẽ khối "Quy trình phê duyệt").

    Đúng luật đang chạy ở `_cap_bat_dau` / `_can_approve_at`: quản lý phòng của đề xuất
    duyệt trước, CEO chỉ vào cuộc khi cần (có ngân sách · liên phòng ban · xin ý kiến CEO).
    Phòng không có quản lý thì nhảy thẳng lên CEO — trả về đúng như vậy để người gửi
    không bất ngờ.
    """
    ds: List[dict] = []
    try:
        if phong_ban:
            rows = db.execute(sql_text("""
                SELECT e.username, e.ho_ten, e.chuc_vu, lower(u.role) AS role
                FROM hcns.employees e JOIN shared.users u ON u.username = e.username
                WHERE (e.phong_ban = :pb OR starts_with(:pb, e.phong_ban || ' ')) AND u.active
                  AND lower(u.role) IN ('manager', 'leader')
                  AND e.username <> :toi
                ORDER BY CASE WHEN e.phong_ban = :pb THEN 0 ELSE 1 END,
                         CASE lower(u.role) WHEN 'manager' THEN 0 ELSE 1 END, e.ho_ten
                LIMIT 1
            """), {"pb": phong_ban, "toi": user.username}).mappings().all()
            for r in rows:
                ds.append({"cap": "manager", "nhan_cap": "Quản lý phòng ban",
                           "username": r["username"], "ho_ten": r["ho_ten"] or r["username"],
                           "chuc_vu": r["chuc_vu"] or "Quản lý"})
        if can_ceo or not ds:
            rows = db.execute(sql_text("""
                SELECT u.username, COALESCE(e.ho_ten, u.username) AS ho_ten, e.chuc_vu
                FROM shared.users u LEFT JOIN hcns.employees e ON e.username = u.username
                WHERE u.active AND lower(u.role) = 'ceo' ORDER BY u.username LIMIT 1
            """)).mappings().all()
            for r in rows:
                ds.append({"cap": "ceo", "nhan_cap": "Giám đốc",
                           "username": r["username"], "ho_ten": r["ho_ten"],
                           "chuc_vu": r["chuc_vu"] or "Giám đốc"})
    except Exception:
        db.rollback()
    return {"items": ds, "ghi_chu": "" if ds else "Chưa xác định được người duyệt cho phòng này"}


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
    ket_qua = [r for r in rows if _can_approve_at(user, r.approval_level, r, db)]
    _gan_chi_tiet(db, ket_qua)
    return ket_qua


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

    ct_in = body.chi_tiet
    nv = _nv_theo_username(db, ct_in.nv_username) if (ct_in and ct_in.nv_username) else {}
    if body.loai == _LOAI_CHI_THU_VIEC:
        if not (ct_in and ct_in.nv_username):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Chọn nhân viên được đề xuất")
        if not nv:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Không tìm thấy nhân viên được đề xuất")
        if not _nv_dang_thu_viec(nv):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                "Chỉ đề xuất lên chính thức cho nhân viên đang thử việc.")

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

    # Bảng phụ: nhân viên được đề xuất + mốc ngày + mã hiển thị. Luôn tạo một dòng, kể cả
    # loại cũ không có nhân viên — để mọi đề xuất đều có mã in ra màn.
    ct = DeXuatChiTiet(
        de_xuat_id=rec.id,
        ma=_ma_de_xuat(db, date.today()),
        nv_username=(ct_in.nv_username if ct_in else None),
        # Mã NV lấy từ hồ sơ ĐÃ KIỂM theo nv_username — không tin mã client tự gửi: lúc duyệt,
        # services/len_chinh_thuc.py tra hồ sơ theo mã này trước (lỗ phát hiện 02/10/2026).
        nv_ma_nv=nv.get("ma_nv"),
        nv_ho_ten=nv.get("ho_ten"),
        nv_phong_ban=nv.get("phong_ban"),
        nv_chuc_vu=nv.get("chuc_vu"),
        nv_ngay_vao=nv.get("ngay_vao"),
        ngay_ket_thuc_thu_viec=(ct_in.ngay_ket_thuc_thu_viec if ct_in else None),
        ngay_hieu_luc=(ct_in.ngay_hieu_luc if ct_in else None),
        du_lieu=(ct_in.du_lieu if ct_in else None),
    )
    db.add(ct)
    db.flush()

    _notify_next_tier(db, rec, by=user.username)
    db.commit()
    db.refresh(rec)
    rec.chi_tiet = _ct_dict(ct)
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
    _gan_chi_tiet(db, [rec])
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
    # Siết 12/09/2026: xem thì approver nào cũng xem được (đúng luật cũ của `GET /{id}`),
    # nhưng GHI vào đề xuất người khác thì chỉ super hoặc quản lý ĐÚNG phòng của đề xuất.
    _pb_nguoi_goi = _user_phong_ban(user.username)
    _duoc_ghi = (
        rec.username == user.username
        or (user.role or "").lower() in _SUPER_ROLES
        or ((user.role or "").lower() in _MANAGER_ROLES
            and _trong_pham_vi_phong(_pb_nguoi_goi, rec.phong_ban))
    )
    if not _duoc_ghi:
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
