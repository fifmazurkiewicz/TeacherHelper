"""Privacy controls and AI disclosure acknowledgement.

Revision ID: 016
Revises: 015
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("ai_disclosure_version", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("ai_disclosure_acknowledged_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_disclosure_acknowledged_at")
    op.drop_column("users", "ai_disclosure_version")
