"""岗位类型推断：从标题与 JD 判断「校招 / 社招 / 实习」。

**为什么需要**：BOSS 等站点的列表接口里没有"校招/社招"这个字段，历史实现给所有采集/导入
的岗位统一填了「校招」——于是岗位广场里几乎全是校招，语义是错的。用户的真实期待是
"大多数岗位是社招"，所以默认值必须是社招，只有出现明确的应届/在校/实习字样才归校招。

判据刻意从宽到窄：先看实习（最明确），再看校招字样，最后回落社招。宁可把边界岗位
判成社招，也不要把社招岗位标成校招——后者会让"校招筛选"结果不可信。
"""

from __future__ import annotations

import re

INTERN = "实习"
CAMPUS = "校招"
SOCIAL = "社招"

_INTERN_HINTS = ("实习", "intern")
# 出现这些词才可能是校招岗位；"经验不限"不算——大量社招岗位也写经验不限。
_CAMPUS_HINTS = ("应届", "在校", "校园", "毕业生", "管培", "校招", "储备干部")

_SPACE = re.compile(r"\s+")


def infer_job_type(title: str = "", description: str = "", requirements: str = "") -> str:
    text = _SPACE.sub("", f"{title} {description} {requirements}").casefold()
    if not text:
        return SOCIAL
    if any(hint in text for hint in _INTERN_HINTS):
        return INTERN
    if any(hint in text for hint in _CAMPUS_HINTS):
        return CAMPUS
    return SOCIAL


__all__ = ["CAMPUS", "INTERN", "SOCIAL", "infer_job_type"]
