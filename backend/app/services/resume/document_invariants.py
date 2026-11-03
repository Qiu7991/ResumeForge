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
    return document_to_json(normalized)
