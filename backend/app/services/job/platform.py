# SPDX-License-Identifier: Apache-2.0
"""招聘平台识别：从来源 URL 与来源/备注文本里判断岗位来自哪个平台。

为什么不新增数据库列：平台是**可从已有字段推导**的展示维度，历史岗位没有单独存过它；
一旦加列就要为所有旧数据回填、还要在每个写入入口记得填。这里用同一个纯函数同时服务
``JobOut.platform``（读取）与列表筛选（SQL 条件），口径只写一次，新导入的岗位也自动有值。

判定优先级：来源域名 > 用户来源字段/备注里的平台名 > 手动/其他。
"""

from __future__ import annotations

from typing import Any

BOSS = "BOSS直聘"
ZHILIAN = "智联招聘"
LIEPIN = "猎聘"
JOB51 = "前程无忧"
LAGOU = "拉勾"
MAIMAI = "脉脉"
LINKEDIN = "LinkedIn"
MANUAL = "手动添加"
OTHER = "其他平台"

# (展示名, 域名片段, 文本别名)。文本别名按顺序匹配，域名优先。
_PLATFORM_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    (BOSS, ("zhipin.com", "boss.com"), ("boss直聘", "boss", "直聘")),
    (ZHILIAN, ("zhaopin.com", "zhaopin.cn"), ("智联招聘", "智联")),
    (LIEPIN, ("liepin.com",), ("猎聘",)),
    (JOB51, ("51job.com",), ("前程无忧", "51job")),
    (LAGOU, ("lagou.com",), ("拉勾",)),
    (MAIMAI, ("maimai.cn",), ("脉脉",)),
    (LINKEDIN, ("linkedin.com",), ("linkedin", "领英")),
)

ALL_PLATFORMS: tuple[str, ...] = tuple(rule[0] for rule in _PLATFORM_RULES) + (MANUAL, OTHER)


def _text(value: Any) -> str:
    return str(value or "").strip().casefold()


def detect_platform(
    *,
    source_url: str = "",
    source: str = "",
    origin_source: str = "",
    recognition_source: str = "",
    note: str = "",
) -> str:
    """返回岗位所属平台的展示名；识别不出时区分「手动添加」与「其他平台」。"""
    url = _text(source_url)
    if url:
        for label, domains, _aliases in _PLATFORM_RULES:
            if any(domain in url for domain in domains):
                return label

    text = " ".join(
        _text(value) for value in (origin_source, source, recognition_source, note)
    )
    for label, _domains, aliases in _PLATFORM_RULES:
        if any(alias.casefold() in text for alias in aliases):
            return label

    # 来源字段明确是手动添加、且没有可识别平台：归到「手动添加」而不是「其他」，
    # 让用户能一眼区分"我手填的"与"采集/导入但平台没认出来"。
    if _text(source) == _text(MANUAL) or _text(origin_source) == _text(MANUAL):
        return MANUAL
    return OTHER


def platform_sql_condition(model: Any, platform: str) -> Any:
    """生成列表筛选用的 SQLAlchemy 条件；未识别/手动需要做 NOT 组合。"""
    from sqlalchemy import and_, func, not_, or_

    def column(name: str) -> Any:
        # 历史行可能为 NULL；coalesce 让 NOT(...) 的三值逻辑仍然可预期。
        return func.coalesce(getattr(model, name), "")

    known: list[Any] = []
    for _label, domains, aliases in _PLATFORM_RULES:
        for domain in domains:
            known.append(column("source_url").ilike(f"%{domain}%"))
        for alias in aliases:
            known.append(column("note").ilike(f"%{alias}%"))
            known.append(column("origin_source").ilike(f"%{alias}%"))
            known.append(column("source").ilike(f"%{alias}%"))
            known.append(column("recognition_source").ilike(f"%{alias}%"))
    known_any = or_(*known)
    if platform == OTHER:
        return and_(not_(known_any), column("source") != MANUAL)
    if platform == MANUAL:
        return and_(not_(known_any), column("source") == MANUAL)
    for label, domains, aliases in _PLATFORM_RULES:
        if label != platform:
            continue
        conditions: list[Any] = []
        for domain in domains:
            conditions.append(column("source_url").ilike(f"%{domain}%"))
        for alias in aliases:
            conditions.append(column("note").ilike(f"%{alias}%"))
            conditions.append(column("origin_source").ilike(f"%{alias}%"))
            conditions.append(column("source").ilike(f"%{alias}%"))
            conditions.append(column("recognition_source").ilike(f"%{alias}%"))
        return or_(*conditions)
    return not_(known_any)


__all__ = [
    "ALL_PLATFORMS",
    "BOSS",
    "JOB51",
    "LAGOU",
    "LIEPIN",
    "LINKEDIN",
    "MAIMAI",
    "MANUAL",
    "OTHER",
    "ZHILIAN",
    "detect_platform",
    "platform_sql_condition",
]
