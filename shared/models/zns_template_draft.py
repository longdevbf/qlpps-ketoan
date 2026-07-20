"""ZNSTemplateDraft — lưu draft template trước khi submit lên Zalo Cloud.

Workflow:
  1. Anh design template (content, biến) trên app + Save draft → row mới với status='draft'
  2. App copy content vào clipboard + redirect Zalo Cloud → anh paste + submit Zalo
  3. App fetch list template từ Zalo API → match với draft theo content/name → update template_id + status
  4. Khi Zalo duyệt → status='approved' + có template_id
"""
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class ZNSTemplateDraft(Base):
    __tablename__ = "zns_template_draft"
    __table_args__ = ({"schema": "shared"},)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[Optional[str]] = mapped_column(String(64))    # welcome_lead | quote_approved
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)   # nội dung tin nhắn với {{1}}, {{2}}, ...
    params_schema: Mapped[Optional[list]] = mapped_column(JSONB)  # ["customer_name","agent_name",...]
    sample_params: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB)  # {"1":"A","2":"B"}
    category: Mapped[Optional[str]] = mapped_column(String(32))   # cskh | order | promotion
    status: Mapped[str] = mapped_column(String(20), server_default="draft", nullable=False)  # draft | pending | approved | rejected
    zalo_template_id: Mapped[Optional[str]] = mapped_column(String(64))   # ID Zalo cấp khi duyệt
    zalo_status_raw: Mapped[Optional[dict]] = mapped_column(JSONB)        # raw response Zalo
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
