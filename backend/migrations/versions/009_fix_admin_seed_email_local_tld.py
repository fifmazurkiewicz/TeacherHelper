"""poprawka e-maila seed admina z .local (email-validator odrzuca TLD .local)

Revision ID: 009
Revises: 008
Create Date: 2026-04-19

Migracja 008 mogła ustawić admin@teacherhelper.local — ten sam problem co wcześniej z localhost.
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ADMIN_SEED_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "teacherhelper.admin.seed.v1")


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE users
            SET email = 'admin@example.com'
            WHERE id = CAST(:id AS uuid)
              AND email = 'admin@teacherhelper.local'
            """
        ),
        {"id": str(ADMIN_SEED_USER_ID)},
    )


def downgrade() -> None:
    pass
