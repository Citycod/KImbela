"""add administrator-controlled public group member count

Revision ID: c7e8f9a0b1c2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = "c7e8f9a0b1c2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "groups",
        sa.Column("display_member_count", sa.String(length=32), nullable=True),
    )


def downgrade():
    op.drop_column("groups", "display_member_count")
