"""Alembic migration."""
import sqlalchemy as sa
from alembic import op


def upgrade():
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("amount", sa.Numeric),
        sa.Column("user_id", sa.Integer),
    )
