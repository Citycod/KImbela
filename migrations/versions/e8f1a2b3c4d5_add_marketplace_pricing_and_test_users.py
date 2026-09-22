"""add marketplace pricing mode and explicit test-user marker

Revision ID: e8f1a2b3c4d5
Revises: c7e8f9a0b1c2
"""

from alembic import op
import sqlalchemy as sa


revision = "e8f1a2b3c4d5"
down_revision = "c7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketplace_services",
        sa.Column(
            "pricing_mode",
            sa.String(length=20),
            server_default="fixed",
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "is_test_user",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_marketplace_services_pricing_mode",
        "marketplace_services",
        "pricing_mode IN ('fixed', 'contact')",
    )


def downgrade():
    op.drop_constraint(
        "ck_marketplace_services_pricing_mode",
        "marketplace_services",
        type_="check",
    )
    op.drop_column("users", "is_test_user")
    op.drop_column("marketplace_services", "pricing_mode")
