"""本地 9 套技术方向模板的版式默认值（与上游新 schema 对齐）。

按方向拆成两个数据模块，聚合后供 `resume_template_layout` 合并进唯一入口。
"""

from __future__ import annotations

from .resume_template_layout_local_backend import TEMPLATE_LAYOUTS as _BACKEND
from .resume_template_layout_local_mobile import TEMPLATE_LAYOUTS as _MOBILE

LOCAL_TEMPLATE_LAYOUT_DEFAULTS: dict[str, dict] = {**_BACKEND, **_MOBILE}

__all__ = ["LOCAL_TEMPLATE_LAYOUT_DEFAULTS"]
