"""Đề xuất chấm công lại — API dùng chung cho cả 8 app (mount tại /api/de-xuat-cham-cong).
Gửi + xem đề xuất của mình: tab trong màn Đề xuất (`/de-xuat#cham-cong`, `_de_xuat_cham_cong_panel.html`).
Duyệt: màn Phê duyệt, mục Đề xuất (`phe_duyet_core.html`, nguồn `cc`).

Luồng: NV gửi (ngày · giờ đến thực tế · lý do; giờ hệ thống do server tự lấy) →
Quản lý phòng duyệt → CEO duyệt cuối → ghi đè giờ vào trong hcns.cham_cong.
Mức phí mỗi đề xuất do HCNS đặt (shared.services.phi_cham_cong), chốt vào `phi` lúc gửi; người gửi
không nhập tiền. Tiền CHỈ bị trừ vào Tối ưu KD khi CEO duyệt và đồng ý trừ — CEO chọn có trừ hay
không và trừ bao nhiêu (mặc định đúng `phi`); bị từ chối ở bất kỳ cấp nào thì không trừ.
"""
import logging
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Annotated, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from shared.audit import log_action
from shared.auth import JWTPayload, current_user
from shared.db import get_db
from shared.models.de_xuat_cham_cong import (
    TRANG_THAI_CHO_CEO,
    TRANG_THAI_CHO_QUAN_LY,
    TRANG_THAI_CON_HIEU_LUC,
    TRANG_THAI_DA_DUYET,
    TRANG_THAI_TU_CHOI,
    DeXuatChamCong,
)
from shared.routers.xin_nghi import _SUPER_ROLES, _approver_depts
from shared.services import phi_cham_cong
from shared.templates import _lookup_user_info

router = APIRouter()
_AUTH = Depends(current_user)
log = logging.getLogger(__name__)

_ROLE_QUAN_LY = {"manager", "leader"}
_ROLE_CAP1_MOI_PHONG = {"admin", "assistant_ceo"}   # duyệt cấp quản lý ở mọi phòng (CEO chỉ duyệt cuối)
_ROLE_XEM_TAT_CA = {"ceo", "admin", "assistant_ceo", "hr_manager"}   # xem toàn bộ (HCNS giữ mức tiền tối thiểu)
_ROLE_CEO = {"ceo"}                                  # duyệt cuối + quyết định trừ thưởng
LOAI_VAN_PHONG = "van_phong"            # `hcns.cham_cong.loai` của NV tự chấm — bảng lương/đi muộn chỉ đếm loại này
CHECK_METHOD_DE_XUAT = "de_xuat"        # `hcns.cham_cong.check_method` của bản ghi sinh từ đề xuất
_LY_DO_TOI_DA = 1000
_NHAN_XET_TOI_DA = 1000
_PHAN_CUA_TOI = "cua_toi"
_PHAN_CAN_DUYET = "can_duyet"
_PHAN_TAT_CA = "tat_ca"


# ── Schemas ───────────────────────────────────────────────────────────────────
class DeXuatCreate(BaseModel):
    ngay: date
    gio_thuc_te: time
    ly_do: str = Field(min_length=1, max_length=_LY_DO_TOI_DA)


class DeXuatReview(BaseModel):
    ket_qua: str  # duyet | tu_choi
    nhan_xet: str = Field(default="", max_length=_NHAN_XET_TOI_DA)
    # Chỉ CEO, ở lần duyệt cuối: có trừ Tối ưu KD không, và trừ bao nhiêu (bỏ trống = đúng số tiền đề xuất).
    tru_thuong: Optional[bool] = None
    so_tien_tru: Optional[int] = Field(default=None, ge=0, le=phi_cham_cong.MAX_PHI_MOI_LUOT)


class DeXuatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    ma_nv: str
    ho_ten: str
    phong_ban: Optional[str]
    ngay: date
    gio_thuc_te: time
    gio_he_thong: Optional[time]
    gio_truoc_khi_sua: Optional[time]
    ly_do: str
    phi: Decimal
    phi_tru: Optional[Decimal]
    trang_thai: str
    tu_choi_boi: Optional[str]
    ho_ten_quan_ly: Optional[str]
    quan_ly_luc: Optional[datetime]
    quan_ly_nhan_xet: Optional[str]
    ho_ten_ceo: Optional[str]
    ceo_luc: Optional[datetime]
    ceo_nhan_xet: Optional[str]
    created_at: datetime


# ── Helpers ───────────────────────────────────────────────────────────────────
def _hom_nay() -> date:
    return datetime.now(ZoneInfo(phi_cham_cong.MUI_GIO_VN)).date()


def _role(user: JWTPayload) -> str:
    return (user.role or "").lower()


def _nhan_vien(db: Session, username: str) -> dict:
    row = db.execute(text("""
        SELECT ma_nv, ho_ten, phong_ban FROM hcns.employees
        WHERE LOWER(username) = LOWER(:u) LIMIT 1
    """), {"u": username}).mappings().first()
    if not row or not row["ma_nv"]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Tài khoản chưa gắn hồ sơ nhân viên — liên hệ HCNS")
    return dict(row)


def _gio_he_thong(db: Session, ma_nv: str, ngay: date) -> Optional[time]:
    """Giờ vào ĐẦU TIÊN của ngày (cùng quy ước với bảng đi muộn)."""
    return db.execute(text("""
        SELECT MIN(gio_vao) FROM hcns.cham_cong
        WHERE UPPER(ma_nv) = UPPER(:m) AND ngay = :d AND gio_vao IS NOT NULL
    """), {"m": ma_nv, "d": ngay}).scalar()


def _la_ceo(user: JWTPayload) -> bool:
    return _role(user) in _ROLE_CEO


def _co_quyen_cap1(db: Session, user: JWTPayload, phong_ban: Optional[str]) -> bool:
    """Admin/trợ lý CEO duyệt mọi phòng; manager/leader chỉ phòng mình quản lý (chính + phụ, khớp tiền tố)."""
    vai = _role(user)
    if vai in _ROLE_CAP1_MOI_PHONG:
        return True
    if vai not in _ROLE_QUAN_LY:
        return False
    rp = (phong_ban or "").strip().lower()
    return any(rp.startswith(d) for d in (_approver_depts(db, user) or []))


def _loc_phong(depts: list[str]):
    """Điều kiện SQL: phòng của đề xuất khớp TIỀN TỐ bất kỳ phòng nào người duyệt quản lý."""
    return or_(*[func.lower(func.coalesce(DeXuatChamCong.phong_ban, "")).like(d + "%") for d in depts])


def _trang_thai_ban_dau(user: JWTPayload) -> str:
    """Quản lý/lãnh đạo không có quản lý phòng duyệt trên mình → vào thẳng CEO."""
    if _role(user) == "manager" or _role(user) in _SUPER_ROLES:
        return TRANG_THAI_CHO_CEO
    return TRANG_THAI_CHO_QUAN_LY


def _nguoi_nhan_cap1(db: Session, phong_ban: Optional[str], tru: str) -> list[str]:
    """Username manager/leader quản lý phòng của đơn (để báo chuông)."""
    rows = db.execute(text("""
        SELECT DISTINCT u.username
        FROM shared.users u
        JOIN hcns.employees e ON LOWER(e.username) = LOWER(u.username)
        WHERE LOWER(u.role) IN ('manager', 'leader')
          AND COALESCE(e.phong_ban, '') <> ''
          AND LOWER(:pb) LIKE LOWER(e.phong_ban) || '%'
          AND LOWER(u.username) <> LOWER(:tru)
    """), {"pb": phong_ban or "", "tru": tru}).all()
    return [r[0] for r in rows]


