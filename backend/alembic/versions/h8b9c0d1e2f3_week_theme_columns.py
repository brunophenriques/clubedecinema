"""Bring fresh databases in line with the pre-existing Week model.

Some deployed databases already have these columns from manual setup.
Rollback intentionally keeps them: the preceding application also needs them.
"""
from alembic import op
import sqlalchemy as sa

revision = "h8b9c0d1e2f3"
down_revision = "g7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    names = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("weeks")}
    if "is_special" not in names:
        op.add_column("weeks", sa.Column("is_special", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "theme" not in names:
        op.add_column("weeks", sa.Column("theme", sa.String(), nullable=True))


def downgrade():
    pass
