"""add ai provider configs table

Revision ID: 20260427_ai_provider_configs
Revises: 20260427_ask_history
Create Date: 2026-04-27 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260427_ai_provider_configs"
down_revision = "20260427_ask_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_provider_configs",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("supported_tasks", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("last_test_status", sa.String(length=64), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ai_provider_configs_updated_at",
        "ai_provider_configs",
        ["updated_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_provider_configs_updated_at", table_name="ai_provider_configs")
    op.drop_table("ai_provider_configs")
