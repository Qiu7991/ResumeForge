# SPDX-License-Identifier: Apache-2.0
"""发送结果写回求职进度（P1-5）：引擎 sent → ``application_track``（source=ai_jobs）。

**幂等**：``attempt_key = f"ai_jobs:{engine_job_id}"``，同一次发送重复同步不会
重复落进度（freeze_delivery 的幂等键挡住）；已有更靠后状态（面试等）不会被拉回。
拉取式同步：调用方（deliver 之后 / 轮询到任务终态时）主动触发，不引入后台线程。
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ...models.tracker import ApplicationTrack
from ...schemas.ai_jobs import AiJobsConfig
from .manager import SidecarManager, get_sidecar_manager
from .settings import get_ai_jobs_config  # noqa: F401 - 供调用方按需扩展（配置感知）时使用

logger = logging.getLogger(__name__)

# 引擎侧"已经发生投递动作"的状态（BossHunter jobs.status 完成态子集）。
_ENGINE_DELIVERED = {"sent", "replied", "resume_sent", "needs_resume", "follow_up_sent"}


def sync_sent_to_tracker(
    db: Session,
    config: AiJobsConfig | None = None,
    manager: SidecarManager | None = None,
) -> int:
    """把引擎侧已发送岗位写回求职进度；返回本次**新建**的进度条数。

    失败不抛：同步是锦上添花，引擎才是权威数据源（页面可重试）。
    ``record_applied`` 对已有记录只补关联、不回退状态（面试不会被拉回），
    所以新建数以写入前后的行数差为准。
    """
    from ...models.tracker import SOURCE_AI_JOBS
    from ..tracker import record_applied

    mgr = manager or get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        return 0
    try:
        data = mgr.client_for(port).get("/api/jobs", params={"deleted": "active", "limit": 500})
    except Exception as exc:  # noqa: BLE001 - 拉取失败下次再试
        logger.info("引擎岗位拉取失败，跳过 tracker 同步：%s", exc)
        return 0
    jobs = (data or {}).get("jobs") or []
    before = db.query(ApplicationTrack.id).count()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = str(job.get("status") or "")
        if status not in _ENGINE_DELIVERED:
            continue
        company = str(job.get("company") or "").strip()
        title = str(job.get("title") or "").strip()
        if not company or not title:
            continue
        engine_job_id = str(job.get("id") or "").strip()
        if not engine_job_id:
            continue
        applied_on = str(job.get("sent_at") or job.get("updated_at") or "")[:10]
        try:
            record_applied(
                db,
                company=company,
                title=title,
                applied_on=applied_on,
                attempt_key=f"ai_jobs:{engine_job_id}",
                source=SOURCE_AI_JOBS,
            )
        except Exception as exc:  # noqa: BLE001 - 单条失败不拖垮批次
            logger.warning("tracker 写回失败 job=%s：%s", engine_job_id, exc)
    db.commit()
    written = db.query(ApplicationTrack.id).count() - before
    if written:
        logger.info("AI 求职发送结果已写回求职进度 %s 条", written)
    return written


__all__ = ["sync_sent_to_tracker"]
