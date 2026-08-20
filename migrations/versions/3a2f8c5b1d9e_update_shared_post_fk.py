"""add on delete set null to shared_post_id

Revision ID: 3a2f8c5b1d9e
Revises: 98a016525660
Create Date: 2026-08-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3a2f8c5b1d9e'
down_revision = '98a016525660'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Clean up any orphaned shared_post_ids so the new constraint doesn't fail
    op.execute(
        "UPDATE posts SET shared_post_id = NULL "
        "WHERE shared_post_id IS NOT NULL AND NOT EXISTS "
        "(SELECT 1 FROM posts p2 WHERE p2.id = posts.shared_post_id)"
    )
    
    # 2. Drop the existing constraint
    op.drop_constraint('posts_shared_post_id_fkey', 'posts', type_='foreignkey')
    
    # 3. Add the new constraint with ON DELETE SET NULL
    op.create_foreign_key('posts_shared_post_id_fkey', 'posts', 'posts', ['shared_post_id'], ['id'], ondelete='SET NULL')


def downgrade():
    op.drop_constraint('posts_shared_post_id_fkey', 'posts', type_='foreignkey')
    op.create_foreign_key('posts_shared_post_id_fkey', 'posts', 'posts', ['shared_post_id'], ['id'])
