"""add per-field user profile privacy

Revision ID: a7c9e2f4b6d8
Revises: f4a1c2d3e4b5
"""

from alembic import op
import sqlalchemy as sa


revision = "a7c9e2f4b6d8"
down_revision = "f4a1c2d3e4b5"
branch_labels = None
depends_on = None


FIELDS = (
    "age",
    "birthday",
    "gender",
    "location",
    "relationship",
    "bio",
    "occupation",
    "education",
    "religion",
    "ethnicity",
    "interests",
    "activity",
)


def upgrade():
    columns = [
        sa.Column("user_id", sa.Integer(), nullable=False),
    ]
    for field in FIELDS:
        default = "private" if field in {"birthday", "ethnicity"} else "friends"
        columns.append(
            sa.Column(
                f"{field}_visibility",
                sa.String(length=10),
                server_default=default,
                nullable=False,
            )
        )
    columns.extend(
        [
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["user_id"], ["users.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("user_id"),
        ]
    )
    columns.extend(
        sa.CheckConstraint(
            f"{field}_visibility IN ('public', 'friends', 'private')",
            name=f"ck_user_profile_privacy_{field}",
        )
        for field in FIELDS
    )
    op.create_table("user_profile_privacy", *columns)

    privacy = sa.table(
        "user_profile_privacy",
        sa.column("user_id", sa.Integer()),
        *(
            sa.column(f"{field}_visibility", sa.String(length=10))
            for field in FIELDS
        ),
    )
    users = sa.table("users", sa.column("id", sa.Integer()))
    field_values = [
        sa.literal("private" if field in {"birthday", "ethnicity"} else "public")
        for field in FIELDS
    ]
    op.execute(
        privacy.insert().from_select(
            ["user_id", *(f"{field}_visibility" for field in FIELDS)],
            sa.select(users.c.id, *field_values),
        )
    )


def downgrade():
    op.drop_table("user_profile_privacy")
