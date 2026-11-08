# SPDX-License-Identifier: Apache-2.0
"""内置板块的「从资料补上这段」：把资料条目确定性转成 v2 entry 并插入简历。

**为什么单独成模块**（2026-11-08）：

`resume_profile_append` 只支持**自建板块**——它的取数口径是
``project_paper_content(...).custom_sections``，而 ``build_custom_section_items``
只认 v1 自建条目的 text/lines 结构。内置板块（projects / experience / education…）
有各自的强类型结构（name/role/tech_stack/highlights…），走不通那条路。

后果：用户在「未收录」清单里看到「项目经历 · 8 条」（后端的 ``builtin_entry_ids``
确实定位到了这 8 条资料的 id），点「去制作台添加」后到制作台又找不到「补这段」入口，
等于死路。而 ``entry_ids`` 一旦传给自建板块的补入函数，还会报
「有 1 条资料已删除或不在当前资料组里」——那句话是**错的**，资料明明在。

**实现取向：复用生成链的转换器，不手写第二套映射。**

``document_converter.convert_content`` 已经把 v1 ``ResumeContent`` 转成 v2 文档，
生成链路就是走它。这里把**单条资料**包成一份最小 v1 content 交给它，取出对应的
entry。好处：

1. 字段位置（title / meta / trail / body）、列表项切分、稳定 id 全部与生成结果一致——
   否则"补进来的项目"和"生成的项目"会长得不一样；
2. ``stable_object_id`` 让同一份资料在任何简历里都得到同一个 entry id，
   重复点补入不会写出第二条（幂等由 id 保证，不靠名字模糊匹配）。
"""

from __future__ import annotations

from typing import Any

from ...schemas.profile_projection import ConsumedProfile, ConsumedSection
from .document_converter import convert_content

#: 内置板块 key → v1 ResumeContent 的列表属性名。
#: 与 `document_converter._V1_LIST_ATTRS` 同源；这里只列"能从资料补入"的那些。
BUILTIN_SECTIONS: dict[str, str] = {
    # 键必须是**资料侧**的分区键（与 `ConsumedProfile.section()` 同口径）。
    # 注意 experience / education / campus_experience 在资料侧是**复数**
    # （experiences / educations / campus_experiences），与简历侧字段名不同——
    # 2026-11-08 实测：用单数查不到分区，报"资料已删除"，而资料明明在。
    "educations": "education",
    "experiences": "experience",
    "projects": "projects",
    "campus_experiences": "campus_experience",
    "awards": "awards",
    "publications": "publications",
    "research_projects": "research_projects",
    "patents": "patents",
    "credentials": "credentials",
}

#: 各板块的身份字段（资料侧 field_id 的后缀）：用于「这条已经写进简历了吗」。
#: 与 `resume_coverage._SECTION_MAP` 的身份字段口径一致。
IDENTITY_FIELDS: dict[str, str] = {
    # 同样按**资料侧**键。身份字段是"这条是不是同一条"的判据。
    "educations": "school",
    "experiences": "company",
    "projects": "name",
    "campus_experiences": "organization",
    "awards": "name",
    "publications": "title",
    "research_projects": "name",
    "patents": "name",
    "credentials": "name",
}


def supports_builtin(section_key: str) -> bool:
    return section_key in BUILTIN_SECTIONS


def _section_of(consumed: ConsumedProfile, section_key: str) -> ConsumedSection | None:
    return consumed.section(section_key)


def _entry_values(entry: Any) -> dict[str, str]:
    """把消费条目的 ``{field_id: 文本}`` 摊平成 ``{字段名: 文本}``。

    消费快照的键是 ``<分区>.<字段>``（如 ``projects.name``），这里剥掉前缀——
    v1 ``ResumeContent`` 的字段名不带分区。
    """
    prefix = ""
    out: dict[str, str] = {}
    for field_id, value in (getattr(entry, "values", None) or {}).items():
        key = str(field_id)
        if "." in key:
            prefix = key.split(".", 1)[0]
            key = key.split(".", 1)[1]
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out[key] = text
    _ = prefix
    return out


def _legacy_entry(values: dict[str, str], section_key: str) -> dict[str, Any]:
    """把摊平后的字段值还原成 v1 列表条目的形状（交给转换器）。"""
    entry: dict[str, Any] = {}
    for key, value in values.items():
        # 列表型字段在 v1 里是数组：tech_stack / highlights / description / outcomes …
        if key in {"tech_stack", "highlights", "description", "outcomes", "responsibilities", "courses"}:
            entry[key] = [part for part in value.split("\n") if part.strip()]
        else:
            entry[key] = value
    # 转换器要求 description 是数组（字符串会触发 pydantic 校验失败）。
    entry.setdefault("description", [])
    _ = section_key
    return entry


