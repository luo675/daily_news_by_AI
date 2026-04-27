"""add ask history records table

Revision ID: 20260427_ask_history
Revises:
Create Date: 2026-04-27 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260427_ask_history"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ask_history_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("answer_mode", sa.String(length=64), nullable=False),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ask_history_records_created_at",
        "ask_history_records",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ask_history_records_created_at", table_name="ask_history_records")
    op.drop_table("ask_history_records")
