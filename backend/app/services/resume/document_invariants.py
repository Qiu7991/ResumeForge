# SPDX-License-Identifier: Apache-2.0
"""AI 写路径的唯一不变量收口（Phase 2）。

生成落库（``save_record``）与 AI 修订（``revise_existing_resume``）共用同一个后处理
序列。**顺序是硬契约，不得调整**：

    1. ensure_document_version      只做版本归一，不校验
    2. dedupe_resume                无损合并（同名条目要点取并集，绝不截断）
    3. limit_resume(page_limit)     仅当 page_limit is not None（有损，只用于生成）
    4. strip_resume_tech_stack      仅当 not include_tech_stack
    5. parse_document               唯一校验点——必须在所有变换**之后**：
                                    先校验再合并会产出超过 schema 上限的文档
                                    （实测合并后 1000 > MAX_LIST_VALUES=500，P8）
    6. validate_document_ids_v2
    7. document_to_json

``page_limit=None`` 表示**不截断**——AI 修订路径必须传 ``None``（P9：修订一次少一个
项目就是事故）；页数限量只属于生成路径。

手工保存（``save_content``）**不接入**这里：用户手写内容不被系统悄悄改掉。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from ...schemas.resume_document import (
    document_to_json,
    parse_document,
    validate_document_ids_v2,
)
from .document_io import ensure_document_version
from .resume_dedupe import dedupe_resume, limit_resume
from .resume_tech_stack import strip_resume_tech_stack

__all__ = ["finalize_ai_document"]

logger = logging.getLogger(__name__)


def finalize_ai_document(
    content: dict,
    *,
    language: str,
    format_config: dict,
    custom_fields: Mapping[str, Sequence[Any]] | None,
    page_limit: int | None,
    include_tech_stack: bool,
) -> dict:
    """AI 产出（v1/v2 均可）→ v2 → 去重 → 限量 → 技术栈 → **校验** → 序列化。

    返回可直接落库的 v2 dict；结构非法/对象 id 非法抛
    ``ConversionError`` / ``DocumentValidationError``（调用方翻 422，不静默重生成）。
    """
    document = ensure_document_version(
        content,
        language=language,
        format_config=format_config,
        custom_fields=custom_fields,
    )
    if language:
        # 记录的语言是这份简历显示语言的唯一权威：与 document_io.prepare_document_for_save
        # 同一口径，避免"切了语言但文档里还写着旧语言"的下一次渲染漂移。
        from .resume_labels import normalize_language

        document["language"] = normalize_language(language)
    document = dedupe_resume(document)
    if page_limit is not None:
        document = limit_resume(document, page_limit=page_limit)
    if not include_tech_stack:
        document = strip_resume_tech_stack(document)
    normalized = parse_document(document)
    validate_document_ids_v2(normalized)
    result = document_to_json(normalized)
    # 收口效果的可观测性：一行日志能回答"技术栈剥了没 / 页数截了没"。
    # 排障时不必再靠猜——历史上这两个不变量失效过一次，当时没有任何日志可看。
    logger.info(
        "AI 文档收口 page_limit=%s include_tech_stack=%s 项目=%d 经历=%d 可见技术栈=%d",
        page_limit,
        include_tech_stack,
        _entry_count(result, "projects"),
        _entry_count(result, "experience"),
        _visible_tech_stack_count(result),
    )
    return result


def _entry_count(document: dict, section_key: str) -> int:
    """某个板块的条目数（v2 形状）；没有该板块返回 0。"""
    for section in document.get("sections") or []:
        if isinstance(section, dict) and section.get("key") == section_key:
            entries = section.get("entries")
            return len(entries) if isinstance(entries, list) else 0
    return 0


def _visible_tech_stack_count(document: dict) -> int:
    """会上纸面的技术栈项数（placement != hidden 且 values 非空）。"""
    count = 0
    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for entry in section.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            for item in entry.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item.get("kind") not in {"field", "list"}:
                    continue
                key = str(item.get("key") or "")
                source = item.get("source")
                is_tech = key == "tech_stack" or (
                    isinstance(source, dict)
                    and str(source.get("field_id") or "").endswith(".tech_stack")
                )
                if not is_tech or item.get("placement") == "hidden":
                    continue
                values = item.get("values")
                if isinstance(values, list) and values:
                    count += 1
                elif str(item.get("value") or "").strip():
                    count += 1
    return count
