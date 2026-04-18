"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

userrole = PgEnum("teacher", "admin", name="userrole", create_type=False)
filecategory = PgEnum("scenario", "graphic", "video", "music", "poetry", "presentation", "other", name="filecategory", create_type=False)
filestatus = PgEnum("draft", "approved", name="filestatus", create_type=False)


def upgrade() -> None:
    op.execute("DO $$ BEGIN CREATE TYPE userrole AS ENUM ('teacher', 'admin'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE filecategory AS ENUM ('scenario','graphic','video','music','poetry','presentation','other'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")
    op.execute("DO $$ BEGIN CREATE TYPE filestatus AS ENUM ('draft', 'approved'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;")

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", userrole, nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)

    op.create_table(
        "file_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("category", filecategory, nullable=False),
        sa.Column("mime_type", sa.String(length=200), nullable=False),
        sa.Column("storage_key", sa.String(length=1024), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("parent_file_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("status", filestatus, nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extra", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_file_id"], ["file_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_file_assets_project_id"), "file_assets", ["project_id"], unique=False)
    op.create_index(op.f("ix_file_assets_user_id"), "file_assets", ["user_id"], unique=False)

    op.create_table(
        "file_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["file_asset_id"], ["file_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_file_chunks_file_asset_id"), "file_chunks", ["file_asset_id"], unique=False)

    op.create_table(
        "ai_read_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["file_asset_id"], ["file_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_read_audit_file_asset_id"), "ai_read_audit", ["file_asset_id"], unique=False)
    op.create_index(op.f("ix_ai_read_audit_user_id"), "ai_read_audit", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_ai_read_audit_user_id"), table_name="ai_read_audit")
    op.drop_index(op.f("ix_ai_read_audit_file_asset_id"), table_name="ai_read_audit")
    op.drop_table("ai_read_audit")
    op.drop_index(op.f("ix_file_chunks_file_asset_id"), table_name="file_chunks")
    op.drop_table("file_chunks")
    op.drop_index(op.f("ix_file_assets_user_id"), table_name="file_assets")
    op.drop_index(op.f("ix_file_assets_project_id"), table_name="file_assets")
    op.drop_table("file_assets")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS filestatus")
    op.execute("DROP TYPE IF EXISTS filecategory")
    op.execute("DROP TYPE IF EXISTS userrole")
