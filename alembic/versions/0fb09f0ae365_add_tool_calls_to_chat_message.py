"""add_tool_calls_to_chat_message

Revision ID: 0fb09f0ae365
Revises: 62d7a388d9b9
Create Date: 2026-08-08 02:26:09.901492

"""
from typing import Sequence, Union

import sqlmodel
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0fb09f0ae365'
down_revision: Union[str, Sequence[str], None] = '62d7a388d9b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('chat_message', sa.Column('tool_call_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('chat_message', sa.Column('tool_calls', sa.JSON(), nullable=True))
    op.create_index(op.f('ix_chat_message_tool_call_id'), 'chat_message', ['tool_call_id'], unique=False)

    op.create_index(
        'ix_chat_message_conversation_id_created_at',
        'chat_message',
        ['conversation_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_chat_conversation_user_id_is_deleted_updated_at',
        'chat_conversation',
        ['user_id', 'is_deleted', 'updated_at'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_chat_conversation_user_id_is_deleted_updated_at'), table_name='chat_conversation')
    op.drop_index(op.f('ix_chat_message_conversation_id_created_at'), table_name='chat_message')
    op.drop_index(op.f('ix_chat_message_tool_call_id'), table_name='chat_message')
    op.drop_column('chat_message', 'tool_calls')
    op.drop_column('chat_message', 'tool_call_id')
