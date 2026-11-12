# SPDX-License-Identifier: Apache-2.0
"""把用户在界面上选的中文标签折成 BOSS 搜索参数（``{参数名: "编码,编码"}``）。

**为什么需要这一层**：界面给用户看的是中文（「应届生」「本科」），站点只认数字编码
（``102`` ``203``）。这中间的映射不能写在组件里、也不能写在 URL 拼接里——两处各写一份
必然分叉，而分叉的后果是**静默筛错**：站点不报错，返回的却是没筛过的结果。

编码来源：``services/sites/boss_filters_catalog`` 的离线快照（2026-09-20 对 BOSS
筛选接口的真实响应）。**不猜、不自造**——BossHunter 的注释记录过一个陷阱：行业分组的
DOM 后缀是渲染序号而不是真实编码，照抄会发一个"合法但不相干"的编码出去。

三条纪律（与 ``boss_filters_catalog.resolve_codes`` 同源）：

1. 「不限」（编码 ``0``）不产生参数——它本来就等于没筛；
2. 标签不在本次清单里 → **不发出去**，记进 ``unapplied``。过期标签发出去会被站点
   当成合法值而返回错误结果，比不筛更糟；
3. 多值用逗号连接（``experience=102,103,104``），不是重复参数名。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 界面分组 → BOSS 查询参数名。顺序与 ``build_search_url`` 的拼接顺序一致。
# 只收短清单（jobType/salary/experience/degree/scale）；**不含 industry**——
# 行业的 134 条编码不进离线快照（体积），界面上也不提供这一项。
GROUP_TO_PARAM: dict[str, str] = {
    "jobType": "jobType",
    "experience": "experience",
    "degree": "degree",
    "scale": "scale",
    "salary": "salary",
}

# 界面分组 → 离线快照里的键（两者名字不同，容易抄错）。
GROUP_TO_SNAPSHOT_KEY: dict[str, str] = {
    "jobType": "jobTypeList",
    "experience": "experienceList",
    "degree": "degreeList",
    "scale": "scaleList",
    "salary": "salaryList",
}


@dataclass
class ResolvedSearchFilters:
    """解析结果：可直接拼进 URL 的 ``{参数名: "编码,编码"}`` + 未生效的标签。"""

    params: dict[str, str] = field(default_factory=dict)
    # 用户选了但没能生效的标签（「学历要求：博士」这种）。界面要如实显示，不能假装筛了。
    unapplied: list[str] = field(default_factory=list)

    def as_extra(self) -> dict[str, str]:
        return dict(self.params)


def _snapshot_groups() -> dict[str, tuple[tuple[str, str], ...]]:
    """读 ``boss_filters_catalog`` 的离线快照（懒加载：那个模块会 import 一堆东西）。"""
    # 绝对导入：本模块在 app/services/job_hunt/，相对层级很容易数错（`...` 会落到
    # 不存在的 app.sites、`....` 又越出顶层包）。函数内导入是为了不在模块加载期
    # 拉起整个 catalog 模块。
    from app.services.sites.boss_filters_catalog import _SNAPSHOT  # noqa: PLC0415


    return _SNAPSHOT


def resolve_search_filters(
    selected: dict[str, list[str]] | None,
) -> ResolvedSearchFilters:
    """``{"experience": ["应届生", "1-3年"], "degree": ["本科"]}`` → 查询参数。

    标签按**精确文本**匹配快照里的 ``label``。不做模糊匹配、不做同义词：
    认不出就如实记进 ``unapplied``，由界面提示用户重选——静默丢弃会让用户以为筛了。
    """
    result = ResolvedSearchFilters()
    if not selected:
        return result

    snapshot = _snapshot_groups()
    for group_key, labels in selected.items():
        param = GROUP_TO_PARAM.get(group_key)
        snapshot_key = GROUP_TO_SNAPSHOT_KEY.get(group_key)
        if param is None or snapshot_key is None:
            # 未知分组：不是错误（可能是别的平台才有），但记一笔便于排查。
            logger.debug("未知的筛选项分组，已忽略：%s", group_key)
            continue
        options = snapshot.get(snapshot_key) or ()
        if not options:
            # 快照里没有这一组 → 整组都不生效，如实上报。
            result.unapplied.extend(f"{group_key}:{label}" for label in labels)
            continue

        label_to_code = {label: code for code, label in options}
        codes: list[str] = []
        for label in labels:
            code = label_to_code.get((label or "").strip())
            if not code or code == "0":
                # 「不限」或认不出的标签：不产生参数。
                result.unapplied.append(f"{group_key}:{label}")
                continue
            if code not in codes:
                codes.append(code)
        if codes:
            # 多值：逗号连接。`build_search_url` 会把它作为一个参数拼进去。
            result.params[param] = ",".join(codes)

    return result


def filter_options(group_key: str) -> tuple[tuple[str, str], ...]:
    """某一组的 ``(编码, 标签)`` 清单，供前端渲染下拉（去掉「不限」那一项）。"""
    snapshot_key = GROUP_TO_SNAPSHOT_KEY.get(group_key)
    if snapshot_key is None:
        return ()
    options = _snapshot_groups().get(snapshot_key) or ()
    return tuple((code, label) for code, label in options if code != "0")


# 经验标签 → 可接受的候选标签集合（本地二次筛选用）。
#
# 为什么要有这张表：站点侧 `experience=102` 是"准入门槛"，但 BOSS 的筛选并不严格——
# 实测会混进相邻档位的岗位（选"应届生"仍会看到"1-3年"）。本地这道按**标签原文**兜底，
# 做不到就放过（宁可多留一条，也不误杀）。所以这张表是"允许集合"而不是"严格相等"。
_EXPERIENCE_COMPATIBLE: dict[str, tuple[str, ...]] = {
    "在校生": ("在校生",),
    "应届生": ("应届生", "经验不限", "1年以内", "在校生"),
    "1年以内": ("1年以内", "应届生", "经验不限"),
    "1-3年": ("1-3年", "1年以内", "应届生", "经验不限"),
    "3-5年": ("3-5年", "1-3年", "经验不限"),
    "5-10年": ("5-10年", "3-5年", "经验不限"),
    "10年以上": ("10年以上", "5-10年", "经验不限"),
    "经验不限": (),  # 不限 = 不筛
}


def filter_stub_by_tags(stub: Any, selected: dict[str, list[str]] | None) -> bool:
    """这条岗位卡片是否**可以保留**（按列表页标签本地二次筛选）。

    只做经验/学历两项——这是用户明确要的两个维度，也是最容易混进来的噪音
    （"10年经验"混进应届生池子）。其它维度（薪资/规模）由站点侧筛选负责。

    **原则：标签缺失就放过。** 列表页偶尔不给标签，此时无法判定，宁可多留一条让用户
    自己看，也不要因为"读不到"就把岗位丢掉——那是静默少数据，比多一条更难发现。
    """
    if not selected:
        return True

    experience_tags = selected.get("experience") or []
    if experience_tags:
        allowed: set[str] = set()
        for label in experience_tags:
            allowed.update(_EXPERIENCE_COMPATIBLE.get((label or "").strip(), ()))
        # 「经验不限」被选中时不构成约束。
        if allowed and "经验不限" not in experience_tags:
            actual = (getattr(stub, "experience", "") or "").strip()
            if actual and actual not in allowed:
                return False

    education_tags = selected.get("degree") or []
    if education_tags:
        actual = (getattr(stub, "education", "") or "").strip()
        wanted = {(label or "").strip() for label in education_tags}
        # 学历只做"是否在所选集合里"的判定；「学历不限」岗位对任何学历都开放。
        if actual and actual not in wanted and actual != "学历不限":
            return False

    return True


__all__ = [
    "GROUP_TO_PARAM",
    "filter_stub_by_tags",
    "ResolvedSearchFilters",
    "filter_options",
    "resolve_search_filters",
]
