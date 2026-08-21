"""add google_sub to users

Revision ID: c7f3a91b2d4e
Revises: 5db14ea85dfe
Create Date: 2026-08-21 16:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c7f3a91b2d4e'
down_revision: Union[str, Sequence[str], None] = '5db14ea85dfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Google 账号唯一 ID（可空，仅 Google 登录用户有值）
    op.add_column('users', sa.Column('google_sub', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.create_index(op.f('ix_users_google_sub'), 'users', ['google_sub'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_google_sub'), table_name='users')
    op.drop_column('users', 'google_sub')
