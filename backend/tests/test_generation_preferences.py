# SPDX-License-Identifier: Apache-2.0
"""生成偏好接口：默认关、整对象读写、脏数据退回默认。

`show_tech_stack` 默认必须是 False（老板的明确要求：生成的简历不要带技术栈），
所以这里既守默认值，也守"存进去的只影响这个字段、读回来一型不差"。
"""

from app.services.profile.generation_preferences import (
    get_generation_preferences,
    save_generation_preferences,
    show_tech_stack,
)
from app.schemas.generation_preferences import GenerationPreferences


def test_default_is_off_without_writing_anything(db_session):
    """没配置过时读默认值，且读路径不往库里写行。"""
    preferences = get_generation_preferences(db_session)

    assert preferences.show_tech_stack is False
    assert show_tech_stack(db_session) is False


def test_roundtrip_saves_and_reads_back(db_session):
    save_generation_preferences(db_session, GenerationPreferences(show_tech_stack=True))

    assert get_generation_preferences(db_session).show_tech_stack is True
    assert show_tech_stack(db_session) is True

    save_generation_preferences(db_session, GenerationPreferences(show_tech_stack=False))
    assert show_tech_stack(db_session) is False


def test_corrupt_setting_falls_back_to_default(db_session):
    """脏数据（手改库 / 旧格式）不能把生成打挂，退回默认关。"""
    from app.models.setting import AppSetting

    db_session.merge(AppSetting(key="profile_generation_preferences", value="{not json"))
    db_session.commit()

    assert get_generation_preferences(db_session).show_tech_stack is False
