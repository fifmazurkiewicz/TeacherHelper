"""users.llm_daily_cost_limit_usd → llm_monthly_cost_limit_usd (limit miesięczny)

Revision ID: 013
Revises: 012
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "llm_daily_cost_limit_usd", new_column_name="llm_monthly_cost_limit_usd")


def downgrade() -> None:
    op.alter_column("users", "llm_monthly_cost_limit_usd", new_column_name="llm_daily_cost_limit_usd")
