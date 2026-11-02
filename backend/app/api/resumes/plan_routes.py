# SPDX-License-Identifier: Apache-2.0
"""岗位生成计划端点：先生成匹配报告，再按 plan_id 生成简历。

路径 `/generation-plan` 是字面量段，必须在 crud 的 `GET /{resume_id}` 之前注册。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import resumes as _api

from ...database import get_db
from ...models.job import Job
from ...models.resume import ResumeRecord
from ...runtime import dataset_scope
from ...runtime.dataset_scope import DatasetScopeError
from ...runtime.log_redact import log_exception_redacted
from ...schemas.generation_plan import (
    GenerationPlanCreate,
    GenerationPlanOut,
    GenerationPlanSelection,
)
from ...services import trash
from ...services.llm.base import LLMError
from ...services.resume.generate_snapshot import (
    consumed_has_content,
    freeze_generation_snapshot,
)
from ...services.resume.generation_plan import (
    apply_selection,
    create_plan,
    load_plan,
    plan_to_out,
)

router = APIRouter()
logger = logging.getLogger(__name__)


def _plan_out(plan) -> GenerationPlanOut:
    return GenerationPlanOut.model_validate(plan_to_out(plan))


@router.post("/generation-plan", response_model=GenerationPlanOut, status_code=201)
async def create_generation_plan(
    payload: GenerationPlanCreate, db: Session = Depends(get_db)
):
    """按岗位 JD 生成证据计划；只读资料，不写简历。"""
    try:
        lease = dataset_scope.acquire_lease("resume-generation-plan")
    except DatasetScopeError as exc:
        raise HTTPException(status_code=409, detail=exc.public_message) from exc
    try:
        job = db.get(Job, payload.job_id)
        if job is None or trash.is_deleted(job):
            raise HTTPException(status_code=404, detail="岗位不存在或已被删除")
        if payload.base_resume_id is not None:
            base = db.get(ResumeRecord, payload.base_resume_id)
            if base is None or trash.is_deleted(base):
                raise HTTPException(status_code=404, detail="底稿不存在或已被删除")

        config = _api.get_llm_config(db)
        if not config.base_url.strip() or not config.model.strip():
            raise HTTPException(status_code=400, detail="尚未配置大模型 API")
        frozen = freeze_generation_snapshot(db)
        if not consumed_has_content(frozen.consumed):
            raise HTTPException(status_code=400, detail="个人资料为空，无法生成匹配报告")
        provider = _api.create_provider(
            config.model_copy(
                update={"timeout_seconds": max(180, min(600, config.timeout_seconds))}
            )
        )
        plan = await create_plan(
            db,
            job=job,
            base_resume_id=payload.base_resume_id,
            custom_instruction=payload.custom_instruction,
            provider=provider,
            consumed=frozen.consumed,
        )
        return _plan_out(plan)
    except LLMError as exc:
        logger.warning("生成岗位计划失败：%s", exc)
        raise HTTPException(status_code=502, detail=f"生成匹配报告失败：{exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - 外部模型异常统一转为可理解错误
        log_exception_redacted(logger, "生成岗位计划发生内部错误")
        raise HTTPException(status_code=502, detail="生成匹配报告失败") from None
    finally:
        lease.release()


@router.get("/generation-plan/{plan_id}", response_model=GenerationPlanOut)
def get_generation_plan(plan_id: int, db: Session = Depends(get_db)):
    plan = load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="生成计划不存在")
    return _plan_out(plan)


@router.patch("/generation-plan/{plan_id}", response_model=GenerationPlanOut)
def update_generation_plan(
    plan_id: int, payload: GenerationPlanSelection, db: Session = Depends(get_db)
):
    """人工换项目：只改计划里已有候选的 selected，不新增证据。"""
    plan = load_plan(db, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="生成计划不存在")
    try:
        apply_selection(plan, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(plan)
    return _plan_out(plan)
