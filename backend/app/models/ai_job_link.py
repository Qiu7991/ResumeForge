# SPDX-License-Identifier: Apache-2.0
"""``ai_job_link``：BossHunter 引擎岗位 ↔ 简历通正式岗位（`job`）的映射行。

引擎库（bosshunter.db）只做暂存，正式岗位池仍是简历通 `job` 表；一张岗位至多
一条 link（``job_id`` unique、``engine_job_id`` unique）。引擎侧的评分/招呼语/
状态快照都挂在 link 上，不污染 `job` 表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from .profile import utcnow


class AiJobLink(Base):
    """一条引擎岗位到简历通岗位的映射与同步快照。"""

    __tablename__ = "ai_job_link"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 简历通正式岗位（一对一）。
    job_id: Mapped[int] = mapped_column(
        ForeignKey("job.id", ondelete="CASCADE"), unique=True, index=True
    )
    # BossHunter 岗位 id（引擎侧唯一）。
    engine_job_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # boss / zhilian / 51job / liepin。
    source_platform: Mapped[str] = mapped_column(String(16), default="boss")
    # 引擎侧状态快照（pending/scored/ready/filtered/approved/sent/replied/...）。
    engine_status: Mapped[str] = mapped_column(String(32), default="", index=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_reason: Mapped[str] = mapped_column(Text, default="")
    score_trace_json: Mapped[str] = mapped_column(Text, default="")
    greeting: Mapped[str] = mapped_column(Text, default="")
    greeting_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    engine_url: Mapped[str] = mapped_column(Text, default="")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
