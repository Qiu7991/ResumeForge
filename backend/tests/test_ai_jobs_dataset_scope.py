# SPDX-License-Identifier: Apache-2.0
"""数据集隔离（P3-4）：runtime 目录按数据集分开；任务持租约期间目录互不串写。"""

from app.services.ai_jobs import tasks
from app.services.ai_jobs.gate import set_ai_jobs_busy
from app.services.ai_jobs.manager import SidecarManager


def test_runtime_dir_is_per_dataset(tmp_path):
    manager = SidecarManager(runtime_root=tmp_path)
    dir_a = manager.runtime_dir("dataset-a")
    dir_b = manager.runtime_dir("dataset-b")
    assert dir_a != dir_b
    assert dir_a.parent.parent == tmp_path


def test_lease_held_between_start_and_terminal(db_session, monkeypatch, tmp_path):
    """任务启动取租约；轮询到终态即放掉。"""
    from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager

    manager = fake_sidecar_manager(tmp_path)
    patch_manager(monkeypatch, manager)
    assert tasks.dataset_lease_held() is False
    tasks.start_task(db_session, "collect", confirm=True)
    assert tasks.dataset_lease_held() is True
    set_ai_jobs_busy(True)  # 保持 busy，验证租约由终态释放而非 busy 标志
    # 引擎侧任务已终态（fake 返回 completed）
    manager_with_terminal = fake_sidecar_manager(tmp_path, task={"id": "t", "status": "completed"})
    patch_manager(monkeypatch, manager_with_terminal)
    tasks.get_workbench_state(tasks.get_ai_jobs_config(db_session))
    assert tasks.dataset_lease_held() is False