def _nguoi_nhan_ceo(db: Session, tru: str) -> list[str]:
    rows = db.execute(text("""
        SELECT username FROM shared.users WHERE LOWER(role) = ANY(:vai)
    """), {"vai": sorted(_ROLE_CEO)}).all()
    return sorted(r[0] for r in rows if r[0].lower() != tru.lower())


URL_PHE_DUYET = "/phe-duyet"                # người duyệt xử lý ở màn Phê duyệt (mục Đề xuất)
URL_DE_XUAT_CUA_TOI = "/de-xuat#cham-cong"  # người gửi xem kết quả ở tab Chấm công lại


def _bao_chuong(db: Session, nguoi_nhan: list[str], rec: DeXuatChamCong, tieu_de: str, noi_dung: str, url: str) -> None:
    """Báo chuông — fail-soft: lỗi thông báo không được làm hỏng nghiệp vụ."""
    try:
        from shared.services.notify import notify
        for u in nguoi_nhan:
            notify(db, target=u, source_app=rec.app_name, event_type="de_xuat_cham_cong",
                   title=tieu_de, message=noi_dung, ref_type="de_xuat_cham_cong", ref_id=rec.id,
                   url=url, created_by=rec.username)
        db.commit()
    except Exception:
        log.warning("bao chuong de xuat cham cong #%s loi", rec.id, exc_info=True)
        db.rollback()


def _ap_dung_vao_cham_cong(db: Session, rec: DeXuatChamCong, nguoi: str) -> None:
    """Ghi đè giờ vào của phiên đầu tiên trong ngày = giờ thực tế; lưu giờ cũ vào đề xuất.
    Ngày hệ thống chưa ghi nhận gì thì tạo bản ghi mới chỉ có giờ vào (HCNS bổ sung giờ ra sau).

    Giữ nguyên `loai` để số công + số lần đi muộn của bảng lương tự tính lại theo giờ mới."""
    from hcns.app.models.cham_cong import ChamCong  # lazy: shared không phụ thuộc HCNS lúc khởi động
    from hcns.app.services.hour_calc import tinh_gio_lam

    cc = db.execute(
        select(ChamCong)
        .where(ChamCong.ma_nv == rec.ma_nv, ChamCong.ngay == rec.ngay, ChamCong.gio_vao.isnot(None))
        .order_by(ChamCong.gio_vao, ChamCong.id)
        .limit(1)
        .with_for_update()
    ).scalar_one_or_none()
    nguoi_sua = f"de_xuat_cham_cong:{rec.id}:{nguoi}"[:128]
    if cc is None:
        db.add(ChamCong(
            ma_nv=rec.ma_nv, ngay=rec.ngay, gio_vao=rec.gio_thuc_te, loai=LOAI_VAN_PHONG,
            check_method=CHECK_METHOD_DE_XUAT, created_by=nguoi_sua, updated_by=nguoi_sua,
            ghi_chu=f"Chấm công theo đề xuất #{rec.id} (hệ thống chưa ghi nhận giờ vào)",
        ))
        return
    rec.gio_truoc_khi_sua = cc.gio_vao
    cc.gio_vao = rec.gio_thuc_te
    if cc.gio_ra:
        cc.tong_gio = tinh_gio_lam(cc.gio_vao, cc.gio_ra)
    cc.updated_by = nguoi_sua
    ghi_chu = f"Chấm công lại theo đề xuất #{rec.id} (giờ cũ {rec.gio_truoc_khi_sua:%H:%M})"
    cc.ghi_chu = f"{cc.ghi_chu}; {ghi_chu}" if cc.ghi_chu else ghi_chu


