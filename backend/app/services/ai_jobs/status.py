# SPDX-License-Identifier: Apache-2.0
"""AI 求职聚合状态与启动前预检：引擎配置、sidecar 健康、进程归属、六类 preflight。

预检六类（P1-1）：简历 / AI / 浏览器 / BOSS 页 / 平台 / 互斥锁。每类给 ``ok``
与**可操作**的 ``message``；预检只探测不启动（浏览器、sidecar 都不代拉）。
BOSS 登录态只能由用户在 9333 窗口里确认，程序给的是"当前观察"，不是保证。
"""

from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models.resume import ResumeRecord
from ...runtime.dataset_scope import current_dataset_id
from ...schemas.ai_jobs import AiJobsConfig, SidecarHealth
from .manager import SidecarManager, get_sidecar_manager

logger = logging.getLogger(__name__)


class AiJobsStatus(BaseModel):
    """``GET /api/ai-jobs/status`` 的响应体。"""

    dataset_id: str
    config: AiJobsConfig
    engine_configured: bool = False
    # 引擎配置了但路径无效时的可操作提示；空串 = 配置有效。
    engine_error: str = ""
    sidecar: SidecarHealth
    owned_running: bool = False
    # 实际端口：自己启动的用进程端口，否则读磁盘状态（复用场景）。
    port: int = 0


class PreflightCheck(BaseModel):
    """一条预检结果。``ok=False`` 不阻断 UI，只把对应动作置灰并说明原因。"""

    key: str
    label: str
    ok: bool
    message: str = ""


def build_ai_jobs_status(
    config: AiJobsConfig,
    manager: SidecarManager | None = None,
    dataset_id: str | None = None,
) -> AiJobsStatus:
    """聚合连接状态。sidecar 未运行时 ``sidecar.reachable=False``（正常形态，不是错误）。"""
    mgr = manager or get_sidecar_manager()
    dataset = dataset_id or current_dataset_id()
    engine_error = mgr.validate_engine(config)
    port = 0
    if mgr.is_owned_running():
        port = mgr.read_state(dataset).port
        health = mgr.client_for(port).health() if port else SidecarHealth(reachable=False, reason="未知端口")
    else:
        # 复用场景：读磁盘状态探一次健康（不启动、不杀进程）。
        state = mgr.read_state(dataset)
        port = state.port
        health = mgr.client_for(port).health() if port else SidecarHealth(reachable=False, reason="sidecar 未启动")
        if not health.reachable:
            port = 0
    return AiJobsStatus(
        dataset_id=dataset,
        config=config,
        engine_configured=not engine_error,
        engine_error=engine_error,
        sidecar=health,
        owned_running=mgr.is_owned_running(),
        port=port,
    )


# ===== 预检（P1-1）=====


def _check_resume(db: Session) -> PreflightCheck:
    """简历中心里存在可投递的通用简历（``job_id IS NULL`` 且非草稿）。"""
    exists = db.scalar(
        select(ResumeRecord.id).where(ResumeRecord.job_id.is_(None), ResumeRecord.draft.is_(False)).limit(1)
    )
    if exists is not None:
        return PreflightCheck(key="resume", label="通用简历", ok=True)
    return PreflightCheck(
        key="resume",
        label="通用简历",
        ok=False,
        message="简历中心里没有通用简历（不绑定岗位、非草稿），请先生成或新建一份",
    )


def _check_llm(db: Session) -> PreflightCheck:
    """实际生效的 LLM 配置齐备（base_url + model + 可落盘的 Key）。"""
    from ..llm_settings import get_llm_config, session_key_configured

    config = get_llm_config(db)
    missing = [name for name, value in (("服务地址", config.base_url), ("模型", config.model)) if not value]
    if not config.api_key:
        missing.append("API Key")
    elif session_key_configured() and config.api_key:
        # 会话密钥不落盘：sidecar 需要可落盘的 Key，纯会话 Key 同步过去也存不住。
        return PreflightCheck(
            key="llm",
            label="模型配置",
            ok=False,
            message="当前只在会话里临时填写了 API Key，请到设置里保存后重试",
        )
    if missing:
        return PreflightCheck(
            key="llm", label="模型配置", ok=False, message="模型配置缺少：" + "、".join(missing)
        )
    return PreflightCheck(key="llm", label="模型配置", ok=True)


