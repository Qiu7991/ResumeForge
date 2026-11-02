# SPDX-License-Identifier: Apache-2.0
"""0074：合并「岗位生成计划」本地迁移与上游 10-29 后的迁移链。

背景：本地 `0069_apply_greeting_confirm` / `0070_resume_generation_plan` 是从
`0068_ai_tasks` 分出的分支；上游同时从 `0068_ai_tasks` 走了
`0069_profile_field_placement` → `0070_failure_taxonomy` → … → `0073`。两条分支
都改了数据库，需要一条 merge revision 把两个 head 汇合，否则 `alembic upgrade head`
会报多 head，备份恢复与迁移测试也无法判断当前版本。

本迁移不写任何表/列，只声明两条分支的汇合点。

Revision ID: 0074_merge_resume_plan_upstream
Revises: 0070_resume_generation_plan, 0073_apply_item_failure_taxonomy
Create Date: 2026-11-02
"""

from collections.abc import Sequence

revision: str = "0074_merge_resume_plan_upstream"
down_revision: str | Sequence[str] | None = (
    "0070_resume_generation_plan",
    "0073_apply_item_failure_taxonomy",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
