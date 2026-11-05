# SPDX-License-Identifier: Apache-2.0
"""AI 求职 × 投递台双向互斥（A4，P1-6 的 2.0 侧收口）。

不依赖真实引擎/浏览器：方向一直接用进程内 TaskRunner；方向二与自愈用
``ai_jobs_fakes`` 的进程内 MockTransport 替身。全部不打开任何网络端口。
"""

from __future__ import annotations

import pytest

from app.services.ai_jobs.gate import (
    ai_jobs_busy,
    ensure_ai_task_can_start,
    set_ai_jobs_busy,
    try_clear_stale_ai_busy,
)
from app.services.apply.task_runner import TaskRunner, TaskRunnerError


def test_apply_start_blocked_by_ai_busy():
    """方向一：AI 求职 busy 时，投递台 start 必须拒绝且未启动任何线程/租约。"""
    runner = TaskRunner()
    set_ai_jobs_busy(True)
    try:
        with pytest.raises(TaskRunnerError) as excinfo:
            runner.start(1)
    finally:
        set_ai_jobs_busy(False)
    assert "AI 求职" in str(excinfo.value)
    # 互斥检查先于租约与线程（TOCTOU 口径）：什么都没启动
    assert runner.is_running() is False


def test_ai_start_blocked_by_apply_running(db_session, monkeypatch):
    """方向二：投递台任务运行中时，AI 任务启动前检查必须给出冲突原因。"""

    class _FakeApplyRunner:
        def is_running(self) -> bool:
            return True

        def current_task_id(self):
            return 7

    from app.services.apply import task_runner as apply_task_runner

    monkeypatch.setattr(apply_task_runner, "get_task_runner", lambda: _FakeApplyRunner())
    reason = ensure_ai_task_can_start(db_session)
    assert reason
    assert "投递" in reason


def test_stale_busy_kept_when_engine_unreachable(monkeypatch, tmp_path):
    """自愈的保守侧：引擎不可达（无端口）时维持 busy，宁误拦不错放。"""
    from tests.ai_jobs_fakes import fake_sidecar_manager

    set_ai_jobs_busy(True)
    try:
        manager = fake_sidecar_manager(tmp_path)
        manager.read_state = lambda dataset_id=None: None  # type: ignore[method-assign,assignment]
        monkeypatch.setattr("app.services.ai_jobs.manager.get_sidecar_manager", lambda: manager)
        assert try_clear_stale_ai_busy() is False
        assert ai_jobs_busy() is True
    finally:
        set_ai_jobs_busy(False)


def test_stale_busy_self_heals_when_engine_idle(monkeypatch, tmp_path):
    """自愈的放行侧：引擎活着且无活动任务（task 终态）→ 清标志放行。"""
    from tests.ai_jobs_fakes import fake_sidecar_manager

    set_ai_jobs_busy(True)
    try:
        manager = fake_sidecar_manager(tmp_path, task={"status": "completed"})
        monkeypatch.setattr("app.services.ai_jobs.manager.get_sidecar_manager", lambda: manager)
        assert try_clear_stale_ai_busy() is True
        assert ai_jobs_busy() is False
    finally:
        set_ai_jobs_busy(False)
