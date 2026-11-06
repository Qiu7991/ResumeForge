# SPDX-License-Identifier: Apache-2.0
"""自研求职采集（``services/job_hunt/``）：不依赖外部引擎的多平台岗位采集。

与 ``services/ai_jobs/``（HTTP 代理到外部引擎的旧路径）**并存**，用设置项
``job_hunt_backend``（``schemas/job_hunt.py``，默认 ``sidecar``）切换；旧路径保留
作 fallback，删除要等自研实现稳定之后。

模块分工：
- ``base``     ：平台适配器抽象（``JobSiteAdapter``）与数据结构（``JobStub``/``JobDetail``）；
- ``registry`` ：适配器注册表（加平台 = 加子类 + 注册一行）；
- ``runner``   ：采集通用层（翻页 / 去重 / 进度 / 断点，J3）；
- ``sites/``   ：各平台适配器与反爬处理（BOSS 字体解密等，J2+）；
- ``replies``  ：回复监测（只读，不自动回复，J8）。
"""
from .base import JobDetail, JobParseError, JobSiteAdapter, JobStub, HuntCriteria
from .registry import JobHuntRegistry, default_registry, get_registry

__all__ = [
    "JobSiteAdapter",
    "JobStub",
    "JobDetail",
    "HuntCriteria",
    "JobParseError",
    "JobHuntRegistry",
    "default_registry",
    "get_registry",
]
