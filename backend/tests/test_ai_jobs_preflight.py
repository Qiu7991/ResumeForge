# SPDX-License-Identifier: Apache-2.0
"""预检六类：简历/AI/浏览器/BOSS 页/平台/锁；单项失败不拖垮整体。"""

import httpx
from app.services.ai_jobs.gate import set_ai_jobs_busy
from app.services.ai_jobs.status import run_preflight
from tests.test_ai_jobs_manager import _engine_config


def _keys(checks):
    return [check.key for check in checks]


def test_preflight_reports_resume_missing(db_session, monkeypatch, tmp_path):
    manager = None
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=manager, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert set(by_key) >= {"resume", "llm", "browser", "boss_page", "lock"}
    assert by_key["resume"].ok is False
    assert "通用简历" in by_key["resume"].message


def test_preflight_resume_ok_when_record_exists(db_session, monkeypatch, tmp_path):
    from app.models.resume import ResumeRecord

    db_session.add(ResumeRecord(title="通用简历", draft=False))
    db_session.commit()
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=None, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert by_key["resume"].ok is True


def test_preflight_llm_requires_config(db_session, tmp_path):
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=None, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert by_key["llm"].ok is False
    assert "缺少" in by_key["llm"].message


def test_preflight_browser_not_running(db_session, tmp_path):
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=None, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert by_key["browser"].ok is False
    assert "浏览器" in by_key["browser"].message


def test_preflight_platform_reports_sidecar_down(db_session, tmp_path):
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=None, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert by_key["platform"].ok is False
    assert "sidecar" in by_key["platform"].message


def test_preflight_lock_blocks_when_ai_busy(db_session, tmp_path):
    set_ai_jobs_busy(True)
    try:
        checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=None, dataset_id="main")
    finally:
        set_ai_jobs_busy(False)
    by_key = {check.key: check for check in checks}
    assert by_key["lock"].ok is False
    assert "AI 求职" in by_key["lock"].message


def test_preflight_platform_translates_engine_messages(db_session, tmp_path):
    """sidecar 在跑时，其 preflight messages 逐条转述。"""
    from app.services.ai_jobs.manager import SidecarManager

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "version": "2.4.1"})
        assert request.url.path == "/api/workbench/preflight"
        return httpx.Response(200, json={"messages": ["简历未上传"], "checks": {}})

    manager = SidecarManager(runtime_root=tmp_path)
    manager.client_for = lambda port: __import__(
        "app.services.ai_jobs.client", fromlist=["SidecarClient"]
    ).SidecarClient("http://127.0.0.1:1", transport=httpx.MockTransport(handler))
    manager.read_state = lambda dataset_id=None: type(
        "S", (), {"port": 8687}
    )()
    checks = run_preflight(db_session, _engine_config(tmp_path, 8687), manager=manager, dataset_id="main")
    by_key = {check.key: check for check in checks}
    assert by_key["platform"].ok is False
    assert "简历未上传" in by_key["platform"].message
