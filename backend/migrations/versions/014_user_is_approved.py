"""users.is_approved — admin acceptance gate for public signups

Revision ID: 014
Revises: 013
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "is_approved" not in columns:
        op.add_column("users", sa.Column("is_approved", sa.Boolean(), nullable=True))
    op.execute(sa.text("UPDATE users SET is_approved = true WHERE is_approved IS NULL"))
    op.alter_column(
        "users",
        "is_approved",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.false(),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("users")}
    if "is_approved" in columns:
        op.drop_column("users", "is_approved")
