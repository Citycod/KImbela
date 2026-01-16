"""new table

Revision ID: 1156d53262b0
Revises: f37affef06a6
Create Date: 2025-12-16 08:49:59.029847

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = '1156d53262b0'
down_revision = 'f37affef06a6'
branch_labels = None
depends_on = None


def _sqlite_table_exists(conn, name: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name}
    ).fetchone() is not None


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # =========================
    # SQLITE BRANCH (SAFE)
    # =========================
    if dialect == "sqlite":
        conn = bind

        # ---- DROP INDEXES SAFELY (IF EXISTS) ----
        # comments
        for idx in [
            "idx_comment_author_id",
            "idx_comment_author_post",
            "idx_comment_created_at",
            "idx_comment_parent_id",
            "idx_comment_post_created",
            "idx_comment_post_id",
            "ix_comment_post",
            "ix_comment_post_created",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # friend_requests
        op.execute("DROP INDEX IF EXISTS ix_friend_requests_receiver_status")

        # friendship
        op.execute("DROP INDEX IF EXISTS ix_friendship_friend")
        op.execute("DROP INDEX IF EXISTS ix_friendship_user")

        # groups
        op.execute("DROP INDEX IF EXISTS ix_groups_active")

        # likes
        op.execute("DROP INDEX IF EXISTS ix_like_post")
        op.execute("DROP INDEX IF EXISTS ix_like_post_user")

        # marketplace_services
        for idx in [
            "idx_services_description_trgm",
            "idx_services_title_trgm",
            "ix_marketplace_services_category",
            "ix_marketplace_services_seller",
            "ix_marketplace_services_status",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # messages
        op.execute("DROP INDEX IF EXISTS ix_messages_conversation")
        op.execute("DROP INDEX IF EXISTS ix_messages_unread")

        # notifications
        for idx in [
            "idx_notifications_user_id_created_at",
            "idx_notifications_user_read_created",
            "ix_notifications_entity",
            "ix_notifications_user_created",
            "ix_notifications_user_read",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # posts
        for idx in [
            "idx_posts_content_trgm",
            "ix_posts_author_created",
            "ix_posts_created_desc",
            "ix_posts_group_created",
        ]:
            op.execute(f"DROP INDEX IF EXISTS {idx}")

        # reactions
        op.execute("DROP INDEX IF EXISTS ix_reactions_post")
        op.execute("DROP INDEX IF EXISTS ix_reactions_post_user")

        # users
        op.execute("DROP INDEX IF EXISTS ix_users_last_seen")

        # ---- CREATE INDEXES ONLY IF TABLE EXISTS ----
        if _sqlite_table_exists(conn, "notifications"):
            op.create_index("ix_notification_created", "notifications", ["created_at"], unique=False)
            op.create_index("ix_notification_user_created", "notifications", ["user_id", "created_at"], unique=False)

        if _sqlite_table_exists(conn, "posts"):
            op.create_index("idx_post_author", "posts", ["author_id"], unique=False)
            op.create_index("idx_post_author_created", "posts", ["author_id", "created_at"], unique=False)
            op.create_index("idx_post_created", "posts", ["created_at"], unique=False)

        # ---- CREATE CONSTRAINT ONLY IF TABLE EXISTS ----
        if _sqlite_table_exists(conn, "user_blocks"):
            with op.batch_alter_table("user_blocks", schema=None) as batch_op:
                batch_op.create_unique_constraint("uq_user_block", ["blocker_id", "blocked_id"])

        return  # ✅ done for sqlite


    # =========================
    # POSTGRES / OTHERS (ORIGINAL)
    # =========================
    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.drop_index('idx_comment_author_id')
        batch_op.drop_index('idx_comment_author_post')
        batch_op.drop_index('idx_comment_created_at')
        batch_op.drop_index('idx_comment_parent_id')
        batch_op.drop_index('idx_comment_post_created')
        batch_op.drop_index('idx_comment_post_id')
        batch_op.drop_index('ix_comment_post')
        batch_op.drop_index('ix_comment_post_created')

    with op.batch_alter_table('friend_requests', schema=None) as batch_op:
        batch_op.drop_index(
            'ix_friend_requests_receiver_status',
            postgresql_where="((status)::text = 'pending'::text)"
        )

    with op.batch_alter_table('friendship', schema=None) as batch_op:
        batch_op.drop_index('ix_friendship_friend')
        batch_op.drop_index('ix_friendship_user')

    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.drop_index('ix_groups_active')

    with op.batch_alter_table('likes', schema=None) as batch_op:
        batch_op.drop_index('ix_like_post')
        batch_op.drop_index('ix_like_post_user')

    with op.batch_alter_table('marketplace_services', schema=None) as batch_op:
        batch_op.drop_index('idx_services_description_trgm', postgresql_using='gin')
        batch_op.drop_index('idx_services_title_trgm', postgresql_using='gin')
        batch_op.drop_index('ix_marketplace_services_category')
        batch_op.drop_index('ix_marketplace_services_seller')
        batch_op.drop_index('ix_marketplace_services_status')

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.drop_index('ix_messages_conversation')
        batch_op.drop_index(
            'ix_messages_unread',
            postgresql_where="((status)::text = 'sent'::text)"
        )

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('idx_notifications_user_id_created_at')
        batch_op.drop_index('idx_notifications_user_read_created')
        batch_op.drop_index('ix_notifications_entity')
        batch_op.drop_index('ix_notifications_user_created')
        batch_op.drop_index('ix_notifications_user_read', postgresql_where='(is_read = false)')
        batch_op.create_index('ix_notification_created', ['created_at'], unique=False)
        batch_op.create_index('ix_notification_user_created', ['user_id', 'created_at'], unique=False)

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_index('idx_posts_content_trgm', postgresql_using='gin')
        batch_op.drop_index('ix_posts_author_created')
        batch_op.drop_index('ix_posts_created_desc')
        batch_op.drop_index('ix_posts_group_created', postgresql_where='(group_id IS NOT NULL)')
        batch_op.create_index('idx_post_author', ['author_id'], unique=False)
        batch_op.create_index('idx_post_author_created', ['author_id', 'created_at'], unique=False)
        batch_op.create_index('idx_post_created', ['created_at'], unique=False)

    with op.batch_alter_table('reactions', schema=None) as batch_op:
        batch_op.drop_index('ix_reactions_post')
        batch_op.drop_index('ix_reactions_post_user')

    with op.batch_alter_table('user_blocks', schema=None) as batch_op:
        batch_op.create_unique_constraint('uq_user_block', ['blocker_id', 'blocked_id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_last_seen')


def downgrade():
    # NOTE: You can leave your original downgrade as-is.
    # SQLite testing rarely uses downgrades; Postgres remains the source of truth.

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_last_seen', [sa.text('last_seen DESC')], unique=False)

    with op.batch_alter_table('user_blocks', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_block', type_='unique')

    with op.batch_alter_table('reactions', schema=None) as batch_op:
        batch_op.create_index('ix_reactions_post_user', ['post_id', 'user_id'], unique=False)
        batch_op.create_index('ix_reactions_post', ['post_id'], unique=False)

    with op.batch_alter_table('posts', schema=None) as batch_op:
        batch_op.drop_index('idx_post_created')
        batch_op.drop_index('idx_post_author_created')
        batch_op.drop_index('idx_post_author')
        batch_op.create_index('ix_posts_group_created', ['group_id', sa.text('created_at DESC')], unique=False, postgresql_where='(group_id IS NOT NULL)')
        batch_op.create_index('ix_posts_created_desc', [sa.text('created_at DESC')], unique=False)
        batch_op.create_index('ix_posts_author_created', ['author_id', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('idx_posts_content_trgm', ['content'], unique=False, postgresql_using='gin')

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_index('ix_notification_user_created')
        batch_op.drop_index('ix_notification_created')
        batch_op.create_index('ix_notifications_user_read', ['user_id', 'is_read'], unique=False, postgresql_where='(is_read = false)')
        batch_op.create_index('ix_notifications_user_created', ['user_id', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('ix_notifications_entity', ['entity_type', 'entity_id'], unique=False)
        batch_op.create_index('idx_notifications_user_read_created', ['user_id', 'is_read', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('idx_notifications_user_id_created_at', ['user_id', sa.text('created_at DESC')], unique=False)

    with op.batch_alter_table('messages', schema=None) as batch_op:
        batch_op.create_index('ix_messages_unread', ['receiver_id', 'status'], unique=False, postgresql_where="((status)::text = 'sent'::text)")
        batch_op.create_index('ix_messages_conversation', [sa.text('LEAST(sender_id, receiver_id)'), sa.text('GREATEST(sender_id, receiver_id)'), sa.text('timestamp DESC')], unique=False)

    with op.batch_alter_table('marketplace_services', schema=None) as batch_op:
        batch_op.create_index('ix_marketplace_services_status', ['status', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('ix_marketplace_services_seller', ['seller_id', 'status'], unique=False)
        batch_op.create_index('ix_marketplace_services_category', ['category_id', 'status', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('idx_services_title_trgm', ['title'], unique=False, postgresql_using='gin')
        batch_op.create_index('idx_services_description_trgm', ['description'], unique=False, postgresql_using='gin')

    with op.batch_alter_table('likes', schema=None) as batch_op:
        batch_op.create_index('ix_like_post_user', ['post_id', 'user_id'], unique=False)
        batch_op.create_index('ix_like_post', ['post_id'], unique=False)

    with op.batch_alter_table('groups', schema=None) as batch_op:
        batch_op.create_index('ix_groups_active', ['is_active', sa.text('member_count DESC')], unique=False)

    with op.batch_alter_table('friendship', schema=None) as batch_op:
        batch_op.create_index('ix_friendship_user', ['user_id'], unique=False)
        batch_op.create_index('ix_friendship_friend', ['friend_id'], unique=False)

    with op.batch_alter_table('friend_requests', schema=None) as batch_op:
        batch_op.create_index('ix_friend_requests_receiver_status', ['receiver_id', 'status'], unique=False, postgresql_where="((status)::text = 'pending'::text)")

    with op.batch_alter_table('comments', schema=None) as batch_op:
        batch_op.create_index('ix_comment_post_created', ['post_id', sa.text('created_at DESC')], unique=False)
        batch_op.create_index('ix_comment_post', ['post_id'], unique=False)
        batch_op.create_index('idx_comment_post_id', ['post_id'], unique=False)
        batch_op.create_index('idx_comment_post_created', ['post_id', 'created_at'], unique=False)
        batch_op.create_index('idx_comment_parent_id', ['parent_id'], unique=False)
        batch_op.create_index('idx_comment_created_at', ['created_at'], unique=False)
        batch_op.create_index('idx_comment_author_post', ['author_id', 'post_id'], unique=False)
        batch_op.create_index('idx_comment_author_id', ['author_id'], unique=False)
