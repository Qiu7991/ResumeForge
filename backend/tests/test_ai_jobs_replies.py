# SPDX-License-Identifier: Apache-2.0
"""回复监测（P3-1）：列表/打开聊天/准备/记录/忽略走引擎代理。"""


import httpx
from app.services.ai_jobs import replies
from app.services.ai_jobs.client import SidecarClient
from app.services.ai_jobs.manager import SidecarManager


def _manager(tmp_path, captures: list[tuple[str, str]]) -> SidecarManager:
    def handler(request: httpx.Request) -> httpx.Response:
        captures.append((request.method, request.url.path))
        path = request.url.path
        if path == "/api/history":
            return httpx.Response(200, json=[{"id": 5, "action": "replied", "title": "AI 应用工程师"}])
        if path == "/api/history/unresolved-replies/count":
            return httpx.Response(200, json={"count": 1})
        if path.endswith(("/open-chat", "/prepare-reply", "/reply", "/dismiss")):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"error": "unknown"})

    manager = SidecarManager(runtime_root=tmp_path)
    manager.client_for = lambda port: SidecarClient("http://127.0.0.1:8687", transport=httpx.MockTransport(handler))  # type: ignore[method-assign]
    manager.read_state = lambda dataset_id=None: type("S", (), {"port": 8687})()  # type: ignore[assignment]
    return manager


def test_list_replies_returns_items_and_count(db_session, monkeypatch, tmp_path):
    captures: list[tuple[str, str]] = []
    manager = _manager(tmp_path, captures)
    monkeypatch.setattr("app.services.ai_jobs.replies.get_sidecar_manager", lambda: manager)
    data = replies.list_replies(db_session)
    assert data["unresolved_count"] == 1
    assert data["items"][0]["id"] == 5
    assert ("GET", "/api/history") in captures


def test_reply_actions_proxy_engine(db_session, monkeypatch, tmp_path):
    captures: list[tuple[str, str]] = []
    manager = _manager(tmp_path, captures)
    monkeypatch.setattr("app.services.ai_jobs.replies.get_sidecar_manager", lambda: manager)
    assert replies.open_chat(db_session, "5") == {"ok": True}
    assert replies.prepare_reply(db_session, "5") == {"ok": True}
    assert replies.record_reply(db_session, "5", "已回复") == {"ok": True}
    assert replies.dismiss(db_session, "5") == {"ok": True}
    posted = [path for method, path in captures if method == "POST"]
    assert "/api/history/5/open-chat" in posted
    assert "/api/history/5/reply" in posted
