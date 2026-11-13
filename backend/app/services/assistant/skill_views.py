# SPDX-License-Identifier: Apache-2.0
"""技能响应视图：列表行与详情（知识文件正文按总量上限截断）。

这两个函数原来长在 ``api/skills.py``。``services/actions`` 的 ``read_skill`` 也要
同一份视图，而服务层不能反向 import 路由模块，所以视图跟着服务走——
"一条技能对外长什么样"只有这一份实现，工具侧与路由侧不会各拼一套。
"""

from __future__ import annotations

from ...models.assistant import AssistantSkill
from ...schemas.skill import (
    MAX_SKILL_DETAIL_FILE_CHARS,
    AssistantSkillDetail,
    AssistantSkillOut,
)


def _is_builtin(skill: AssistantSkill) -> bool:
    """这条技能是不是随包内置的（二开 2026-11-10）。

    判据是"同名包是否存在"而不是额外加一列：内置技能由 `seed_builtin_skills` 按包名
    注册，用户即使改过它的提示词，名字仍是包里的那个——界面上依旧该标「推荐」
    （它确实来自产品自带）。**不落库**是为了不给 assistant_skill 加迁移。
    """
    from .builtin_skills import builtin_skill_names

    return skill.name in builtin_skill_names()


def skill_out(skill: AssistantSkill) -> AssistantSkillOut:
    return AssistantSkillOut(
        id=skill.id,
        name=skill.name,
        description=skill.description,
        enabled=skill.enabled,
        source_name=skill.source_name,
        prompt_chars=len(skill.prompt),
        files=[item.path for item in skill.files],
        # 二开（2026-11-10）：内置技能标「推荐」，界面据此提示"默认没打开，要用请启用"。
        builtin=_is_builtin(skill),
        updated_at=skill.updated_at,
        # 0016（#31D/E）：技能学习四段内容 / 版本 / 验证状态，前端据此显示「待验证」徽标。
        when_to_use=skill.when_to_use or "",
        steps=skill.steps or "",
        pitfalls=skill.pitfalls or "",
        version=int(skill.version or 1),
        generated=bool(skill.generated),
        validation_status=skill.validation_status or "",
        last_loaded_at=skill.last_loaded_at,
    )


def skill_detail(skill: AssistantSkill) -> AssistantSkillDetail:
    """详情视图：带上知识文件正文，但按总量上限截断并标记 ``files_truncated``。"""
    budget = MAX_SKILL_DETAIL_FILE_CHARS
    truncated = False
    file_details = []
    for item in skill.files:
        content = item.content or ""
        if len(content) > budget:
            content = content[: max(budget, 0)]
            truncated = True
        budget -= len(content)
        file_details.append({"path": item.path, "size_bytes": item.size_bytes, "content": content})
    return AssistantSkillDetail(
        **skill_out(skill).model_dump(),
        prompt=skill.prompt,
        file_details=file_details,
        files_truncated=truncated,
    )


__all__ = ["skill_detail", "skill_out"]
