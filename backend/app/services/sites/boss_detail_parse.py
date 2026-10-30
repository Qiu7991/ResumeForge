"""BOSS 岗位详情字段规整：把详情页读到的原始结构变成标准岗位字段。

单独成文件的原因很朴素：``boss_search.py`` 已经贴着行数预算，而"把页面读到的薪资/城市/
正文拆成标准字段"是一条可以脱离搜索流程单独读、单独测的规则。
"""

from __future__ import annotations

from typing import Any

from ...models.apply import FAILURE_SELECTOR_INVALID
from .base import SiteFailure
from .boss_text import normalize_text, split_job_fields


def parse_job_detail(payload: dict[str, Any]) -> dict[str, Any]:
    """把 BOSS 岗位详情响应规整成标准字段；需求缺失时退回描述里拆出的需求。"""
    if not isinstance(payload, dict):
        raise SiteFailure(FAILURE_SELECTOR_INVALID, "岗位详情返回了无法解析的内容")
    dom_requirements = normalize_text(payload.get("requirements", ""))
    sections = split_job_fields(payload.get("description", ""))
    return {
        "job_title": normalize_text(payload.get("job_title", "")),
        "company": normalize_text(payload.get("company", "")),
        "description": sections.description,
        "requirements": dom_requirements or sections.requirements,
        # 福利待遇 / 公司介绍这类第三段（对应 ``Job.additional_info``）。
        "additional_info": sections.additional,
        # 详情页 DOM 能直接读到薪资与城市；接口详情响应没有这两项时保留空串。
        "salary": normalize_text(payload.get("salary", "")),
        "location": normalize_text(payload.get("location", "")),
        "url": str(payload.get("url", "")),
    }


__all__ = ["parse_job_detail"]
