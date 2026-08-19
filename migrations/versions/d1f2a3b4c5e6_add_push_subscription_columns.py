"""Add user_agent, last_seen_at and unique constraint to push_subscriptions

Revision ID: d1f2a3b4c5e6
Revises: 98a016525660
Create Date: 2026-08-19 22:47:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd1f2a3b4c5e6'
down_revision = '98a016525660'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_agent', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_push_subscriptions_endpoint', ['endpoint'])


def downgrade():
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('uq_push_subscriptions_endpoint', type_='unique')
        batch_op.drop_column('last_seen_at')
        batch_op.drop_column('user_agent')
