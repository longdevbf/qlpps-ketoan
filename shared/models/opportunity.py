"""Product opportunities — Module 7 CEO: phân tích nhóm SP mới.

3 nguồn ingest:
    - 'quote_miss': KH hỏi SP không có trong pricing → log từ baogia
    - 'lead_keyword': từ khoá SP lạ trong marketing.leads.note
    - 'repeat_buy': KH đặt lặp 1 SP > 3 lần → gợi ý combo
    - 'ncc_offer': NCC chào SP mới trong muahang
    - 'manual': CEO/trợ lý nhập tay

status: 'new' | 'researching' | 'approved' | 'rejected'
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, BigInteger, Integer, Numeric, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from shared.db import Base


class ProductOpportunity(Base):
    __tablename__ = "product_opportunities"
    __table_args__ = (
        Index("ix_opp_status", "status"),
        Index("ix_opp_source", "source"),
        Index("ix_opp_last_seen", "last_seen"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nhom_hang: Mapped[Optional[str]] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    notes: Mapped[list["OpportunityNote"]] = relationship(
        "OpportunityNote", back_populates="opportunity", cascade="all, delete-orphan"
    )
    scorecard: Mapped[Optional["OpportunityScorecard"]] = relationship(
        "OpportunityScorecard", back_populates="opportunity",
        uselist=False, cascade="all, delete-orphan",
    )


class OpportunityNote(Base):
    __tablename__ = "opportunity_notes"
    __table_args__ = (
        Index("ix_opp_notes_opp", "opportunity_id"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("shared.product_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    author_username: Mapped[Optional[str]] = mapped_column(String(64))
    author_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("shared.users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    opportunity: Mapped["ProductOpportunity"] = relationship(
        "ProductOpportunity", back_populates="notes"
    )


class OpportunityScorecard(Base):
    __tablename__ = "opportunity_scorecard"
    __table_args__ = ({"schema": "shared"},)

    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("shared.product_opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    gia_von: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    gia_ban_du_kien: Mapped[Optional[float]] = mapped_column(Numeric(15, 2))
    bien_du_kien_pct: Mapped[Optional[float]] = mapped_column(Numeric(6, 2))
    san_luong_du_kien_thang: Mapped[Optional[int]] = mapped_column(Integer)
    doi_thu: Mapped[Optional[str]] = mapped_column(Text)
    rui_ro: Mapped[Optional[str]] = mapped_column(Text)
    co_hoi: Mapped[Optional[str]] = mapped_column(Text)
    ke_hoach: Mapped[Optional[str]] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[Optional[str]] = mapped_column(String(64))

    opportunity: Mapped["ProductOpportunity"] = relationship(
        "ProductOpportunity", back_populates="scorecard"
    )
