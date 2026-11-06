# SPDX-License-Identifier: Apache-2.0
"""生成结果收口：同名项目/经历条目按身份合并（**无损**）。

模型在长提示词 + 质量重试后偶尔会把同一个项目写两遍（名称完全相同、要点不同），
纸面上就会出现两段「民生消费类内容账号」。这里做确定性收口：按身份键合并条目，
要点取并集——**不减少条目数量、不删条目、不按篇幅裁剪**。

与篇幅控制的分工（E15，硬约束）：

- 本模块只做**合并**。同一身份的两条合成一条，条目数只减于"真的是同一条被写了两遍"；
- 篇幅裁剪由 ``resume_space_gate.finalize_page_budget``（行预算）与导出层的按页收敛
  负责，两者与本模块**没有任何调用关系**；
- 1.x 曾把两者塞进同一个函数（``dedupe_and_limit_resume``），结果出现"点一次 AI 修订
  少一个项目"的事故。2.0 不设那个包装函数。

经历的身份是 ``(company, role, period)`` 复合键：只按 company 会把同公司两段不同职位的
任职合并成一条，晋升经历直接消失。v1 没有 ``period`` 属性，用 ``start_date``/``end_date``。

只作用于**生成落库**（``resume_record.save_record``）：用户手工编辑与 AI 修订不走这里。
"""

from __future__ import annotations

import re
from typing import Any

from ...schemas.resume_document import MAX_LIST_VALUES

_NORM_RE = re.compile(r"\s+")

#: v2 分区 key -> 条目身份字段（field item 的 key）。
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
    # 合并后的列表可能超过 schema 上限（实测两条各 500 值的同名项目合并成 1000
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


def _dedupe_v1_list(items: list[Any], identity: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    index: dict[tuple[str, ...], int] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = tuple(_norm(raw.get(field)) for field in identity)
        if not any(key):
            # 身份字段全空 = 认不出是谁：原样保留，绝不因为"匹配不上"而丢用户内容。
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


def dedupe_resume(
    content: dict[str, Any], *, sections: tuple[str, ...] = ("projects", "experience")
) -> dict[str, Any]:
    """按身份合并同名条目，要点取并集。无损：不删条目；原地修改并返回。

    ``sections`` 限定作用的分区（默认项目与经历）；v1 顶层列表与 v2 ``sections``
    数组同时处理。
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


__all__ = ["dedupe_resume"]
