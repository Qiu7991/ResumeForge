# SPDX-License-Identifier: Apache-2.0
"""语义评分的编排层：拼提示词 → 调模型 → 解析 → （可选）落库。

**为什么单独成模块**（2026-11-11）：这段编排放原来写在
``api/job_hunt_score.py`` 的路由函数里。现在有两个调用方——岗位评分（已入库的 Job）
和备选岗位评分（还没导入，没有 Job 行）——留在路由里就只能复制一遍，或者让
service 反向依赖 API 模块。

这里是**唯一**做「调 LLM 评岗位」的地方。``services/job_hunt/scoring.py`` 仍然只有
纯函数（拼模板、解析输出），不碰网络、不碰数据库。

调用方要区分两类失败：
- :class:`ScoringUnavailable` —— 环境问题（没配模型 / 个人资料为空），重试也没用；
- :class:`ScoringFailed` —— 这一次调用失败（网络、超时、输出解析不了），可以重试。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ...models.job import Job
from .scoring import SemanticScore, build_scoring_prompt, parse_semantic_score

logger = logging.getLogger(__name__)


class ScoringUnavailable(Exception):
    """评分无法进行（缺模型配置 / 缺资料）——重试无意义。"""


class ScoringFailed(Exception):
    """这一次评分失败（模型调用或输出解析）——可以重试。"""


def profile_field(profile: Any, name: str) -> str:
    """读个人资料里的文本字段（列表拼成顿号分隔）。"""
    value = getattr(profile, name, None)
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(v) for v in value)
    return str(value).strip()


def expected_salary_k(profile: Any) -> float:
    """从 ``expected_salary`` 文本（"15-25K" / "20K"）里取上限（单位 K）。

    资料里的期望薪资是自由文本，不是数值列；取不到就返回 0（= 未设置），
    让提示词明确说「未填写」，而不是把一个猜的数字喂给模型。
    """
    import re

    text = profile_field(profile, "expected_salary")
    numbers = re.findall(r"(\d+(?:\.\d+)?)", text)
    if not numbers:
        return 0.0
    high = float(numbers[-1])
    if "万" in text:
        high *= 10
    return high


def resolve_resume_text(
    db: Session, *, resume_id: int | None
) -> tuple[Any, str, str]:
    """取评分要用的简历文本与个人资料。

    返回 ``(profile, profile_text, resume_text)``。

    ``resume_id`` 给定时用它（用于「同一岗位对比不同简历」）；不给时走默认简历。
    这里是候选评分与岗位评分的**唯一**取源路径——两处各取一次必然分叉。

    用 ``apply_service.resolve_resume(db, None, resume_id)`` 而不是
    ``job_resume_text(db, job)``：后者的第二个参数是 Job 对象（内部读 ``job.id`` 去
    找该岗位的专属简历）。备选岗位没有 Job 行，传 None 让 ``job_id`` 走「跳过岗位
    专属 → 落默认简历」那条分支——这正是备选阶段想要的语义。
    """
    from ..apply import apply_service
    from ..job.job_match_context import profile_text, resume_prompt_text
    from ..profile.ai_profile import load_ai_profile

    profile = load_ai_profile(db)
    record = apply_service.resolve_resume(db, None, resume_id)
    if record is None:
        if resume_id is not None:
            raise ScoringUnavailable("指定的简历不存在")
        return profile, profile_text(profile), ""
    return profile, profile_text(profile), resume_prompt_text(db, record)


def build_prompt_for_texts(
    *,
    resume: str,
    title: str,
    company: str,
    city: str = "",
    salary: str = "",
    jd: str = "",
    profile: Any = None,
) -> str:
    """按统一口径拼评分提示词。

    预算控制：简历 6000 + JD 5000 ≈ 3.5k token，加提示词约 5k，是 deepseek 这类
    模型能在 60s 内完成的量级（实测 12000+8000 会触发网关 504）。
    """
    return build_scoring_prompt(
        resume=resume[:6000],
        title=title,
        company=company,
        city=city,
        salary=salary,
        jd=jd[:5000],
        # 字段名与 ProfileOut 对齐（实测：target_city / expected_salary / job_intent）。
        # 早期版本写成了 target_cities / salary_min / salary_max，永远取到空值。
        candidate_education=profile_field(profile, "education"),
        candidate_recruitment_type=profile_field(profile, "job_intent"),
        target_cities=profile_field(profile, "target_city") or profile_field(profile, "city"),
        salary_min=0,
        salary_max=expected_salary_k(profile),
    )


async def call_scoring_model(prompt: str) -> tuple[SemanticScore, str]:
    """调模型并解析，返回 ``(score, model_name)``。

    不做任何 HTTP 转换、不碰数据库：调用方自己决定失败怎么表达
    （API 路由转 502，后台任务写 ``score_error``）。
    """
    from ...database import SessionLocal
    from ..llm import create_provider
    from ..llm.base import LLMError
    from ..settings_service import get_llm_config

    config = get_llm_config(SessionLocal())
    if not (config.base_url.strip() and config.model.strip()):
        raise ScoringUnavailable("还没有配置大模型，无法评分")

    provider = create_provider(config)
    try:
        raw = await provider.chat([{"role": "user", "content": prompt}], thinking=False)
    except LLMError as exc:
        raise ScoringFailed(f"评分失败：{exc}") from exc
    except Exception as exc:  # noqa: BLE001 — 任何调用侧异常都归为「这次失败」
        raise ScoringFailed(f"评分失败：{type(exc).__name__}: {exc}") from exc

    score = parse_semantic_score(raw)
    if not score.ok:
        raise ScoringFailed(f"评分结果无法解析：{score.error}")
    return score, config.model


async def score_texts(
    db: Session,
    *,
    title: str,
    company: str,
    city: str = "",
    salary: str = "",
    jd: str = "",
    resume_id: int | None = None,
) -> tuple[SemanticScore, str]:
    """对「标题 + 公司 + JD 文本」评分，**不需要 Job 行**。

    这是备选岗位评分的入口，也是岗位评分入口的底座。返回 ``(score, model_name)``。
    """
    profile, profile_text, resume_text = resolve_resume_text(db, resume_id=resume_id)
    if not resume_text.strip() and not profile_text.strip():
        raise ScoringUnavailable("个人资料为空，无法评分")

    prompt = build_prompt_for_texts(
        resume=resume_text or profile_text,
        title=title,
        company=company,
        city=city,
        salary=salary,
        jd=jd,
        profile=profile,
    )
    # 调用模型期间不占着连接池：长连接会让并发请求排队。
    db.close()
    return await call_scoring_model(prompt)


def persist_semantic_for_job(
    session: Session, job_id: int, payload: dict[str, Any], *, model: str
) -> bool:
    """把语义评分写进 ``job_match_analysis.result`` 的 ``semantic_score`` 子键。

    不覆盖同一行的五类结论（``result`` 里其它键原样保留）：两个结论同一行不同用途。
    返回是否写入（岗位不存在时返回 False）。

    **从 ``api/job_hunt_score.py`` 下沉到这里**：导入备选岗位时也要迁移分数，
    而 service 不该反向 import API 模块。
    """
    from ..apply._match import latest_match

    job = session.get(Job, job_id)
    if job is None:
        return False

    row = latest_match(session, job_id)
    if row is None:
        from ...models.apply import JobMatchAnalysis

        row = JobMatchAnalysis(
            job_id=job.id,
            job_title=job.title,
            company=job.company,
            result={"semantic_score": payload},
            hard_gate="unknown",
            requires_confirm=False,
            model=model,
        )
        session.add(row)
    else:
        merged = dict(row.result or {})
        merged["semantic_score"] = payload
        row.result = merged
        row.model = model
    return True


__all__ = [
    "ScoringFailed",
    "ScoringUnavailable",
    "build_prompt_for_texts",
    "call_scoring_model",
    "expected_salary_k",
    "persist_semantic_for_job",
    "profile_field",
    "resolve_resume_text",
    "score_texts",
]
