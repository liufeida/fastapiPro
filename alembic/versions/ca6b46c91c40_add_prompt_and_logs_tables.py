"""add_prompt_and_logs_tables

Revision ID: ca6b46c91c40
Revises: 9c3e7a1f5d2b
Create Date: 2026-08-06 16:49:07.986986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'ca6b46c91c40'
down_revision: Union[str, Sequence[str], None] = '9c3e7a1f5d2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'system_prompt',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('prompt_code', sa.String(), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('model_code', sa.String(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('prompt_code'),
    )

    op.create_table(
        'api_access_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('trace_id', sa.String(), nullable=False),
        sa.Column('method', sa.String(), nullable=False),
        sa.Column('path', sa.String(), nullable=False),
        sa.Column('query_params', sa.Text(), nullable=True),
        sa.Column('request_body', sa.Text(), nullable=True),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('is_streaming', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_error', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('ip', sa.String(), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_access_log_trace_id', 'api_access_log', ['trace_id'], unique=False)
    op.create_index('ix_api_access_log_path', 'api_access_log', ['path'], unique=False)

    op.create_table(
        'ai_chat_log',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('trace_id', sa.String(), nullable=False),
        sa.Column('model_code', sa.String(), nullable=False),
        sa.Column('provider_code', sa.String(), nullable=False),
        sa.Column('user_prompt', sa.Text(), nullable=True),
        sa.Column('system_prompt', sa.Text(), nullable=True),
        sa.Column('messages', sa.Text(), nullable=True),
        sa.Column('response_content', sa.Text(), nullable=True),
        sa.Column('thinking_content', sa.Text(), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=True),
        sa.Column('output_tokens', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('thinking_ms', sa.Float(), nullable=True),
        sa.Column('is_error', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_ai_chat_log_trace_id', 'ai_chat_log', ['trace_id'], unique=False)
    op.create_index('ix_ai_chat_log_model_code', 'ai_chat_log', ['model_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ai_chat_log_model_code', table_name='ai_chat_log')
    op.drop_index('ix_ai_chat_log_trace_id', table_name='ai_chat_log')
    op.drop_table('ai_chat_log')

    op.drop_index('ix_api_access_log_path', table_name='api_access_log')
    op.drop_index('ix_api_access_log_trace_id', table_name='api_access_log')
    op.drop_table('api_access_log')

    op.drop_table('system_prompt')
