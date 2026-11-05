# SPDX-License-Identifier: Apache-2.0
"""fake BossHunter sidecar：本地 loopback HTTP 桩，供 manager/契约/端到端测试用。

只模拟 BossHunter 的 ``/api`` 表面（health/task/jobs/deliver/...），**不访问任何
招聘平台**。用法：``python fake_bosshunter.py --port 8687 [--version 2.4.1]``。
"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

VERSION = "2.4.1"

TASK_SNAPSHOT = {
    "id": "task-1",
    "mode": "full",
    "label": "全流程",
    "status": "running",
    "logs": ["fake sidecar: task started"],
    "error": None,
    "created_at": "2026-11-03T01:00:00",
    "updated_at": "2026-11-03T01:00:00",
    "deadline_at": None,
    "stop_reason": None,
    "stop_requested": False,
    "metrics": {},
    "progress": {},
}

WORKBENCH_STATE = {
    "pending_confirmation": [
        {
            "id": "job-1",
            "title": "AI 应用工程师",
            "company": "示例公司",
            "status": "ready",
            "score": 82,
            "greeting": "您好，看到贵司在招 AI 应用工程师",
            "source_platform": "boss",
        }
    ],
    "pending_greetings": [],
    "send_errors": [],
    "needs_resume": [],
    "send_quota": {"daily_limit": 30, "sent": 0, "remaining": 30, "exhausted": False},
    "task": None,
    "last_task": None,
}

JOBS_PAGE = {
    "jobs": [
        {
            "id": "job-1",
            "title": "AI 应用工程师",
            "company": "示例公司",
            "status": "sent",
            "score": 82,
            "source_platform": "boss",
            "sent_at": "2026-11-02T21:00:00",
            "updated_at": "2026-11-02T21:00:00",
        }
    ],
    "total": 1,
}

# 可变任务态（stop 之后置为 stopped）
_CURRENT_TASK = dict(TASK_SNAPSHOT)


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def do_GET(self) -> None:  # noqa: N802 - http.server 命名
        global _CURRENT_TASK
        path = self.path.split("?")[0]
        if path == "/api/health":
            self._send({"status": "ok", "version": VERSION})
        elif path == "/api/workbench":
            state = dict(WORKBENCH_STATE)
            state["task"] = None if _CURRENT_TASK.get("status") in {"completed", "stopped", "failed"} else dict(_CURRENT_TASK)
            self._send(state)
        elif path == "/api/workbench/preflight":
            self._send({"messages": [], "checks": {}})
        elif path == "/api/jobs":
            self._send(dict(JOBS_PAGE))
        else:
            self._send({"error": f"fake sidecar: 未知路径 {path}"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        global _CURRENT_TASK
        path = self.path.split("?")[0]
        body = self._read_json()
        if path == "/api/workbench/task":
            mode = str(body.get("mode") or "")
            if mode not in {"full", "collect", "monitor"}:
                self._send({"error": f"未知模式 {mode}"}, 400)
                return
            _CURRENT_TASK = dict(TASK_SNAPSHOT, mode=mode)
            self._send(dict(_CURRENT_TASK))
        elif path.startswith("/api/workbench/task/") and path.endswith("/stop"):
            _CURRENT_TASK["status"] = "stopped"
            self._send(dict(_CURRENT_TASK))
        elif path == "/api/workbench/deliver":
            job_ids = body.get("job_ids") or []
            if not job_ids:
                self._send({"error": "请选择要投递的岗位"}, 400)
                return
            outside = [job_id for job_id in job_ids if job_id not in {"job-1"}]
            if outside:
                self._send({"error": "所选岗位不在当前待确认列表里", "invalid_ids": outside}, 409)
                return
            _CURRENT_TASK = dict(TASK_SNAPSHOT, mode="deliver")
            self._send(dict(_CURRENT_TASK))
        elif path == "/api/workbench/reject":
            self._send({"rejected": body.get("job_ids") or []})
        else:
            self._send({"error": f"fake sidecar: 未知路径 {path}"}, 404)

    def log_message(self, *_args) -> None:  # 静默：测试输出只留 pytest 汇总
        return


def main() -> None:
    global VERSION  # noqa: PLW0603 - 桩进程内全局即可
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--version", default=VERSION)
    args = parser.parse_args()
    VERSION = args.version
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
