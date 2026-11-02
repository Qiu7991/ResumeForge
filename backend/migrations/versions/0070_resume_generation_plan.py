# SPDX-License-Identifier: Apache-2.0
"""0070：岗位生成计划（JD 要求 → 证据映射）。

生成前先让用户看到「岗位要求 / 直接证据 / 可迁移证据 / 缺口」，再按这份计划生成，
避免模型只按关键词字面挑项目。计划表只存模型输出与确定性校验后的结果，不改任何
既有简历/资料表；旧库升级只是多一张空表。

Revision ID: 0070_resume_generation_plan
Revises: 0069_apply_greeting_confirm
Create Date: 2026-11-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0070_resume_generation_plan"
down_revision: str | Sequence[str] | None = "0069_apply_greeting_confirm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
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


def downgrade() -> None:
    if not _has_table("resume_generation_plan"):
        return
    op.drop_index("ix_resume_generation_plan_created_at", table_name="resume_generation_plan")
    op.drop_index("ix_resume_generation_plan_job_id", table_name="resume_generation_plan")
    op.drop_table("resume_generation_plan")
