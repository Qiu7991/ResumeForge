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
from ..services.job_hunt.scoring import build_scoring_prompt, parse_semantic_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


def _job_has_jd(job: Job) -> bool:
    return bool((job.description or "").strip())


@router.post("/jobs/{job_id}/score")
async def score_job(
    job_id: int,
    force: bool = Query(default=False, description="为真时忽略已有评分，强制重算"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """对单个岗位做语义评分（五维 + 封顶）。

    前置：岗位必须有 JD 正文。没有 JD 时只能拿标题猜，结果没有参考价值——
    与其返回一个中性分误导用户，不如明确告诉用户「先补 JD」。
    """
    from ..services.apply import apply_service
    from ..services.settings_service import get_llm_config

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

    # 简历与候选人设置：复用匹配分析同一条取源路径，避免两处口径不一致。
    from ..services.job.job_match_context import match_source_texts

    profile, profile_text, resume_text = match_source_texts(db, job)
    if not resume_text.strip() and not profile_text.strip():
        raise HTTPException(status_code=400, detail="个人资料为空，无法评分")

    prompt = build_scoring_prompt(
        resume=(resume_text or profile_text)[:12000],
        title=job.title,
        company=job.company,
        city=job.location,
        salary=job.salary,
        jd=(job.description or "")[:8000],
        # 字段名与 ProfileOut 对齐（实测：target_city / expected_salary / job_intent）。
        # 早期版本写成了 target_cities / salary_min / salary_max，永远取到空值。
        candidate_education=_profile_field(profile, "education"),
        candidate_recruitment_type=_profile_field(profile, "job_intent"),
        target_cities=_profile_field(profile, "target_city") or _profile_field(profile, "city"),
        salary_min=0,
        salary_max=_expected_salary_k(profile),
    )

    db.close()  # await 期间不占着连接池

    from ..services.llm import create_provider
    from ..services.llm.base import LLMError

    config = get_llm_config(SessionLocal())
    if not (config.base_url.strip() and config.model.strip()):
        raise HTTPException(status_code=409, detail="还没有配置大模型，无法评分")

    provider = create_provider(config)
    try:
        raw = await provider.chat(
            [{"role": "user", "content": prompt}], thinking=False
        )
    except LLMError as exc:
        logger.warning("语义评分失败 job=%s：%s", job_id, exc)
        raise HTTPException(status_code=502, detail=f"评分失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("语义评分内部错误 job=%s：%s", job_id, exc)
        raise HTTPException(status_code=502, detail="评分失败") from exc

    score = parse_semantic_score(raw)
    if not score.ok:
        raise HTTPException(status_code=502, detail=f"评分结果无法解析：{score.error}")

    _persist_semantic(job_id, score.as_dict(), model=config.model)
    return {"job_id": job_id, "cached": False, **score.as_dict()}


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

    不覆盖同一行的五类结论（result 里其它键原样保留）：两个结论同一行不同用途。
    """
    from ..services.apply._match import latest_match

    session = SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None:
            return
        row = latest_match(session, job_id)
        if row is None:
            from ..models.apply import JobMatchAnalysis

            row = JobMatchAnalysis(
                job_id=job.id,
                job_title=job.title,
                company=job.company,
                result={"semantic_score": payload},
                hard_gate="unknown",
                requires_confirm=False,
                model=model,
            )
            session.add(row)
        else:
            merged = dict(row.result or {})
            merged["semantic_score"] = payload
            row.result = merged
            row.model = model
        session.commit()
    finally:
        session.close()


def _profile_field(profile: Any, name: str) -> str:
    value = getattr(profile, name, None)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value)
    return str(value).strip()


def _profile_number(profile: Any, name: str) -> float:
    try:
        return float(getattr(profile, name, 0) or 0)
    except (TypeError, ValueError):
        return 0.0


def _expected_salary_k(profile: Any) -> float:
    """从 expected_salary 文本（"15-25K" / "20K"）里取上限（单位 K）。

    资料里的期望薪资是自由文本，不是数值列；取不到就返回 0（= 未设置），
    让提示词明确说「未填写」，而不是把一个猜的数字喂给模型。
    """
    import re

    text = _profile_field(profile, "expected_salary")
    numbers = re.findall(r"(\d+(?:\.\d+)?)", text)
    if not numbers:
        return 0.0
    high = float(numbers[-1])
    if "万" in text:
        high *= 10
    return high


__all__ = ["router"]
