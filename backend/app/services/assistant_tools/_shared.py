# SPDX-License-Identifier: Apache-2.0
"""跨工具域共享的 helper 与常量。"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ...models.job import Job
from ...schemas.profile import ProfileOut
from ..profile.ai_profile import load_ai_profile
from ..profile.profile_service import (
    legacy_profile_has_entries,
    project_legacy_profile,
)

logger = logging.getLogger(__name__)

MAX_JOB_RESULT_CHARS = 6_000
MAX_PROFILE_RESULT_CHARS = 8_000
# 简历正文专属的结果上限：与 `_RESUME_CONTENT_BUDGET` 同源（预算 + 元信息余量）。
# 不能沿用 6000 —— 那会把已按 30KB 预算保住的正文从中间切断，JSON 不完整。
MAX_RESUME_RESULT_CHARS = 36_000
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50

MAX_ASSISTANT_SKILL_FILE_CHARS = 20_000
MAX_ASSISTANT_SKILL_TOTAL_CHARS = 60_000
MAX_ASSISTANT_SKILL_FILES = 10

PROFILE_EDITABLE_FIELDS = (
    "name",
    "gender",
    "birth_year",
    "phone",
    "email",
    "city",
    "target_city",
    "job_intent",
    "personal_website",
    "github",
    "summary",
)


def _trim(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit].rstrip()}…"


def int_argument(arguments: dict[str, Any], key: str, error: str) -> int:
    """把工具参数里的整数 id 收成 `int`，缺失或不是数字时抛 `error`（中文提示）。

    工具参数是模型生成的 JSON：同一个 id 既可能给成 `"12"` 也可能给成 `12`，缺失时是
    `None`。三者要落到同一个出口——"先用 list_xxx 查"这句提示对模型来说是唯一有用的
    下一步。写成一处实现，免得二十个工具各抄一份 `try: int(...) except ...`。
    """
    value = arguments.get(key)
    if value is None:
        raise ValueError(error)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(error) from None


# 读简历时留给正文的预算（从总预算里扣掉元信息与版式那部分）。
#
# 2026-11-08 上调：旧口径是 `MAX_JOB_RESULT_CHARS - 1500` = 4500 字节，对一份正常简历
# 远远不够。实测简历 52 去掉照片后正文 10,918 字节，4500 的预算会把
# skills / projects / education **整段摘掉**——而用户这次的要求恰好是"改写项目经历"，
# 模型拿到的简历里根本没有项目，只能瞎猜路径（`projects.2/3/4` 连续失败）。
#
# 现在按「一份简历正文的真实量级」给预算（30KB ≈ 3 份满页简历的量），并**不**回收
# 到通用岗位结果上限：工具结果长度本来也不是同一种东西——岗位详情是给模型看的摘要，
# 简历正文是要被改写的工作对象，截掉它等于让任务无法完成。
_RESUME_CONTENT_BUDGET = 30_000
# v1 扁平结构（导入期 / 旧记录）沿用旧预算：`get_resume` 对它的省略语义
# （超长必须省略、`experience` 留到最后）已有测试钉住，抬预算会让那条契约失效。
_RESUME_CONTENT_BUDGET_LEGACY = MAX_JOB_RESULT_CHARS - 1_500
# 正文过长时按这个顺序**整段**省略（越靠前越先丢）：
# 荣誉 → 校园经历 → 技能 → 教育 → 经历 → 项目。
#
# 顺序的依据是「模型做改写时最不能缺什么」，不是"哪段不重要"：
# 项目与经历是改写的主体，放最后丢；技能/教育是补充信息，可以先让位。
# 旧顺序把 projects 排在倒数第二、education 排最后，实测导致"要改项目却先把项目摘了"。
_RESUME_CONTENT_DROP_ORDER = (
    "awards",
    "campus_experience",
    "skills",
    "education",
    "experience",
    "projects",
)


def _resume_content_for_model(content: dict, budget: int) -> tuple[dict, list[str]]:
    """把简历正文压进预算：超出时**整段**省略次要段落，并返回省略了哪些。

    刻意不是"从中间截断字符串"：那会让模型收到一段缺了结尾的 JSON，进而以为简历就这么多
    内容，回答时漏掉后面的经历——而用户完全看不出来。整段省略 + 明说省略了哪几段，
    模型至少知道自己没看全，可以再单独去查。

    **v2 文档结构（2026-11-08 修复）**：``_RESUME_CONTENT_DROP_ORDER`` 当初按 v1 的
    扁平结构写（顶层就是 ``projects`` / ``skills`` …），而 2.0 的文档是
    ``{"version": 2, "sections": [...]}``——顶层根本没有那些键，于是 ``key in trimmed``
    永远为假，裁剪一次都没生效（实测：410KB 正文配 4500 预算，``dropped`` 仍是空）。
    后果不是"没裁剪"这么简单：整份正文被塞进模型上下文，超限时 provider 直接报错，
    用户看到的就是助手连试几轮工具后失败。
    这里改成按 ``sections[].key`` 摘除，两种结构都认。
    """
    trimmed = dict(content)

    def _size(data: dict) -> int:
        return len(json.dumps(data, ensure_ascii=False))

    dropped: list[str] = []
    sections = trimmed.get("sections")
    if isinstance(sections, list) and _size(trimmed) > budget:
        # v2：按板块 key 摘除，其余板块原样保留（顺序、id 都不动）。
        for key in _RESUME_CONTENT_DROP_ORDER:
            if _size(trimmed) <= budget:
                break
            kept = [s for s in sections if not (isinstance(s, dict) and s.get("key") == key)]
            if len(kept) == len(sections):
                continue
            sections = kept
            trimmed = {**trimmed, "sections": sections}
            dropped.append(key)

    # v1 扁平结构（导入期 / 旧记录）：保持原行为。
    for key in _RESUME_CONTENT_DROP_ORDER:
        if _size(trimmed) <= budget:
            break
        if key in trimmed:
            trimmed.pop(key)
            dropped.append(key)
    return trimmed, dropped


def _job_brief(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "salary": job.salary,
        "status": job.status,
        "favorite": job.favorite,
        "posted_at": job.posted_at,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def _load_profile(db: Session) -> ProfileOut | None:
    """read-modify-write 用的旧形状全量快照（含 hidden/未映射字段的值）。

    工具写入口是旧 PUT 协议：拿不到隐藏字段的值，"只改一个字段"的 read-modify-write
    就会把隐藏值清空（R-67 要求值保留）。所以这里读**编辑视图**（project_legacy_profile）
    而不是消费快照；它不是发给模型的内容，不构成 AI 取数。
    """
    if not legacy_profile_has_entries(db):
        return None
    return project_legacy_profile(db)


def _profile_snapshot(db: Session) -> ProfileOut | None:
    """AI 可读资料快照：当前组 + hidden 已剔除（唯一入口见 ``profile.ai_profile``）。"""
    if not legacy_profile_has_entries(db):
        return None
    return load_ai_profile(db)
