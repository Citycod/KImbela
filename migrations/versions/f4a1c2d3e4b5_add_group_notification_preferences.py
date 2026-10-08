"""add per-member group notification preferences

Revision ID: f4a1c2d3e4b5
Revises: e8f1a2b3c4d5
"""

from alembic import op
import sqlalchemy as sa


revision = "f4a1c2d3e4b5"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "group_notification_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column(
            "level",
            sa.String(length=20),
            server_default="highlights",
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "level IN ('all', 'highlights', 'muted')",
            name="ck_group_notification_preference_level",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "group_id"),
    )
    op.create_index(
        "ix_group_notification_preferences_group_id_user_id",
        "group_notification_preferences",
        ["group_id", "user_id"],
        unique=False,
    )


def downgrade():
    op.drop_table("group_notification_preferences")
