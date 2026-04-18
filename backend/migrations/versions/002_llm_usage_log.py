"""llm usage log for admin monitoring

Revision ID: 002
Revises: 001
Create Date: 2026-04-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_usage_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=256), nullable=False),
        sa.Column("call_kind", sa.String(length=64), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_llm_usage_log_user_id"), "llm_usage_log", ["user_id"], unique=False)
    op.create_index(op.f("ix_llm_usage_log_provider"), "llm_usage_log", ["provider"], unique=False)
    op.create_index(op.f("ix_llm_usage_log_model"), "llm_usage_log", ["model"], unique=False)
    op.create_index(op.f("ix_llm_usage_log_call_kind"), "llm_usage_log", ["call_kind"], unique=False)
    op.create_index("ix_llm_usage_log_created_at", "llm_usage_log", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_usage_log_created_at", table_name="llm_usage_log")
    op.drop_index(op.f("ix_llm_usage_log_call_kind"), table_name="llm_usage_log")
    op.drop_index(op.f("ix_llm_usage_log_model"), table_name="llm_usage_log")
    op.drop_index(op.f("ix_llm_usage_log_provider"), table_name="llm_usage_log")
    op.drop_index(op.f("ix_llm_usage_log_user_id"), table_name="llm_usage_log")
    op.drop_table("llm_usage_log")