def _so_tien_ceo_tru(rec: DeXuatChamCong, body: DeXuatReview) -> Decimal:
    """Số tiền CEO quyết trừ vào Tối ưu KD khi duyệt: 0 = không trừ; bỏ trống số = đúng số tiền đề xuất."""
    if body.tru_thuong is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "CEO cần chọn có trừ thưởng Tối ưu KD hay không")
    if not body.tru_thuong:
        return Decimal(0)
    so_tien = rec.phi if body.so_tien_tru is None else body.so_tien_tru
    if so_tien <= 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Số tiền trừ phải lớn hơn 0 — hoặc chọn không trừ")
    return Decimal(so_tien)


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/thong-tin")
def thong_tin(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    ngay: Optional[date] = None,
):
    """Dữ liệu cho form: phí, số ngày tối đa, giờ hệ thống của `ngay`, quyền duyệt của người xem."""
    nv = _nhan_vien(db, user.username)
    cfg = phi_cham_cong.load_config(db, _hom_nay().strftime("%Y-%m"))
    return {
        "ma_nv": nv["ma_nv"],
        "ho_ten": nv["ho_ten"],
        "phi_moi_luot": cfg["phi_moi_luot"],
        "so_ngay_toi_da": cfg["so_ngay_toi_da"],
        "hom_nay": _hom_nay().isoformat(),
        "gio_he_thong": (_gio_he_thong(db, nv["ma_nv"], ngay) if ngay else None),
        "quyen_duyet": {
            "cap1": _role(user) in (_ROLE_QUAN_LY | _ROLE_CAP1_MOI_PHONG),
            "ceo": _la_ceo(user),
            "xem_tat_ca": _role(user) in _ROLE_XEM_TAT_CA,
        },
    }


@router.post("", response_model=DeXuatOut, status_code=status.HTTP_201_CREATED)
def tao_de_xuat(
    body: DeXuatCreate,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    nv = _nhan_vien(db, user.username)
    hom_nay = _hom_nay()
    cfg = phi_cham_cong.load_config(db, hom_nay.strftime("%Y-%m"))

    if body.ngay > hom_nay:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Không đề xuất cho ngày chưa tới")
    if (hom_nay - body.ngay).days > cfg["so_ngay_toi_da"]:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Chỉ được đề xuất cho ngày trong {cfg['so_ngay_toi_da']} ngày gần nhất",
        )
    ly_do = body.ly_do.strip()
    if not ly_do:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Lý do không được để trống")

    # Hệ thống không ghi nhận (lỗi phần mềm, quên chấm…) vẫn được đề xuất: khi đó không có giờ để so.
    gio_he_thong = _gio_he_thong(db, nv["ma_nv"], body.ngay)
    if gio_he_thong is not None and body.gio_thuc_te >= gio_he_thong:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Giờ đến thực tế phải sớm hơn giờ trên hệ thống ({gio_he_thong:%H:%M})",
        )
    da_co = db.execute(
        select(DeXuatChamCong.id).where(
            DeXuatChamCong.username == user.username,
            DeXuatChamCong.ngay == body.ngay,
            DeXuatChamCong.trang_thai.in_(TRANG_THAI_CON_HIEU_LUC),
        ).limit(1)
    ).first()
    if da_co:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ngày này đã có đề xuất đang chờ hoặc đã được duyệt")

    ho_ten, phong_ban, _, _, _ = _lookup_user_info(user.username)
    rec = DeXuatChamCong(
        username=user.username,
        ma_nv=nv["ma_nv"],
        ho_ten=ho_ten or nv["ho_ten"] or user.username,
        phong_ban=phong_ban or nv["phong_ban"],
        # Giống xin_nghi: `app.state.app_name` là nguồn chuẩn, cột là varchar(32).
        app_name=str(getattr(request.app.state, "app_name", None) or "internal")[:32],
        ngay=body.ngay,
        gio_thuc_te=body.gio_thuc_te.replace(second=0, microsecond=0),
        gio_he_thong=gio_he_thong,
        ly_do=ly_do,
        phi=Decimal(cfg["phi_moi_luot"]),  # mức phí theo quy chế tại thời điểm gửi
        trang_thai=_trang_thai_ban_dau(user),
    )
    db.add(rec)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Ngày này đã có đề xuất đang chờ hoặc đã được duyệt")
    db.refresh(rec)

    nguoi_nhan = (_nguoi_nhan_ceo(db, user.username) if rec.trang_thai == TRANG_THAI_CHO_CEO
                  else _nguoi_nhan_cap1(db, rec.phong_ban, user.username))
    gio_cu = f"{rec.gio_he_thong:%H:%M}" if rec.gio_he_thong else "chưa có"
    _bao_chuong(db, nguoi_nhan, rec, "Đề xuất chấm công lại cần duyệt",
                f"{rec.ho_ten} đề xuất sửa giờ vào ngày {rec.ngay:%d/%m/%Y}: "
                f"{gio_cu} → {rec.gio_thuc_te:%H:%M}", URL_PHE_DUYET)
    log_action(db, app=rec.app_name, action="tao_de_xuat_cham_cong", user=user, request=request,
               resource=f"de_xuat_cham_cong:{rec.id}", payload={"ngay": str(rec.ngay), "phi": int(rec.phi)})
    return rec


