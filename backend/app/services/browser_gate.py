# SPDX-License-Identifier: Apache-2.0
"""浏览器互斥门：同一时间只允许一个自动化任务占用投递专用浏览器。

## 为什么需要这个模块

投递台、岗位采集、网申填表三者共用**同一个**投递专用浏览器（同一端口、同一
profile）。两个任务同时驱动它，会出现一个任务把页面导航走、另一个还在等自己
那一页的 DOM——实测表现是"补抓 JD 只成功 1/13"这类看似随机失败的故障。

## 从 ai_jobs.gate 搬来的原因

原实现在 ``services/ai_jobs/gate.py``，而那一层是**遥控外部 BossHunter 引擎**的
旧路径。2026-11-19 删除 ai_jobs 时发现：自研采集（``services/job_hunt/``）不看
这个门，也从不置位 ``_ai_busy``——所以那个"互斥"实际上**早就失效了**：采集在跑
的时候点投递，照样能启动，两边一起抢浏览器。

搬到这里之后三件事都变了：

1. 门是**纯查询**的：不维护自己的标志位，每次去问各个任务管理器"你忙不忙"。
   标志位版本需要每个任务在生命周期两端记得置位/清除，漏一处就永久卡死——
   而这正是原来 ``try_clear_stale_ai_busy`` 那段自愈逻辑存在的原因。
2. 采集与投递**对等**：两边启动前都过同一个门，不再是"投递被采集拦、采集不看门"。
3. 无引擎依赖：不需要访问任何 HTTP 端口，进程内查状态即可。

## 用法

启动任何一个自动化任务**之前**调用 :func:`ensure_browser_free`，返回非空字符串
表示有冲突（调用方把那段文案直接给用户看）；返回空串表示可以启动。

**注意 TOCTOU**：本模块只做检查、不做占位。调用方必须把检查放在**自己的启动
锁内**（``TaskRunner.start`` 就是这么做的），否则两个请求可能同时通过检查。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 冲突文案里点名的"占用者"。顺序即优先级：采集与投递是常驻功能，网申填表是
# 交互式操作（用户就在旁边等着），所以它排最后但也最容易被看到。
_OCCUPIER_COLLECT = "岗位采集正在运行，请等它结束或停止后再启动"
_OCCUPIER_APPLY = "投递任务正在运行，请等它结束或停止后再启动"
_OCCUPIER_WEBFORM = "网申填表正在进行，请等它结束后再启动"


def _collect_busy() -> bool:
    """是否有岗位采集任务在跑（进程内，不访问网络）。"""
    try:
        from ..job_hunt.collect_task import get_collect_manager

        return get_collect_manager().active() is not None
    except Exception:  # noqa: BLE001 - 采集模块不可用不该让投递也起不来
        logger.debug("采集忙碌探测失败，按空闲处理", exc_info=True)
        return False


def _apply_busy() -> bool:
    """投递台是否有任务在跑（纯查询，不启动任何东西）。"""
    try:
        from ..apply.task_runner import get_task_runner

        runner = get_task_runner()
        return runner.is_running() or runner.current_task_id() is not None
    except Exception:  # noqa: BLE001
        logger.debug("投递忙碌探测失败，按空闲处理", exc_info=True)
        return False


def _webform_busy() -> bool:
    try:
        from ..webform.service.fill import is_filling

        return is_filling()
    except Exception:  # noqa: BLE001 - 网申模块可选
        logger.debug("网申忙碌探测失败，按空闲处理", exc_info=True)
        return False


def browser_occupier() -> str:
    """正在占用浏览器的那类任务；空闲返回空串。

    检查顺序固定：采集 → 投递 → 网申。用户看到的文案要稳定，不能因为某个探测
    恰好失败而换个说法。
    """
    if _collect_busy():
        return "collect"
    if _apply_busy():
        return "apply"
    if _webform_busy():
        return "webform"
    return ""


def ensure_browser_free() -> str:
    """启动自动化任务前的互斥检查。冲突返回原因文案，空闲返回空串。

    调用方负责把检查放进自己的启动锁内（TOCTOU：检查与占位必须原子）。
    """
    occupier = browser_occupier()
    if occupier == "collect":
        return _OCCUPIER_COLLECT
    if occupier == "apply":
        return _OCCUPIER_APPLY
    if occupier == "webform":
        return _OCCUPIER_WEBFORM
    return ""


__all__ = ["browser_occupier", "ensure_browser_free"]
