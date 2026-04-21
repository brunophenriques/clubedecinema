"""add week is_ready

Revision ID: 7f1efcdba895
Revises: d65d8b1e0838
Create Date: YYYY-MM-DD HH:MM:SS

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "7f1efcdba895"
down_revision = "d65d8b1e0838"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # If the column already exists, this would crash — but after we fix the file,
    # we will STAMP the migration, not run it.
    op.add_column(
        "weeks",
        sa.Column("is_ready", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column("weeks", "is_ready")
