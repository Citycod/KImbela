"""merge production and age visibility migration heads

Revision ID: 67bc3f94dca5
Revises: 8a586cb644c2, a2b3c4d5e6f7
Create Date: 2026-11-16 12:47:13.987371

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '67bc3f94dca5'
down_revision = ('8a586cb644c2', 'a2b3c4d5e6f7')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
