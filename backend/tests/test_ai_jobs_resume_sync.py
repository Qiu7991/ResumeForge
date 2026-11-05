# SPDX-License-Identifier: Apache-2.0
"""简历同步（P2-5）：通用简历筛选口径、DOCX 导出、哈希缓存不重复上传。"""

import httpx
from app.models.resume import ResumeRecord
from app.services.ai_jobs.resume_sync import (
    export_general_resume_docx,
    get_general_resume_record,
    sync_resume_to_engine,
)
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


def test_get_general_resume_excludes_job_bound_and_drafts(db_session):
    from app.models.job import Job

    job = Job(title="岗位", company="公司")
    db_session.add(job)
    db_session.flush()
    db_session.add(ResumeRecord(title="岗位简历", job_id=job.id, draft=False))
    db_session.add(ResumeRecord(title="草稿", draft=True))
    db_session.add(ResumeRecord(title="通用简历", draft=False, favorite=False))
    db_session.commit()
    record = get_general_resume_record(db_session)
    assert record is not None
    assert record.title == "通用简历"


def test_get_general_resume_prefers_favorite(db_session):
    db_session.add(ResumeRecord(title="普通", draft=False))
    db_session.add(ResumeRecord(title="收藏", draft=False, favorite=True))
    db_session.commit()
    assert get_general_resume_record(db_session).title == "收藏"


def test_export_produces_docx_bytes(db_session):
    db_session.add(ResumeRecord(title="通用简历", draft=False, content={"blocks": []}))
    db_session.commit()
    record = get_general_resume_record(db_session)
    content = export_general_resume_docx(db_session, record)
    assert content[:2] == b"PK"  # DOCX 是 zip 容器


def test_sync_skips_when_content_unchanged(db_session, monkeypatch, tmp_path):
    """哈希缓存：内容没变不重复上传（第二次 uploaded=False）。"""
    uploads: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/resume/upload":
            uploads.append(request.read())
            return httpx.Response(200, json={"success": True})
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "version": "2.4.1"})
        return httpx.Response(404, json={"error": "unknown"})

    manager = fake_sidecar_manager(tmp_path)
    manager.client_for = lambda port: __import__(
        "app.services.ai_jobs.client", fromlist=["SidecarClient"]
    ).SidecarClient("http://127.0.0.1:8687", transport=httpx.MockTransport(handler))  # type: ignore[method-assign]
    patch_manager(monkeypatch, manager)
    db_session.add(ResumeRecord(title="通用简历", draft=False, content={"blocks": []}))
    db_session.commit()

    first = sync_resume_to_engine(db_session, manager=manager)
    assert first["uploaded"] is True
    assert len(uploads) == 1
    second = sync_resume_to_engine(db_session, manager=manager)
    assert second["uploaded"] is False
    assert second["reason"] == "简历未变化"
    forced = sync_resume_to_engine(db_session, manager=manager, force=True)
    assert forced["uploaded"] is True


def test_sync_without_general_resume_is_noop(db_session, monkeypatch, tmp_path):
    patch_manager(monkeypatch, fake_sidecar_manager(tmp_path))
    result = sync_resume_to_engine(db_session)
    assert result["uploaded"] is False
    assert "通用简历" in result["reason"]


def test_sync_without_sidecar_is_noop(db_session, monkeypatch, tmp_path):
    manager = fake_sidecar_manager(tmp_path)
    manager.read_state = lambda dataset_id=None: type("S", (), {"port": 0})()  # type: ignore[assignment]
    patch_manager(monkeypatch, manager)
    db_session.add(ResumeRecord(title="通用简历", draft=False))
    db_session.commit()
    result = sync_resume_to_engine(db_session, manager=manager)
    assert result["uploaded"] is False
    assert "sidecar" in result["reason"]
