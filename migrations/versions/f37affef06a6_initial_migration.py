"""Initial migration (idempotent)

Revision ID: f37affef06a6
Revises: 
Create Date: 2025-12-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import ProgrammingError

# revision identifiers, used by Alembic.
revision = 'f37affef06a6'
down_revision = None
branch_labels = None
depends_on = None

def safe_create_index_raw(table_name, index_name, columns):
    op.execute(
        f'CREATE INDEX IF NOT EXISTS {index_name} ON {table_name} ({", ".join(columns)})'
    )


def upgrade():
    # Create tables if they don't exist
    try:
        op.create_table(
            'comments',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('content', sa.Text, nullable=False),
            sa.Column('created_at', sa.DateTime),
            sa.Column('author_id', sa.Integer, nullable=False),
            sa.Column('post_id', sa.Integer, nullable=False),
            sa.Column('parent_id', sa.Integer),
            sa.ForeignKeyConstraint(['author_id'], ['users.id']),
            sa.ForeignKeyConstraint(['parent_id'], ['comments.id']),
            sa.ForeignKeyConstraint(['post_id'], ['posts.id'])
        )
    except ProgrammingError:
        print("Table 'comments' already exists, skipping")

    try:
        op.create_table(
            'likes',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('user_id', sa.Integer, nullable=False),
            sa.Column('post_id', sa.Integer, nullable=False),
            sa.Column('created_at', sa.DateTime),
            sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.UniqueConstraint('user_id', 'post_id', name='unique_like')
        )
    except ProgrammingError:
        print("Table 'likes' already exists, skipping")

    # Add indexes safely using raw SQL
    safe_create_index_raw('comments', 'idx_comments_author_id', ['author_id'])
    safe_create_index_raw('comments', 'idx_comments_author_post', ['author_id', 'post_id'])
    safe_create_index_raw('comments', 'idx_comments_created_at', ['created_at'])
    safe_create_index_raw('comments', 'idx_comments_parent_id', ['parent_id'])
    safe_create_index_raw('comments', 'idx_comments_post_created', ['post_id', 'created_at'])
    safe_create_index_raw('comments', 'idx_comments_post_id', ['post_id'])

    safe_create_index_raw('likes', 'ix_like_post', ['post_id'])
    safe_create_index_raw('likes', 'ix_like_post_user', ['post_id', 'user_id'])



def downgrade():
    # Drop tables if they exist
    try:
        op.drop_table('likes')
    except ProgrammingError:
        print("Table 'likes' does not exist, skipping")
    try:
        op.drop_table('comments')
    except ProgrammingError:
        print("Table 'comments' does not exist, skipping")
