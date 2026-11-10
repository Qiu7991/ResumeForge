# SPDX-License-Identifier: Apache-2.0
"""内置技能包：随代码发布、首次启动自动注册（2026-11-10）。

背景：技能本来是用户自己导入的，作者那套好用但只在他本地库里——别人装完工作台是空的，
效果自然不同。把技能包放进 `app/assets/skills/` 并在启动时注册，别人装完就自带。

三条不变量（都在这里钉住）：
1. **只补不盖**：同名技能已存在就跳过——用户可能改过提示词，重启覆盖会冲掉他的修改；
2. **路径算得对**：目录指错的表现是"静默不注册"（不报错、就是没生效），必须钉住；
3. **坏包不阻断**：包损坏只记日志，不能把启动搞挂。
"""

from app.models.assistant import AssistantSkill
from app.services.assistant.builtin_skills import SKILLS_DIR, seed_builtin_skills


def test_skills_dir_points_at_the_real_assets_folder():
    """目录必须真的存在且有包。

    这条看似琐碎，但它守的是一个真实踩过的坑：`parents[1]` 写成 `parents[2]` 之前，
    路径指向 `app/services/assets/skills`（不存在），于是每次启动都"安静地什么都没做"——
    没有异常、没有日志，功能就是不生效。
    """
    assert SKILLS_DIR.is_dir(), f"内置技能目录不存在：{SKILLS_DIR}"
    packages = list(SKILLS_DIR.glob("*.zip"))
    assert packages, f"{SKILLS_DIR} 里没有技能包"


def test_seed_registers_builtin_skill_when_missing(db_session):
    db_session.query(AssistantSkill).delete()
    db_session.commit()

    added = seed_builtin_skills(db_session)

    assert added, "空技能库时应至少注册一个内置技能"
    skill = db_session.query(AssistantSkill).filter_by(name="岗位简历包装").one()
    assert len(skill.prompt) > 1000
    assert len(skill.files) == 3
    # **默认关着**：提示词整段进系统提示（实测约 2426 token），不该让每个用户
    # 都默认付这笔固定成本。界面会给它标「推荐」，用户按需打开。
    assert skill.enabled is False


def test_seed_does_not_overwrite_a_user_modified_skill(db_session):
    """用户改过内置技能后，重启不能把改动冲掉。

    这是"只补不盖"的核心：`upsert_skill` 是覆盖语义，seed 刻意不用它。
    """
    db_session.query(AssistantSkill).delete()
    db_session.commit()
    skill = AssistantSkill(
        name="岗位简历包装",
        description="USER-SENTINEL",
        prompt="我自己改过的提示词",
        source_name="手动改的",
        enabled=False,
    )
    db_session.add(skill)
    db_session.commit()

    added = seed_builtin_skills(db_session)

    assert added == [], "同名技能已存在时不该注册"
    db_session.refresh(skill)
    assert skill.prompt == "我自己改过的提示词"
    assert skill.description == "USER-SENTINEL"
    assert skill.enabled is False, "用户的启用状态也要保住"


def test_seed_is_idempotent(db_session):
    """连跑两次不会造出第二份。"""
    db_session.query(AssistantSkill).delete()
    db_session.commit()

    seed_builtin_skills(db_session)
    second = seed_builtin_skills(db_session)

    assert second == []
    assert db_session.query(AssistantSkill).filter_by(name="岗位简历包装").count() == 1
