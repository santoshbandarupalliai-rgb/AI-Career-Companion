"""email verification and resume labels

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-24 19:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    # Accounts that exist today were created before verification existed: treat them as verified.
    op.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")
    op.add_column('resumes', sa.Column('label', sa.String(length=100), nullable=True))
    op.create_table('email_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.String(length=20), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_email_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_tokens')),
    )
    op.create_index(op.f('ix_email_tokens_token_hash'), 'email_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_email_tokens_user_id'), 'email_tokens', ['user_id'], unique=False)
    # Block Supabase's public REST API from this table.
    op.execute('ALTER TABLE "email_tokens" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_index(op.f('ix_email_tokens_user_id'), table_name='email_tokens')
    op.drop_index(op.f('ix_email_tokens_token_hash'), table_name='email_tokens')
    op.drop_table('email_tokens')
    op.drop_column('resumes', 'label')
    op.drop_column('users', 'email_verified_at')
