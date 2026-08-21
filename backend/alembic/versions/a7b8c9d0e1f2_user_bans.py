"""add user participation bans and viewing requirements

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-08-21 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("ban_reason", sa.String(), nullable=True))
    op.add_column("users", sa.Column("banned_at", sa.Integer(), nullable=True))
    op.create_table(
        "ban_requirements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("poster_url", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ban_requirements_user_id", "ban_requirements", ["user_id"])
    op.create_index("ix_ban_requirements_tmdb_id", "ban_requirements", ["tmdb_id"])


def downgrade() -> None:
    op.drop_index("ix_ban_requirements_tmdb_id", table_name="ban_requirements")
    op.drop_index("ix_ban_requirements_user_id", table_name="ban_requirements")
    op.drop_table("ban_requirements")
    op.drop_column("users", "banned_at")
    op.drop_column("users", "ban_reason")
    op.drop_column("users", "is_banned")
