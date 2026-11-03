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
# 技术栈也可能接在正文末尾（「……。技术栈：Docker、Caddy」），不是独立行。
_INLINE_LABEL_RE = re.compile(
    r"(?:[；;。]\s*)?(?:技术栈(?:/工具)?|tech\s*stack)\s*[：:][^。\n]*[。]?",
    re.IGNORECASE,
)


def _drop_label_lines(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    cleaned: list[str] = []
    for raw in value:
        line = str(raw or "")
        if _LABEL_RE.match(line):
            continue
        line = _INLINE_LABEL_RE.sub("", line)
        if line:
            cleaned.append(line)
    return cleaned


def _is_tech_stack_item(item: dict[str, Any]) -> bool:
    if item.get("kind") not in {"field", "list"}:
        return False
    if str(item.get("key") or "") == "tech_stack":
        return True
    source = item.get("source")
    return isinstance(source, dict) and str(source.get("field_id") or "").endswith(
        ".tech_stack"
    )


def strip_resume_tech_stack(content: dict[str, Any]) -> dict[str, Any]:
    """返回去掉技术栈后的简历 dict（原地修改调用方传入的 dict 并返回）。

    同时支持两代结构：
    - v1：``projects[].tech_stack`` + description/highlights 里的「技术栈：」行；
    - v2：``sections[].entries[].items[]`` 里的 ``tech_stack`` 列表项与
      ``source.field_id`` 指向技术栈的字段项。v2 用 ``placement=hidden`` 保留数据
      （编辑器仍能恢复），而不是删除条目。
    """
    projects = content.get("projects")
    if isinstance(projects, list):
        for project in projects:
            if not isinstance(project, dict):
                continue
            project["tech_stack"] = []
            for field in ("description", "highlights"):
                if field in project:
                    project[field] = _drop_label_lines(project[field])

    sections = content.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            for entry in section.get("entries") or []:
                if not isinstance(entry, dict):
                    continue
                for item in entry.get("items") or []:
                    if not isinstance(item, dict):
                        continue
                    if _is_tech_stack_item(item):
                        item["placement"] = "hidden"
                        item["hidden_from"] = "trail"
                    elif item.get("kind") == "text":
                        item["text"] = "\n".join(
                            _drop_label_lines(str(item.get("text") or "").splitlines())
                        )
    return content


__all__ = ["strip_resume_tech_stack"]
