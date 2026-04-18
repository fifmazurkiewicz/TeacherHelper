"""topics + file_assets.topic_id (RAG per Omówienie tematu)

Revision ID: 005
Revises: 004
Create Date: 2026-04-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topics_user_id", "topics", ["user_id"], unique=False)
    op.add_column(
        "file_assets",
        sa.Column("topic_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_file_assets_topic_id", "file_assets", ["topic_id"], unique=False)
    op.create_foreign_key(
        "fk_file_assets_topic_id_topics",
        "file_assets",
        "topics",
        ["topic_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_file_assets_topic_id_topics", "file_assets", type_="foreignkey")
    op.drop_index("ix_file_assets_topic_id", table_name="file_assets")
    op.drop_column("file_assets", "topic_id")
    op.drop_index("ix_topics_user_id", table_name="topics")
    op.drop_table("topics")
