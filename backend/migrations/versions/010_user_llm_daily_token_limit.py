"""users.llm_daily_token_limit — opcjonalny dzienny limit tokenów LLM (UTC) per użytkownik

Revision ID: 010
Revises: 009
Create Date: 2026-04-19
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("llm_daily_token_limit", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "llm_daily_token_limit")
