# SPDX-License-Identifier: Apache-2.0
"""岗位匹配分析所需的个人资料与简历来源快照。

**唯一的取数口径**：`services.profile.ai_profile.load_ai_profile`——「我的资料」页
**当前选中的组** + **未隐藏字段**。单岗匹配、批量匹配、横向对比都走这里，因此三者看到
的资料永远一致；用户切组后新发起的分析自动跟随，已生成结论不受影响。

历史说明：F2 曾让三链外消费者读 `load_all_consumed_profile`（不按组限制，R-64）。
2026-10-28 用户要求统一为"当前组 + 去隐藏"，本模块随之切换；旧入口仍保留给网申重叠值
裁决等确实需要全量分区的场景，**AI 取数不得再直接使用它**。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ...models.job import Job
from ...models.profile import UserProfile
from ...schemas.profile import ProfileOut
from ...schemas.profile_projection import ConsumedProfile
from ..apply import apply_service
from ..profile.ai_profile import load_ai_profile
from ..profile.profile_service import (
    legacy_profile_is_empty,
    project_legacy_profile_from_consumed,
    to_profile_out,
)


def _is_empty_user_profile(profile: UserProfile) -> bool:
    return not any(
        [
            profile.name,
            profile.phone,
            profile.email,
            profile.summary,
            profile.job_intent,
            profile.educations,
            profile.experiences,
            profile.projects,
            profile.skills,
        ]
    )


def profile_is_empty(profile: ProfileOut | UserProfile | ConsumedProfile) -> bool:
    """判断用户是否完全没有可用于匹配的资料（旧协议口径，三种来源同一答案）。"""
    if isinstance(profile, ConsumedProfile):
        return legacy_profile_is_empty(project_legacy_profile_from_consumed(profile))
    if isinstance(profile, ProfileOut):
        return legacy_profile_is_empty(profile)
    return _is_empty_user_profile(profile)


def profile_text(profile: ProfileOut | UserProfile | ConsumedProfile) -> str:
    """序列化匹配需要的个人资料，排除照片等无关字段（旧协议字段名，提示词不变）。"""
    if isinstance(profile, ConsumedProfile):
        profile = project_legacy_profile_from_consumed(profile)
    snapshot = profile if isinstance(profile, ProfileOut) else to_profile_out(profile)
    return json.dumps(
        snapshot.model_dump(mode="json", exclude={"photo"}),
        ensure_ascii=False,
    )


def resume_prompt_text(
    db: Session | None,
    record: Any,
    *,
    job_payload_data: dict[str, Any] | None = None,
) -> str:
    """把一份简历压成**给模型看的紧凑文本**（标题 + 正文 markdown）。

    为什么不用 ``json.dumps(content)``：v2 文档是带 id / layout / placement 的富结构，
    一份正常简历序列化后能有 3 万字符，而调用方的个人文本预算只有 8000
    （``job_match._MAX_PERSONAL_CHARS``）——JSON 会把后面几个项目、专业技能、个人总结
    整段截掉，模型只看到第一个项目，于是每次招呼语都拿它举例。
    markdown 导出同一份简历只有 3–4 千字符，7 个项目全在里面。

    ``job_payload_data`` 非空时，会把「项目经历」按与这份 JD 的相关度重排并标注第一名
    （见 :mod:`jd_relevance`）；传 None（匹配分析等场景）保持简历原本的顺序。

    ``db`` 为空（纯函数上下文/脚本）时无法解析自定义字段定义，仍走 document_io 的
    默认转换路径；它只影响自定义字段的落位，不影响"内容是否完整"。
    """
    from ..resume.document_io import document_for_record, ensure_document_version
    from ..resume.markdown_export import export_markdown

    content = getattr(record, "content", None) or {}
    try:
        if db is not None:
            document, _report = document_for_record(db, record)
        else:
            document = ensure_document_version(
                content,
                language=getattr(record, "language", None),
                format_config=getattr(record, "format_config", None),
            )
        body = export_markdown(
            document,
            language=getattr(record, "language", None) or "zh-CN",
            format_config=getattr(record, "format_config", None) or {},
        )
    except Exception:  # noqa: BLE001 - 渲染失败不能连带把招呼语/匹配打断
        # 兜底：至少把纯文本字段捞出来，别让整次调用因为渲染异常而失败。
        body = json.dumps(content, ensure_ascii=False)
    if job_payload_data:
        # 按 JD 相关度重排项目：模型对"排在前面的内容"有强烈偏好，实测会举错项目。
        from .jd_relevance import reorder_projects_by_relevance

        body = reorder_projects_by_relevance(body, job_payload_data)
    title = str(getattr(record, "title", "") or "").strip()
    job_title = str(getattr(record, "job_title", "") or "").strip()
    header = f"# {title}" if title else ""
    if job_title:
        header += f"（求职意向：{job_title}）"
    return f"{header}\n\n{body}".strip()


def job_resume_text(db: Session, job: Job) -> str:
    """岗位对应简历（绑定/默认）的序列化文本；没有简历时是空串。

    单岗匹配与批量匹配共用这一处序列化，避免两条链路对"模型看到的简历"出现差异。
    产出的是**紧凑 markdown**（见 :func:`resume_prompt_text`），不是 JSON ——
    JSON 会在调用方的 8000 字预算里被截掉大半，模型看不到后面的项目。
    """
    resume = apply_service.resolve_resume(db, job.id, None)
    if resume is None:
        return ""
    return resume_prompt_text(db, resume)


def match_source_texts(
    db: Session, job: Job, *, profile: ProfileOut | UserProfile | None = None
) -> tuple[ProfileOut | UserProfile, str, str]:
    """返回岗位匹配所需的资料文本与岗位对应简历文本（当前组 + 去隐藏）。"""
    current = profile or load_ai_profile(db)
    return current, profile_text(current), job_resume_text(db, job)


__all__ = [
    "job_resume_text",
    "match_source_texts",
    "profile_is_empty",
    "profile_text",
    "resume_prompt_text",
]
