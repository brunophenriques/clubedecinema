"""letterboxd integration

Revision ID: b3f1a2c4d5e6
Revises: efe9de7c931d
Create Date: 2026-05-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3f1a2c4d5e6"
down_revision: Union[str, Sequence[str], None] = "efe9de7c931d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Letterboxd fields to users
    op.add_column("users", sa.Column("letterboxd_username", sa.String(), nullable=True))
    op.add_column("users", sa.Column("letterboxd_avatar_url", sa.String(), nullable=True))
    op.add_column("users", sa.Column("letterboxd_synced_at", sa.Integer(), nullable=True))

    # New letterboxd_entries table
    op.create_table(
        "letterboxd_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tmdb_id", sa.Integer(), nullable=True),
        sa.Column("film_title", sa.String(), nullable=False),
        sa.Column("film_year", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("watched_date", sa.Integer(), nullable=True),
        sa.Column("letterboxd_url", sa.String(), nullable=True),
        sa.Column("is_rewatch", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tmdb_id", name="uq_lb_entry_user_tmdb"),
    )
    op.create_index(op.f("ix_letterboxd_entries_id"), "letterboxd_entries", ["id"], unique=False)
    op.create_index(op.f("ix_letterboxd_entries_user_id"), "letterboxd_entries", ["user_id"], unique=False)
    op.create_index(op.f("ix_letterboxd_entries_tmdb_id"), "letterboxd_entries", ["tmdb_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_letterboxd_entries_tmdb_id"), table_name="letterboxd_entries")
    op.drop_index(op.f("ix_letterboxd_entries_user_id"), table_name="letterboxd_entries")
    op.drop_index(op.f("ix_letterboxd_entries_id"), table_name="letterboxd_entries")
    op.drop_table("letterboxd_entries")

    op.drop_column("users", "letterboxd_synced_at")
    op.drop_column("users", "letterboxd_avatar_url")
    op.drop_column("users", "letterboxd_username")
