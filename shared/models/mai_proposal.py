"""MaiProposal — Mai đề xuất việc → CEO chốt (Mode B).

Workflow:
  1) Mai (qua tool) tạo proposal status='pending' với items=[…], rationale.
  2) CEO duyệt qua /api/mai-proposals/{id}/decide:
       - approve         → status='approved', accepted_ids=NULL (= all).
       - partial         → status='partial',  accepted_ids=[i, j, …].
       - reject          → status='rejected', accepted_ids=[].
  3) Tool execute từng accepted item → tạo Directive / Approval / … ghi
     executed_results=[{item_index, directive_id, status: ok|fail, error?}]
     → status='executed'.
  4) User có thể /cancel khi pending → status='cancelled'.

Field nghĩa nhanh:
  - items          : JSONB list — vd directive items:
        [{ "to_user": "phuc",
           "title":   "Chạy báo cáo Sale T5",
           "body":    "...",
           "due_date":"2026-05-30",
           "priority":"high",
           "app":     "sale_admin" }, …]
  - accepted_ids   : INT[] index 0-based của items được CEO duyệt.
                     NULL = all items (status='approved'),
                     []   = không item nào (status='rejected').
  - executed_results: JSONB list parallel với accepted items — kết quả execute.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, DateTime, Index, Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiProposal(Base):
    __tablename__ = "mai_proposals"
    __table_args__ = (
        Index("ix_mai_proposals_user_status", "user_id", "status"),
        Index("ix_mai_proposals_status", "status"),
        Index("ix_mai_proposals_type", "proposal_type"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)

    proposal_type: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="directive", default="directive"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)

    # items: JSONB list of action specs (vd directive payload)
    items: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="[]", default=list
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="pending", default="pending"
    )

    approved_by: Mapped[Optional[str]] = mapped_column(String(64))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # accepted_ids: index của items được CEO duyệt
    #   NULL = duyệt all; [] = reject all; [0,2] = partial.
    accepted_ids: Mapped[Optional[list[int]]] = mapped_column(ARRAY(Integer))

    # executed_results: kết quả execute (do tool layer ghi sau)
    executed_results: Mapped[Optional[list]] = mapped_column(JSONB)
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
