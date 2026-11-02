# SPDX-License-Identifier: Apache-2.0
"""个人资料里的「生成偏好」：当前只有一项——简历是否显示项目技术栈。

为什么存在：
- 技术栈在资料库里是事实（用于匹配、检索、面试准备），但很多岗位的简历不需要单独一行
  「技术栈：...」，用户希望按投递方向决定要不要露出来；
- 开关放资料页而不是生成弹窗，是因为它描述的是"我的资料怎么被使用"，不是单次生成的版式；
- 生成时读取，**不回溯修改已经生成的简历**——旧简历保持用户当时看到的样子。

默认关闭：老板明确要求"生成的简历里面不要带技术栈"，想露时再打开。
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from ...models.setting import AppSetting

_KEY = "profile_generation_preferences"
_DEFAULT = {"include_tech_stack": False}


def get_generation_preferences(db: Session) -> dict[str, bool]:
    """读当前数据集的生成偏好；没配置过时返回默认值（不写库）。"""
    row = db.get(AppSetting, _KEY)
    if row is None or not (row.value or "").strip():
        return dict(_DEFAULT)
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        return dict(_DEFAULT)
    if not isinstance(data, dict):
        return dict(_DEFAULT)
    return {"include_tech_stack": bool(data.get("include_tech_stack", False))}


def save_generation_preferences(db: Session, *, include_tech_stack: bool) -> dict[str, bool]:
    value = {"include_tech_stack": bool(include_tech_stack)}
    row = db.get(AppSetting, _KEY)
    serialized = json.dumps(value, ensure_ascii=False)
    if row is None:
        db.add(AppSetting(key=_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()
    return value


__all__ = ["get_generation_preferences", "save_generation_preferences"]
