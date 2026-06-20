"""add indexes for bounded egress queries

Revision ID: f6a7b8c9d0e1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-20 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_films_submitter_key", "films", ["submitter_key"], unique=False)
    op.create_index("ix_films_week_id", "films", ["week_id"], unique=False)
    op.create_index("ix_votes_voter_key", "votes", ["voter_key"], unique=False)
    op.create_index("ix_votes_week_id", "votes", ["week_id"], unique=False)
    op.create_index("ix_votes_film_id", "votes", ["film_id"], unique=False)
    op.create_index("ix_chat_messages_week_id_id", "chat_messages", ["week_id", "id"], unique=False)
    op.create_index("ix_letterboxd_entries_user_watched", "letterboxd_entries", ["user_id", "watched_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_letterboxd_entries_user_watched", table_name="letterboxd_entries")
    op.drop_index("ix_chat_messages_week_id_id", table_name="chat_messages")
    op.drop_index("ix_votes_film_id", table_name="votes")
    op.drop_index("ix_votes_week_id", table_name="votes")
    op.drop_index("ix_votes_voter_key", table_name="votes")
    op.drop_index("ix_films_week_id", table_name="films")
    op.drop_index("ix_films_submitter_key", table_name="films")
