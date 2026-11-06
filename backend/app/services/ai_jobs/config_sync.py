# SPDX-License-Identifier: Apache-2.0
"""配置同步（P3-2）：简历通全局 LLM Profile → 引擎 config（AI 是唯一配置源）。

映射（§4.5）：``api_style=openai`` → ``ai.service=custom`` + ``ai.provider=
openai_compatible``；``anthropic`` → ``ai.service=anthropic``。``base_url``/``model``/
``api_key``/``timeout_seconds``/``max_tokens`` 一并写入。引擎会把 Key 落到它自己的
私有凭据文件；简历通不返回 Key、不写日志。

**会话密钥不落盘**：当前只有内存态 session key 时阻断并提示先保存（§4.5）。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ..llm_settings import get_llm_config, session_key_configured
from .tasks import TaskGateError

logger = logging.getLogger(__name__)

# 引擎版本窗口内的 ai 配置段（BossHunter config.yaml 的 ai 节）。
_SUPPORTED_API_STYLES = {"openai": ("custom", "openai_compatible"), "anthropic": ("anthropic", "anthropic")}


def build_engine_ai_config(db: Session) -> dict[str, Any]:
    """从简历通 LLM Profile 构造引擎 ai 配置段。"""
    config = get_llm_config(db)
    api_style = _SUPPORTED_API_STYLES.get(config.api_style)
    if api_style is None:
        raise TaskGateError(f"不支持的接口协议：{config.api_style}", 400)
    if not config.api_key:
        raise TaskGateError("模型配置缺少 API Key：请先到设置里保存", 400)
    if session_key_configured():
        raise TaskGateError("当前只在会话里临时填写了 API Key，请到设置里保存后再同步", 400)
    service, provider = api_style
    ai_section: dict[str, Any] = {
        "service": service,
        "provider": provider,
        "base_url": config.base_url,
        "model": config.model,
        "api_key": config.api_key,
        "timeout_seconds": config.timeout_seconds,
    }
    # max_tokens=0 表示「不限制」：请求体里省略该字段，不把 0 写给引擎。
    if config.max_tokens > 0:
        ai_section["max_tokens"] = config.max_tokens
    return ai_section


def sync_llm_to_engine(db: Session, client: Any) -> dict[str, Any]:
    """读引擎 config → 深度合并 ai 段 → 写回。返回引擎确认后的配置（不含 Key）。"""
    ai_section = build_engine_ai_config(db)
    current = client.get("/api/config")
    if not isinstance(current, dict):
        raise TaskGateError("引擎返回了无法识别的配置", 422)
    merged = dict(current)
    ai_old = merged.get("ai") if isinstance(merged.get("ai"), dict) else {}
    merged["ai"] = {**ai_old, **ai_section}
    client.post("/api/config", merged)
    # 回读给前端的摘要绝不含 Key。
    logger.info("LLM 配置已同步给引擎 model=%s", ai_section["model"])
    return {"synced": True, "model": ai_section["model"], "service": ai_section["service"]}


__all__ = ["build_engine_ai_config", "sync_llm_to_engine"]
