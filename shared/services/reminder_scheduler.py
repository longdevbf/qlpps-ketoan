"""APScheduler reminder cho CalendarEvent.

Chạy mỗi 5 phút. Tìm events có:
  - reminder_minutes NOT NULL
  - reminder_sent_at IS NULL
  - start_dt - reminder_minutes <= NOW() < start_dt
→ Tạo notification cho owner + participants (status='accepted'|'invited')
→ Set reminder_sent_at = NOW() (idempotent)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

log = logging.getLogger(__name__)
_scheduler: Optional[BackgroundScheduler] = None


def reminder_tick():
    """1 tick — tìm events đến hạn nhắc + push noti. Fail-soft."""
    try:
        from shared.db import SessionLocal
        from shared.models import CalendarEvent
        from shared.services.notify import notify
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            # Pre-filter: chỉ events trong 24h sắp tới chưa nhắc
            window_end = now + timedelta(hours=24)
            rows = db.execute(
                select(CalendarEvent).where(
                    CalendarEvent.reminder_minutes.isnot(None),
                    CalendarEvent.reminder_sent_at.is_(None),
                    CalendarEvent.start_dt > now,
                    CalendarEvent.start_dt <= window_end,
                )
            ).scalars().all()
            processed = 0
            for ev in rows:
                # Trigger time = start - reminder_minutes
                trigger_at = ev.start_dt - timedelta(minutes=ev.reminder_minutes or 0)
                if trigger_at > now:
                    continue  # chưa đến giờ nhắc
                # Build target list: owner + participants accepted/invited
                targets = {ev.owner_username}
                for p in (ev.participants or []):
                    if p.status in ('accepted', 'invited'):
                        targets.add(p.username)
                title = f'⏰ [Lịch] {ev.title}'
                msg = f'Bắt đầu lúc {ev.start_dt.strftime("%H:%M %d/%m")}'
                if ev.location:
                    msg += f' @ {ev.location}'
                for u in targets:
                    if not u:
                        continue
                    try:
                        notify(db, target=u, source_app='calendar',
                               event_type='calendar:reminder',
                               title=title, message=msg,
                               ref_type='calendar_event', ref_id=ev.id,
                               url='/lich-lam-viec', severity='info',
                               created_by='system')
                    except Exception as e:
                        log.warning("notify reminder fail %s: %s", u, e)
                ev.reminder_sent_at = now
                processed += 1
            db.commit()
            log.info("reminder_tick processed %d events (scanned %d)",
                     processed, len(rows))
    except Exception as e:
        log.error("reminder_tick error: %s", e, exc_info=True)


def start_scheduler():
    """Gọi 1 lần lúc app startup."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(timezone='Asia/Ho_Chi_Minh')
    _scheduler.add_job(reminder_tick, 'interval', minutes=5,
                       id='calendar_reminder', max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("Calendar reminder scheduler started (5min interval)")
    return _scheduler


def stop_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
