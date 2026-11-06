# SPDX-License-Identifier: Apache-2.0
"""生成偏好：当前只有一项——简历是否单独显示项目技术栈。

为什么存在：
- 技术栈在资料库里是事实（用于匹配、检索、面试准备），但很多岗位的简历不需要单独一行
  「技术栈：…」，用户希望按投递方向决定要不要露出来；
- 开关放设置页而不是生成弹窗，是因为它描述的是"我的资料怎么被使用"，不是单次生成的版式；
- 生成时读取，**不回溯修改已经生成的简历**——旧简历保持用户当时看到的样子。

**默认关闭**：老板明确要求"生成的简历里面不要带技术栈"，想露时再打开。
关闭的含义是"不上纸面"，不是删除数据：v2 用 ``placement=hidden`` 保留，
编辑器里仍能看到、能拖回来。
"""

from __future__ import annotations

from pydantic import BaseModel


class GenerationPreferences(BaseModel):
    """生成偏好整对象（读写同一形状，避免"只改一项把别的项静默清空"）。"""

    show_tech_stack: bool = False


__all__ = ["GenerationPreferences"]
