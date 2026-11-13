# SPDX-License-Identifier: Apache-2.0
"""0018：二开功能所需的基线后合并迁移（招呼语确认 / 生成计划 / AI 求职链表）。

编号说明：本文件在原分支叫 ``0002``，合并上游 2.1.0 后上游已占用 0002-0017，
所以改号成 0018、接在 ``0017_agent_task_params`` 之后；revision id 同步改号，
否则 alembic 会因为两条链各有一个「0002」而出现双头。

把 1.x 的 0069/0070/0075 三张卡合并成 2.0 基线（0001_baseline_v2）之后的一条迁移；
**只加列、只加表，不改不删任何既有结构**。三块的来源与语义：

- ``apply_queue_item.greeting_confirmed`` / ``apply_task_item.greeting_confirmed``
  （源自 1.x 0069）：把「有文案」与「人看过」拆成两件事。批量生成写入的是未确认文案，
  用户在编辑弹窗里保存/确认才置真；历史行回填口径与 0069 一致——升级前能出现在库里的
  招呼语只可能来自用户手工填写/入队带入，一律视为已确认（greeting 非空 → 1）。
- ``resume_generation_plan``（源自 1.x 0070）：岗位生成计划（JD 要求 → 证据映射），
  只存模型输出与确定性校验后的结果，不改任何既有简历/资料表；旧库升级只是多一张空表。
- ``ai_job_link``（源自 1.x 0075）：BossHunter 引擎岗位 ↔ 简历通岗位映射，持
  ``engine_job_id``（唯一）与引擎侧评分/招呼语/状态快照；引擎库只做暂存，正式岗位池
  仍是简历通 ``job`` 表。

1.x 的失败三列（0073）与 failure_category/detail **不在本迁移里**：2.0 基线已原生具备
（见 docs/fork-2.0-baseline.md §6）。

**升级安全 / 幂等**：列已存在跳过、表已存在跳过，重复执行不报错。
**可逆**：downgrade 只删本迁移新增的东西。

Revision ID: 0018_fork_apply_greeting_plan_aijob
Revises: 0017_agent_task_params
Create Date: 2026-11-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_fork_apply_greeting_plan_aijob"
down_revision: str | Sequence[str] | None = "0017_agent_task_params"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONFIRM_TABLES = ("apply_queue_item", "apply_task_item")
_CONFIRM_COLUMN = "greeting_confirmed"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in _inspector().get_table_names()


def _columns(table: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table)}


def _add_greeting_confirmed() -> None:
    for table in _CONFIRM_TABLES:
        if not _has_table(table):
            # 迁移链也会跑在只有部分业务表的历史库上：没有这张表就没有可补的列。
            continue
        existing = _columns(table)
        if _CONFIRM_COLUMN in existing:
            continue
        op.add_column(
            table,
            sa.Column(_CONFIRM_COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        # 迁移链也会跑在"只有一张残表"的历史库上：那张表可能连 greeting 列都没有，
        # 此时没有可回填的东西。
        if "greeting" not in existing:
            continue
        # 升级前的招呼语都是用户亲手填/带进来的，回填为已确认。
        op.execute(
            sa.text(
                f"UPDATE {table} SET {_CONFIRM_COLUMN} = 1 "
                "WHERE TRIM(COALESCE(greeting, '')) <> ''"
            )
        )


def _create_resume_generation_plan() -> None:
    if _has_table("resume_generation_plan"):
        return
    op.create_table(
        "resume_generation_plan",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("job.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "base_resume_id",
            sa.Integer(),
            sa.ForeignKey("resume_record.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resume_id",
            sa.Integer(),
            sa.ForeignKey("resume_record.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requirements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("coverage", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("model", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="ready"),
        sa.Column("error", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_resume_generation_plan_job_id", "resume_generation_plan", ["job_id"]
    )
    op.create_index(
        "ix_resume_generation_plan_created_at", "resume_generation_plan", ["created_at"]
    )


def _create_ai_job_link() -> None:
    table = "ai_job_link"
    if _has_table(table):
        return
    op.create_table(
        table,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Integer(),
            sa.ForeignKey("job.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("engine_job_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("source_platform", sa.String(length=16), nullable=False, server_default="boss"),
        sa.Column("engine_status", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("score_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("score_trace_json", sa.Text(), nullable=False, server_default=""),
        sa.Column("greeting", sa.Text(), nullable=False, server_default=""),
        sa.Column("greeting_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("engine_url", sa.Text(), nullable=False, server_default=""),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_ai_job_link_job_id", table, ["job_id"])
    op.create_index("ix_ai_job_link_engine_job_id", table, ["engine_job_id"])
    op.create_index("ix_ai_job_link_engine_status", table, ["engine_status"])


def upgrade() -> None:
    _add_greeting_confirmed()
    _create_resume_generation_plan()
    _create_ai_job_link()


def downgrade() -> None:
    if _has_table("ai_job_link"):
        op.drop_index("ix_ai_job_link_engine_status", table_name="ai_job_link")
        op.drop_index("ix_ai_job_link_engine_job_id", table_name="ai_job_link")
        op.drop_index("ix_ai_job_link_job_id", table_name="ai_job_link")
        op.drop_table("ai_job_link")
    if _has_table("resume_generation_plan"):
        op.drop_index("ix_resume_generation_plan_created_at", table_name="resume_generation_plan")
        op.drop_index("ix_resume_generation_plan_job_id", table_name="resume_generation_plan")
        op.drop_table("resume_generation_plan")
    for table in _CONFIRM_TABLES:
        if _has_table(table) and _CONFIRM_COLUMN in _columns(table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(_CONFIRM_COLUMN)
