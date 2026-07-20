"""CalendarEvent + EventParticipant — lịch làm việc cross-app."""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class CalendarEvent(Base):
    __tablename__ = "calendar_events"
    __table_args__ = (
        Index("ix_calendar_events_owner", "owner_username"),
        Index("ix_calendar_events_start", "start_dt"),
        Index("ix_calendar_events_source", "source", "source_ref_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_username: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_dt: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    all_day: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    event_type: Mapped[str] = mapped_column(
        String(16), server_default="personal", nullable=False
    )
    # personal | shared | public
    location: Mapped[Optional[str]] = mapped_column(String(255))
    color: Mapped[Optional[str]] = mapped_column(String(16))  # hex #aabbcc
    timezone: Mapped[str] = mapped_column(
        String(64), server_default="Asia/Ho_Chi_Minh", nullable=False
    )
    # Source tracking — link tới origin entity nếu auto-create
    source: Mapped[Optional[str]] = mapped_column(String(32))
    # 'manual' | 'leave_request' | 'directive' | 'dao_tao_session'
    source_ref_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Reminder
    reminder_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # phút trước event
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Lặp lại (recurrence): none|daily|weekday|weekly|monthly. recurrence_until = lặp đến khi nào.
    recurrence: Mapped[Optional[str]] = mapped_column(String(16))
    recurrence_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    participants: Mapped[list["EventParticipant"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin"
    )
    attachments: Mapped[list["EventAttachment"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", lazy="selectin",
        order_by="EventAttachment.created_at",
    )


class EventParticipant(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("event_id", "username", name="uq_event_participant"),
        Index("ix_event_participants_username", "username"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("shared.calendar_events.id", ondelete="CASCADE"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), server_default="invited", nullable=False
    )
    # invited | accepted | declined
    role: Mapped[str] = mapped_column(
        String(16), server_default="attendee", nullable=False
    )
    # organizer | attendee
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["CalendarEvent"] = relationship(back_populates="participants")


class EventAttachment(Base):
    """Tài liệu đính kèm 1 event (CV phỏng vấn, tài liệu họp...).

    File lưu vật lý qua shared.utils.uploads: {UPLOAD_DIR}/calendar/{scope}/{stored_name}
    với scope = 'event_{event_id}'. Serve/xoá qua router calendar (resolve_path).
    """
    __tablename__ = "event_attachments"
    __table_args__ = (
        Index("ix_event_attachments_event", "event_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("shared.calendar_events.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)      # tên gốc
    stored_name: Mapped[str] = mapped_column(String(128), nullable=False)   # uuid.ext
    scope: Mapped[str] = mapped_column(String(64), nullable=False)          # event_{id}
    size: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    content_type: Mapped[Optional[str]] = mapped_column(String(128))
    uploaded_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    event: Mapped["CalendarEvent"] = relationship(back_populates="attachments")
