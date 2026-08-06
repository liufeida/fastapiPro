"""add ai_model_config

Revision ID: 9c3e7a1f5d2b
Revises: ac2fba4fac9d
Create Date: 2026-08-05 00:00:00.000000

"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c3e7a1f5d2b"
down_revision: Union[str, Sequence[str], None] = "ac2fba4fac9d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ai_model_config",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("provider_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("api_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("base_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("extra_config", sa.JSON(), nullable=True),
        sa.Column("supports_thinking", sa.Boolean(), nullable=False),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_stream", sa.Boolean(), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 插入种子数据
    ai_model_config_table = sa.table(
        "ai_model_config",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("provider_code", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("model_code", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("model_name", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("api_key", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("base_url", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("extra_config", sa.JSON()),
        sa.Column("supports_thinking", sa.Boolean()),
        sa.Column("supports_tools", sa.Boolean()),
        sa.Column("supports_stream", sa.Boolean()),
        sa.Column("supports_vision", sa.Boolean()),
        sa.Column("max_tokens", sa.Integer()),
        sa.Column("temperature", sa.Float()),
        sa.Column("is_enabled", sa.Boolean()),
        sa.Column("is_default", sa.Boolean()),
        sa.Column("sort_order", sa.Integer()),
        sa.Column("description", sqlmodel.sql.sqltypes.AutoString()),
        sa.Column("is_deleted", sa.Boolean()),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)

    op.bulk_insert(
        ai_model_config_table,
        [
            {
                "id": "f1e2d3c4b5a6f1e2d3c4b5a6f1e2d3c4",
                "provider_code": "deepseek",
                "model_code": "deepseek-v4-flash",
                "model_name": "DeepSeek V4 Flash",
                "api_key": None,
                "base_url": "https://api.deepseek.com",
                "extra_config": None,
                "supports_thinking": True,
                "supports_tools": True,
                "supports_stream": True,
                "supports_vision": False,
                "max_tokens": None,
                "temperature": None,
                "is_enabled": True,
                "is_default": True,
                "sort_order": 0,
                "description": "DeepSeek V4 Flash 模型（思考模式需走原生 httpx）",
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": "e2d3c4b5a6f7e2d3c4b5a6f7e2d3c4b5",
                "provider_code": "ollama",
                "model_code": "ollama-deepseek-r1-8b",
                "model_name": "Ollama DeepSeek R1 8B",
                "api_key": None,
                "base_url": "http://localhost:11434",
                "extra_config": {"cloud_url": "https://ollama.com"},
                "supports_thinking": False,
                "supports_tools": False,
                "supports_stream": True,
                "supports_vision": False,
                "max_tokens": None,
                "temperature": None,
                "is_enabled": True,
                "is_default": False,
                "sort_order": 1,
                "description": "Ollama 本地部署的 DeepSeek R1 8B 模型",
                "is_deleted": False,
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("ai_model_config")
