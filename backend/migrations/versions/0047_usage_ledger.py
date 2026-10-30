"""0047：模型用量账本与单价档案（R04）。

只加两张表，不动任何业务表：

- ``llm_usage_record``：每次模型调用的**数字**（token / 耗时 / 结束原因 / 重试次数），
  不含提示词、回复、密钥或个人资料；token 缺失为 NULL（界面显示"未知"，不伪造 0）。
- ``usage_pricing_record``：用户可命名、可回溯的单价档案，按**每百万 token** 计，
  输入分「缓存命中 / 未命中」两档。同时只有一条 ``is_active`` 生效。

两表都是新增，历史库直接建表即可；用 ``has_table`` 跳过已存在的表，保证迁移可重跑。

Revision ID: 0047_usage_ledger
Revises: 0046_search_fts
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_usage_ledger"
down_revision: str | Sequence[str] | None = "0046_search_fts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("llm_usage_record"):
        op.create_table(
            "llm_usage_record",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("task", sa.String(length=32), nullable=False, server_default="unknown"),
            sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
            sa.Column(
                "resume_id",
                sa.Integer(),
                sa.ForeignKey("resume_record.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("prompt_tokens", sa.Integer(), nullable=True),
            sa.Column("cache_hit_tokens", sa.Integer(), nullable=True),
            sa.Column("cache_miss_tokens", sa.Integer(), nullable=True),
            sa.Column("completion_tokens", sa.Integer(), nullable=True),
            sa.Column("total_tokens", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("finish_reason", sa.String(length=32), nullable=False, server_default=""),
            sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cost_estimate", sa.Float(), nullable=True),
            sa.Column("cost_currency", sa.String(length=8), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_llm_usage_record_task", "llm_usage_record", ["task"])
        op.create_index("ix_llm_usage_record_resume_id", "llm_usage_record", ["resume_id"])
        op.create_index("ix_llm_usage_record_created_at", "llm_usage_record", ["created_at"])

    if not _has_table("usage_pricing_record"):
        op.create_table(
            "usage_pricing_record",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
            sa.Column("input_cache_hit_per_million", sa.Float(), nullable=True),
            sa.Column("input_cache_miss_per_million", sa.Float(), nullable=True),
            sa.Column("output_per_million", sa.Float(), nullable=True),
            sa.Column("currency", sa.String(length=8), nullable=False, server_default="CNY"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_usage_pricing_record_is_active", "usage_pricing_record", ["is_active"])
        op.create_index("ix_usage_pricing_record_created_at", "usage_pricing_record", ["created_at"])


def downgrade() -> None:
    if _has_table("usage_pricing_record"):
        op.drop_table("usage_pricing_record")
    if _has_table("llm_usage_record"):
        op.drop_table("llm_usage_record")
