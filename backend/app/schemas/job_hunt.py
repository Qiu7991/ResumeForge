# SPDX-License-Identifier: Apache-2.0
"""自研求职采集的配置结构：``AppSetting`` key ``job_hunt_config``（按数据集隔离，无需迁移）。

``job_hunt_backend`` 是新旧实现的总开关：
- ``sidecar``（默认）：AI 求职页面走既有 HTTP 代理（``services/ai_jobs/`` → 外部引擎）；
- ``native``：切换到自研实现（``services/job_hunt/``）。

新老并存、开关切换、不删旧路径（E19）。默认必须是 ``sidecar``——旧路径是能跑的现状。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

JobHuntBackend = Literal["sidecar", "native"]


class JobHuntConfig(BaseModel):
    job_hunt_backend: JobHuntBackend = "sidecar"


__all__ = ["JobHuntConfig", "JobHuntBackend"]
