"""Worker — fail-soft entry points called from FastAPI background tasks + scheduler.

Functions:
    - send_zns_for_lead(lead_id)       : khi lead mới được tạo → DM khách qua ZNS
    - send_zns_for_quote(quote_id)     : khi báo giá được duyệt → DM khách
    - refresh_token_if_needed()        : cron tự refresh access_token
    - _log_send(...)                   : insert shared.zns_send_log
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _log_send(
    db: Session,
    *,
    ref_type: str,
    ref_id: str,
    phone: str,
    template_id: str,
    template_key: str,
    params: dict,
    status: str,
    error_code: Optional[int] = None,
    error_message: Optional[str] = None,
    msg_id: Optional[str] = None,
    response: Optional[dict] = None,
    quota_remaining: Optional[int] = None,
    triggered_by: Optional[str] = None,
) -> None:
    """Insert row vào shared.zns_send_log. Fail-soft."""
    try:
        db.execute(
            text("""
                INSERT INTO shared.zns_send_log
                    (ref_type, ref_id, phone, template_id, template_key,
                     params, status, error_code, error_message, zalo_msg_id,
                     response, quota_remaining, triggered_by, sent_at)
                VALUES (:rt, :ri, :ph, :tid, :tk, CAST(:p AS JSONB),
                        :st, :ec, :em, :mi, CAST(:r AS JSONB), :qr, :tb, NOW())
            """),
            {
                "rt": ref_type, "ri": ref_id, "ph": phone,
                "tid": template_id, "tk": template_key,
                "p": _json(params or {}),
                "st": status, "ec": error_code, "em": (error_message or "")[:500],
                "mi": msg_id, "r": _json(response or {}),
                "qr": quota_remaining, "tb": triggered_by,
            },
        )
        db.commit()
    except Exception as e:
        logger.warning("[ZNS] log_send fail: %s", e)
        try:
            db.rollback()
        except Exception:
            pass


def _json(obj: Any) -> str:
    import json as _j
    try:
        return _j.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return "{}"

def _parse_remaining_quota(data: dict) -> Optional[int]:
    """Zalo API trả nested: data.quota.remainingQuota (str). Parse → int."""
    if not isinstance(data, dict):
        return None
    q = data.get('quota')
    if not isinstance(q, dict):
        return None
    raw = q.get('remainingQuota')
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None



def send_zns_for_lead(lead_id: str, triggered_by: Optional[str] = None) -> dict:
    """Background task: gửi ZNS chào khách khi lead mới được tạo.

    Hook từ marketing/routers/leads.py:create_lead qua BackgroundTasks.
    Fail-soft mọi nơi — không bao giờ raise vào caller.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from .client import send_zns_message, normalize_vn_phone

    db: Session = SessionLocal()
    result: dict = {"ok": False, "skipped": True, "reason": ""}
    try:
        # 1. Check auto_send enabled
        if not zcfg.is_auto_send_enabled(db, "on_lead_new"):
            result["reason"] = "auto_send disabled"
            return result

        # 2. Check config + token sẵn sàng
        if not zcfg.is_configured(db):
            result["reason"] = "OA credentials missing"
            return result
        # Token V4 sống 1h — proactive refresh nếu còn <5 phút
        if not zcfg.has_valid_token(db, safety_margin_min=5):
            ref = refresh_token_if_needed(force=True)
            if not ref.get("refreshed"):
                result["reason"] = f"Token hết hạn + refresh fail: {ref.get('reason')}"
                return result
        token_row = zcfg.load_token(db)
        access_token = token_row.get("access_token")
        if not access_token:
            result["reason"] = "access_token missing — anh chạy auth flow để lấy token"
            return result

        # 3. Lookup template
        template_id = zcfg.get_template_id(db, "welcome_lead")
        if not template_id:
            result["reason"] = "template welcome_lead chưa được set"
            return result

        # 4. Load lead
        from marketing.app.models import Lead  # lazy cross-app
        lead = db.get(Lead, lead_id)
        if lead is None:
            result["reason"] = f"lead {lead_id} không tồn tại"
            return result

        # 5. Normalize phone
        phone = normalize_vn_phone(lead.sdt)
        if not phone:
            result["reason"] = f"SĐT không hợp lệ: {lead.sdt!r}"
            _log_send(db, ref_type="lead", ref_id=str(lead_id),
                      phone=str(lead.sdt or ""), template_id=template_id,
                      template_key="welcome_lead", params={},
                      status="invalid_phone",
                      error_message=result["reason"], triggered_by=triggered_by)
            return result

        # 6. Build template_data — template 531454 CRM Khách Hàng
        # Params: _GIOI_TINH_KHACH_HANG_, _TEN_KHACH_HANG_, _TEN_SAN_PHAM_, _ID_KHACH_HANG_
        gioi_tinh = (getattr(lead, "gioi_tinh", None) or "").strip() or "Quý khách"
        params = {
            "_GIOI_TINH_KHACH_HANG_": gioi_tinh[:20],
            "_TEN_KHACH_HANG_": (lead.ho_ten or "Quý khách")[:60],
            "_TEN_SAN_PHAM_": (lead.nhom_hang or "Nội thất")[:60],
            "_ID_KHACH_HANG_": str(lead.id),
        }

        # 7. Gọi API
        resp = send_zns_message(
            access_token=access_token,
            phone=phone,
            template_id=template_id,
            template_data=params,
            tracking_id=f"lead-{lead.id}",
        )

        # 8. Parse response
        err = int(resp.get("error") or 0)
        data = resp.get("data") or {}
        status_str = "sent" if err == 0 else "failed"
        msg_id = str(data.get("msg_id") or "") or None
        quota = _parse_remaining_quota(data)
        _log_send(
            db, ref_type="lead", ref_id=str(lead.id), phone=phone,
            template_id=template_id, template_key="welcome_lead", params=params,
            status=status_str, error_code=err if err != 0 else None,
            error_message=resp.get("message") if err != 0 else None,
            msg_id=msg_id, response=resp, quota_remaining=quota,
            triggered_by=triggered_by,
        )
        result = {"ok": err == 0, "error": err, "msg_id": msg_id,
                  "skipped": False, "phone": phone}
        return result
    except Exception as e:
        logger.exception("[ZNS] send_zns_for_lead fail: %s", e)
        result["reason"] = f"exception: {e}"
        return result
    finally:
        try:
            db.close()
        except Exception:
            pass


