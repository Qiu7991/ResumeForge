# SPDX-License-Identifier: Apache-2.0
"""生成结果收口：同名项目/公司去重（无损）与按页数收敛条目数量（有损）拆成两步。

模型在长提示词 + 质量重试后偶尔会把同一个项目写两遍（名称完全相同、要点不同），
纸面上就会出现两段「民生消费类内容账号」。这里做确定性收口：

- :func:`dedupe_resume` 按身份合并条目，要点取并集——**无损**：不截断、不删条目。
  经历的身份是 ``(company, role, period)`` 复合键：只按 company 会把同公司两段不同
  职位的任职合并成一条，晋升经历直接消失（P10）。
- :func:`limit_resume` 按页数保留最前面的 N 条——**有损**：只允许**生成**路径调用；
  AI 修订/手工保存绝不走它（点一次「AI 修订」少一个项目就是事故，P9）。
- :func:`dedupe_and_limit_resume` 是兼容包装（dedupe + limit），只服务既有生成调用点；
  修订路径必须直接调 :func:`dedupe_resume`。

只作用于**生成落库**，用户手工编辑不走这里。
"""

from __future__ import annotations

import re
from typing import Any

from ...schemas.resume_document import MAX_LIST_VALUES

_NORM_RE = re.compile(r"\s+")

_PROJECT_LIMITS = {1: 3, 2: 5}
_EXPERIENCE_LIMITS = {1: 2, 2: 3}
_LONG_PROJECT_LIMIT = 6
_LONG_EXPERIENCE_LIMIT = 4

#: v2 分区 key -> 条目身份字段（field item 的 key）。经历必须复合身份（P10）。
_V2_IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "projects": ("name",),
    "experience": ("company", "role", "period"),
    # 旧请求里出现过的复数别名，与旧行为保持一致。
    "experiences": ("company", "role", "period"),
}

#: v1 顶层列表 -> 条目身份字段。v1 经历没有 period 属性，时间段是 start_date/end_date。
_V1_IDENTITY_KEYS: dict[str, tuple[str, ...]] = {
    "projects": ("name",),
    "experience": ("company", "role", "start_date", "end_date"),
}


def _norm(value: Any) -> str:
    return _NORM_RE.sub("", str(value or "")).casefold()


