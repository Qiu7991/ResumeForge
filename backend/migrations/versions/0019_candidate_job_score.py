# SPDX-License-Identifier: Apache-2.0
"""0019：备选岗位（candidate_job）增加语义评分五列。

编号说明：本文件在原分支叫 ``0003``，合并上游 2.1.0 后改号成 0019、接在
``0018_fork_apply_greeting_plan_aijob`` 之后。

链路背景（2026-11-11）：用户要求「采集评分后，我再决定导入」。原来的链路是
采集 → 用户勾选 → 导入正式岗位 → 才能评分（评分端点第一行就是 ``db.get(Job, job_id)``），
评分来得太晚。现在把评分提前到导入之前，分数落在备选岗位上。

**为什么加在 candidate_job 而不是 job_match_analysis**：那张表的 ``job_id`` 是
``unique`` 且外键指向 ``job.id``，而备选岗位在用户确认导入前没有 job 行——硬塞会撞
外键，而且多条备选无法在同一张表里并存（唯一索引）。备选与评分是一对一，同表加列
既省一次 join，也让列表能直接按分数排序。

**为什么不新增 status 取值**：``status`` 只有 pending/imported 两态，且被
``api/candidate_jobs.py`` 的 Literal 白名单校验。用 ``score_total IS NULL`` +
``scored_at`` 表达「评没评过」不占状态位，还能表达「评分失败」（``score_error`` 非空）。

**升级安全 / 幂等**：列已存在跳过；重复执行不报错。
**可逆**：downgrade 只删本迁移新增的五列。

Revision ID: 0019_candidate_job_score
Revises: 0018_fork_apply_greeting_plan_aijob
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_candidate_job_score"
down_revision: str | Sequence[str] | None = "0018_fork_apply_greeting_plan_aijob"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "candidate_job"

# (列名, 列定义)。顺序即添加顺序，downgrade 反向删。
_SCORE_COLUMNS: tuple[tuple[str, sa.Column], ...] = (
    # 语义评分总分 0-100；NULL = 还没评过。用它当「评没评过」的判据。
    ("score_total", sa.Column("score_total", sa.Integer(), nullable=True)),
    # 完整 SemanticScore（五维/封顶/理由/技能比对）。列表接口不下发这一列（体积），
    # 只在单条详情里给——与 JD 三段「不进列表」是同一条取舍。
    ("score_payload", sa.Column("score_payload", sa.JSON(), nullable=True)),
    # 评分用的模型名：换模型后能看出这个分数是谁给的。
    ("score_model", sa.Column("score_model", sa.String(64), nullable=False, server_default="")),
    ("scored_at", sa.Column("scored_at", sa.DateTime(), nullable=True)),
    # 评分失败原因（缺 JD / 模型未配置 / 解析失败）。空串 = 无错。
    ("score_error", sa.Column("score_error", sa.String(255), nullable=False, server_default="")),
)


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _columns(table: str) -> set[str]:
    if table not in _inspector().get_table_names():
        return set()
    return {column["name"] for column in _inspector().get_columns(table)}


def upgrade() -> None:
    existing = _columns(_TABLE)
    if not existing:
        # 迁移链也会跑在只有部分业务表的历史库上：没有这张表就没有可补的列。
        return
    for name, column in _SCORE_COLUMNS:
        if name in existing:
            continue
        op.add_column(_TABLE, column)


def downgrade() -> None:
    existing = _columns(_TABLE)
    if not existing:
        return
    for name, _ in reversed(_SCORE_COLUMNS):
        if name not in existing:
            continue
        with op.batch_alter_table(_TABLE) as batch:
            batch.drop_column(name)
