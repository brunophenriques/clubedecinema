"""reactions and chat

Revision ID: d5e6f7a8b9c0
Revises: c4e2b1d3f5a7
Create Date: 2026-05-19 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c4e2b1d3f5a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("film_id", sa.Integer(), nullable=False),
        sa.Column("emoji", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["film_id"], ["films.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "film_id", name="uq_reaction_user_film"),
    )
    op.create_index(op.f("ix_reactions_id"), "reactions", ["id"], unique=False)
    op.create_index(op.f("ix_reactions_film_id"), "reactions", ["film_id"], unique=False)
    op.create_index(op.f("ix_reactions_user_id"), "reactions", ["user_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("week_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("created_at", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["week_id"], ["weeks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chat_messages_id"), "chat_messages", ["id"], unique=False)
    op.create_index(op.f("ix_chat_messages_week_id"), "chat_messages", ["week_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chat_messages_week_id"), table_name="chat_messages")
    op.drop_index(op.f("ix_chat_messages_id"), table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index(op.f("ix_reactions_user_id"), table_name="reactions")
    op.drop_index(op.f("ix_reactions_film_id"), table_name="reactions")
    op.drop_index(op.f("ix_reactions_id"), table_name="reactions")
    op.drop_table("reactions")
