"""add marketplace listing locations

Revision ID: 2f4a6d9e8c11
Revises: 1c7f4d8b9e10, f19c61faee54
Create Date: 2026-04-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "2f4a6d9e8c11"
down_revision = ("1c7f4d8b9e10", "f19c61faee54")
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "marketplace_services", sa.Column("country", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "marketplace_services", sa.Column("state", sa.String(length=128), nullable=True)
    )
    op.add_column(
        "marketplace_services", sa.Column("city", sa.String(length=128), nullable=True)
    )
    op.create_index(
        "idx_services_country", "marketplace_services", ["country"], unique=False
    )
    op.create_index(
        "idx_services_state", "marketplace_services", ["state"], unique=False
    )
    op.create_index("idx_services_city", "marketplace_services", ["city"], unique=False)
    op.create_index(
        "idx_services_country_state_city",
        "marketplace_services",
        ["country", "state", "city"],
        unique=False,
    )


def downgrade():
    op.drop_index("idx_services_country_state_city", table_name="marketplace_services")
    op.drop_index("idx_services_city", table_name="marketplace_services")
    op.drop_index("idx_services_state", table_name="marketplace_services")
    op.drop_index("idx_services_country", table_name="marketplace_services")
    op.drop_column("marketplace_services", "city")
    op.drop_column("marketplace_services", "state")
    op.drop_column("marketplace_services", "country")