def _rekey_entry(entry: dict[str, Any], section_key: str, entry_id: str) -> dict[str, Any]:
    """把转换器产出的 id 换成**由 entry_id 派生**的稳定 id。

    为什么必须重写：转换器用 ``stable_object_id("ob_", key, scope)`` 派生 entry id，
    而 ``scope`` 是"在本次输入里的序号"。我们每次只喂**单条**资料，序号永远是 0，
    于是两个不同项目会拿到同一个 id（实测：'AI 简历工作台' 与
    'CreatorDistill…' 都是 ``ob_80e2b4e2bacba15f``）——插入文档后 id 冲突，
    后续按 id 定位、去重、保存全都会错。

    改成以 entry_id 为输入派生：同一份资料在任何一份简历里都是同一个 id，
    既满足确定性，又天然幂等（重复补入同一条 = 同一个 id = 不会写出第二条）。
    """
    from .document_conversion_types import stable_object_id

    new_entry_id = stable_object_id("ob_", section_key, entry_id)
    items: list[dict[str, Any]] = []
    for index, item in enumerate(entry.get("items") or []):
        if not isinstance(item, dict):
            continue
        # item id 同样从 (entry_id, 序号) 派生：同一份资料的同一字段永远同一个 id。
        item_id = stable_object_id("it_", section_key, entry_id, index)
        items.append({**item, "id": item_id})
    return {**entry, "id": new_entry_id, "items": items}


def build_builtin_entries(
    consumed: ConsumedProfile, section_key: str, entry_ids: list[str]
) -> dict[str, dict[str, Any]]:
    """把指定的资料条目转成 v2 entry dict（``entry_id -> entry``）。

    返回空 dict 表示：板块不支持 / 快照里没这个分区 / 这些 id 都不在。
    调用方据此区分"资料已删除"与"这个板块压根不支持补入"。
    """
    if section_key not in BUILTIN_SECTIONS:
        return {}
    section = _section_of(consumed, section_key)
    if section is None:
        return {}
    wanted = {str(item) for item in entry_ids if str(item).strip()}
    if not wanted:
        return {}

    result: dict[str, dict[str, Any]] = {}
    for entry in section.entries:
        entry_id = str(getattr(entry, "entry_id", "") or "")
        if entry_id not in wanted:
            continue
        values = _entry_values(entry)
        if not values:
            continue
        legacy = _legacy_entry(values, section_key)
        # 用转换器生成 entry：与生成链完全同源，字段位置与列表切分都一致。
        # 注意 v1 入参用**简历侧**属性名（`experience` 单数），转换器输出也用简历侧
        # 分区 key；而 `section_key` 是资料侧（`experiences`）。两边必须分开取。
        document, _report = convert_content(
            {"version": 1, "language": "zh-CN", BUILTIN_SECTIONS[section_key]: [legacy]},
            language="zh-CN",
        )
        target = next((s for s in document.sections if s.key == BUILTIN_SECTIONS[section_key]), None)
        if target is None or not target.entries:
            continue
        payload = target.entries[0].model_dump(mode="json")
        result[entry_id] = _rekey_entry(payload, section_key, entry_id)
    return result


def identity_of(entry: dict[str, Any], section_key: str) -> str:
    """v2 entry 的身份名：身份字段的值（用于「已在简历里就跳过」）。

    取不到身份字段时退回首个文本项——与 `resume_profile_append._document_entry_name`
    同一口径，两处必须一致，否则"已存在"会被判成"不存在"而写出重复条目。
    """
    want = IDENTITY_FIELDS.get(section_key, "name")
    items = entry.get("items") or []
    for item in items:
        if isinstance(item, dict) and item.get("key") == want:
            value = str(item.get("value") or "").strip()
            if value:
                return value
    for item in items:
        if isinstance(item, dict) and item.get("kind") == "text":
            text = str(item.get("text") or "").strip()
            if text:
                return text
    for item in items:
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            if value:
                return value
    return ""


__all__ = [
    "BUILTIN_SECTIONS",
    "IDENTITY_FIELDS",
    "build_builtin_entries",
    "identity_of",
    "supports_builtin",
]
