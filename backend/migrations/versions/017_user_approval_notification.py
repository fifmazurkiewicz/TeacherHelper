"""add approval notification state

Revision ID: 017_user_approval_notification
Revises: 016
"""

from alembic import op
import sqlalchemy as sa

revision = "017_user_approval_notification"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("approval_notification_status", sa.String(length=16), nullable=False, server_default="sent"))
    op.add_column("users", sa.Column("approval_notification_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("approval_notification_error", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "approval_notification_error")
    op.drop_column("users", "approval_notification_sent_at")
    op.drop_column("users", "approval_notification_status")
