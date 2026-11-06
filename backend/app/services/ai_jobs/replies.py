# SPDX-License-Identifier: Apache-2.0
"""回复监测（P3-1）：未处理回复列表与人工处置（打开聊天/准备回复/记录回复/忽略）。

第一版口径（§14.5）：HR 回复只在新标签页处理，**不同步** reminder /
application_track_event；打开聊天只是在 9333 窗口导航，不代发任何内容。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from .manager import get_sidecar_manager
from .tasks import TaskGateError

logger = logging.getLogger(__name__)


def _client() -> tuple[Any, object]:
    mgr = get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        raise TaskGateError("sidecar 未运行：请先启动引擎", 422)
    return mgr.client_for(port), mgr


def list_replies(db: Session) -> dict[str, Any]:
    """未处理回复 + 会话列表（引擎 ``/api/history`` 的监测投影）。"""
    client, _mgr = _client()
    history = client.get(
        "/api/history",
        params={"limit": 50, "include_unresolved": "true", "include_monitor_conversations": "true"},
    )
    unresolved = client.get("/api/history/unresolved-replies/count")
    items = history if isinstance(history, list) else (history or {}).get("items") or []
    return {
        "items": items,
        "unresolved_count": (unresolved or {}).get("count", 0) if isinstance(unresolved, dict) else 0,
    }


def open_chat(db: Session, history_id: str) -> dict[str, Any]:
    """在 9333 窗口打开该会话的聊天页（导航，不代发）。"""
    client, _mgr = _client()
    try:
        return client.post(f"/api/history/{history_id}/open-chat", {})
    except Exception as exc:  # noqa: BLE001
        raise TaskGateError(f"打开聊天失败：{exc}", 422) from exc


def prepare_reply(db: Session, history_id: str) -> dict[str, Any]:
    """准备回复（引擎给出草稿上下文；由用户在窗口里自行发送）。"""
    client, _mgr = _client()
    try:
        return client.post(f"/api/history/{history_id}/prepare-reply", {})
    except Exception as exc:  # noqa: BLE001
        raise TaskGateError(f"准备回复失败：{exc}", 422) from exc


def record_reply(db: Session, history_id: str, content: str) -> dict[str, Any]:
    """记录人工回复结果（用户已在窗口里发过；此处只是落账）。"""
    client, _mgr = _client()
    try:
        # 契约改造①（A1）：引擎 2.4.0 读 body["message"]（server.py:2361），1.x 的
        # "content" 键引擎不消费，恒 400「回复内容不能为空」。
        return client.post(f"/api/history/{history_id}/reply", {"message": content})
    except Exception as exc:  # noqa: BLE001
        raise TaskGateError(f"记录回复失败：{exc}", 422) from exc


def dismiss(db: Session, history_id: str) -> dict[str, Any]:
    client, _mgr = _client()
    try:
        return client.post(f"/api/history/{history_id}/dismiss", {})
    except Exception as exc:  # noqa: BLE001
        raise TaskGateError(f"忽略失败：{exc}", 422) from exc


__all__ = ["dismiss", "list_replies", "open_chat", "prepare_reply", "record_reply"]
