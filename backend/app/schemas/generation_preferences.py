# SPDX-License-Identifier: Apache-2.0
"""个人资料 → 生成偏好。"""

from pydantic import BaseModel


class GenerationPreferencesOut(BaseModel):
    include_tech_stack: bool = False


class GenerationPreferencesIn(BaseModel):
    include_tech_stack: bool


__all__ = ["GenerationPreferencesIn", "GenerationPreferencesOut"]
