# SPDX-License-Identifier: Apache-2.0
"""``job_hunt_config`` 读写：存 ``AppSetting`` KV，随数据集库天然按数据集隔离。

与 ``services/ai_jobs/settings.py`` 同一模式：缺失/脏数据回默认，不抛错。不存任何
Key、Token、Cookie。
"""

import json
import logging

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ...models.setting import AppSetting
from ...schemas.job_hunt import JobHuntConfig

logger = logging.getLogger(__name__)

_JOB_HUNT_CONFIG_KEY = "job_hunt_config"


def get_job_hunt_config(db: Session) -> JobHuntConfig:
    """读取自研求职开关配置；缺失或损坏时回默认值（默认走旧 sidecar 路径）。"""
    row = db.get(AppSetting, _JOB_HUNT_CONFIG_KEY)
    if row is None:
        return JobHuntConfig()
    try:
        return JobHuntConfig.model_validate(json.loads(row.value))
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning("自研求职配置数据损坏，已重置为默认值")
        return JobHuntConfig()


def save_job_hunt_config(db: Session, config: JobHuntConfig) -> JobHuntConfig:
    """保存自研求职开关配置（整对象落库）。"""
    row = db.get(AppSetting, _JOB_HUNT_CONFIG_KEY)
    serialized = json.dumps(config.model_dump(), ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=_JOB_HUNT_CONFIG_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()
    return config


__all__ = ["get_job_hunt_config", "save_job_hunt_config"]
