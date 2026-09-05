"""One active chat generation job per conversation.

Revision ID: 014
Revises: 013
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_generation_jobs_one_active_chat
        ON generation_jobs (conversation_id)
        WHERE kind = 'chat'
          AND status IN ('pending', 'running')
          AND conversation_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_generation_jobs_one_active_chat")
