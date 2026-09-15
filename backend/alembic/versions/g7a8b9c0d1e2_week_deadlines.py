"""Add separate submission and voting deadlines."""
from alembic import op
import sqlalchemy as sa

revision = "g7a8b9c0d1e2"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("weeks", sa.Column("submission_deadline", sa.Integer(), nullable=True))
    op.add_column("weeks", sa.Column("voting_deadline", sa.Integer(), nullable=True))
    op.add_column("weeks", sa.Column("voting_paused", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("weeks", "voting_paused")
    op.drop_column("weeks", "voting_deadline")
    op.drop_column("weeks", "submission_deadline")