def send_zns_for_quote(quote_id: int, triggered_by: Optional[str] = None) -> dict:
    """Background task: gửi ZNS khi báo giá được duyệt.

    Template key: 'quote_approved'. Anh setup template trên Zalo Cloud + lưu id.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from .client import send_zns_message, normalize_vn_phone

    db: Session = SessionLocal()
    result: dict = {"ok": False, "skipped": True, "reason": ""}
    try:
        if not zcfg.is_auto_send_enabled(db, "on_quote_approved"):
            result["reason"] = "auto_send on_quote_approved disabled"
            return result
        if not zcfg.is_configured(db):
            result["reason"] = "OA credentials missing"
            return result
        if not zcfg.has_valid_token(db, safety_margin_min=5):
            ref = refresh_token_if_needed(force=True)
            if not ref.get("refreshed"):
                result["reason"] = f"Token hết hạn + refresh fail: {ref.get('reason')}"
                return result
        token_row = zcfg.load_token(db)
        access_token = token_row.get("access_token")
        if not access_token:
            result["reason"] = "access_token missing"
            return result
        template_id = zcfg.get_template_id(db, "quote_approved")
        if not template_id:
            result["reason"] = "template quote_approved chưa được set"
            return result

        from baogia.app.models import Quote
        q = db.get(Quote, quote_id)
        if q is None:
            result["reason"] = f"quote {quote_id} không tồn tại"
            return result

        phone = normalize_vn_phone(q.customer_phone)
        if not phone:
            result["reason"] = f"SĐT khách không hợp lệ: {q.customer_phone!r}"
            return result

        # Dedup: đã gửi thành công "Xác nhận hóa đơn" cho đơn này rồi thì bỏ qua
        # (tránh double-send khi KT thao tác lại / chạy backfill lại).
        already = db.execute(text(
            "SELECT 1 FROM shared.zns_send_log "
            "WHERE template_key='quote_approved' AND ref_id=:r AND status='sent' LIMIT 1"
        ), {"r": str(q.id)}).first()
        if already:
            result["reason"] = "đã gửi quote_approved trước đó"; return result

        # Params template 530952: Xác nhận hóa đơn mua hàng
        # _TEN_KHACH_HANG_, _ID_DON_HANG_, _CHIET_KHAU_, _NHAN_VIEN_BAN_HANG_,
        # _TIEN_DAT_COC_, _TONG_TIEN_, _NGAY_MUA_
        def _fmt_money(v) -> str:
            try: return f"{int(float(v or 0)):,}".replace(",", ".")
            except Exception: return "0"
        def _fmt_date(v) -> str:
            if not v: return "—"
            try:
                from datetime import datetime as _dt
                if hasattr(v, "strftime"): return v.strftime("%d/%m/%Y")
                return str(v)[:10]
            except Exception: return str(v)[:10]

        ngay_duyet = q.kt_duyet_luc or q.duyet_luc  # ưu tiên ngày KT duyệt
        params = {
            "_TEN_KHACH_HANG_":     (q.customer_name or "Quý khách")[:60],
            "_ID_DON_HANG_":        str(q.quote_number or "")[:30],
            "_CHIET_KHAU_":         _fmt_money(getattr(q, "discount_amount", 0)),
            "_NHAN_VIEN_BAN_HANG_": str(q.salesperson or "Papasan")[:60],
            "_TIEN_DAT_COC_":       _fmt_money(getattr(q, "coc_so_tien", 0)),
            "_TONG_TIEN_":          _fmt_money(getattr(q, "tong_don", 0)),
            "_NGAY_MUA_":           _fmt_date(ngay_duyet),
        }
        resp = send_zns_message(
            access_token=access_token, phone=phone, template_id=template_id,
            template_data=params, tracking_id=f"quote-{q.id}",
        )
        err = int(resp.get("error") or 0)
        data = resp.get("data") or {}
        _log_send(
            db, ref_type="quote", ref_id=str(q.id), phone=phone,
            template_id=template_id, template_key="quote_approved", params=params,
            status="sent" if err == 0 else "failed",
            error_code=err if err != 0 else None,
            error_message=resp.get("message") if err != 0 else None,
            msg_id=str(data.get("msg_id") or "") or None,
            response=resp, quota_remaining=_parse_remaining_quota(data),
            triggered_by=triggered_by,
        )
        return {"ok": err == 0, "error": err, "skipped": False, "phone": phone}
    except Exception as e:
        logger.exception("[ZNS] send_zns_for_quote fail: %s", e)
        result["reason"] = f"exception: {e}"
        return result
    finally:
        try: db.close()
        except Exception: pass


def send_zns_for_delivered(ma_don: str, triggered_by: Optional[str] = None) -> dict:
    """Gửi ZNS Giao Hàng Thành Công (template 530507) khi kế toán đánh dấu đơn Đã xong.

    Lookup thông tin đơn từ baogia.quotes theo quote_number = ma_don.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from .client import send_zns_message, normalize_vn_phone

    db: Session = SessionLocal()
    result: dict = {"ok": False, "skipped": True, "reason": ""}
    try:
        if not zcfg.is_configured(db):
            result["reason"] = "OA credentials missing"; return result
        if not zcfg.has_valid_token(db, safety_margin_min=5):
            ref = refresh_token_if_needed(force=True)
            if not ref.get("refreshed"):
                result["reason"] = f"Token refresh fail: {ref.get('reason')}"; return result
        access_token = (zcfg.load_token(db) or {}).get("access_token")
        if not access_token:
            result["reason"] = "access_token missing"; return result
        template_id = zcfg.get_template_id(db, "delivered")
        if not template_id:
            result["reason"] = "template delivered chưa set"; return result

        from baogia.app.models import Quote
        from sqlalchemy import select as _sel
        q = db.execute(_sel(Quote).where(Quote.quote_number == ma_don)).scalar_one_or_none()
        if q is None:
            result["reason"] = f"quote {ma_don} không tồn tại"; return result

        phone = normalize_vn_phone(q.customer_phone)
        if not phone:
            result["reason"] = f"SĐT không hợp lệ: {q.customer_phone!r}"; return result

        # Dedup: đã gửi thành công ZNS "Giao hàng thành công" cho đơn này rồi
        # thì bỏ qua (tránh double-send khi KT duyệt lại / chạy backfill lại).
        already = db.execute(text(
            "SELECT 1 FROM shared.zns_send_log "
            "WHERE template_key='delivered' AND ref_id=:r AND status='sent' LIMIT 1"
        ), {"r": ma_don}).first()
        if already:
            result["reason"] = "đã gửi delivered trước đó"; return result

        def _fmt_money(v) -> str:
            try: return f"{int(float(v or 0)):,}".replace(",", ".")
            except Exception: return "0"

        params = {
            "_TEN_KHACH_HANG_":      (q.customer_name or "Quý khách")[:60],
            "_ID_DON_HANG_":         str(q.quote_number or "")[:30],
            "_CHIET_KHAU_":          _fmt_money(getattr(q, "discount_amount", 0)),
            "_TONG_TIEN_":           _fmt_money(getattr(q, "tong_don", 0)),
            "_TRANG_THAI_DON_HANG_": "Đã xong",
        }
        resp = send_zns_message(
            access_token=access_token, phone=phone, template_id=template_id,
            template_data=params, tracking_id=f"delivered-{ma_don}",
        )
        err = int(resp.get("error") or 0)
        data = resp.get("data") or {}
        _log_send(db, ref_type="delivered", ref_id=ma_don, phone=phone,
                  template_id=template_id, template_key="delivered", params=params,
                  status="sent" if err == 0 else "failed",
                  error_code=err if err != 0 else None,
                  error_message=resp.get("message") if err != 0 else None,
                  msg_id=str(data.get("msg_id") or "") or None,
                  response=resp, quota_remaining=_parse_remaining_quota(data),
                  triggered_by=triggered_by)
        return {"ok": err == 0, "error": err, "skipped": False, "phone": phone}
    except Exception as e:
        logger.exception("[ZNS] send_zns_for_delivered fail: %s", e)
        result["reason"] = f"exception: {e}"; return result
    finally:
        try: db.close()
        except Exception: pass


