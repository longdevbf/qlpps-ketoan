"""ceo foundation tables (approvals, directives, ceo_comments, feedback, opportunities)

Revision ID: 0002_ceo_foundation
Revises: 0001_baseline_shared
Create Date: 2026-04-26

Bảng nền cho App CEO (port 8007). Bao gồm:
    shared.approvals             — phê duyệt vượt ngưỡng
    shared.directives            — CEO giao việc trưởng phòng
    shared.ceo_comments          — bút phê CEO trên 1 entity
    shared.feedback              — phản hồi KH ingest từ Pancake/Zalo/FB/manual
    shared.product_opportunities — cơ hội SP mới
    shared.opportunity_notes     — ghi chú phân tích từng cơ hội
    shared.opportunity_scorecard — scorecard chấm điểm SP định mở
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0002_ceo_foundation"
down_revision: Union[str, None] = "0001_baseline_shared"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── shared.approvals ──────────────────────────────────────────────────
    op.create_table(
        "approvals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("app", sa.String(32), nullable=False),
        sa.Column("ref_id", sa.String(64)),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("status", sa.String(16), server_default="pending", nullable=False),
        sa.Column("requested_by", sa.String(64)),
        sa.Column("requested_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("approved_by", sa.String(64)),
        sa.Column("approved_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("comment", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        schema="shared",
    )
    op.create_index("ix_approvals_status", "approvals", ["status"], schema="shared")
    op.create_index("ix_approvals_app_status", "approvals", ["app", "status"], schema="shared")
    op.create_index("ix_approvals_kind", "approvals", ["kind"], schema="shared")
    op.create_index("ix_approvals_created", "approvals", ["created_at"], schema="shared")

    # ─── shared.directives ─────────────────────────────────────────────────
    op.create_table(
        "directives",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("from_user", sa.String(64), nullable=False),
        sa.Column("from_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("to_user", sa.String(64), nullable=False),
        sa.Column("to_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("app", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("priority", sa.String(8), server_default="med", nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("response", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        schema="shared",
    )
    op.create_index("ix_directives_to_status", "directives", ["to_user", "status"], schema="shared")
    op.create_index("ix_directives_app", "directives", ["app"], schema="shared")
    op.create_index("ix_directives_due", "directives", ["due_date"], schema="shared")

    # ─── shared.ceo_comments ───────────────────────────────────────────────
    op.create_table(
        "ceo_comments",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("app", sa.String(32), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("author_username", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="shared",
    )
    op.create_index("ix_ceo_comments_entity", "ceo_comments", ["app", "entity_type", "entity_id"], schema="shared")
    op.create_index("ix_ceo_comments_created", "ceo_comments", ["created_at"], schema="shared")

    # ─── shared.feedback ───────────────────────────────────────────────────
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(128)),
        sa.Column("customer_id", sa.String(64)),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("customer_phone", sa.String(32)),
        sa.Column("app", sa.String(32)),
        sa.Column("severity", sa.String(16), server_default="med", nullable=False),
        sa.Column("category", sa.String(32), server_default="khac", nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("san_pham", sa.String(255)),
        sa.Column("extra", postgresql.JSONB()),
        sa.Column("status", sa.String(16), server_default="new", nullable=False),
        sa.Column("assigned_to", sa.String(64)),
        sa.Column("assigned_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("resolution", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        schema="shared",
    )
    op.create_index("ix_feedback_status", "feedback", ["status"], schema="shared")
    op.create_index("ix_feedback_severity", "feedback", ["severity"], schema="shared")
    op.create_index("ix_feedback_category", "feedback", ["category"], schema="shared")
    op.create_index("ix_feedback_source", "feedback", ["source"], schema="shared")
    op.create_index("ix_feedback_created", "feedback", ["created_at"], schema="shared")
    op.create_index("ix_feedback_customer", "feedback", ["customer_id"], schema="shared")

    # ─── shared.product_opportunities ──────────────────────────────────────
    op.create_table(
        "product_opportunities",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("nhom_hang", sa.String(64)),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("signal_count", sa.Integer(), server_default="1", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(16), server_default="new", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="shared",
    )
    op.create_index("ix_opp_status", "product_opportunities", ["status"], schema="shared")
    op.create_index("ix_opp_source", "product_opportunities", ["source"], schema="shared")
    op.create_index("ix_opp_last_seen", "product_opportunities", ["last_seen"], schema="shared")

    op.create_table(
        "opportunity_notes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("opportunity_id", sa.BigInteger(),
                  sa.ForeignKey("shared.product_opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author_username", sa.String(64)),
        sa.Column("author_user_id", sa.Integer(), sa.ForeignKey("shared.users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="shared",
    )
    op.create_index("ix_opp_notes_opp", "opportunity_notes", ["opportunity_id"], schema="shared")

    op.create_table(
        "opportunity_scorecard",
        sa.Column("opportunity_id", sa.BigInteger(),
                  sa.ForeignKey("shared.product_opportunities.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("gia_von", sa.Numeric(15, 2)),
        sa.Column("gia_ban_du_kien", sa.Numeric(15, 2)),
        sa.Column("bien_du_kien_pct", sa.Numeric(6, 2)),
        sa.Column("san_luong_du_kien_thang", sa.Integer()),
        sa.Column("doi_thu", sa.Text()),
        sa.Column("rui_ro", sa.Text()),
        sa.Column("co_hoi", sa.Text()),
        sa.Column("ke_hoach", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", sa.String(64)),
        schema="shared",
    )

    # ─── seed default thresholds vào shared.app_config ──────────────────────
    op.execute("""
        INSERT INTO shared.app_config (app, key, value) VALUES
            ('ceo', 'threshold_quote',          '50000000'::jsonb),
            ('ceo', 'threshold_po',             '30000000'::jsonb),
            ('ceo', 'threshold_km_pct',         '15'::jsonb),
            ('ceo', 'threshold_salary_inc_pct', '10'::jsonb),
            ('ceo', 'leaderboard_public',       'true'::jsonb)
        ON CONFLICT (app, key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM shared.app_config WHERE app = 'ceo'")
    op.drop_table("opportunity_scorecard", schema="shared")
    op.drop_table("opportunity_notes", schema="shared")
    op.drop_table("product_opportunities", schema="shared")
    op.drop_table("feedback", schema="shared")
    op.drop_table("ceo_comments", schema="shared")
    op.drop_table("directives", schema="shared")
    op.drop_table("approvals", schema="shared")
