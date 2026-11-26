"""interview prep agent: chat type and documents

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f('ck_chat_sessions_assistant_type_valid'), 'chat_sessions', type_='check')
    op.create_check_constraint(op.f('ck_chat_sessions_assistant_type_valid'), 'chat_sessions',
                               "assistant_type IN ('career','product','interview')")
    op.drop_constraint(op.f('ck_rag_documents_corpus_valid'), 'rag_documents', type_='check')
    op.create_check_constraint(op.f('ck_rag_documents_corpus_valid'), 'rag_documents', "corpus IN ('internship','product','prep_doc')")
    op.create_table('prep_documents',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('char_count', sa.Integer(), nullable=False),
    sa.Column('text', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], name=op.f('fk_prep_documents_session_id_chat_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_prep_documents_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_prep_documents')),
    )
    op.create_index(op.f('ix_prep_documents_session_id'), 'prep_documents', ['session_id'], unique=False)
    op.create_index(op.f('ix_prep_documents_user_id'), 'prep_documents', ['user_id'], unique=False)
    # Block Supabase's public REST API from this table.
    op.execute('ALTER TABLE "prep_documents" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    op.drop_index(op.f('ix_prep_documents_user_id'), table_name='prep_documents')
    op.drop_index(op.f('ix_prep_documents_session_id'), table_name='prep_documents')
    op.drop_table('prep_documents')
    op.execute("DELETE FROM rag_documents WHERE corpus = 'prep_doc'")
    op.drop_constraint(op.f('ck_rag_documents_corpus_valid'), 'rag_documents', type_='check')
    op.create_check_constraint(op.f('ck_rag_documents_corpus_valid'), 'rag_documents', "corpus IN ('internship','product')")
    op.execute("DELETE FROM chat_sessions WHERE assistant_type = 'interview'")
    op.drop_constraint(op.f('ck_chat_sessions_assistant_type_valid'), 'chat_sessions', type_='check')
    op.create_check_constraint(op.f('ck_chat_sessions_assistant_type_valid'), 'chat_sessions', "assistant_type IN ('career','product')")
