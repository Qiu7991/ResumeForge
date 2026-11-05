# SPDX-License-Identifier: Apache-2.0
"""AI 求职与旧投递台/网申填表的互斥门（P1-6）。

同一时间只允许一个自动化任务占用浏览器：AI 全流程、旧投递台
（apply/collect/backfill 三入口都经 ``TaskRunner.start``）、网申填表互斥。
冲突一律 409，文案写明"谁在跑"。

实现：进程内 ``threading.Lock`` 保护的状态标志（``_AI_BUSY``）+ 对既有运行态的
查询（``TaskRunner.is_running`` / ``webform`` ``is_filling``）。旧投递台一侧的
检查加在 ``TaskRunner.start`` 锁内（覆盖最全），见该文件的 ai_jobs 检查段。
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session

_lock = threading.Lock()
_ai_busy = False

logger = logging.getLogger(__name__)


def ai_jobs_busy() -> bool:
    """当前是否有 AI 求职任务在跑（进程内标志）。"""
    with _lock:
        return _ai_busy


def set_ai_jobs_busy(busy: bool) -> None:
    """AI 任务生命周期两端调用：启动置 True、终态置 False。"""
    global _ai_busy
    with _lock:
        _ai_busy = busy


def apply_busy(db: Session) -> bool:
    """旧投递台是否有任务在跑（不启动任何东西，纯查询）。"""
    from ..apply.task_runner import get_task_runner

    runner = get_task_runner()
    return runner.is_running() or runner.current_task_id() is not None


def webform_busy() -> bool:
    from ..webform.service.fill import is_filling

    return is_filling()


def ensure_ai_task_can_start(db: Session) -> str:
    """AI 任务启动前的互斥检查；冲突返回原因文案，空闲返回空串。"""
    if not try_clear_stale_ai_busy():
        return "已有 AI 求职任务在运行"
    if apply_busy(db):
        return "已有投递任务在运行，请等它结束或停止后再启动 AI 求职"
    if webform_busy():
        return "网申填表正在进行，请等它结束后再启动 AI 求职"
    return ""


def try_clear_stale_ai_busy() -> bool:
    """busy 标志可能因"任务自己跑完、无人打开页面轮询"而滞留（F3）。

    在冲突点上做一次**有界**核查（健康 2s 超时）：引擎活着且没有活动任务 →
    放掉标志与数据集租约并返回 True（调用方可继续启动）；引擎不可达或仍有
    任务 → 维持 busy（保守，宁误拦不错放）。
    """
    if not ai_jobs_busy():
        return True
    try:
        from .manager import get_sidecar_manager

        mgr = get_sidecar_manager()
        port = mgr.read_state().port
        if not port:
            return False
        client = mgr.client_for(port)
        health = client.health()
        if not (health.reachable and health.version_ok):
            return False
        state = client.get("/api/workbench")
        task = (state or {}).get("task") if isinstance(state, dict) else None
        if task:
            return False
        # 引擎侧确认空闲：自愈。
        set_ai_jobs_busy(False)
        from .tasks import _release_dataset_lease

        _release_dataset_lease()
        logger.info("检测到 AI 任务已结束（无人轮询），互斥标志已自愈放行")
        return True
    except Exception:  # noqa: BLE001 - 探测失败维持 busy，保守不误放
        logger.warning("AI 互斥自愈探测失败，维持 busy", exc_info=True)
        return False


__all__ = [
    "ai_jobs_busy",
    "try_clear_stale_ai_busy",
    "apply_busy",
    "ensure_ai_task_can_start",
    "set_ai_jobs_busy",
    "webform_busy",
]
