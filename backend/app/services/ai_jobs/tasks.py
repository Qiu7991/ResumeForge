# SPDX-License-Identifier: Apache-2.0
"""AI 求职任务：启动/当前/停止（P1-2）。

**确认门**：启动任务必须 ``confirm=True``（HTTP 层再兜一道）；这只是"用户真的点了
开始"，不是发送授权——发送还有独立的人工确认门（P1-4）。
**模式白名单**：full/collect/monitor；deliver 永远不走这里（走 /deliver）。
**状态映射**：引擎状态 → 前端状态只在本模块做一次（§7.4），前端不散落 if/else。
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from sqlalchemy.orm import Session

from ...schemas.ai_jobs import AiJobsConfig
from .client import SidecarClient, SidecarError
from .gate import ensure_ai_task_can_start, set_ai_jobs_busy
from .manager import SidecarManager, get_sidecar_manager
from .settings import get_ai_jobs_config

logger = logging.getLogger(__name__)

MODES = ("full", "collect", "monitor")

# 引擎终态（BossHunter web/tasks.py TERMINAL_STATUSES）。
_ENGINE_TERMINAL = {"completed", "failed", "stopped"}


# 长任务租约（P3-4）：数据集切换期间 acquire_lease 直接失败；持租约期间切换会
# 排空等待，保证 sidecar 的岗位数据不写进另一个数据集。
_current_lease = None
_lease_lock = threading.Lock()


def _acquire_dataset_lease() -> None:
    from ...runtime.dataset_scope import acquire_lease

    global _current_lease
    with _lease_lock:
        lease = acquire_lease("ai-jobs")
        _current_lease = lease


def _release_dataset_lease() -> None:
    global _current_lease
    with _lease_lock:
        if _current_lease is not None:
            _current_lease.release()
            _current_lease = None


def dataset_lease_held() -> bool:
    with _lease_lock:
        return _current_lease is not None


class TaskGateError(Exception):
    """启动前置条件不满足（互斥/未确认/非法模式），HTTP 层映射 400/409。"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_task_status(engine_status: str | None) -> str:
    """引擎任务状态 → 前端 ``AiJobTaskStatus``。未知值按 running 处理（不丢轮询）。"""
    status = (engine_status or "").strip()
    if status in {"running", "stopping", "completed", "failed", "stopped", "waiting_confirmation", "paused"}:
        return status
    return "running"


def is_terminal(snapshot: dict[str, Any]) -> bool:
    return (snapshot or {}).get("status") in _ENGINE_TERMINAL


def _require_sidecar(config: AiJobsConfig, manager: SidecarManager) -> tuple[SidecarClient, int]:
    # 复用与自有进程统一走磁盘状态里的端口（start 时已写回实际端口）。
    port = manager.read_state().port
    if not port:
        raise TaskGateError("sidecar 未运行：请先启动引擎", 422)
    client = manager.client_for(port)
    health = client.health()
    if not health.reachable:
        raise TaskGateError("sidecar 未运行：请先启动引擎", 422)
    if not health.version_ok:
        raise TaskGateError(health.reason, 422)
    return client, port


def start_task(db: Session, mode: str, confirm: bool) -> dict[str, Any]:
    """启动一次 full/collect/monitor 任务，返回引擎任务快照。"""
    if not confirm:
        raise TaskGateError("缺少确认：启动 AI 求职任务必须显式确认", 400)
    if mode not in MODES:
        raise TaskGateError(f"不支持的任务模式：{mode}（可用：{'/'.join(MODES)}）", 400)
    conflict = ensure_ai_task_can_start(db)
    if conflict:
        raise TaskGateError(conflict, 409)
    try:
        _acquire_dataset_lease()
    except Exception as exc:  # noqa: BLE001 - DatasetScopeError → 409 语义
        raise TaskGateError(str(exc), 409) from exc
    config = get_ai_jobs_config(db)
    manager = get_sidecar_manager()
    client, _port = _require_sidecar(config, manager)
    try:
        snapshot = client.post("/api/workbench/task", {"mode": mode})
    except SidecarError as exc:
        if exc.code == "http_error" and "409" in str(exc):
            raise TaskGateError(exc.message, 409) from exc
        raise TaskGateError(exc.message, 422) from exc
    if not isinstance(snapshot, dict) or "id" not in snapshot:
        raise TaskGateError("sidecar 返回了无法识别的任务快照", 422)
    set_ai_jobs_busy(True)
    logger.info("AI 任务已启动 mode=%s task=%s", mode, snapshot.get("id"))
    return snapshot


# F4：上一次观察到的任务活动态；active→终态的边沿触发一次 tracker 同步
# （deliver 后引擎低频发送要几分钟，deliver 时点的那次同步基本同步不到）。
_last_task_active: bool | None = None


def get_workbench_state(config: AiJobsConfig, manager: SidecarManager | None = None) -> dict[str, Any]:
    """透传 sidecar ``GET /api/workbench``（含当前任务、待确认、配额、漏斗）。"""
    global _last_task_active
    mgr = manager or get_sidecar_manager()
    client, _port = _require_sidecar(config, mgr)
    state = client.get("/api/workbench")
    if not isinstance(state, dict):
        raise TaskGateError("sidecar 返回了无法识别的工作台状态", 422)
    _sync_busy_flag(state)
    task = state.get("task")
    now_active = bool(task) and not is_terminal(task if isinstance(task, dict) else {})
    if _last_task_active and not now_active:
        # 边沿：任务刚结束 → 把引擎侧已发送岗位写回求职进度（幂等，失败不抛）。
        try:
            from sqlalchemy.orm import Session as _Session  # noqa: F401 - 仅类型提示用

            # 此处没有请求会话：同步需要一个 db。惰性自建一个短会话（引擎权威数据，
            # 写的是 application_track，与请求会话无关）。
            from ...database import SessionLocal
            from .delivery_sync import sync_sent_to_tracker as _sync

            db = SessionLocal()
            try:
                _sync(db)
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001 - 同步失败不影响状态返回
            logger.info("终态边沿 tracker 同步失败（下次边沿重试）：%s", exc)
    _last_task_active = now_active
    return state


def _sync_busy_flag(state: dict[str, Any]) -> None:
    """引擎侧任务已到终态/消失时，把进程内互斥标志与数据集租约放掉（轮询自愈）。"""
    task = state.get("task")
    active = bool(task) and not is_terminal(task if isinstance(task, dict) else {})
    if not active:
        set_ai_jobs_busy(False)
        _release_dataset_lease()


def stop_task(task_id: str) -> dict[str, Any]:
    """停止任务（幂等：引擎对终态任务直接回快照）。终态后放掉互斥标志。"""
    manager = get_sidecar_manager()
    config_port = manager.read_state().port
    if not config_port:
        raise TaskGateError("sidecar 未运行：无任务可停止", 422)
    client = manager.client_for(config_port)
    snapshot = client.post(f"/api/workbench/task/{task_id}/stop", {})
    if is_terminal(snapshot):
        set_ai_jobs_busy(False)
        _release_dataset_lease()
    return snapshot


__all__ = [
    "MODES",
    "dataset_lease_held",
    "TaskGateError",
    "get_workbench_state",
    "is_terminal",
    "normalize_task_status",
    "start_task",
    "stop_task",
]
