# SPDX-License-Identifier: Apache-2.0
"""采集任务：把「一次同步请求跑完」改成「后台任务 + 可暂停/可停止 + 实时进度」。

为什么要这个
------------
原来的 ``POST /api/job-hunt/collect`` 是同步的：请求进来 → 抓页面 → 返回。
翻 3 页要 15 秒，期间既看不到进度，也停不下来。用户的实际诉求是
「像 BossHunter 那样能暂停、能一眼看到跑到哪」。

设计
----
1. **一线程一任务**：任务在独立线程里跑，HTTP 只负责启动与查询。
2. **暂停靠 Event**：``threading.Event`` 置位=可跑、清除=暂停。检查点在
   :func:`JobHuntRunner.run` 的 ``on_progress`` 里（**每页一次**），所以暂停粒度是
   「页」——单次 CDP 调用中途停不下来，这一点与参考实现一致。
3. **状态快照**：``progress`` 记录当前页/已采条数/总条数，前端轮询这个快照。
4. **进程内单例**：同一时刻只允许一个采集任务（``threading.Lock`` + 活跃任务检查），
   避免两个任务同时驱动同一个浏览器。
5. **不持久化**：进程重启后任务丢失是**预期**的——这类任务的生命周期就是几分钟，
   持久化反而要处理"重启后任务状态不明"的麻烦。
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 任务状态（与前端流程条的取值一致）。
TASK_RUNNING = "running"
TASK_PAUSED = "paused"
TASK_COMPLETED = "completed"
TASK_STOPPED = "stopped"
TASK_FAILED = "failed"
TERMINAL = {TASK_COMPLETED, TASK_STOPPED, TASK_FAILED}


@dataclass
class CollectTask:
    """一次采集任务的运行状态与结果。"""

    task_id: str
    site_key: str
    keywords: str = ""
    city: str = ""
    max_pages: int = 1
    status: str = TASK_RUNNING
    # 进度：当前页 / 已采条数 / 目标页数。
    current_page: int = 0
    collected: int = 0
    message: str = ""
    error: str = ""
    # 结果（任务完成后填充）。
    stubs: list[dict[str, Any]] = field(default_factory=list)
    blocked: int = 0
    stopped_reason: str = ""
    # 控制信号：置位=运行，清除=暂停。
    _resume: threading.Event = field(default_factory=threading.Event, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)

    def __post_init__(self) -> None:
        self._resume.set()

    def snapshot(self) -> dict[str, Any]:
        """给前端的只读快照（不含 Event 这类不可序列化对象）。"""
        return {
            "task_id": self.task_id,
            "site_key": self.site_key,
            "keywords": self.keywords,
            "city": self.city,
            "max_pages": self.max_pages,
            "status": self.status,
            "current_page": self.current_page,
            "collected": self.collected,
            "message": self.message,
            "error": self.error,
            "blocked": self.blocked,
            "stopped_reason": self.stopped_reason,
            # 只给条数，不把整批 stubs 塞进轮询响应（15 条 × 每次轮询会很吵）。
            "stub_count": len(self.stubs),
            "finished": self.status in TERMINAL,
        }

    def full_result(self) -> dict[str, Any]:
        """任务完成后取完整结果（含 stubs）。"""
        return {**self.snapshot(), "stubs": list(self.stubs)}


class CollectTaskManager:
    """进程内采集任务表（单例）。"""

    def __init__(self) -> None:
        self._tasks: dict[str, CollectTask] = {}
        self._lock = threading.Lock()

    # -- 查询 ---------------------------------------------------------------

    def get(self, task_id: str) -> CollectTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def active(self) -> CollectTask | None:
        """当前未结束的任务（有就说明不能开新的）。"""
        with self._lock:
            for task in self._tasks.values():
                if task.status not in TERMINAL:
                    return task
        return None

    def prune(self, keep: int = 20) -> None:
        """只留最近 N 个任务，避免长跑进程里字典无限增长。"""
        with self._lock:
            if len(self._tasks) <= keep:
                return
            finished = [t for t in self._tasks.values() if t.status in TERMINAL]
            for task in finished[: max(0, len(self._tasks) - keep)]:
                self._tasks.pop(task.task_id, None)

    # -- 控制 ---------------------------------------------------------------

    def pause(self, task_id: str) -> CollectTask | None:
        task = self.get(task_id)
        if task is None or task.status in TERMINAL:
            return task
        task._resume.clear()
        task.status = TASK_PAUSED
        task.message = "已暂停（当前页跑完后停下）"
        return task

    def resume(self, task_id: str) -> CollectTask | None:
        task = self.get(task_id)
        if task is None or task.status in TERMINAL:
            return task
        task._resume.set()
        task.status = TASK_RUNNING
        task.message = "已继续"
        return task

    def stop(self, task_id: str) -> CollectTask | None:
        task = self.get(task_id)
        if task is None or task.status in TERMINAL:
            return task
        task._stop.set()
        # 停止要能立刻生效：同时放开暂停，让工作线程走到检查点看到 stop。
        task._resume.set()
        task.message = "正在停止…"
        return task

    # -- 启动 ---------------------------------------------------------------

    def start(
        self,
        *,
        site_key: str,
        keywords: str,
        city: str,
        max_pages: int,
        worker: Callable[[CollectTask], None],
    ) -> CollectTask:
        """建任务并在后台线程里跑 ``worker(task)``。

        ``worker`` 里应该周期性检查 ``task._stop`` / 等待 ``task._resume``——
        具体检查点由调用方（API 层）通过 ``on_progress`` 注入。
        """
        with self._lock:
            task = CollectTask(
                task_id=uuid.uuid4().hex,
                site_key=site_key,
                keywords=keywords,
                city=city,
                max_pages=max_pages,
            )
            self._tasks[task.task_id] = task
        threading.Thread(target=worker, args=(task,), daemon=True).start()
        self.prune()
        return task


_manager: CollectTaskManager | None = None


def get_collect_manager() -> CollectTaskManager:
    global _manager
    if _manager is None:
        _manager = CollectTaskManager()
    return _manager


def control_hook(task: CollectTask) -> Callable[[int, int, int], bool]:
    """把任务的暂停/停止信号包成 ``runner.run(on_progress=...)`` 要的回调。

    返回 ``True`` = 继续翻页，``False`` = 停。
    暂停就是在这里**阻塞等待** ``_resume`` 置位——这样暂停期间不消耗任何抓取动作，
    恢复后从下一页继续。
    """

    def _mark_stopped() -> None:
        """停止要从钩子里就把状态落定。

        为什么不在 worker 的返回路径统一处理：暂停中的线程是被这个钩子"叫停"的，
        从钩子返回 False 后 runner 就走 ``stopped`` 分支返回；而 worker 里对
        ``stopped_reason`` 的判定发生在**之后**——如果钩子途中抛了异常（底层 fetch
        被中断），worker 会进 except 分支。两边都写一遍状态，才不会出现
        「用户点了停止、界面还停在暂停」这种自相矛盾的结果。
        """
        task.stopped_reason = "stopped"
        task.status = TASK_STOPPED
        task.message = f"已停止（已采 {task.collected} 条）"

    def hook(page: int, new_count: int, total: int) -> bool:
        task.current_page = page
        task.collected = total
        if task._stop.is_set():
            _mark_stopped()
            return False
        if not task._resume.is_set():
            task.message = f"已暂停（第 {page} 页已完成，共 {total} 条）"
            # 阻塞等恢复或停止（0.2s 轮询，响应停止信号更快）。
            while not task._resume.wait(timeout=0.2):
                if task._stop.is_set():
                    _mark_stopped()
                    return False
            task.message = "已继续"
        task.message = f"已完成第 {page} 页，累计 {total} 条"
        return True

    return hook


__all__ = [
    "TASK_RUNNING",
    "TASK_PAUSED",
    "TASK_COMPLETED",
    "TASK_STOPPED",
    "TASK_FAILED",
    "TERMINAL",
    "CollectTask",
    "CollectTaskManager",
    "get_collect_manager",
    "control_hook",
]
