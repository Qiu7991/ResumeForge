# SPDX-License-Identifier: Apache-2.0
"""内置技能包：随代码发布的技能，首次启动自动注册（2026-11-10）。

## 为什么需要它

技能（`assistant_skill`）本来是**用户自己导入**的：工作台 →「导入技能」→ 选 .zip。
作者本地有一套自己写的技能，效果很好，但那只存在于他的数据库里——别人装上项目后
工作台是空的，效果自然不同。

把技能包放进 `app/assets/skills/` 并在启动时注册，别人装完就自带同一套技能。

## 三条纪律

1. **只补不盖**：同名技能已存在就跳过。用户可能改过内置技能的提示词，也可能导入过
   更新的版本——启动时覆盖会把他的修改冲掉，而他不会想到是"重启"干的。
   （`upsert_skill` 是覆盖语义，这里刻意不用它。）
2. **失败不阻断启动**：技能包损坏只记日志。技能是增强功能，不该让整个应用起不来。
3. **幂等**：每次启动都跑一遍，已注册的判断靠名字，重复执行没有副作用。

## 用户能删掉它吗

能。删掉后下次启动会重新注册——这是刻意的：内置技能属于"产品自带能力"，
不是用户数据。真不想要就在工作台里关掉开关（`enabled=False` 会被保留）。
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ..skill_archive import parse_zip_skill

logger = logging.getLogger(__name__)

#: 内置技能包所在目录：``app/assets/skills``。与其它随包资源（lili / toutou）同级。
#: **parents[2] = app/**：本文件在 ``app/services/assistant/`` 下，数错一层就会指向
#: ``app/services/assets``（那个目录不存在，于是"静默不注册"——第一版就这么错过）。
SKILLS_DIR = Path(__file__).resolve().parents[2] / "assets" / "skills"


def seed_builtin_skills(db: Session) -> list[str]:
    """把 ``assets/skills/*.zip`` 注册进库；返回**本次新注册**的技能名。

    已存在的同名技能跳过（见模块说明第 1 条）。任何单包的解析失败只记日志、
    继续处理下一个——一个坏包不该让其它技能也装不上。
    """
    if not SKILLS_DIR.is_dir():
        return []

    # 延迟导入：本模块在启动期被调用，顶层导入会把 models/schemas 拉进装配顺序。
    from ...models.assistant import AssistantSkill
    from ..skill_archive import SkillImportError

    added: list[str] = []
    for package in sorted(SKILLS_DIR.glob("*.zip")):
        try:
            parsed = parse_zip_skill(package, package.name)
        except SkillImportError as exc:
            logger.warning("内置技能包解析失败，已跳过：%s（%s）", package.name, exc)
            continue
        except Exception:  # noqa: BLE001 - 坏包不该让启动失败
            logger.exception("内置技能包读取异常，已跳过：%s", package.name)
            continue

        exists = db.query(AssistantSkill).filter(AssistantSkill.name == parsed.name).first()
        if exists is not None:
            # 已存在（可能是用户改过的版本）：**不覆盖**，只在 debug 里留一笔。
            logger.debug("内置技能已存在，跳过：%s", parsed.name)
            continue

        from ...models.assistant import AssistantSkillFile

        skill = AssistantSkill(
            name=parsed.name,
            description=parsed.description,
            prompt=parsed.prompt,
            source_name=parsed.source_name,
            # **默认关着**（2026-11-10）：技能提示词会整段进系统提示，实测这条占
            # ~2426 token（3408 字），一直开着等于每次对话都白花这笔固定成本。
            # 用户在「工作台」里按需打开即可（界面会给它标「推荐」）。
            enabled=False,
            files=[
                AssistantSkillFile(path=path, content=content, size_bytes=len(content))
                for path, content in parsed.files
            ],
        )
        db.add(skill)
        added.append(parsed.name)

    if added:
        db.commit()
        logger.info("已注册内置技能：%s", "、".join(added))
    return added


def builtin_skill_names() -> set[str]:
    """内置技能的名字集合（从包解析出来，**不查库**）。

    界面用它判断"这条技能是不是产品自带的"，从而标「推荐」。解析失败时返回空集——
    只是少一个标签，不该让技能列表接口挂掉。

    结果按进程缓存：包内容不会在运行时变，每次列表都解一遍 zip 是浪费。
    """
    global _NAMES_CACHE
    if _NAMES_CACHE is not None:
        return _NAMES_CACHE
    names: set[str] = set()
    if SKILLS_DIR.is_dir():
        for package in SKILLS_DIR.glob("*.zip"):
            try:
                names.add(parse_zip_skill(package, package.name).name)
            except Exception:  # noqa: BLE001 - 解析失败只是少一个标签
                logger.debug("内置技能包解析失败（忽略）：%s", package.name, exc_info=True)
    _NAMES_CACHE = names
    return names


_NAMES_CACHE: set[str] | None = None


__all__ = ["SKILLS_DIR", "builtin_skill_names", "seed_builtin_skills"]
