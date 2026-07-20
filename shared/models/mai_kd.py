"""SQLAlchemy ORM cho 6 bảng Mai KD.

Anh Quang 2026-06-15 — match schema migration 0036_mai_kd_features.py.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKeyConstraint, Index,
    Integer, Numeric, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiFeatureConfig(Base):
    __tablename__ = "mai_feature_config"
    __table_args__ = (
        Index("ix_mai_fc_dept_enabled", "dept", "enabled"),
        Index("ix_mai_fc_category", "category"),
        {"schema": "shared"},
    )

    feature_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    dept: Mapped[str] = mapped_column(String(16), primary_key=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    instruction_prompt: Mapped[Optional[str]] = mapped_column(Text)
    fallback_text: Mapped[Optional[str]] = mapped_column(Text)
    requires_promotion: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MaiPersona(Base):
    __tablename__ = "mai_persona"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tone_description: Mapped[Optional[str]] = mapped_column(Text)
    forbidden_patterns: Mapped[list] = mapped_column(ARRAY(Text), nullable=False, server_default="{}")
    max_message_length: Mapped[int] = mapped_column(Integer, nullable=False, server_default="200")
    min_message_length: Mapped[int] = mapped_column(Integer, nullable=False, server_default="30")
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False, server_default="0.7")
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MaiCustomerExclude(Base):
    __tablename__ = "mai_customer_exclude"
    __table_args__ = (
        Index("ix_mai_excl_cust", "customer_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    feature_key: Mapped[Optional[str]] = mapped_column(String(64))
    nv_username: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MaiGeneratedMessage(Base):
    __tablename__ = "mai_generated_message"
    __table_args__ = (
        Index("ix_mai_msg_feature_time", "feature_key", "created_at"),
        Index("ix_mai_msg_dept_time", "dept", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dept: Mapped[str] = mapped_column(String(16), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    customer_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    nv_username: Mapped[Optional[str]] = mapped_column(String(64))
    conv_id: Mapped[Optional[str]] = mapped_column(String(64))
    chat_room_id: Mapped[Optional[int]] = mapped_column(Integer)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(64))
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 6))
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    guard_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    guard_fail_reason: Mapped[Optional[str]] = mapped_column(Text)
    customer_replied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    replied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MaiPromotionUsed(Base):
    __tablename__ = "mai_promotion_used"
    __table_args__ = (
        Index("ix_mai_promo_km_time", "khuyen_mai_id", "sent_at"),
        Index("ix_mai_promo_cust", "customer_id", "sent_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    khuyen_mai_id: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    customer_replied: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    customer_redeemed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    redeemed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MaiActionLog(Base):
    __tablename__ = "mai_action_log"
    __table_args__ = (
        Index("ix_mai_act_feature_time", "feature_key", "created_at"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    dept: Mapped[str] = mapped_column(String(16), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[Optional[str]] = mapped_column(String(64))
    nv_username: Mapped[Optional[str]] = mapped_column(String(64))
    customer_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    ref_id: Mapped[Optional[str]] = mapped_column(String(64))
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text)
    error: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
