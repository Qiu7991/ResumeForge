# SPDX-License-Identifier: Apache-2.0
"""招呼语（P2-4）：300 字上限、确认状态、link 快照同步。"""

import pytest
from app.models.ai_job_link import AiJobLink
from app.services.ai_jobs import greeting
from app.services.ai_jobs.greeting import confirm_greeting, save_greeting
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


@pytest.fixture(autouse=True)
def _manager(monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))


def _seed_link(db_session):
    from app.models.job import Job

    job = Job(title="AI 应用工程师", company="示例公司")
    db_session.add(job)
    db_session.flush()
    link = AiJobLink(job_id=job.id, engine_job_id="job-1", greeting="原招呼语", greeting_confirmed=True)
    db_session.add(link)
    db_session.commit()
    return link


def test_save_rejects_empty(db_session):
    with pytest.raises(greeting.TaskGateError) as excinfo:
        save_greeting(db_session, "job-1", "   ")
    assert excinfo.value.status_code == 400


def test_save_rejects_over_300_chars(db_session):
    with pytest.raises(greeting.TaskGateError) as excinfo:
        save_greeting(db_session, "job-1", "好" * 301)
    assert "300" in excinfo.value.message


def test_save_updates_link_and_resets_confirmation(db_session):
    _seed_link(db_session)
    result = save_greeting(db_session, "job-1", "编辑后的招呼语")
    assert result["greeting_confirmed"] is False
    link = db_session.query(AiJobLink).one()
    assert link.greeting == "编辑后的招呼语"
    assert link.greeting_confirmed is False


def test_confirm_marks_link(db_session):
    _seed_link(db_session)
    result = confirm_greeting(db_session, "job-1")
    assert result["greeting_confirmed"] is True
    link = db_session.query(AiJobLink).one()
    assert link.greeting_confirmed is True


def test_read_greeting_from_link(db_session):
    _seed_link(db_session)
    data = greeting.read_greeting(db_session, "job-1")
    assert data["greeting"] == "原招呼语"
    assert data["greeting_confirmed"] is True
    assert data["source"] == "local"


def test_read_greeting_falls_back_to_engine(db_session):
    data = greeting.read_greeting(db_session, "job-9")
    assert data["source"] == "engine"
    assert data["greeting_confirmed"] is False
