# SPDX-License-Identifier: Apache-2.0
"""0069：招呼语的「人工确认」标记。

**只加列，不动任何既有列**：

- ``apply_queue_item.greeting_confirmed``：队列里的招呼语是否经用户确认。
- ``apply_task_item.greeting_confirmed``：建批次时的确认状态快照。

背景：原来闸门只判断"招呼语非空"，而本版允许在投递台一键按岗位批量生成招呼语。
若沿用旧判据，AI 生成完就会直接被发出去，等于绕过"发送前逐条确认"的约定。所以把
"有字"与"人看过"拆成两件事：批量生成写入的是未确认文案，用户在编辑弹窗里保存才置真。

**历史行回填**：升级前能出现在库里的招呼语只可能来自用户手工填写 / 入队时带入，都视为
已确认（``greeting`` 非空 → 1）。两个表同一口径，避免升级后历史队列突然全被跳过。

**升级安全 / 可逆**：表或列已存在时跳过；SQLite 删列走 ``batch_alter_table``。

Revision ID: 0069_apply_greeting_confirm
Revises: 0068_ai_tasks
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0069_apply_greeting_confirm"
down_revision: str | Sequence[str] | None = "0068_ai_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("apply_queue_item", "apply_task_item")
_COLUMN = "greeting_confirmed"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def upgrade() -> None:
    for table in _TABLES:
        if not _has_table(table):
            # 迁移链也会跑在只有部分业务表的历史库上：没有这张表就没有可补的列。
            continue
        existing = _columns(table)
        if _COLUMN in existing:
            continue
        op.add_column(
            table,
            sa.Column(_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # 迁移链也会跑在"只有一张残表"的历史库上（迁移执行器的兜底用例）：
        # 那张表可能连 greeting 列都没有，此时没有可回填的东西。
        if "greeting" not in existing:
            continue
        # 升级前的招呼语都是用户亲手填/带进来的，回填为已确认。
        op.execute(
            sa.text(
                f"UPDATE {table} SET {_COLUMN} = 1 "
                "WHERE TRIM(COALESCE(greeting, '')) <> ''"
            )
        )


def downgrade() -> None:
    for table in _TABLES:
        if not _has_table(table) or _COLUMN not in _columns(table):
            continue
        with op.batch_alter_table(table) as batch:
            batch.drop_column(_COLUMN)
