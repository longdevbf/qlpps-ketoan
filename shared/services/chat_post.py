"""Auto-post 1 tin nhắn hệ thống vào 1 nhóm chat có sẵn (hcns.chat_rooms/messages).

Dùng bởi luồng Báo Giá / Kế Toán để bắn thông báo vào nhóm "Kinh Doanh - Kế Toán"
(báo cọc khi KD gửi duyệt, báo đã duyệt tiền khi KT xác nhận cọc).

Nguyên tắc:
- **Fail-soft tuyệt đối**: mọi lỗi đều nuốt, KHÔNG được làm hỏng luồng gọi
  (gửi duyệt / duyệt cọc vẫn phải chạy dù chat lỗi).
- Ghi thẳng bằng **SQL thô** vào schema `hcns` — KHÔNG import model/route của
  `hcns.app.routers.chat` (tránh phụ thuộc chéo + tránh lỗi import ở app không
  bundle hcns đầy đủ). Tin đăng dưới danh nghĩa Mai (mai_ai).
- Sau khi insert: bắn chuông cho thành viên nhóm (trừ người gửi) + publish
  realtime lên Redis channel `chat:room:{id}` cho ai đang mở phòng — cả 2 đều
  best-effort.
"""
from __future__ import annotations

import json
import logging
import time as _time
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAI_USERNAME = "mai_ai"
MAI_DISPLAY_NAME = "Mai - Trợ Lý"

# Nhóm mặc định cho luồng KD ↔ Kế Toán (đã tồn tại trên hệ thống).
ROOM_KD_KETOAN = "Kinh Doanh - Kế Toán"


def _resolve_room(db: Session, room_name: str) -> Optional[int]:
    """Tìm room_id của 1 nhóm (type='group') theo tên; fallback theo bộ phòng ban.

    Không hardcode id (đề phòng nhóm bị tạo lại). Ưu tiên khớp tên chính xác;
    nếu không có → tìm nhóm gắn CẢ 'Kinh Doanh' lẫn 'Kế Toán'.
    """
    try:
        rid = db.execute(
            text(
                "SELECT id FROM hcns.chat_rooms "
                "WHERE type = 'group' AND name = :n ORDER BY id LIMIT 1"
            ),
            {"n": room_name},
        ).scalar()
        if rid:
            return int(rid)
        # Fallback: nhóm group có gắn cả 2 phòng ban Kinh Doanh + Kế Toán
        rid = db.execute(
            text(
                "SELECT d.room_id FROM hcns.chat_room_departments d "
                "JOIN hcns.chat_rooms r ON r.id = d.room_id AND r.type = 'group' "
                "WHERE d.phong_ban IN ('Kinh Doanh', 'Kế Toán') "
                "GROUP BY d.room_id "
                "HAVING COUNT(DISTINCT d.phong_ban) = 2 "
                "ORDER BY d.room_id LIMIT 1"
            )
        ).scalar()
        return int(rid) if rid else None
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


def _notify_members(db: Session, room_id: int, mid: int, sender: str, content: str) -> None:
    """Bắn chuông cross-app cho mọi thành viên nhóm (trừ người gửi). Best-effort."""
    try:
        from shared.services.notify import notify

        members = db.execute(
            text("SELECT username FROM hcns.chat_room_members WHERE room_id = :r"),
            {"r": room_id},
        ).scalars().all()
        preview = (content or "").split("\n", 1)[0][:120]
        for u in members:
            if not u or u == sender:
                continue
            notify(
                db,
                target=u,
                source_app="chat",
                event_type="chat:message",
                title="💬 Nhóm Kinh Doanh - Kế Toán",
                message=preview,
                ref_type="chat_room",
                ref_id=str(room_id),
                url=f"/chat#room={room_id}&msg={mid}",
                severity="info",
                created_by=sender,
                webpush=False,
            )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_post notify members failed (room=%s): %s", room_id, exc)
        try:
            db.rollback()
        except Exception:
            pass