@router.get("", response_model=List[DeXuatOut])
def danh_sach(
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
    phan: str = Query(_PHAN_CUA_TOI, pattern=f"^({_PHAN_CUA_TOI}|{_PHAN_CAN_DUYET}|{_PHAN_TAT_CA})$"),
    thang: Optional[str] = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),  # tháng GỬI
):
    stmt = select(DeXuatChamCong)
    if phan == _PHAN_CAN_DUYET:
        stmt = stmt.order_by(DeXuatChamCong.created_at.asc())   # hàng duyệt: gửi trước duyệt trước
    else:
        stmt = stmt.order_by(DeXuatChamCong.created_at.desc())
    if phan == _PHAN_CUA_TOI:
        stmt = stmt.where(DeXuatChamCong.username == user.username)
    else:
        la_ceo = _la_ceo(user)
        if phan == _PHAN_TAT_CA:
            if _role(user) not in _ROLE_XEM_TAT_CA:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ HCNS / CEO xem được toàn bộ đề xuất")
        else:
            stmt = stmt.where(DeXuatChamCong.username != user.username)
            dieu_kien = []
            if la_ceo:
                dieu_kien.append(DeXuatChamCong.trang_thai == TRANG_THAI_CHO_CEO)
            if _role(user) in _ROLE_CAP1_MOI_PHONG:
                dieu_kien.append(DeXuatChamCong.trang_thai == TRANG_THAI_CHO_QUAN_LY)
            elif _role(user) in _ROLE_QUAN_LY:
                depts = _approver_depts(db, user)
                if depts:
                    dieu_kien.append(
                        (DeXuatChamCong.trang_thai == TRANG_THAI_CHO_QUAN_LY) & _loc_phong(depts)
                    )
            if not dieu_kien:
                return []
            stmt = stmt.where(or_(*dieu_kien))
    if thang:
        nam, thg = (int(x) for x in thang.split("-"))
        dau = datetime(nam, thg, 1, tzinfo=ZoneInfo(phi_cham_cong.MUI_GIO_VN))
        cuoi = datetime(nam + (thg == 12), thg % 12 + 1, 1, tzinfo=ZoneInfo(phi_cham_cong.MUI_GIO_VN))
        stmt = stmt.where(DeXuatChamCong.created_at >= dau, DeXuatChamCong.created_at < cuoi)
    return db.execute(stmt.limit(500)).scalars().all()


