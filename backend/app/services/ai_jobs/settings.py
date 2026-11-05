# SPDX-License-Identifier: Apache-2.0
"""``ai_jobs_config`` 读写：存 ``AppSetting`` KV，随数据集库天然按数据集隔离。

与 ``services/settings_service`` 同一模式：缺失/脏数据回默认，不抛错（状态页
据此展示"未配置"而不是白屏）。不存任何 Key、Token、Cookie。
"""

import json
import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ...models.setting import AppSetting
from ...schemas.ai_jobs import AiJobsConfig

logger = logging.getLogger(__name__)

_AI_JOBS_CONFIG_KEY = "ai_jobs_config"


def get_ai_jobs_config(db: Session) -> AiJobsConfig:
    """读取 AI 求职连接配置；缺失或损坏时回默认值。"""
    row = db.get(AppSetting, _AI_JOBS_CONFIG_KEY)
    if row is None:
        return AiJobsConfig()
    try:
        return AiJobsConfig.model_validate(json.loads(row.value))
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning("AI 求职配置数据损坏，已重置为默认值")
        return AiJobsConfig()


def save_ai_jobs_config(db: Session, config: AiJobsConfig) -> AiJobsConfig:
    """保存 AI 求职连接配置（整对象落库）。"""
    row = db.get(AppSetting, _AI_JOBS_CONFIG_KEY)
    serialized = json.dumps(config.model_dump(), ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=_AI_JOBS_CONFIG_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()
    return config
