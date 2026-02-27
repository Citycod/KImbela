"""add location tables

Revision ID: b8c1a3d4e5f6
Revises: 4e6c0a484dff
Create Date: 2026-02-27

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b8c1a3d4e5f6"
down_revision = "4e6c0a484dff"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "countries",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False, unique=True),
        sa.Column("iso2", sa.String(length=2), nullable=True),
        sa.Column("iso3", sa.String(length=3), nullable=True),
    )
    op.create_index("ix_countries_name", "countries", ["name"], unique=True)
    op.create_index("ix_countries_iso2", "countries", ["iso2"], unique=False)
    op.create_index("ix_countries_iso3", "countries", ["iso3"], unique=False)

    op.create_table(
        "states",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "country_id",
            sa.Integer,
            sa.ForeignKey("countries.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_states_name", "states", ["name"], unique=False)
    op.create_index("ix_states_country_id", "states", ["country_id"], unique=False)
    op.create_index(
        "ix_states_country_name", "states", ["country_id", "name"], unique=False
    )

    op.create_table(
        "cities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "state_id",
            sa.Integer,
            sa.ForeignKey("states.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "country_id",
            sa.Integer,
            sa.ForeignKey("countries.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index("ix_cities_name", "cities", ["name"], unique=False)
    op.create_index("ix_cities_state_id", "cities", ["state_id"], unique=False)
    op.create_index(
        "ix_cities_state_name", "cities", ["state_id", "name"], unique=False
    )
    op.create_index("ix_cities_country_id", "cities", ["country_id"], unique=False)


def downgrade():
    op.drop_index("ix_cities_country_id", table_name="cities")
    op.drop_index("ix_cities_state_name", table_name="cities")
    op.drop_index("ix_cities_state_id", table_name="cities")
    op.drop_index("ix_cities_name", table_name="cities")
    op.drop_table("cities")

    op.drop_index("ix_states_country_name", table_name="states")
    op.drop_index("ix_states_country_id", table_name="states")
    op.drop_index("ix_states_name", table_name="states")
    op.drop_table("states")

    op.drop_index("ix_countries_iso3", table_name="countries")
    op.drop_index("ix_countries_iso2", table_name="countries")
    op.drop_index("ix_countries_name", table_name="countries")
    op.drop_table("countries")
