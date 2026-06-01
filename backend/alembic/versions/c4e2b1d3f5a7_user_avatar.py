"""user avatar_url

Revision ID: c4e2b1d3f5a7
Revises: b3f1a2c4d5e6
Create Date: 2026-05-19 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c4e2b1d3f5a7"
down_revision: Union[str, Sequence[str], None] = "b3f1a2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_url")
