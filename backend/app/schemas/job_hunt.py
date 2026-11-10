# SPDX-License-Identifier: Apache-2.0
"""自研求职采集的配置结构：``AppSetting`` key ``job_hunt_config``（按数据集隔离，无需迁移）。

``job_hunt_backend`` 是新旧实现的总开关：
- ``native``（**默认**）：自研实现（``services/job_hunt/``），内置采集/评分/入队，
  不需要任何外部引擎；
- ``sidecar``：旧路径（``services/ai_jobs/`` → 外部 BossHunter 引擎的 HTTP 代理）。

新老并存、开关切换、不删旧路径（E19）。

**默认值 2026-11-10 由 ``sidecar`` 改为 ``native``。** 当初做「新老并存」时保守地保留了
旧路径当默认；但工作通的意义就是自研采集，而 ``sidecar`` 需要用户另外装 BossHunter 引擎
（GitHub 上的公开版拿不到那个引擎）——新用户装完点「AI 投递」会被要求去装引擎，
明明自研实现已经能跑。实测：作者本地之所以正常，就是因为他手动把它设成了 native，
而别人拿到默认值就撞墙。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

JobHuntBackend = Literal["sidecar", "native"]


class JobHuntConfig(BaseModel):
    job_hunt_backend: JobHuntBackend = "native"


__all__ = ["JobHuntConfig", "JobHuntBackend"]
