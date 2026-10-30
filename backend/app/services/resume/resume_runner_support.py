"""简历生成运行器的旁路能力：只读快照、用量汇总日志与错误类型。

从 ``resume_generate_runner.py`` 拆出来，一是让运行器只保留"编排 + 落库"，
二是这些能力彼此独立、可以单独读（快照在流开始前一次性取齐，用量日志在所有终态
各记一次）。拆出后运行器仍在同一位置 re-export 错误类型，调用点与测试锚点不变。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from ...models.job import Job
from ...schemas.job import JobOut
from ...services import trash
from ...services.claims import build_baseline
from ...services.llm import create_provider
from ...services.llm.usage import summarize_usages
from ...services.profile.profile_service import get_profile_detail, to_profile_out
from ...services.settings_service import get_llm_config

logger = logging.getLogger(__name__)


class ResumeGenerateRunnerError(Exception):
    """运行器控制类错误（任务未在运行等），message 为中文提示。"""


def build_snapshot(
    session: Session,
    task: Any,
    *,
    make_provider: Callable[[Any], Any] = create_provider,
) -> tuple[JobOut | None, Any, Any, Any]:
    """在后台线程里重建生成所需的只读快照，返回 ``(job_out, profile_out, baseline, provider)``。

    快照在流开始前一次性取齐，随后立即释放请求会话——生成本身是纯计算 + 模型调用，
    不持有数据库连接（与 SSE 路径 ``db.close()`` 的做法一致）。
    """
    job = session.get(Job, task.job_id) if task.job_id is not None else None
    if task.job_id is not None and (job is None or trash.is_deleted(job)):
        raise ResumeGenerateRunnerError("岗位不存在或已被删除")
    job_out = JobOut.model_validate(job) if job is not None else None
    profile = get_profile_detail(session)
    profile_out = to_profile_out(profile)
    baseline = build_baseline(session)
    config = get_llm_config(session)
    if not config.base_url or not config.model:
        raise ResumeGenerateRunnerError("请先在「设置」页配置大模型 API")
    provider = make_provider(config)
    return job_out, profile_out, baseline, provider


def log_generation_usage(
    task_id: int,
    generator: Any,
    *,
    estimated_prompt_tokens: int | None,
) -> None:
    """多段用量汇总日志（审计 PR-07-6，RF-14 §2.2-5）。

    主生成 / 格式修复 / 质量重试 / 失败与取消轮次的用量在
    ``generator.usage_records`` 里逐段收集（假 Provider 缺该属性时容忍），
    这里合并为一条总口径。token 缺失保留 None（「未知」，不伪造 0）；
    estimated_* 遥测只在估算开启时存在。
    """
    records = list(getattr(generator, "usage_records", None) or [])
    summary = summarize_usages(records)
    if summary is None:
        return
    fields = [
        f"model={summary['model']}",
        f"prompt_tokens={summary['prompt_tokens']}",
        f"completion_tokens={summary['completion_tokens']}",
        f"total_tokens={summary['total_tokens']}",
        f"elapsed_ms={summary['elapsed_ms']}",
        f"finish_reason={summary['finish_reason']}",
        f"retries={summary['retries']}",
    ]
    if estimated_prompt_tokens is not None:
        fields.append(f"estimated_prompt_tokens={estimated_prompt_tokens}")
    logger.info("简历生成任务模型用量 task_id=%s %s", task_id, " ".join(fields))


__all__ = [
    "ResumeGenerateRunnerError",
    "build_snapshot",
    "log_generation_usage",
]
