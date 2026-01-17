"""added json for cities

Revision ID: 8ef400feaca0
Revises: aeed8122db93
Create Date: 2026-01-02 07:36:05.096305

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "8ef400feaca0"
down_revision = "aeed8122db93"
branch_labels = None
depends_on = None


def upgrade():
    # 1) add as nullable first
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("state", sa.String(length=50), nullable=True))

    # 2) give existing rows something (pick what makes sense for your app)
    # If you want a neutral default:
    op.execute("UPDATE users SET state = 'Unknown' WHERE state IS NULL")

    # 3) now make it NOT NULL (only if you truly want it required)
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "state", existing_type=sa.String(length=50), nullable=False
        )


def downgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("state")

    # ### end Alembic commands ###
