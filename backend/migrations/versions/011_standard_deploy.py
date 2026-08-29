"""Migracja na standard Vercel + Render + Supabase."""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011_standard_deploy"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=True)

    op.execute(
        """
        ALTER TABLE file_chunks
        ALTER COLUMN embedding TYPE vector(1536)
        USING (
            CASE
                WHEN embedding IS NULL THEN NULL
                ELSE (embedding::text)::vector
            END
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_file_chunks_embedding_hnsw
        ON file_chunks USING hnsw (embedding vector_cosine_ops)
        """
    )

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rate_limit_events_user_id", "rate_limit_events", ["user_id"])
    op.create_index("ix_rate_limit_events_created_at", "rate_limit_events", ["created_at"])

    op.create_table(
        "generation_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("result", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generation_jobs_user_id", "generation_jobs", ["user_id"])
    op.create_index("ix_generation_jobs_status", "generation_jobs", ["status"])
    op.create_index("ix_generation_jobs_conversation_id", "generation_jobs", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_generation_jobs_conversation_id", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_status", table_name="generation_jobs")
    op.drop_index("ix_generation_jobs_user_id", table_name="generation_jobs")
    op.drop_table("generation_jobs")

    op.drop_index("ix_rate_limit_events_created_at", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_user_id", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")

    op.drop_index("ix_file_chunks_embedding_hnsw", table_name="file_chunks")
    op.execute(
        """
        ALTER TABLE file_chunks
        ALTER COLUMN embedding TYPE jsonb
        USING to_jsonb(embedding::float4[])
        """
    )

    op.alter_column("users", "hashed_password", existing_type=sa.String(255), nullable=False)
