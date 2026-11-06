# SPDX-License-Identifier: Apache-2.0
"""人工确认投递门（P1-4）：待确认列表、确认投递、拒绝。

**红线**：``deliver`` 绝不因任务完成自动调用；必须 ``confirm=True`` + 非空
``job_ids`` + 岗位在**当前待确认列表**里。后端校验后仍由引擎做最终状态校验
（重复发送/缺招呼语由引擎 409 拒绝）。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy.orm import Session

from ...schemas.ai_jobs import AiJobsConfig
from .client import SidecarError
from .gate import apply_busy, webform_busy
from .manager import SidecarManager, get_sidecar_manager
from .settings import get_ai_jobs_config
from .tasks import TaskGateError, _require_sidecar

logger = logging.getLogger(__name__)

# 发送总闸（2.0 默认关，与 1.x 的「=0 才拒」语义相反）：仅当环境变量
# AI_JOBS_ALLOW_SEND 显式为真值时才允许把岗位送进 /api/workbench/deliver。
# 定义在服务层、检查在 API 层（api/ai_jobs.py 的 deliver 端点先挡 403）：
# 1.x 的服务级测试直调 deliver() 验证确认门 400/409，不能被环境闸拦截（E4）。
# 这是不可逆对外动作的唯一入口；晨间人工验收需要真实发送时由用户显式打开。
_SEND_ENV_VAR = "AI_JOBS_ALLOW_SEND"
_SEND_ENV_TRUTHY = ("1", "true", "yes", "on")


def send_gate_open() -> bool:
    """发送总闸当前是否打开（默认关：未设置或非真值一律 False）。"""
    return os.environ.get(_SEND_ENV_VAR, "").strip().lower() in _SEND_ENV_TRUTHY


def workbench_snapshot(
    db: Session, config: AiJobsConfig | None = None, manager: SidecarManager | None = None
) -> dict[str, Any]:
    """取引擎工作台聚合状态（含待确认/配额/任务），供确认门与页面共用。"""
    from .tasks import get_workbench_state

    return get_workbench_state(config or get_ai_jobs_config(db), manager)


def pending_confirmation_ids(state: dict[str, Any]) -> set[str]:
    """当前待确认岗位 id 集合（引擎已按阈值与平台能力过滤）。"""
    return {str(job.get("id")) for job in state.get("pending_confirmation") or [] if job.get("id")}


def deliver(db: Session, job_ids: list[str], confirm: bool) -> dict[str, Any]:
    """人工确认后投递选中岗位；返回引擎响应（任务快照或排队回执）。

    **发送总闸在 API 层**（``api/ai_jobs.py`` 调 ``send_gate_open``，2.0 默认关）：
    与 1.x 的层级一致——服务层保持纯确认门（``confirm=True`` + 待确认列表校验），
    因为 1.x 的服务级测试直调本函数验证 400/409 语义，不能被环境闸拦截（E4）。
    """
    if not confirm:
        raise TaskGateError("缺少确认：投递前必须二次确认", 400)
    if not job_ids or not all(isinstance(j, str) and j.strip() for j in job_ids):
        raise TaskGateError("请选择要投递的岗位", 400)
    if apply_busy(db):
        raise TaskGateError("已有投递任务在运行，请等它结束或停止后再确认投递", 409)
    if webform_busy():
        raise TaskGateError("网申填表正在进行，请等它结束后再确认投递", 409)
    config = get_ai_jobs_config(db)
    manager = get_sidecar_manager()
    client, _port = _require_sidecar(config, manager)
    state = client.get("/api/workbench")
    allowed = pending_confirmation_ids(state if isinstance(state, dict) else {})
    outside = [job_id for job_id in job_ids if job_id not in allowed]
    if outside:
        raise TaskGateError(f"所选岗位不在当前待确认列表里：{', '.join(outside)}", 400)
    try:
        result = client.post("/api/workbench/deliver", {"job_ids": job_ids})
    except SidecarError as exc:
        # 引擎的 403/409（重复发送/缺招呼语/平台不支持）原样透传给前端。
        raise TaskGateError(exc.message, 409 if exc.code == "http_error" else 422) from exc
    logger.info("AI 求职确认投递 ids=%s", ",".join(job_ids))
    return result if isinstance(result, dict) else {}


def reject(db: Session, job_ids: list[str]) -> dict[str, Any]:
    """拒绝选中岗位（引擎侧标记 rejected；不改简历通岗位状态）。"""
    if not job_ids or not all(isinstance(j, str) and j.strip() for j in job_ids):
        raise TaskGateError("请选择要拒绝的岗位", 400)
    config = get_ai_jobs_config(db)
    manager = get_sidecar_manager()
    client, _port = _require_sidecar(config, manager)
    try:
        result = client.post("/api/workbench/reject", {"job_ids": job_ids})
    except SidecarError as exc:
        raise TaskGateError(exc.message, 409 if exc.code == "http_error" else 422) from exc
    return result if isinstance(result, dict) else {}


__all__ = ["deliver", "pending_confirmation_ids", "reject", "workbench_snapshot"]
