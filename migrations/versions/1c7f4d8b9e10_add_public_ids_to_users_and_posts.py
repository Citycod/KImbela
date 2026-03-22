"""add public ids to users and posts

Revision ID: 1c7f4d8b9e10
Revises: b8c1a3d4e5f6
Create Date: 2026-03-22 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
import uuid


# revision identifiers, used by Alembic.
revision = "1c7f4d8b9e10"
down_revision = "b8c1a3d4e5f6"
branch_labels = None
depends_on = None


def _fill_public_ids(table_name):
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id FROM {table_name} WHERE public_id IS NULL"))
    for row in rows:
        connection.execute(
            sa.text(f"UPDATE {table_name} SET public_id = :public_id WHERE id = :id"),
            {"public_id": str(uuid.uuid4()), "id": row.id},
        )


def upgrade():
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("public_id", sa.String(length=36), nullable=True))

    _fill_public_ids("users")
    _fill_public_ids("posts")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index(batch_op.f("ix_users_public_id"), ["public_id"], unique=True)

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.alter_column("public_id", existing_type=sa.String(length=36), nullable=False)
        batch_op.create_index(batch_op.f("ix_posts_public_id"), ["public_id"], unique=True)


def downgrade():
    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_posts_public_id"))
        batch_op.drop_column("public_id")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_users_public_id"))
        batch_op.drop_column("public_id")
