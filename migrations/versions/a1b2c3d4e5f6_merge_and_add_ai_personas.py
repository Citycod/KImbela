"""merge heads and add ai personas and logs

Revision ID: a1b2c3d4e5f6
Revises: 3a2f8c5b1d9e, d1f2a3b4c5e6
Create Date: 2026-08-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = ('3a2f8c5b1d9e', 'd1f2a3b4c5e6')
branch_labels = None
depends_on = None


def upgrade():
    # --- Add is_ai_persona to users table ---
    op.add_column('users', sa.Column('is_ai_persona', sa.Boolean(), nullable=True, server_default=sa.text('false')))

    # --- Create ai_personas table ---
    op.create_table('ai_personas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('bio_disclosure', sa.Text(), nullable=False),
        sa.Column('personality', sa.Text(), nullable=False),
        sa.Column('interests', sa.JSON(), nullable=True),
        sa.Column('posting_frequency', sa.String(length=100), nullable=True),
        sa.Column('comment_frequency', sa.String(length=255), nullable=True),
        sa.Column('allowed_actions', sa.JSON(), nullable=True),
        sa.Column('forbidden_actions', sa.JSON(), nullable=True),
        sa.Column('escalation_rule', sa.Text(), nullable=True),
        sa.Column('voice_samples', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )

    # --- Create ai_logs table ---
    op.create_table('ai_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('persona_id', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(length=50), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=True),
        sa.Column('prompt_context', sa.Text(), nullable=True),
        sa.Column('generated_content', sa.Text(), nullable=True),
        sa.Column('provider_used', sa.String(length=50), nullable=True),
        sa.Column('is_escalated', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['persona_id'], ['ai_personas.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('ai_logs')
    op.drop_table('ai_personas')
    op.drop_column('users', 'is_ai_persona')
