# SPDX-License-Identifier: Apache-2.0
"""招呼语（P2-4）：读取/编辑/确认。引擎侧生成，简历通侧编辑与确认快照。

**约束**：编辑上限 300 字（引擎生成口径 20–150，编辑放宽到 300）；确认走引擎
``greeting-selection=original``（选原文 = 人工确认发送用这条）；确认后引擎批准备
本岗位，link 快照同步 ``greeting_confirmed``。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ...models.ai_job_link import AiJobLink
from .manager import SidecarManager, get_sidecar_manager
from .tasks import TaskGateError

logger = logging.getLogger(__name__)

GREETING_MAX_CHARS = 300


def _client(manager: SidecarManager, config_port: int):
    return manager.client_for(config_port)


def read_greeting(db: Session, engine_job_id: str) -> dict[str, Any]:
    """招呼语快照：link 有就取 link（含确认状态），否则只透传引擎值。"""
    link = db.query(AiJobLink).filter(AiJobLink.engine_job_id == engine_job_id).one_or_none()
    if link is not None:
        return {
            "engine_job_id": engine_job_id,
            "greeting": link.greeting,
            "greeting_confirmed": link.greeting_confirmed,
            "source": "local",
        }
    mgr = get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        return {"engine_job_id": engine_job_id, "greeting": "", "greeting_confirmed": False, "source": "none"}
    try:
        data = mgr.client_for(port).get(f"/api/jobs/{engine_job_id}")
    except Exception:  # noqa: BLE001 - 引擎不可用/岗位不存在时给空值而不是 500
        data = {}
    job = data if isinstance(data, dict) else {}
    return {
        "engine_job_id": engine_job_id,
        "greeting": str(job.get("greeting") or ""),
        "greeting_confirmed": False,
        "source": "engine",
    }


def save_greeting(db: Session, engine_job_id: str, greeting: str) -> dict[str, Any]:
    """保存编辑后的招呼语（≤300 字）：写引擎 + 更新 link 快照（确认状态复位）。"""
    text = (greeting or "").strip()
    if not text:
        raise TaskGateError("招呼语不能为空", 400)
    if len(text) > GREETING_MAX_CHARS:
        raise TaskGateError(f"招呼语不能超过 {GREETING_MAX_CHARS} 字（当前 {len(text)} 字）", 400)
    mgr = get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        raise TaskGateError("sidecar 未运行：请先启动引擎", 422)
    try:
        # 契约改造②（A1）：引擎 2.4.0 要求 confirmed=true（server.py:2117-2118），
        # 1.x 不发该键，此调用在 2.4.0 引擎下恒 400（一直走本地快照兜底）。
        _client(mgr, port).post(f"/api/jobs/{engine_job_id}/greeting", {"greeting": text, "confirmed": True})
    except Exception as exc:  # noqa: BLE001 - 引擎不可用时只存本地快照并如实说明
        logger.info("招呼语写引擎失败（保留本地快照）：%s", exc)
        engine_saved = False
    else:
        engine_saved = True
    link = db.query(AiJobLink).filter(AiJobLink.engine_job_id == engine_job_id).one_or_none()
    if link is not None:
        link.greeting = text
        link.greeting_confirmed = False
        db.commit()
    return {"engine_job_id": engine_job_id, "greeting": text, "greeting_confirmed": False, "engine_saved": engine_saved}


def confirm_greeting(db: Session, engine_job_id: str) -> dict[str, Any]:
    """确认招呼语：引擎侧选原文（准备发送），link 快照置已确认。"""
    mgr = get_sidecar_manager()
    port = mgr.read_state().port
    if not port:
        raise TaskGateError("sidecar 未运行：请先启动引擎", 422)
    try:
        # confirmed=True：让引擎侧的审批态一并推进（selection 只选原文，confirmed 才是"人工拍板"）。
        _client(mgr, port).post(
            f"/api/jobs/{engine_job_id}/greeting-selection",
            {"selection": "original", "confirmed": True},
        )
    except Exception as exc:  # noqa: BLE001
        raise TaskGateError(f"招呼语确认失败：{exc}", 422) from exc
    link = db.query(AiJobLink).filter(AiJobLink.engine_job_id == engine_job_id).one_or_none()
    if link is not None:
        link.greeting_confirmed = True
        db.commit()
    return {"engine_job_id": engine_job_id, "greeting_confirmed": True}


__all__ = ["GREETING_MAX_CHARS", "confirm_greeting", "read_greeting", "save_greeting"]