def send_zns_for_cskh(ma_don: str, triggered_by: Optional[str] = None) -> dict:
    """Gửi ZNS Đánh giá trải nghiệm (template 530518) sau khi đơn hoàn thành.

    Lookup từ baogia.quotes theo quote_number = ma_don.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from .client import send_zns_message, normalize_vn_phone

    db: Session = SessionLocal()
    result: dict = {"ok": False, "skipped": True, "reason": ""}
    try:
        if not zcfg.is_configured(db):
            result["reason"] = "OA credentials missing"; return result
        if not zcfg.has_valid_token(db, safety_margin_min=5):
            ref = refresh_token_if_needed(force=True)
            if not ref.get("refreshed"):
                result["reason"] = f"Token refresh fail: {ref.get('reason')}"; return result
        access_token = (zcfg.load_token(db) or {}).get("access_token")
        if not access_token:
            result["reason"] = "access_token missing"; return result
        template_id = zcfg.get_template_id(db, "cskh_followup")
        if not template_id:
            result["reason"] = "template cskh_followup chưa set"; return result

        from baogia.app.models import Quote
        from sqlalchemy import select as _sel
        q = db.execute(_sel(Quote).where(Quote.quote_number == ma_don)).scalar_one_or_none()
        if q is None:
            result["reason"] = f"quote {ma_don} không tồn tại"; return result

        phone = normalize_vn_phone(q.customer_phone)
        if not phone:
            result["reason"] = f"SĐT không hợp lệ: {q.customer_phone!r}"; return result

        params = {
            "_TEN_KHACH_HANG_": (q.customer_name or "Quý khách")[:60],
            "_ID_DON_HANG_":    str(q.quote_number or "")[:30],
        }
        resp = send_zns_message(
            access_token=access_token, phone=phone, template_id=template_id,
            template_data=params, tracking_id=f"cskh-{ma_don}",
        )
        err = int(resp.get("error") or 0)
        data = resp.get("data") or {}
        _log_send(db, ref_type="cskh", ref_id=ma_don, phone=phone,
                  template_id=template_id, template_key="cskh_followup", params=params,
                  status="sent" if err == 0 else "failed",
                  error_code=err if err != 0 else None,
                  error_message=resp.get("message") if err != 0 else None,
                  msg_id=str(data.get("msg_id") or "") or None,
                  response=resp, quota_remaining=_parse_remaining_quota(data),
                  triggered_by=triggered_by)
        return {"ok": err == 0, "error": err, "skipped": False, "phone": phone}
    except Exception as e:
        logger.exception("[ZNS] send_zns_for_cskh fail: %s", e)
        result["reason"] = f"exception: {e}"; return result
    finally:
        try: db.close()
        except Exception: pass


def _find_ceo_username(db: Session) -> Optional[str]:
    """Tìm username CEO (role admin/ceo/assistant_ceo) để Mai DM."""
    try:
        from sqlalchemy import text as _t
        row = db.execute(_t(
            "SELECT username FROM shared.users "
            "WHERE active=TRUE AND role IN ('ceo','admin','assistant_ceo') "
            "ORDER BY CASE role WHEN 'ceo' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END LIMIT 1"
        )).first()
        return row[0] if row else None
    except Exception:
        return None


def _alert_ceo_refresh_failed(db: Session, fail_count: int, error_msg: str) -> None:
    """Mai DM CEO cảnh báo ZNS refresh fail liên tiếp. Fail-soft."""
    try:
        ceo = _find_ceo_username(db)
        if not ceo:
            return
        from ceo.app.ai_brief.notify import ensure_dm_with_mai, mai_send_message
        room_id = ensure_dm_with_mai(db, ceo)
        if not room_id:
            return
        msg = (
            f"🚨 Sếp ơi, ZNS token refresh **fail {fail_count} lần liên tiếp**.\n\n"
            f"Lý do: `{error_msg[:200]}`\n\n"
            f"Anh re-OAuth lại giúp em ở app:\n"
            f"➡ marketing.qlpps.com/zalo-oa → bấm '🔗 Lấy URL cấp quyền' → Cho phép.\n\n"
            f"Sau khi xong, em tự refresh được trở lại bình thường."
        )
        mai_send_message(db, int(room_id), msg)
    except Exception as e:
        logger.warning("[ZNS] alert_ceo_refresh_failed fail: %s", e)


def check_refresh_token_age_and_alert(*, alert_days_before_expire: int = 10) -> dict:
    """Cron daily: cảnh báo CEO trước khi refresh_token (3 tháng) sắp hết hạn.

    Zalo refresh_token sống ~90 ngày. Khi đạt 80 ngày → DM CEO nhắc re-OAuth
    trong vòng 10 ngày tới để tránh ZNS gián đoạn.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td

    db: Session = SessionLocal()
    try:
        tok = zcfg.load_token(db)
        issued_at_str = tok.get("refresh_token_issued_at")
        if not issued_at_str:
            return {"alerted": False, "reason": "chưa biết refresh_token_issued_at"}
        try:
            issued = _dt.fromisoformat(issued_at_str.replace("Z", "+00:00"))
        except Exception:
            return {"alerted": False, "reason": f"parse fail: {issued_at_str}"}
        days_old = (_dt.now(_tz.utc) - issued).days
        days_left = 90 - days_old
        # Cảnh báo khi còn <= alert_days_before_expire ngày
        if days_left > alert_days_before_expire:
            return {"alerted": False, "reason": f"còn {days_left} ngày, chưa cần cảnh báo"}
        # Dedupe: chỉ DM 1 lần / 3 ngày
        last_alert = tok.get("last_expiry_alert_at")
        if last_alert:
            try:
                la = _dt.fromisoformat(last_alert.replace("Z", "+00:00"))
                if (_dt.now(_tz.utc) - la) < _td(days=3):
                    return {"alerted": False, "reason": "đã alert gần đây, skip"}
            except Exception:
                pass
        # DM CEO
        ceo = _find_ceo_username(db)
        if not ceo:
            return {"alerted": False, "reason": "no CEO found"}
        try:
            from ceo.app.ai_brief.notify import ensure_dm_with_mai, mai_send_message
            room_id = ensure_dm_with_mai(db, ceo)
            if room_id:
                msg = (
                    f"⏰ Sếp ơi, ZNS refresh_token sắp hết hạn (còn ~{days_left} ngày).\n\n"
                    f"Anh re-OAuth giúp em trong tuần này nhé:\n"
                    f"➡ marketing.qlpps.com/zalo-oa → bấm '🔗 Lấy URL cấp quyền' → Cho phép.\n\n"
                    f"Em sẽ nhắc lại nếu chưa OAuth mới."
                )
                mai_send_message(db, int(room_id), msg)
                tok["last_expiry_alert_at"] = _dt.now(_tz.utc).isoformat()
                from shared.models import AppConfig
                from sqlalchemy import select as _select
                row = db.execute(_select(AppConfig).where(AppConfig.app=="zalo_oa", AppConfig.key=="token")).scalar_one_or_none()
                if row is not None:
                    row.value = tok
                    db.commit()
                return {"alerted": True, "days_left": days_left}
        except Exception as e:
            logger.warning("[ZNS] expiry alert DM fail: %s", e)
        return {"alerted": False, "reason": "DM failed"}
    finally:
        try: db.close()
        except Exception: pass


