"""seed administrator account (role admin)

Revision ID: 007
Revises: 006
Create Date: 2026-04-19

Stałe id umożliwia cofnięcie seeda w downgrade. Hasło: zmienne ADMIN_SEED_EMAIL /
ADMIN_SEED_PASSWORD (domyślne tylko pod dev — zmień w produkcji przed pierwszą migracją).
"""
from __future__ import annotations

import os
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Deterministyczny identyfikator rekordu seed — ten sam w upgrade i downgrade.
ADMIN_SEED_USER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "teacherhelper.admin.seed.v1")


def upgrade() -> None:
    if os.environ.get("SKIP_ADMIN_SEED", "").strip() in ("1", "true", "yes"):
        return

    from teacher_helper.security import hash_password

    email = (os.environ.get("ADMIN_SEED_EMAIL") or "admin@example.com").strip()
    raw_pw = (os.environ.get("ADMIN_SEED_PASSWORD") or "ChangeMeAdmin123!").strip()
    if not raw_pw:
        raw_pw = "ChangeMeAdmin123!"

    hashed = hash_password(raw_pw)
    display_name = (os.environ.get("ADMIN_SEED_DISPLAY_NAME") or "Administrator").strip() or "Administrator"

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO users (id, email, hashed_password, role, display_name, rate_limit_rpm)
            VALUES (
                CAST(:id AS uuid),
                :email,
                :hashed_password,
                'admin'::userrole,
                :display_name,
                NULL
            )
            ON CONFLICT (email) DO NOTHING
            """
        ),
        {
            "id": str(ADMIN_SEED_USER_ID),
            "email": email,
            "hashed_password": hashed,
            "display_name": display_name,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM users WHERE id = CAST(:id AS uuid)"),
        {"id": str(ADMIN_SEED_USER_ID)},
    )
