# SPDX-License-Identifier: Apache-2.0
"""确认投递门（P1-4）与发送结果写回（P1-5）：二次确认、白名单、幂等写回。"""

import pytest
from app.models.tracker import ApplicationTrack
from app.services.ai_jobs import delivery
from app.services.ai_jobs.delivery_sync import sync_sent_to_tracker
from app.services.ai_jobs.gate import set_ai_jobs_busy
from app.services.tracker_merge import normalize_key
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


@pytest.fixture(autouse=True)
def _reset_busy():
    set_ai_jobs_busy(False)
    yield
    set_ai_jobs_busy(False)


def test_deliver_requires_confirm(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    with pytest.raises(delivery.TaskGateError) as excinfo:
        delivery.deliver(db_session, ["job-1"], confirm=False)
    assert excinfo.value.status_code == 400


def test_deliver_requires_job_ids(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    with pytest.raises(delivery.TaskGateError) as excinfo:
        delivery.deliver(db_session, [], confirm=True)
    assert "选择" in excinfo.value.message


def test_deliver_rejects_ids_outside_confirmation(db_session, monkeypatch, tmp_path):
    """不在当前待确认列表里的岗位直接拒绝（人工确认门的硬约束）。"""
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    with pytest.raises(delivery.TaskGateError) as excinfo:
        delivery.deliver(db_session, ["job-999"], confirm=True)
    assert excinfo.value.status_code == 400
    assert "job-999" in excinfo.value.message


def test_deliver_blocked_while_apply_running(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    monkeypatch.setattr("app.services.ai_jobs.delivery.apply_busy", lambda db: True)
    with pytest.raises(delivery.TaskGateError) as excinfo:
        delivery.deliver(db_session, ["job-1"], confirm=True)
    assert excinfo.value.status_code == 409


def test_deliver_engine_409_passthrough(db_session, monkeypatch, tmp_path):
    """引擎的重复发送/未就绪 409 原样透传给前端。"""
    manager = fake_sidecar_manager(
        tmp_path,
        errors={"/api/workbench/deliver": (409, {"error": "所选岗位已经投递，不能重复发送"})},
    )
    patch_manager(monkeypatch, manager)
    with pytest.raises(delivery.TaskGateError) as excinfo:
        delivery.deliver(db_session, ["job-1"], confirm=True)
    assert excinfo.value.status_code == 409
    assert "不能重复发送" in excinfo.value.message


def test_deliver_success_returns_task(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    result = delivery.deliver(db_session, ["job-1"], confirm=True)
    assert result.get("mode") == "deliver"


def test_reject_passthrough(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    result = delivery.reject(db_session, ["job-1"])
    assert result == {"rejected": ["job-1"]}


# ===== P1-5：tracker 写回 =====


def test_sync_writes_track_with_ai_jobs_source(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    written = sync_sent_to_tracker(db_session)
    assert written == 1
    row = db_session.query(ApplicationTrack).one()
    assert row.source == "ai_jobs"
    assert row.company == "示例公司"
    assert row.status == "applied"


def test_sync_is_idempotent(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    assert sync_sent_to_tracker(db_session) == 1
    assert sync_sent_to_tracker(db_session) == 0  # 重放不新建
    assert db_session.query(ApplicationTrack).count() == 1


def test_sync_ignores_non_delivered_statuses(db_session, monkeypatch, tmp_path):
    jobs = {"jobs": [{"id": "job-2", "title": "后端工程师", "company": "另一家", "status": "scored"}], "total": 1}
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path, jobs=jobs))
    assert sync_sent_to_tracker(db_session) == 0
    assert db_session.query(ApplicationTrack).count() == 0


def test_sync_keeps_later_status(db_session, monkeypatch, tmp_path):
    """已有更靠后状态（面试）的记录不被拉回「已投递」。"""
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    # 合并键是归一化列（uq_application_track_company_title），直插时必须带上。
    db_session.add(
        ApplicationTrack(
            company="示例公司",
            title="AI 应用工程师",
            company_key=normalize_key("示例公司"),
            title_key=normalize_key("AI 应用工程师"),
            status="interview",
            source="manual",
        )
    )
    db_session.commit()
    assert sync_sent_to_tracker(db_session) == 0
    row = db_session.query(ApplicationTrack).one()
    assert row.status == "interview"


def test_sync_without_sidecar_is_noop(db_session, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    manager.read_state = lambda dataset_id=None: type("S", (), {"port": 0})()  # type: ignore[assignment]
    patch_manager(monkeypatch, manager)
    assert sync_sent_to_tracker(db_session) == 0
