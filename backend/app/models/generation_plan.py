# SPDX-License-Identifier: Apache-2.0
"""岗位生成计划：JD 要求 → 证据映射，先给用户看匹配报告，再按计划生成简历。"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .profile import utcnow

PLAN_STATUS_READY = "ready"
PLAN_STATUS_FAILED = "failed"


class ResumeGenerationPlan(Base):
    __tablename__ = "resume_generation_plan"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("job.id", ondelete="SET NULL"), nullable=True, index=True
    )
    base_resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_record.id", ondelete="SET NULL"), nullable=True
    )
    # 生成完成后回填，便于从简历反查当时的证据计划（生成失败/取消保持 NULL）。
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_record.id", ondelete="SET NULL"), nullable=True
    )
    # [{id, text, type, weight, keywords}]
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # [{id, requirement_id, ref_type, ref_id, ref_name, match, rationale,
    #   fact_quotes, selected, source_text?}]
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # {direct: n, transferable: n, gaps: [...], requirements: {...}}
    coverage: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    model: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(16), default=PLAN_STATUS_READY)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=True
    )


__all__ = ["PLAN_STATUS_FAILED", "PLAN_STATUS_READY", "ResumeGenerationPlan"]
