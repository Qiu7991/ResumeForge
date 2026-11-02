# SPDX-License-Identifier: Apache-2.0
"""按「我的资料 → 生成偏好」决定简历里是否出现项目技术栈。

模型偶尔会把「技术栈：...」也写进 description/highlights，所以除了清空
``projects[].tech_stack``，还要把这类单独成行的标签行去掉；只删整行以
「技术栈 / 技术栈工具 / Tech Stack」开头的行，不碰正文里自然提到的技术名词。
"""

from __future__ import annotations

import re
from typing import Any

_LABEL_RE = re.compile(
    r"^\s*(?:技术栈(?:/工具)?|tech\s*stack)\s*[：:]\s*",
    re.IGNORECASE,
)


def _drop_label_lines(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [line for line in value if not _LABEL_RE.match(str(line or ""))]


def strip_resume_tech_stack(content: dict[str, Any]) -> dict[str, Any]:
    """返回去掉技术栈后的简历 dict（原地修改调用方传入的 dict 并返回）。"""
    projects = content.get("projects")
    if not isinstance(projects, list):
        return content
    for project in projects:
        if not isinstance(project, dict):
            continue
        project["tech_stack"] = []
        for field in ("description", "highlights"):
            if field in project:
                project[field] = _drop_label_lines(project[field])
    return content


__all__ = ["strip_resume_tech_stack"]