def _publish_realtime(
    room_id: int, mid: int, sender: str, sender_name: str,
    content: str, created_at: Optional[str],
) -> None:
    """Publish tin lên Redis `chat:room:{id}` cho ai đang mở phòng. Best-effort."""
    try:
        import redis as _redis_mod

        from shared.config import settings

        cli = _redis_mod.Redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )
        message = {
            "id": mid, "room_id": room_id,
            "sender_username": sender, "sender_name": sender_name,
            "content": content, "msg_type": "text",
            "created_at": created_at, "edited_at": None,
            "file_url": None, "file_name": None, "file_mime": None,
            "img_w": None, "img_h": None,
            "reply_to": None, "thread_count": 0, "read_by": [],
            "reactions": [], "is_pinned": False, "is_starred": False,
            "mentions": [], "task_id": None, "is_deleted": False,
        }
        cli.publish(
            f"chat:room:{room_id}",
            json.dumps({"type": "message", "room_id": room_id, "message": message}, default=str),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_post publish realtime failed (room=%s): %s", room_id, exc)


# --- Ai dang phu trach mot phong ban -----------------------------------------
# Anh Quang 07/09/2026: tin cua Mai goi chung chung "Moi Ke Toan duyet coc" thi
# khong ai thay do la viec cua minh. Doi thanh goi dich danh "anh Nguyen Duy
# Thanh". Tra DB chu KHONG go cung ten: hom nay phong Ke Toan co 1 nguoi, mai
# nguoi do nghi thi cau chu tu cap nhat theo, khong bien thanh loi noi doi.
_PHU_TRACH_CACHE: dict = {}
_PHU_TRACH_TTL_SEC = 300.0   # 5 phut, cung ly do voi shared/templates.py

# Thu tu uu tien khi mot phong co nhieu nguoi: ai lam dau moi thi goi ten nguoi do.
_CHUC_VU_DAU_MOI = ("CEO", "Manager", "Leader")


def _xung_ho(gioi_tinh: str) -> str:
    """Gioi tinh -> xung ho: Nam -> "anh ", Nu -> "chi ", khong ro -> ""."""
    g = (gioi_tinh or "").strip().lower()
    if g.startswith("nam"):
        return "anh "
    if g.startswith("nữ") or g.startswith("nu"):
        return "chị "
    return ""


def ten_phu_trach(db: Session, phong_ban: str) -> str:
    """Ten nguoi dang phu trach `phong_ban`, vd "anh Nguyen Duy Thanh".

    **Roi ve chinh ten phong ban** khi khong chac chan duoc mot nguoi (phong
    trong, hoac nhieu nguoi ma khong ai la dau moi ro rang). Cau "Moi Ke Toan
    duyet coc" hoi chung chung van tot hon la goi nham ten mot nguoi.

    Fail-soft giong ca file nay: moi loi deu nuot, tra ve ten phong ban.
    """
    pb = (phong_ban or "").strip()
    if not pb:
        return ""
    now = _time.time()
    cached = _PHU_TRACH_CACHE.get(pb)
    if cached and cached[1] > now:
        return cached[0]

    ten = pb
    try:
        rows = db.execute(
            text(
                "SELECT ho_ten, gioi_tinh, chuc_vu FROM hcns.employees "
                "WHERE phong_ban = :pb AND trang_thai = :dl "
                "AND ngay_nghi_viec IS NULL AND COALESCE(ho_ten, '') <> ''"
            ),
            {"pb": pb, "dl": "Đang làm"},
        ).all()
        if len(rows) > 1:
            rows = [r for r in rows if (r[2] or "").strip() in _CHUC_VU_DAU_MOI]
        if len(rows) == 1:
            ten = _xung_ho(rows[0][1]) + (rows[0][0] or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_post ten_phu_trach(%r) that bai: %s", pb, exc)
        try:
            db.rollback()
        except Exception:
            pass

    _PHU_TRACH_CACHE[pb] = (ten, now + _PHU_TRACH_TTL_SEC)
    return ten


def post_to_group(
    db: Session,
    *,
    content: str,
    room_name: str = ROOM_KD_KETOAN,
    sender_username: str = MAI_USERNAME,
    sender_name: str = MAI_DISPLAY_NAME,
) -> Optional[int]:
    """Đăng 1 tin vào nhóm `room_name`. Trả message id (None nếu không gửi được).

    Fail-soft: KHÔNG raise ra ngoài — caller bọc thêm try/except cũng không sao.
    """
    try:
        room_id = _resolve_room(db, room_name)
        if not room_id:
            logger.warning("chat_post: khong tim thay nhom %r — bo qua", room_name)
            return None
        row = db.execute(
            text(
                "INSERT INTO hcns.chat_messages "
                "(room_id, sender_username, sender_name, content) "
                "VALUES (:r, :su, :sn, :c) RETURNING id, created_at"
            ),
            {"r": room_id, "su": sender_username, "sn": sender_name, "c": content},
        ).first()
        db.commit()
        mid = int(row[0])
        created_at = row[1].isoformat() if row[1] is not None else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_post insert failed (room=%r): %s", room_name, exc)
        try:
            db.rollback()
        except Exception:
            pass
        return None

    _notify_members(db, room_id, mid, sender_username, content)
    _publish_realtime(room_id, mid, sender_username, sender_name, content, created_at)
    return mid
