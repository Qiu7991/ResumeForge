# SPDX-License-Identifier: Apache-2.0
"""AI 求职接口（prefix ``/api/ai-jobs``）：状态、配置、sidecar 启停。

后端代理原则：前端不直接访问 sidecar——统一走这里，归一化错误、隐藏 Key。
写接口的 loopback 防护由全局 ``LoopbackOriginGuardMiddleware`` 承担。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.ai_jobs import AiJobsConfig
from ..services.ai_jobs import delivery, tasks
from ..services.ai_jobs.delivery_sync import sync_sent_to_tracker
from ..services.ai_jobs.manager import get_sidecar_manager
from ..services.ai_jobs.settings import get_ai_jobs_config, save_ai_jobs_config
from ..services.ai_jobs.status import build_ai_jobs_status, run_preflight

router = APIRouter(prefix="/api/ai-jobs", tags=["ai-jobs"])
logger = logging.getLogger(__name__)


class TaskStartRequest(BaseModel):
    mode: str
    confirm: bool = False


class DeliverRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)
    confirm: bool = False


class RejectRequest(BaseModel):
    job_ids: list[str] = Field(default_factory=list)


def _gate_error(exc: tasks.TaskGateError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    """聚合连接状态（页面骨架据此渲染 已连接/未安装/版本不匹配 三态）。"""
    return build_ai_jobs_status(get_ai_jobs_config(db))


@router.get("/config", response_model=AiJobsConfig)
def read_config(db: Session = Depends(get_db)):
    return get_ai_jobs_config(db)


@router.put("/config", response_model=AiJobsConfig)
def write_config(payload: AiJobsConfig, db: Session = Depends(get_db)):
    """保存连接配置。校验由 Pydantic 承担；不含任何凭据字段。"""
    return save_ai_jobs_config(db, payload)


@router.post("/engine/start")
def start_engine(db: Session = Depends(get_db)):
    """启动 sidecar（只启动简历通自己拥有的进程）。"""
    config = get_ai_jobs_config(db)
    result = get_sidecar_manager().start(config)
    if not result.ok:
        # 422：可由用户修复的前置条件（引擎路径、端口、健康检查），不是服务器错误。
        raise HTTPException(status_code=422, detail=result.error or "sidecar 启动失败")
    return {
        "ok": True,
        "port": result.port,
        "pid": result.pid,
        "owned": result.owned,
        "health": result.health.model_dump() if result.health else None,
    }


@router.post("/engine/stop")
def stop_engine():
    """停止自己启动的 sidecar；未持有进程时幂等返回。"""
    stopped = get_sidecar_manager().stop()
    return {"ok": True, "stopped": stopped}


# ===== P1：预检 / 任务 / 确认投递 =====


@router.post("/preflight")
def preflight(db: Session = Depends(get_db)):
    """启动前聚合检查（六类）；单项失败不拖垮整体。"""
    config = get_ai_jobs_config(db)
    checks = run_preflight(db, config)
    return {
        "checks": [check.model_dump() for check in checks],
        "all_ok": all(check.ok for check in checks),
    }


@router.post("/tasks")
def start_task(payload: TaskStartRequest, db: Session = Depends(get_db)):
    """启动 full/collect/monitor 任务；confirm 必填，互斥冲突 409。"""
    try:
        snapshot = tasks.start_task(db, payload.mode, payload.confirm)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc
    return snapshot


@router.get("/workbench")
def workbench(db: Session = Depends(get_db)):
    """透传引擎工作台聚合状态（当前任务/待确认/配额/漏斗）；轮询入口。"""
    try:
        return tasks.get_workbench_state(get_ai_jobs_config(db))
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: str):
    """停止任务（幂等）；终态后放掉互斥标志。"""
    try:
        return tasks.stop_task(task_id)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.get("/confirmation")
def confirmation(db: Session = Depends(get_db)):
    """待确认投递列表 + 发送配额（确认弹窗的数据源）。"""
    try:
        state = delivery.workbench_snapshot(db)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc
    return {
        "pending_confirmation": [_decorate_engine_job(job) for job in state.get("pending_confirmation") or []],
        "send_quota": state.get("send_quota") or {},
        "task": state.get("task") or {},
    }


@router.post("/deliver")
def deliver(payload: DeliverRequest, db: Session = Depends(get_db)):
    """人工确认后投递；成功后尽力把已有发送结果写回求职进度。

    发送总闸（2.0 默认关）收口在 ``services.ai_jobs.delivery.send_gate_open``：
    API 层先挡一次（403，省掉无效 DB/引擎开销），服务层 ``deliver`` 内再挡一次，
    任何路径都绕不过；1.x 的「AI_JOBS_ALLOW_SEND=0 才拒」语义已废弃。
    """
    if not delivery.send_gate_open():
        raise HTTPException(
            status_code=403,
            detail="发送闸门未打开：设置环境变量 AI_JOBS_ALLOW_SEND=1 并重启后端后才允许投递（默认关）",
        )
    try:
        result = delivery.deliver(db, payload.job_ids, payload.confirm)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc
    written = sync_sent_to_tracker(db)
    return {"result": result, "tracker_synced": written}


@router.post("/reject")
def reject(payload: RejectRequest, db: Session = Depends(get_db)):
    try:
        result = delivery.reject(db, payload.job_ids)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc
    return {"result": result}


@router.post("/sync")
def sync(db: Session = Depends(get_db)):
    """手动全量同步：拉引擎岗位导入岗位池 + 已发送岗位写回求职进度。"""
    from ..services.ai_jobs.job_sync import sync_engine_jobs

    imported = sync_engine_jobs(db)
    tracker_written = sync_sent_to_tracker(db)
    return {"import": imported.as_dict(), "tracker_synced": tracker_written}


# ===== P2：岗位池 / 评分 / 招呼语 / 简历 =====


# 引擎 source_platform（协议值）→ 展示名与只读标记（前端不写死站点 token）。
_PLATFORM_LABELS = {"boss": "BOSS直聘", "zhilian": "智联招聘", "51job": "前程无忧", "liepin": "猎聘"}
_PLATFORM_READ_ONLY = {"zhilian", "51job", "liepin"}


def _decorate_engine_job(job: object) -> dict:
    if not isinstance(job, dict):
        return {}
    platform = str(job.get("source_platform") or "boss")
    decorated = dict(job)
    decorated.setdefault("platform_label", _PLATFORM_LABELS.get(platform, platform))
    decorated.setdefault("platform_read_only", platform in _PLATFORM_READ_ONLY)
    return decorated


@router.get("/engine-jobs")
def engine_jobs(
    deleted: str = "active",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """引擎岗位列表（分页/回收站筛选），原样代理 sidecar ``GET /api/jobs``。"""
    manager = get_sidecar_manager()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    try:
        data = manager.client_for(port).get(
            "/api/jobs", params={"deleted": deleted, "limit": max(1, min(limit, 500)), "offset": max(0, offset)}
        )
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):
        data["jobs"] = [_decorate_engine_job(job) for job in data["jobs"]]
    return data


class ImportJobsRequest(BaseModel):
    engine_job_ids: list[str] = Field(default_factory=list)
    auto_import: bool = True


@router.post("/jobs/import")
def jobs_import(payload: ImportJobsRequest, db: Session = Depends(get_db)):
    """把引擎岗位导入简历通岗位池（可只导入选中 ids）。"""
    from ..services.ai_jobs.job_sync import import_engine_jobs, sync_engine_jobs

    if payload.engine_job_ids:
        manager = get_sidecar_manager()
        port = manager.read_state().port
        if not port:
            raise HTTPException(status_code=422, detail="sidecar 未运行")
        data = manager.client_for(port).get("/api/jobs", params={"deleted": "all", "limit": 500})
        jobs = [job for job in (data or {}).get("jobs") or [] if str(job.get("id")) in set(payload.engine_job_ids)]
        summary = import_engine_jobs(db, jobs, auto_import=payload.auto_import)
    else:
        summary = sync_engine_jobs(db)
    return summary.as_dict()


@router.get("/engine-jobs/{engine_job_id}/score-trace")
def engine_score_trace(engine_job_id: str, db: Session = Depends(get_db)):
    """五维评分详情：link 有快照用快照，否则代理引擎。"""
    import json

    from ..models.ai_job_link import AiJobLink

    manager = get_sidecar_manager()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    data = manager.client_for(port).get(f"/api/jobs/{engine_job_id}/score-trace")
    trace = data if isinstance(data, dict) else {}
    # 有快照就顺手刷新 link（评分详情是导入岗位的常驻数据源）
    link = db.query(AiJobLink).filter(AiJobLink.engine_job_id == engine_job_id).one_or_none()
    if link is not None and trace:
        link.score_trace_json = json.dumps(trace, ensure_ascii=False)
        db.commit()
    return trace


class GreetingSaveRequest(BaseModel):
    greeting: str = Field(default="", max_length=600)


@router.get("/engine-jobs/{engine_job_id}/greeting")
def read_greeting(engine_job_id: str, db: Session = Depends(get_db)):
    from ..services.ai_jobs.greeting import read_greeting as _read

    return _read(db, engine_job_id)


@router.post("/engine-jobs/{engine_job_id}/greeting")
def save_greeting(engine_job_id: str, payload: GreetingSaveRequest, db: Session = Depends(get_db)):
    from ..services.ai_jobs.greeting import save_greeting as _save

    try:
        return _save(db, engine_job_id, payload.greeting)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/engine-jobs/{engine_job_id}/greeting/confirm")
def confirm_greeting(engine_job_id: str, db: Session = Depends(get_db)):
    from ..services.ai_jobs.greeting import confirm_greeting as _confirm

    try:
        return _confirm(db, engine_job_id)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.get("/replies")
def replies(db: Session = Depends(get_db)):
    """未处理回复 + 会话列表（监测页签数据源）。"""
    from ..services.ai_jobs import replies as replies_service

    try:
        return replies_service.list_replies(db)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


class ReplyActionRequest(BaseModel):
    content: str = Field(default="", max_length=4000)


@router.post("/replies/{history_id}/open-chat")
def reply_open_chat(history_id: str, db: Session = Depends(get_db)):
    from ..services.ai_jobs import replies as replies_service

    try:
        return replies_service.open_chat(db, history_id)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/replies/{history_id}/prepare-reply")
def reply_prepare(history_id: str, db: Session = Depends(get_db)):
    from ..services.ai_jobs import replies as replies_service

    try:
        return replies_service.prepare_reply(db, history_id)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/replies/{history_id}/reply")
def reply_record(history_id: str, payload: ReplyActionRequest, db: Session = Depends(get_db)):
    from ..services.ai_jobs import replies as replies_service

    try:
        return replies_service.record_reply(db, history_id, payload.content)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/replies/{history_id}/dismiss")
def reply_dismiss(history_id: str, db: Session = Depends(get_db)):
    from ..services.ai_jobs import replies as replies_service

    try:
        return replies_service.dismiss(db, history_id)
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.post("/config/sync-llm")
def config_sync_llm(db: Session = Depends(get_db)):
    """把简历通全局 LLM Profile 同步给引擎（Key 只在后端流转）。"""
    from ..services.ai_jobs.config_sync import sync_llm_to_engine
    from ..services.ai_jobs.manager import get_sidecar_manager as _gsm

    manager = _gsm()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    try:
        return sync_llm_to_engine(db, manager.client_for(port))
    except tasks.TaskGateError as exc:
        raise _gate_error(exc) from exc


@router.get("/history")
def history(limit: int = 20, db: Session = Depends(get_db)):
    """引擎历史记录代理（采集/评分/任务/投递记录页签）。"""
    manager = get_sidecar_manager()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    return manager.client_for(port).get("/api/history", params={"limit": max(1, min(limit, 100))})


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """今日数据/漏斗/趋势（透传引擎聚合）。"""
    manager = get_sidecar_manager()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    client = manager.client_for(port)
    return {
        "funnel_today": client.get("/api/workbench").get("funnel_today") if isinstance(client.get("/api/workbench"), dict) else None,
        "stats": client.get("/api/stats"),
        "activity": client.get("/api/activity", params={"days": 7}),
    }


@router.post("/resume/sync")
def resume_sync(db: Session = Depends(get_db)):
    """把最新通用简历上传给引擎（内容哈希缓存，未变不重复上传）。"""
    from ..services.ai_jobs.resume_sync import sync_resume_to_engine

    return sync_resume_to_engine(db)


@router.get("/engine-jobs/{engine_job_id}/resume/download")
def engine_resume_download(engine_job_id: str):
    """引擎定制简历下载（流式透传，不在简历通落盘）。"""
    import httpx
    from fastapi import Response

    manager = get_sidecar_manager()
    port = manager.read_state().port
    if not port:
        raise HTTPException(status_code=422, detail="sidecar 未运行")
    try:
        upstream = httpx.get(f"http://127.0.0.1:{port}/api/jobs/{engine_job_id}/resume/download", timeout=30.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"引擎下载失败：{exc}") from exc
    if upstream.status_code >= 400:
        raise HTTPException(status_code=upstream.status_code, detail="引擎未提供该岗位的定制简历")
    return Response(
        content=upstream.content,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers={"Content-Disposition": upstream.headers.get("content-disposition", "attachment")},
    )


__all__ = ["router"]
