"""0048：通用 AI 任务登记表（``ai_task``）。

所有"跑起来几十秒到几分钟、用户还想干别的事"的 AI 入口共用一张表：``kind`` 区分业务，
``payload`` 存输入摘要（只放标识与选项），``result_ref`` 存完成后跳转所需的落点。
业务结果仍保存在各自的业务表里，本表只负责**任务生命周期**（可取消、可恢复、可回看）。

任务只活在进程内工作线程里，因此启动时会把遗留的 pending/running 收尾成 failed
（见 ``services/ai_task_recovery.py``）；迁移本身只建表。

Revision ID: 0048_ai_task
Revises: 0047_usage_ledger
Create Date: 2026-10-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0048_ai_task"
down_revision: str | Sequence[str] | None = "0047_usage_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if _has_table("ai_task"):
        return
    op.create_table(
        "ai_task",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("label", sa.String(length=256), nullable=False, server_default=""),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result_ref", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_ai_task_status", "ai_task", ["status"])
    op.create_index("ix_ai_task_kind", "ai_task", ["kind"])
    op.create_index("ix_ai_task_created_at", "ai_task", ["created_at"])


def downgrade() -> None:
    if _has_table("ai_task"):
        op.drop_table("ai_task")
