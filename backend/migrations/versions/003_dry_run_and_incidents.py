"""dry_run on llm_usage_log + system_incidents

Revision ID: 003
Revises: 002
Create Date: 2026-04-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_usage_log",
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "system_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_incidents_event_type"), "system_incidents", ["event_type"], unique=False)
    op.create_index(op.f("ix_system_incidents_severity"), "system_incidents", ["severity"], unique=False)
    op.create_index(op.f("ix_system_incidents_user_id"), "system_incidents", ["user_id"], unique=False)
    op.create_index("ix_system_incidents_created_at", "system_incidents", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_system_incidents_created_at", table_name="system_incidents")
    op.drop_index(op.f("ix_system_incidents_user_id"), table_name="system_incidents")
    op.drop_index(op.f("ix_system_incidents_severity"), table_name="system_incidents")
    op.drop_index(op.f("ix_system_incidents_event_type"), table_name="system_incidents")
    op.drop_table("system_incidents")
    op.drop_column("llm_usage_log", "dry_run")
