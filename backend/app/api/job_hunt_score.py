# SPDX-License-Identifier: Apache-2.0
"""自研求职 · 语义评分路由（``/api/job-hunt/score``）。

与 ``/api/jobs/{id}/match-analysis`` 的关系
-----------------------------------------
后者产出「五类结论 + 准入闸门」（硬性条件/核心能力/加分项逐条判定），是**准入**用的；
本路由产出**0-100 的量化评分 + 五维明细 + 封顶原因**，是**排序与快速筛选**用的。
两者结论可以互相印证，但用途不同，所以并存、不互相覆盖。

存储：结果写进 ``job_match_analysis.result`` 的 ``semantic_score`` 子键，
复用现有表（job_id 唯一）与查询路径，**不新建表**。
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import SessionLocal, get_db
from ..models.job import Job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


def _job_has_jd(job: Job) -> bool:
    return bool((job.description or "").strip())


@router.post("/jobs/{job_id}/score")
async def score_job(
    job_id: int,
    force: bool = Query(default=False, description="为真时忽略已有评分，强制重算"),
    resume_id: int | None = Query(
        default=None,
        description="用哪份简历评分；不传时按「岗位专属 → 默认简历」回退",
    ),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """对单个岗位做语义评分（五维 + 封顶）。

    前置：岗位必须有 JD 正文。没有 JD 时只能拿标题猜，结果没有参考价值——
    与其返回一个中性分误导用户，不如明确告诉用户「先补 JD」。
    """
    from ..services.apply import apply_service
    from ..services.job_hunt.scoring_service import (
        ScoringFailed,
        ScoringUnavailable,
        build_prompt_for_texts,
        call_scoring_model,
        resolve_resume_text,
    )

    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="岗位不存在或已被删除")

    existing = apply_service.latest_match(db, job_id)
    cached = (existing.result or {}).get("semantic_score") if existing else None
    if cached and not force:
        return {"job_id": job_id, "cached": True, **cached}

    if not _job_has_jd(job):
        raise HTTPException(
            status_code=409,
            detail="该岗位还没有 JD 正文，无法做语义评分。请先让采集补抓详情（或手动补全 JD）。",
        )

    # 简历与资料：与备选评分走**同一条**取源路径（scoring_service），避免两处口径分叉。
    # 岗位专属简历优先（job 行存在），再落设置里的默认简历。
    chosen_resume_title = ""
    try:
        profile, profile_text, resume_text = resolve_resume_text(db, resume_id=resume_id)
    except ScoringUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if resume_id is not None:
        from ..models.resume import ResumeRecord  # noqa: PLC0415 — 局部导入避免循环

        record = db.get(ResumeRecord, resume_id)
        chosen_resume_title = (record.title if record is not None else "") or ""
    if not resume_text.strip() and not profile_text.strip():
        raise HTTPException(status_code=400, detail="个人资料为空，无法评分")

    prompt = build_prompt_for_texts(
        resume=resume_text or profile_text,
        title=job.title,
        company=job.company,
        city=job.location,
        salary=job.salary,
        jd=(job.description or ""),
        profile=profile,
    )

    db.close()  # await 期间不占着连接池

    try:
        score, model = await call_scoring_model(prompt)
    except ScoringUnavailable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ScoringFailed as exc:
        logger.warning("语义评分失败 job=%s：%s", job_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    payload = score.as_dict()
    payload["resume_id"] = resume_id
    payload["resume_title"] = chosen_resume_title
    _persist_semantic(job_id, payload, model=model)
    return {"job_id": job_id, "cached": False, **payload}


@router.get("/jobs/{job_id}/score")
def get_score(job_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """读已落库的语义评分（没有则返回 ok=False）。"""
    from ..services.apply import apply_service

    existing = apply_service.latest_match(db, job_id)
    cached = (existing.result or {}).get("semantic_score") if existing else None
    if not cached:
        return {"job_id": job_id, "ok": False, "error": "尚未评分"}
    return {"job_id": job_id, **cached}


def _persist_semantic(job_id: int, payload: dict[str, Any], *, model: str) -> None:
    """把语义评分写进 job_match_analysis.result 的 semantic_score 子键。

    实际写入在 ``scoring_service.persist_semantic_for_job``——导入备选岗位时也要
    迁移分数，两处必须用同一份实现（尤其是「不覆盖五类结论」这条）。
    这里只负责给它一个独立的 Session：调用点在 await 之后，请求的 Session 已关闭。
    """
    from ..services.job_hunt.scoring_service import persist_semantic_for_job

    session = SessionLocal()
    try:
        persist_semantic_for_job(session, job_id, payload, model=model)
        session.commit()
    finally:
        session.close()


__all__ = ["router"]