def _unique_lines(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = _norm(value) if isinstance(value, (str, int, float)) else repr(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    # P8：合并后的列表可能超过 schema 上限（实测两条各 500 值的同名项目合并成 1000
    # > MAX_LIST_VALUES=500）——落库成功但下次读取直接 422。这里统一守住上限。
    return result[:MAX_LIST_VALUES]


def _merge_dict_items(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """合并两个 v1 条目：列表字段取并集，标量只补空。"""
    merged = dict(base)
    for key, value in extra.items():
        current = merged.get(key)
        if isinstance(current, list) and isinstance(value, list):
            merged[key] = _unique_lines([*current, *value])
        elif not current and value:
            merged[key] = value
    return merged


def _dedupe_v1_list(
    items: list[Any], identity: tuple[str, ...]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    index: dict[tuple[str, ...], int] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = tuple(_norm(raw.get(field)) for field in identity)
        if not any(key):
            result.append(raw)
            continue
        if key not in index:
            index[key] = len(result)
            result.append(raw)
        else:
            result[index[key]] = _merge_dict_items(result[index[key]], raw)
    return result


def _dedupe_v2_entry_items(
    base: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    merged = [dict(item) for item in base]
    for item in extra:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind")
        key = item.get("key")
        if kind == "text":
            text = _norm(item.get("text"))
            if text and not any(
                current.get("kind") == "text" and _norm(current.get("text")) == text
                for current in merged
            ):
                merged.append(dict(item))
            continue
        same = next(
            (
                current
                for current in merged
                if current.get("kind") == kind and current.get("key") == key
            ),
            None,
        )
        if same is None:
            merged.append(dict(item))
            continue
        if kind == "list":
            same["values"] = _unique_lines(
                [*(same.get("values") or []), *(item.get("values") or [])]
            )
        elif kind == "field" and not str(same.get("value") or "").strip():
            same["value"] = item.get("value") or ""
    return merged


def _v2_entry_identity(entry: dict[str, Any], identity: tuple[str, ...]) -> tuple[str, ...]:
    """条目的复合身份：按 identity 里的字段 key 取第一个 field item 的值。"""
    values: dict[str, str] = {}
    for item in entry.get("items") or []:
        if isinstance(item, dict) and item.get("kind") == "field":
            key = str(item.get("key") or "")
            if key in identity and key not in values:
                values[key] = str(item.get("value") or "")
    return tuple(_norm(values.get(field)) for field in identity)


def _dedupe_v2_section(section: dict[str, Any], identity: tuple[str, ...]) -> None:
    entries = section.get("entries")
    if not isinstance(entries, list):
        return
    result: list[dict[str, Any]] = []
    index: dict[tuple[str, ...], int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = _v2_entry_identity(entry, identity)
        if not any(key):
            result.append(entry)
            continue
        if key not in index:
            index[key] = len(result)
            result.append(entry)
            continue
        base = result[index[key]]
        # 优先保留可见、内容更多的那一条作为承载条目。
        if base.get("hidden") and not entry.get("hidden"):
            base, entry = entry, base
        base["items"] = _dedupe_v2_entry_items(
            [item for item in (base.get("items") or []) if isinstance(item, dict)],
            [item for item in (entry.get("items") or []) if isinstance(item, dict)],
        )
        result[index[key]] = base
    section["entries"] = result


def _limits(page_limit: int | None) -> tuple[int, int]:
    if page_limit is None:
        return _LONG_PROJECT_LIMIT, _LONG_EXPERIENCE_LIMIT
    if page_limit <= 1:
        return _PROJECT_LIMITS[1], _EXPERIENCE_LIMITS[1]
    if page_limit <= 2:
        return _PROJECT_LIMITS[2], _EXPERIENCE_LIMITS[2]
    return _LONG_PROJECT_LIMIT, _LONG_EXPERIENCE_LIMIT


def _truncate(content: dict[str, Any], project_limit: int, experience_limit: int) -> None:
    """按上限截前 N 条（有损）；仅由 limit_resume / 兼容包装调用。"""
    projects = content.get("projects")
    if isinstance(projects, list):
        content["projects"] = projects[:project_limit]
    experiences = content.get("experience")
    if isinstance(experiences, list):
        content["experience"] = experiences[:experience_limit]

    sections = content.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            key = str(section.get("key") or "")
            if key not in {"projects", "experience", "experiences"}:
                continue
            entries = section.get("entries")
            if isinstance(entries, list):
                limit = project_limit if key == "projects" else experience_limit
                section["entries"] = entries[:limit]


def dedupe_resume(
    content: dict[str, Any], *, sections: tuple[str, ...] = ("projects", "experience")
) -> dict[str, Any]:
    """按身份合并同名条目，要点取并集。无损：不截断、不删条目；原地修改并返回。

    ``sections`` 限定作用的分区（默认项目与经历）；v1 顶层列表与 v2 ``sections``
    数组同时处理。**修订路径只允许调这个函数**——它绝不减少条目数量。
    """
    for key in sections:
        items = content.get(key)
        if isinstance(items, list):
            content[key] = _dedupe_v1_list(items, _V1_IDENTITY_KEYS[key])

    section_list = content.get("sections")
    if isinstance(section_list, list):
        for section in section_list:
            if not isinstance(section, dict):
                continue
            key = str(section.get("key") or "")
            identity = _V2_IDENTITY_KEYS.get(key)
            if identity is None:
                continue
            if key == "experiences":
                if "experience" not in sections:
                    continue
            elif key not in sections:
                continue
            _dedupe_v2_section(section, identity)
    return content


def limit_resume(content: dict[str, Any], *, page_limit: int) -> dict[str, Any]:
    """按页数截断条目数量。有损：**只用于生成路径**（1 页 3 项目/2 经历；2 页 5/3；更长 6/4）。"""
    project_limit, experience_limit = _limits(page_limit)
    _truncate(content, project_limit, experience_limit)
    return content


def dedupe_and_limit_resume(
    content: dict[str, Any], *, page_limit: int | None = None
) -> dict[str, Any]:
    """兼容包装（旧签名逐字保留）：dedupe_resume + 按页数限量。

    ``page_limit=None`` 沿用旧行为＝长简历上限（6/4）。新代码请直接用
    :func:`dedupe_resume` / :func:`limit_resume`；修订路径只允许 dedupe_resume。
    """
    content = dedupe_resume(content)
    project_limit, experience_limit = _limits(page_limit)
    _truncate(content, project_limit, experience_limit)
    return content


__all__ = ["dedupe_and_limit_resume", "dedupe_resume", "limit_resume"]
