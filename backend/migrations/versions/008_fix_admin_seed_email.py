"""poprawka e-maila seed admina (adres musi przejść walidację EmailStr / email-validator)

Revision ID: 008
Revises: 007
Create Date: 2026-04-19

Starsze wersje seeda: admin@localhost (nieważny) lub admin@teacherhelper.local (.local zastrzeżone).
Docelowo: admin@example.com (domena dokumentacyjna, akceptowana przez bibliotekę).
"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
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
              AND email = 'admin@localhost'
            """
        ),
        {"id": str(ADMIN_SEED_USER_ID)},
    )


def downgrade() -> None:
    # Nie cofamy do admin@localhost — ten adres nie przechodzi walidacji EmailStr w API.
    pass
