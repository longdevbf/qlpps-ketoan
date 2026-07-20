"""MaiPolicy — Hạn mức / định mức cho Mai AI quyết định auto-approve vs escalate.

source     : 'baogia_quote' | 'muahang_po' | 'marketing_km' | 'duyet_chi'
             | 'denghitt' | 'xin_nghi' | 'lenh_di_do' | 'muahang_ncc_new'
             | 'hcns_salary_increase' | ...
rule_type  : 'max_amount' | 'max_discount_pct' | 'max_percent'
             | 'max_days' | 'max_km' | 'enabled' | ...
value      : Numeric(15,2) threshold (hoặc 0/1 cho rule_type='enabled').
unit       : 'VND' | '%' | 'ngày' | 'km' | 'bool' | ...
enabled    : True = áp dụng, False = bỏ qua rule.
note       : Mô tả ngắn (Mai dùng để giải thích khi escalate).
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, func as sa_func, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from shared.db import Base


class MaiPolicy(Base):
    __tablename__ = "mai_policies"
    __table_args__ = (
        # UNIQUE (source, rule_type, scope,
        #         COALESCE(scope_value, ''), COALESCE(rule_category, ''))
        # — Index expression được DDL/migration tạo trước; ở model ta khai
        # báo Index thường (nullable=True trên scope_value, rule_category).
        Index(
            "ux_mai_policies_source_rule_scope_cat",
            "source",
            "rule_type",
            "scope",
            sa_func.coalesce(text("scope_value"), text("''")),
            sa_func.coalesce(text("rule_category"), text("''")),
            unique=True,
        ),
        Index("ix_mai_policies_scope", "scope", "scope_value"),
        {"schema": "shared"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    source: Mapped[str] = mapped_column(Text, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)

    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # scope: 'company' | 'department' | 'employee'
    scope: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="company", default="company"
    )
    # scope_value: NULL khi scope='company';
    # tên phòng ban khi 'department'; username khi 'employee'.
    scope_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # rule_category: loại chi cụ thể trong cùng (source, scope_value).
    # VD: 'cong_tac' | 'ccdc' | 'ads' | 'van_tu' | 'trang_thiet_bi'
    #     | 'tam_ung' | 'default'. NULL khi rule áp cho cả phòng.
    rule_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    updated_by: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
