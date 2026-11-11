# SPDX-License-Identifier: Apache-2.0
"""自研求职采集各路由模块共用的部件：浏览器客户端、黑名单类型与判定。

为什么单独成一个模块：``api/job_hunt.py`` 已经越过 500 行预算
（``tests/test_file_size_budget.py`` 会拦），2026-11-11 修 JD 补抓时再往里加
几行就越界更多。任务化采集那组路由（``/collect/task/*``）与采集入口耦合很松，
拆到 ``job_hunt_tasks.py`` 之后两边都需要 ``_acquire_client`` 与 ``is_blocked``，
放进本模块既不循环导入，也不用把私有函数从路由模块里 import 回来。

这里只放**不依赖路由**的东西：类型、纯函数、取客户端的辅助。任何 ``@router``
都不该出现在本文件。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 黑名单在 AppSetting 里的键（按数据集隔离，不建表）。
BLOCKLIST_KEY = "job_hunt_blocklist"


class BlocklistConfig(BaseModel):
    """采集时自动跳过的公司名与关键词（大小写不敏感，子串匹配）。"""

    companies: list[str] = Field(default_factory=list, max_length=200)
    keywords: list[str] = Field(default_factory=list, max_length=200)


def select_setting():
    """取 ``app_setting.value`` 的 SQL 语句（调用方自己传 key 绑定参数）。"""
    from sqlalchemy import text

    return text("SELECT value FROM app_setting WHERE key = :key")


def read_blocklist_config(db: Session) -> BlocklistConfig:
    """读黑名单配置；键不存在或内容损坏时返回空配置（不报错）。"""
    raw = db.execute(select_setting(), {"key": BLOCKLIST_KEY}).scalar_one_or_none()
    if not raw:
        return BlocklistConfig()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return BlocklistConfig()
    return BlocklistConfig(
        companies=[str(x) for x in (data.get("companies") or [])][:200],
        keywords=[str(x) for x in (data.get("keywords") or [])][:200],
    )


def is_blocked(stub: Any, config: BlocklistConfig) -> bool:
    """这条卡片是否命中黑名单（公司名或标题里含任一关键词）。"""
    company = (stub.company or "").lower()
    title = (stub.title or "").lower()
    for name in config.companies:
        needle = name.strip().lower()
        if needle and needle in company:
            return True
    for word in config.keywords:
        needle = word.strip().lower()
        if needle and (needle in title or needle in company):
            return True
    return False


def acquire_client(db: Session):
    """取专用浏览器的 CDP 客户端（复用投递台的浏览器管理，不自建）。"""
    from ..services.apply._site_browser import get_browser_manager

    try:
        manager = get_browser_manager(db)
        return manager.client()
    except Exception as exc:  # noqa: BLE001 — 浏览器没启动/连不上 → 给可操作的提示
        logger.info("native 采集取浏览器客户端失败：%s: %s", type(exc).__name__, exc)
        raise HTTPException(
            503,
            # 前缀 ``browser_required`` 是**协议值**：前端据它决定要不要给「启动浏览器」
            # 按钮。不要靠中文文案匹配——后端改一次措辞，那个按钮就静默消失了。
            "browser_required: native 采集需要先启动专用浏览器（投递台 → 启动浏览器），稍后重试",
        ) from exc


__all__ = [
    "BLOCKLIST_KEY",
    "BlocklistConfig",
    "acquire_client",
    "is_blocked",
    "read_blocklist_config",
    "select_setting",
]
