"""add show_age_on_profile to users

Revision ID: a2b3c4d5e6f7
Revises: f4a1c2d3e4b5
"""

from alembic import op
import sqlalchemy as sa


revision = "a2b3c4d5e6f7"
down_revision = "f4a1c2d3e4b5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column(
            "show_age_on_profile",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade():
    op.drop_column("users", "show_age_on_profile")