def _check_browser(db: Session) -> PreflightCheck:
    """9333 专用浏览器在跑（只探测，不代启动）。"""
    from ..apply._site_browser import get_browser_manager

    status = get_browser_manager(db).status()
    if status.state == "running":
        return PreflightCheck(key="browser", label="专用浏览器", ok=True, message=f"运行中（端口 {status.port}）")
    return PreflightCheck(
        key="browser",
        label="专用浏览器",
        ok=False,
        message="专用浏览器未运行：请先在投递台启动浏览器并登录 BOSS（程序不代登录）",
    )


def _check_boss_page(db: Session) -> PreflightCheck:
    """BOSS 登录态只能人工确认；这里只如实报告当前观察，不保证已登录。"""
    from ..apply._site_browser import get_browser_manager

    status = get_browser_manager(db).status()
    if status.state != "running":
        return PreflightCheck(
            key="boss_page",
            label="BOSS 登录",
            ok=False,
            message="浏览器未运行，无法确认 BOSS 登录态",
        )
    return PreflightCheck(
        key="boss_page",
        label="BOSS 登录",
        ok=True,
        message="浏览器运行中：登录态以你在窗口里的实际状态为准",
    )


def _check_platform(manager: SidecarManager, config: AiJobsConfig, dataset_id: str) -> PreflightCheck:
    """sidecar 自身的启动前检查（其 messages 逐条转述）。"""
    if not (manager.is_owned_running() or _reachable_state_port(manager, dataset_id)):
        return PreflightCheck(
            key="platform",
            label="引擎预检",
            ok=False,
            message="sidecar 未运行：请先启动引擎",
        )
    port = manager.read_state(dataset_id).port
    try:
        data = manager.client_for(port).get("/api/workbench/preflight")
    except Exception as exc:  # noqa: BLE001 - 预检失败如实转述
        logger.info("sidecar preflight 不可用：%s", exc)
        return PreflightCheck(key="platform", label="引擎预检", ok=False, message=f"引擎预检不可用：{exc}")
    messages = [str(m) for m in (data or {}).get("messages", []) if m]
    if messages:
        return PreflightCheck(key="platform", label="引擎预检", ok=False, message="；".join(messages))
    return PreflightCheck(key="platform", label="引擎预检", ok=True)


def _reachable_state_port(manager: SidecarManager, dataset_id: str) -> bool:
    port = manager.read_state(dataset_id).port
    if not port:
        return False
    return manager.client_for(port).health().reachable


def _check_lock(db: Session) -> PreflightCheck:
    """互斥锁：旧投递台任务、网申填表、AI 任务两两互斥。"""
    from ..webform.service.fill import is_filling
    from .gate import ai_jobs_busy, apply_busy

    if ai_jobs_busy():
        return PreflightCheck(key="lock", label="任务互斥", ok=False, message="已有 AI 求职任务在运行")
    if apply_busy(db):
        return PreflightCheck(key="lock", label="任务互斥", ok=False, message="已有投递任务在运行")
    if is_filling():
        return PreflightCheck(key="lock", label="任务互斥", ok=False, message="网申填表正在进行")
    return PreflightCheck(key="lock", label="任务互斥", ok=True)


def run_preflight(
    db: Session,
    config: AiJobsConfig,
    manager: SidecarManager | None = None,
    dataset_id: str | None = None,
) -> list[PreflightCheck]:
    """六类预检逐项执行；单项异常不拖垮整体（该项报错误信息）。"""
    mgr = manager or get_sidecar_manager()
    dataset = dataset_id or current_dataset_id()
    checks: list[PreflightCheck] = []
    builders = (
        lambda: _check_resume(db),
        lambda: _check_llm(db),
        lambda: _check_browser(db),
        lambda: _check_boss_page(db),
        lambda: _check_platform(mgr, config, dataset),
        lambda: _check_lock(db),
    )
    for build in builders:
        try:
            checks.append(build())
        except Exception as exc:  # noqa: BLE001 - 单项失败不影响其余预检
            logger.warning("预检项执行失败：%s", exc)
            checks.append(PreflightCheck(key="error", label="预检异常", ok=False, message=str(exc)))
    return checks