def refresh_token_if_needed(*, force: bool = False) -> dict:
    """Cron — refresh access_token nếu sắp hết hạn (TTL <30 phút) hoặc force=True.

    Fail-soft. Trả {refreshed: bool, reason}.
    """
    from shared.db import SessionLocal
    from . import config as zcfg
    from .client import refresh_oauth_token

    db: Session = SessionLocal()
    try:
        if not zcfg.is_configured(db):
            return {"refreshed": False, "reason": "OA chưa cấu hình"}
        if not force and zcfg.has_valid_token(db, safety_margin_min=30):
            return {"refreshed": False, "reason": "token còn hợp lệ"}
        creds = zcfg.load_creds(db)
        tok = zcfg.load_token(db)
        rt = tok.get("refresh_token")
        if not rt:
            return {"refreshed": False, "reason": "refresh_token missing — anh chạy authorize flow"}
        resp = refresh_oauth_token(
            app_id=creds["app_id"],
            secret_key=creds["secret_key"],
            refresh_token=rt,
        )
        new_at = resp.get("access_token")
        if not new_at:
            # Increment fail counter — alert nếu >=3 lần liên tiếp
            fail_n = zcfg.increment_refresh_fail(db)
            import json as _j
            err_msg = (resp.get("error_description")
                       or resp.get("error_name")
                       or resp.get("message")
                       or f"Full response: {_j.dumps(resp, ensure_ascii=False, default=str)[:300]}")
            if fail_n >= 3:
                _alert_ceo_refresh_failed(db, fail_n, err_msg)
            return {
                "refreshed": False,
                "reason": err_msg,
                "fail_count": fail_n,
                "raw_response": resp,
            }
        zcfg.save_token(
            db,
            access_token=new_at,
            refresh_token=resp.get("refresh_token") or rt,
            expires_in=int(resp.get("expires_in") or 90000),
        )
        return {"refreshed": True, "reason": "OK", "expires_in": resp.get("expires_in")}
    except Exception as e:
        logger.exception("[ZNS] refresh fail: %s", e)
        return {"refreshed": False, "reason": f"exception: {e}"}
    finally:
        try: db.close()
        except Exception: pass
