# SPDX-License-Identifier: Apache-2.0
"""生成偏好（设置页）的读写：只存 AppSetting KV，与 2.0 既有的设置项同一套写法。

key 与 1.x 保持同一个字面量 ``profile_generation_preferences``：这样从 1.x 迁移过来的
数据集不必重设偏好，用户升级后看到的开关状态与升级前一致。

**读路径永远不写库**：没配置过时返回默认值（默认关闭），这样"只读一次设置"不会在
库里留下空行。脏数据（手改库、旧格式）一律退回默认关闭，而不是让生成失败。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ...models.setting import AppSetting
from ...schemas.generation_preferences import GenerationPreferences

_KEY = "profile_generation_preferences"


def get_generation_preferences(db: Session) -> GenerationPreferences:
    """读当前数据集的生成偏好；没配置过/数据损坏时返回默认值（不写库）。"""
    row = db.get(AppSetting, _KEY)
    if row is None or not (row.value or "").strip():
        return GenerationPreferences()
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        return GenerationPreferences()
    if not isinstance(data, dict):
        return GenerationPreferences()
    return GenerationPreferences.model_validate(
        {"show_tech_stack": bool(data.get("show_tech_stack", False))}
    )


def save_generation_preferences(
    db: Session, preferences: GenerationPreferences
) -> GenerationPreferences:
    """整对象落库：只写单个字段会让以后新增的偏好项被静默清空。"""
    row = db.get(AppSetting, _KEY)
    serialized = json.dumps(preferences.model_dump(), ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()
    return preferences


def show_tech_stack(db: Session) -> bool:
    """便捷读：生成/保存路径只需要一个 bool。"""
    return get_generation_preferences(db).show_tech_stack


__all__ = ["get_generation_preferences", "save_generation_preferences", "show_tech_stack"]
