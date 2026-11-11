# SPDX-License-Identifier: Apache-2.0
"""备选岗位评分路由：``/api/candidate-jobs/score*``。

**为什么单独成模块**：``api/candidate_jobs.py`` 已经 320+ 行（守 500 行预算），
而评分是后台任务语义（建任务 / 轮询 / 取消），和「增删改查候选」不是一类东西。

路由前缀与 tag 与原文件一致，所以对外仍是 ``/api/candidate-jobs/score``。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..models.material import CANDIDATE_JOB_PENDING, CandidateJob
from ..services.job_hunt.candidate_score_task import (
    CandidateScoreBusy,
    get_candidate_score_runner,
    get_candidate_score_task,
)
from ..services.job_hunt.candidate_scoring import candidate_has_jd

router = APIRouter(prefix="/api/candidate-jobs", tags=["candidate-jobs"])


class CandidateScoreIn(BaseModel):
    """发起一次批量评分。"""

    # 空列表 = 把所有「未导入且还没评过」的候选都评一遍。
    candidate_ids: list[int] = Field(default_factory=list, max_length=2000)
    # 是否重评已有分数的；默认跳过（省 token，也避免覆盖用户看过的那份）。
    force: bool = False
    # 用哪份简历评分；不传走设置里的默认简历。
    resume_id: int | None = None


@router.post("/score")
def start_score(req: CandidateScoreIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    """发起后台评分任务，立刻返回任务快照。

    为什么只建任务不直接评：一轮 15-18 条、每条 LLM 调用 3-5 秒，合计约一分钟，
    同步跑必然超时。前端轮询 ``GET /score/task`` 看进度。
    """
    ids = list(req.candidate_ids)
    if not ids:
        # 默认范围只挑「还没评过」的：已评过的重跑要显式 force 或显式给 id。
        query = db.query(CandidateJob).filter(
            CandidateJob.status == CANDIDATE_JOB_PENDING,
            CandidateJob.deleted_at.is_(None),
            CandidateJob.score_total.is_(None),
        )
        ids = [row.id for row in query.order_by(CandidateJob.id).limit(2000).all()]
    if not ids:
        raise HTTPException(400, "没有需要评分的备选岗位")

    if not req.force:
        # 显式给了 id 但已评过的，跳过（而不是把分数重算一遍覆盖掉）。
        scored = {
            row.id
            for row in db.query(CandidateJob)
            .filter(CandidateJob.id.in_(ids), CandidateJob.score_total.isnot(None))
            .all()
        }
        ids = [candidate_id for candidate_id in ids if candidate_id not in scored]
        if not ids:
            raise HTTPException(400, "这些备选岗位都已经评过分（要重评请传 force=true）")

    # 缺 JD 的直接标错误，不占用模型调用：先按「有没有正文」筛一遍，
    # 剩下的才进任务队列。判定与拼 JD 同源（candidate_has_jd）。
    scorable: list[int] = []
    for candidate in db.query(CandidateJob).filter(CandidateJob.id.in_(ids)).all():
        if candidate_has_jd(candidate):
            scorable.append(candidate.id)
        else:
            candidate.score_error = "jd_missing: 缺 JD 正文"
            candidate.score_total = None
    db.commit()
    if not scorable:
        raise HTTPException(400, "这些备选岗位都没有 JD 正文，无法评分（先补抓详情）")

    try:
        task = get_candidate_score_runner().start(scorable, resume_id=req.resume_id)
    except CandidateScoreBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return task.model_dump(mode="json")


@router.get("/score/task")
def read_score_task(db: Session = Depends(get_db)) -> dict[str, Any]:
    """查当前评分任务（前端轮询这个）。没有任务时返回 running=false。"""
    task = get_candidate_score_task(db)
    if task is None:
        return {"running": False}
    return {"running": task.status == "running", **task.model_dump(mode="json")}


@router.post("/score/task/cancel")
def cancel_score_task(db: Session = Depends(get_db)) -> dict[str, Any]:
    task = get_candidate_score_task(db)
    if task is None:
        raise HTTPException(404, "没有评分任务")
    try:
        get_candidate_score_runner().cancel(task.task_id)
    except CandidateScoreBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"ok": True, "task_id": task.task_id}


__all__ = ["router"]
