"""llm_usage_log.cost_usd + users.llm_daily_cost_limit_usd (limit dzienny w USD zamiast tokenów)

Revision ID: 012
Revises: 011_standard_deploy
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "012"
down_revision: Union[str, None] = "011_standard_deploy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llm_usage_log",
        sa.Column("cost_usd", sa.Numeric(precision=16, scale=8), nullable=True),
    )
    op.drop_column("users", "llm_daily_token_limit")
    op.add_column(
        "users",
        sa.Column("llm_daily_cost_limit_usd", sa.Numeric(precision=10, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "llm_daily_cost_limit_usd")
    op.add_column(
        "users",
        sa.Column("llm_daily_token_limit", sa.Integer(), nullable=True),
    )
    op.drop_column("llm_usage_log", "cost_usd")
