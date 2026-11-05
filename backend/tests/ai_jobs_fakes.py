# SPDX-License-Identifier: Apache-2.0
"""AI 求职测试共用桩：进程内 MockTransport 版 fake sidecar（比起子进程快）。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import httpx
from app.services.ai_jobs.client import SidecarClient
from app.services.ai_jobs.manager import SidecarManager
from tests.fixtures.fake_bosshunter import JOBS_PAGE, TASK_SNAPSHOT, WORKBENCH_STATE


def make_fake_handler(
    version: str = "2.4.1",
    *,
    workbench: dict[str, Any] | None = None,
    jobs: dict[str, Any] | None = None,
    task: dict[str, Any] | None = None,
    errors: dict[str, tuple[int, dict[str, Any]]] | None = None,
):
    """构造 fake sidecar 的请求处理器；``errors`` 按 ``POST 路径`` 注入错误响应。"""
    state = json.loads(json.dumps(workbench or WORKBENCH_STATE))
    jobs_page = json.loads(json.dumps(jobs or JOBS_PAGE))
    current = dict(task or TASK_SNAPSHOT)
    error_map = errors or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET":
            if path == "/api/health":
                return httpx.Response(200, json={"status": "ok", "version": version})
            if path == "/api/workbench":
                payload = dict(state)
                payload["task"] = (
                    None if current.get("status") in {"completed", "stopped", "failed"} else dict(current)
                )
                return httpx.Response(200, json=payload)
            if path == "/api/workbench/preflight":
                return httpx.Response(200, json={"messages": [], "checks": {}})
            if path == "/api/config":
                return httpx.Response(200, json={"profile": {"keywords": ["测试"]}, "ai": {}})
            if path == "/api/jobs":
                return httpx.Response(200, json=jobs_page)
            if path.endswith("/score-trace"):
                engine_job_id = path.split("/")[3]
                return httpx.Response(200, json={"engine_job_id": engine_job_id, "score": 82, "dimensions": {}, "caps": [], "hard_gaps": [], "reason": "匹配"})
            if path.startswith("/api/jobs/") and path.count("/") == 3:
                engine_job_id = path.split("/")[3]
                return httpx.Response(200, json={"id": engine_job_id, "greeting": "引擎侧招呼语", "status": "ready"})
            return httpx.Response(404, json={"error": f"未知路径 {path}"})
        body: dict[str, Any] = {}
        if request.content:
            try:
                body = json.loads(request.content.decode("utf-8"))
            except json.JSONDecodeError:
                body = {}
        if path in error_map:
            status, payload = error_map[path]
            return httpx.Response(status, json=payload)
        if path.startswith("/api/jobs/") and path.endswith("/greeting"):
            return httpx.Response(200, json={"greeting": body.get("greeting", "")})
        if path.startswith("/api/jobs/") and path.endswith("/greeting-selection"):
            return httpx.Response(200, json={"selection": body.get("selection", "")})
        if path == "/api/config":
            return httpx.Response(200, json=body)
        if path == "/api/workbench/task":
            mode = str(body.get("mode") or "")
            if mode not in {"full", "collect", "monitor"}:
                return httpx.Response(400, json={"error": f"未知模式 {mode}"})
            current.update(TASK_SNAPSHOT, mode=mode)
            return httpx.Response(200, json=dict(current))
        if path.endswith("/stop"):
            current["status"] = "stopped"
            return httpx.Response(200, json=dict(current))
        if path == "/api/workbench/deliver":
            job_ids = body.get("job_ids") or []
            allowed = {str(job.get("id")) for job in state.get("pending_confirmation") or []}
            outside = [job_id for job_id in job_ids if job_id not in allowed]
            if outside:
                return httpx.Response(409, json={"error": "所选岗位不在当前待确认列表里", "invalid_ids": outside})
            current.update(TASK_SNAPSHOT, mode="deliver")
            return httpx.Response(200, json=dict(current))
        if path == "/api/workbench/reject":
            return httpx.Response(200, json={"rejected": body.get("job_ids") or []})
        return httpx.Response(404, json={"error": f"未知路径 {path}"})

    return handler


def fake_sidecar_manager(tmp_path, **kwargs) -> SidecarManager:
    """构造一个"已在运行"的 sidecar manager 替身：端口固定、HTTP 走 MockTransport。"""
    manager = SidecarManager(runtime_root=tmp_path)
    transport = httpx.MockTransport(make_fake_handler(**kwargs))
    manager.client_for = lambda port: SidecarClient(f"http://127.0.0.1:{port}", transport=transport)  # type: ignore[method-assign]
    manager.read_state = lambda dataset_id=None: SimpleNamespace(port=8687)  # type: ignore[method-assign,assignment]
    manager.is_owned_running = lambda: True  # type: ignore[method-assign]
    return manager


def patch_manager(monkeypatch, manager: SidecarManager) -> None:
    """把服务层取 manager 的两处入口都指到替身上。"""
    monkeypatch.setattr("app.services.ai_jobs.tasks.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.delivery.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.status.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.api.ai_jobs.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.delivery_sync.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.greeting.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.job_sync.get_sidecar_manager", lambda: manager)
    monkeypatch.setattr("app.services.ai_jobs.resume_sync.get_sidecar_manager", lambda: manager)
