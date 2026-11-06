# SPDX-License-Identifier: Apache-2.0
"""自研求职采集的适配器注册表：按站点标识 / URL 主机分发到具体适配器。

与 ``services/sites/registry.py`` 同一模式：业务层只管 ``registry.for_url(url)``；
加平台时只要新增一个子类并在 ``default_registry`` 里 ``register`` 一行，通用层不用改。
"""
from __future__ import annotations

from .base import JobSiteAdapter


class JobHuntRegistry:
    """适配器注册表（保持注册顺序，便于「先注册先匹配」）。"""

    def __init__(self) -> None:
        self._adapters: list[JobSiteAdapter] = []

    def register(self, adapter: JobSiteAdapter) -> JobSiteAdapter:
        self._adapters.append(adapter)
        return adapter

    def all(self) -> list[JobSiteAdapter]:
        return list(self._adapters)

    def resolve(self, key: str) -> JobSiteAdapter | None:
        """按站点标识取适配器；没有则返回 ``None``（调用方决定回退策略）。"""
        target = (key or "").strip()
        for adapter in self._adapters:
            if adapter.key == target:
                return adapter
        return None

    def supported_keys(self) -> list[str]:
        return [adapter.key for adapter in self._adapters]

    def supported_names(self) -> str:
        """已注册平台的展示名，用「、」连成一句（错误信息里「目前支持：…」用）。"""
        return "、".join(a.name for a in self._adapters) or "暂无"

    def for_url(self, url: str) -> JobSiteAdapter:
        """按 URL 分发适配器；没有平台认领时抛 ``LookupError``。"""
        for adapter in self._adapters:
            if adapter.supports(url):
                return adapter
        raise LookupError(f"暂不支持该链接的招聘平台；目前支持：{self.supported_names()}")


def default_registry() -> JobHuntRegistry:
    """构建默认注册表：加平台 = 加一个子类 + 在这里 register 一行。"""
    from .sites.job51 import Job51Adapter
    from .sites.zhilian import ZhilianAdapter

    registry = JobHuntRegistry()
    registry.register(ZhilianAdapter())
    registry.register(Job51Adapter())
    return registry


_REGISTRY: JobHuntRegistry | None = None


def get_registry() -> JobHuntRegistry:
    """进程内共享的默认注册表（延迟构建，避免导入期循环依赖）。"""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = default_registry()
    return _REGISTRY


__all__ = ["JobHuntRegistry", "default_registry", "get_registry"]
