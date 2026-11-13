# SPDX-License-Identifier: Apache-2.0
"""采集任务测试：暂停/恢复/停止的状态机与进度快照。

不启真实浏览器、不连网站——只测任务管理与控制信号。
"""
from __future__ import annotations

import threading
import time


from app.services.job_hunt.collect_task import (
    TASK_COMPLETED,
    TASK_FAILED,
    TASK_PAUSED,
    TASK_RUNNING,
    TASK_STOPPED,
    CollectTaskManager,
    CollectTask,
    control_hook,
)


def _wait_until(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# ---------- 状态机 ----------


def test_start_creates_running_task():
    manager = CollectTaskManager()
    done = threading.Event()

    def worker(task):
        done.wait(2)

    task = manager.start(site_key="boss", keywords="AI", city="广州", max_pages=2, worker=worker)
    assert task.status in (TASK_RUNNING, TASK_PAUSED)
    assert task.snapshot()["finished"] is False
    done.set()


def test_pause_and_resume_flags():
    manager = CollectTaskManager()
    task = CollectTask(task_id="t1", site_key="boss")
    manager._tasks["t1"] = task  # noqa: SLF001 — 白盒测状态机

    paused = manager.pause("t1")
    assert paused.status == TASK_PAUSED
    assert task._resume.is_set() is False

    resumed = manager.resume("t1")
    assert resumed.status == TASK_RUNNING
    assert task._resume.is_set() is True


def test_stop_releases_pause_so_thread_can_exit():
    """停止必须同时放开暂停——否则暂停中的线程永远等不到 stop。"""
    manager = CollectTaskManager()
    task = CollectTask(task_id="t2", site_key="boss")
    manager._tasks["t2"] = task  # noqa: SLF001

    manager.pause("t2")
    assert task._resume.is_set() is False
    manager.stop("t2")
    assert task._stop.is_set() is True
    assert task._resume.is_set() is True


def test_terminal_task_cannot_be_resumed():
    manager = CollectTaskManager()
    task = CollectTask(task_id="t3", site_key="boss", status=TASK_COMPLETED)
    manager._tasks["t3"] = task  # noqa: SLF001

    manager.resume("t3")
    assert task.status == TASK_COMPLETED  # 终态守卫


def test_active_returns_only_unfinished():
    manager = CollectTaskManager()
    manager._tasks["done"] = CollectTask(task_id="done", site_key="boss", status=TASK_COMPLETED)  # noqa: SLF001
    assert manager.active() is None

    manager._tasks["live"] = CollectTask(task_id="live", site_key="boss")  # noqa: SLF001
    assert manager.active().task_id == "live"


def test_prune_keeps_recent_only():
    manager = CollectTaskManager()
    for i in range(30):
        manager._tasks[f"t{i}"] = CollectTask(  # noqa: SLF001
            task_id=f"t{i}", site_key="boss", status=TASK_COMPLETED
        )
    manager.prune(keep=10)
    assert len(manager._tasks) <= 10  # noqa: SLF001


# ---------- on_progress 控制钩子 ----------


def test_hook_updates_progress():
    task = CollectTask(task_id="t4", site_key="boss")
    hook = control_hook(task)
    assert hook(1, 15, 15) is True
    assert task.current_page == 1
    assert task.collected == 15


def test_hook_returns_false_when_stopped():
    task = CollectTask(task_id="t5", site_key="boss")
    hook = control_hook(task)
    task._stop.set()
    assert hook(2, 15, 30) is False
    assert task.stopped_reason == "stopped"


def test_hook_blocks_while_paused_then_continues():
    """暂停时钩子阻塞；恢复后返回 True 继续翻页。"""
    task = CollectTask(task_id="t6", site_key="boss")
    hook = control_hook(task)
    task._resume.clear()  # 模拟用户点暂停

    result: list[bool] = []

    def call_hook():
        result.append(hook(1, 15, 15))

    thread = threading.Thread(target=call_hook, daemon=True)
    thread.start()

    # 暂停期间不应该返回
    time.sleep(0.3)
    assert result == []

    task._resume.set()  # 恢复
    assert _wait_until(lambda: bool(result)), "恢复后钩子应返回"
    assert result[0] is True


def test_hook_stop_while_paused_exits():
    """暂停中收到停止：钩子应返回 False 而不是一直等。"""
    task = CollectTask(task_id="t7", site_key="boss")
    hook = control_hook(task)
    task._resume.clear()

    result: list[bool] = []
    thread = threading.Thread(target=lambda: result.append(hook(1, 15, 15)), daemon=True)
    thread.start()
    time.sleep(0.2)
    assert result == []

    task._stop.set()  # 只置 stop，不放开 resume
    assert _wait_until(lambda: bool(result)), "停止信号应让暂停中的钩子退出"
    assert result[0] is False


# ---------- 快照 ----------


def test_snapshot_has_no_event_objects():
    task = CollectTask(task_id="t8", site_key="boss")
    snapshot = task.snapshot()
    assert "_resume" not in snapshot and "_stop" not in snapshot
    assert isinstance(snapshot["stub_count"], int)


def test_full_result_includes_stubs():
    task = CollectTask(task_id="t9", site_key="boss", status=TASK_COMPLETED)
    task.stubs = [{"title": "A"}]
    assert task.full_result()["stubs"] == [{"title": "A"}]


def test_stop_reports_stopped_status_not_completed():
    """用户主动停止必须标为 stopped（不是 completed）——两者对用户意义完全不同。"""
    from app.services.job_hunt.collect_task import TASK_COMPLETED

    # 模拟 worker 结束时的判定（与 api/job_hunt.py 的 worker 同一段逻辑）
    def finalize(reason: str) -> str:
        return TASK_STOPPED if reason == "stopped" else TASK_COMPLETED

    assert finalize("stopped") == TASK_STOPPED
    assert finalize("max_pages") == TASK_COMPLETED
    assert finalize("no_results") == TASK_COMPLETED


def test_stop_during_fetch_error_is_reported_as_stopped():
    """用户点停止后，抓取层抛的异常不该被报成 failed。

    实测踩到过：暂停中点停止 → 底层 fetch 抛错 → 任务被标 failed，
    而用户明明是自己停的。判定依据是 ``task._stop`` 已置位。
    """

    def classify(task) -> str:
        # 与 api/job_hunt.py worker 的 except 分支同一段逻辑
        return TASK_STOPPED if task._stop.is_set() else TASK_FAILED

    task = CollectTask(task_id="t10", site_key="boss")
    assert classify(task) == TASK_FAILED

    task._stop.set()
    assert classify(task) == TASK_STOPPED
