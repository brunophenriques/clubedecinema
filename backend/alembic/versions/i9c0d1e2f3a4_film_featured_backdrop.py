"""Persist an optional per-film featured backdrop and crop position."""
from alembic import op
import sqlalchemy as sa

revision = "i9c0d1e2f3a4"
down_revision = "h8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("films", sa.Column("featured_backdrop_path", sa.String(), nullable=True))
    op.add_column("films", sa.Column("featured_backdrop_x", sa.Float(), nullable=True))
    op.add_column("films", sa.Column("featured_backdrop_y", sa.Float(), nullable=True))


def downgrade():
    op.drop_column("films", "featured_backdrop_y")
    op.drop_column("films", "featured_backdrop_x")
    op.drop_column("films", "featured_backdrop_path")