@router.put("/{rid}/duyet", response_model=DeXuatOut)
def duyet(
    rid: int,
    body: DeXuatReview,
    request: Request,
    user: Annotated[JWTPayload, _AUTH],
    db: Annotated[Session, Depends(get_db)],
):
    if body.ket_qua not in ("duyet", "tu_choi"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Kết quả phải là duyet hoặc tu_choi")
    rec = db.execute(
        select(DeXuatChamCong).where(DeXuatChamCong.id == rid).with_for_update()
    ).scalar_one_or_none()
    if not rec:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy đề xuất")
    if (rec.username or "").lower() == (user.username or "").lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Không được tự duyệt đề xuất của chính mình")
    nhan_xet = body.nhan_xet.strip()
    if body.ket_qua == "tu_choi" and not nhan_xet:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Từ chối cần ghi lý do")

    ho_ten_duyet, _, _, _, _ = _lookup_user_info(user.username)
    ho_ten_duyet = ho_ten_duyet or user.username
    bay_gio = datetime.now(timezone.utc)

    if rec.trang_thai == TRANG_THAI_CHO_QUAN_LY:
        if not _co_quyen_cap1(db, user, rec.phong_ban):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không quản lý phòng của người gửi đề xuất này")
        rec.quan_ly_duyet, rec.ho_ten_quan_ly = user.username, ho_ten_duyet
        rec.quan_ly_luc, rec.quan_ly_nhan_xet = bay_gio, nhan_xet
        cap = "quan_ly"
    elif rec.trang_thai == TRANG_THAI_CHO_CEO:
        if not _la_ceo(user):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Chỉ CEO được duyệt cuối")
        if (rec.quan_ly_duyet or "").lower() == (user.username or "").lower():
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Người duyệt cấp quản lý không được duyệt tiếp cấp CEO")
        if body.ket_qua == "duyet":
            rec.phi_tru = _so_tien_ceo_tru(rec, body)
        rec.ceo_duyet, rec.ho_ten_ceo = user.username, ho_ten_duyet
        rec.ceo_luc, rec.ceo_nhan_xet = bay_gio, nhan_xet
        cap = "ceo"
    else:
        raise HTTPException(status.HTTP_409_CONFLICT, "Đề xuất này đã được xử lý xong")

    if body.ket_qua == "tu_choi":
        rec.trang_thai, rec.tu_choi_boi = TRANG_THAI_TU_CHOI, cap
    elif cap == "quan_ly":
        rec.trang_thai = TRANG_THAI_CHO_CEO
    else:
        _ap_dung_vao_cham_cong(db, rec, user.username)
        rec.trang_thai = TRANG_THAI_DA_DUYET
    db.commit()
    db.refresh(rec)

    if rec.trang_thai == TRANG_THAI_CHO_CEO:
        _bao_chuong(db, _nguoi_nhan_ceo(db, rec.username), rec, "Đề xuất chấm công lại cần CEO duyệt",
                    f"{rec.ho_ten} · ngày {rec.ngay:%d/%m/%Y} · quản lý {ho_ten_duyet} đã duyệt · "
                    f"số tiền đề xuất {int(rec.phi):,}đ".replace(",", "."), URL_PHE_DUYET)
    else:
        ket_qua = "đã được duyệt" if rec.trang_thai == TRANG_THAI_DA_DUYET else "bị từ chối"
        tru = ""
        if rec.trang_thai == TRANG_THAI_DA_DUYET:
            tru = (f" · trừ {int(rec.phi_tru):,}đ vào thưởng Tối ưu KD".replace(",", ".")
                   if rec.phi_tru else " · không trừ thưởng")
        _bao_chuong(db, [rec.username], rec, f"Đề xuất chấm công lại {ket_qua}",
                    f"Ngày {rec.ngay:%d/%m/%Y}{tru}" + (f" — {nhan_xet}" if nhan_xet else ""), URL_DE_XUAT_CUA_TOI)
    log_action(db, app=rec.app_name, action=f"duyet_de_xuat_cham_cong_{cap}", user=user, request=request,
               resource=f"de_xuat_cham_cong:{rec.id}",
               payload={"ket_qua": body.ket_qua, "phi_tru": int(rec.phi_tru) if rec.phi_tru is not None else None})
    return rec
