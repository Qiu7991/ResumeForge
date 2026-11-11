# SPDX-License-Identifier: Apache-2.0
"""备选岗位的 JD 补抓。

**为什么不复用 ``detail_backfill.backfill_details``**（2026-11-11 实测）：那个函数是给
正式岗位写的——它按 ``Job`` 模型读写 ``job.description``，并且用「已有 JD 就跳过」判断。
拿备选岗位 id 传进去时，``db.get(Job, id)`` 取不到对应行，于是**每一条都被判成"已有 JD"
静默跳过**：实测日志 `尝试 0 / 成功 0 / 跳过 11`，采集后一条 JD 都没补到，评分全部变成
「缺 JD」。

结构上两者要的东西是一样的（同一个适配器解析、同一条限速），所以这里复用解析与限速
常量，只是把读写目标换成 ``CandidateJob``。候选的 JD 分三段存（description /
requirements / additional_info），详情页解析出来是完整正文，按小标题再切一次放进
职责与要求两列——与投递台采集时的落库口径一致。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...models.material import CandidateJob
from .base import JobParseError
from .detail_backfill import DETAIL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)


@dataclass
class CandidateJdReport:
    """一次备选岗位 JD 补抓的账目。"""

    attempted: int = 0
    filled: int = 0
    skipped_has_jd: int = 0
    no_url: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "filled": self.filled,
            "skipped_has_jd": self.skipped_has_jd,
            "no_url": self.no_url,
            "errors": self.errors,
        }


def _split_like_collector(text: str) -> tuple[str, str, str]:
    """把详情页正文按小标题切成「职责 / 要求 / 其他」。

    与投递台采集落库时的口径一致（``services/sites/boss_text.split_job_sections``）。
    切不出来时整段留在职责里——宁可全进 description，也不要让正文消失。
    """
    # 用**绝对导入**：本模块在 ``app/services/job_hunt/``，相对层级容易数错
    # （``...`` 会落到 ``app.sites`` 不存在、``....`` 又越出顶层包）。
    # 这里的导入是函数内延迟的，不会把 services.sites 拖进模块加载期。
    from app.services.sites.boss_text import split_job_sections

    try:
        description, requirements = split_job_sections(text)
    except Exception:  # noqa: BLE001 — 切分是增强，失败不该丢正文
        return text, "", ""
    return description or text, requirements, ""


def backfill_candidate_jd(
    db: Session,
    candidate_ids: list[int],
    *,
    fetch: Any,
    adapter: Any,
    interval: float = DETAIL_INTERVAL_SECONDS,
    limit: int | None = None,
) -> CandidateJdReport:
    """给备选岗位补 JD 正文（``fetch(url) -> html`` 由调用方注入）。

    与正式岗位那条的差别只有两点：读写的模型是 ``CandidateJob``；「已有 JD」按候选的
    ``description/requirements/raw_text`` 判（与评分判定同源，见 ``candidate_scoring``）。
    """
    from .candidate_scoring import candidate_has_jd

    report = CandidateJdReport()
    if not candidate_ids:
        return report

    ids = candidate_ids[:limit] if limit is not None else candidate_ids
    for index, candidate_id in enumerate(ids):
        candidate = db.get(CandidateJob, candidate_id)
        if candidate is None:
            report.errors.append(f"备选岗位 {candidate_id} 不存在")
            continue
        if candidate_has_jd(candidate):
            report.skipped_has_jd += 1
            continue
        url = (candidate.source_url or "").strip()
        if not url:
            report.no_url += 1
            continue

        report.attempted += 1
        try:
            html = fetch(url)
            detail = adapter.parse_detail(html)
            if detail.description:
                description, requirements, additional = _split_like_collector(detail.description)
                candidate.description = description
                if requirements:
                    candidate.requirements = requirements
                if additional:
                    candidate.additional_info = additional
                # 详情页薪资是明文，比列表页靠字体映射推测更可信。
                if detail.salary_decoded and detail.salary_decoded_ok:
                    candidate.salary = detail.salary_decoded[:64]
                if detail.location and not (candidate.location or "").strip():
                    candidate.location = detail.location
                db.flush()
                report.filled += 1
            else:
                report.errors.append(f"备选岗位 {candidate_id} 详情页没有 JD 正文")
        except JobParseError as exc:
            report.errors.append(f"备选岗位 {candidate_id} 解析失败：{exc.detail}")
        except Exception as exc:  # noqa: BLE001 — 单条失败不中断整批
            report.errors.append(
                f"备选岗位 {candidate_id} 抓取失败：{type(exc).__name__}: {exc}"
            )

        if index < len(ids) - 1 and interval > 0:
            time.sleep(interval)

    db.commit()
    logger.info(
        "备选岗位补 JD：尝试 %s / 成功 %s / 跳过 %s / 无链接 %s",
        report.attempted,
        report.filled,
        report.skipped_has_jd,
        report.no_url,
    )
    return report


__all__ = ["CandidateJdReport", "backfill_candidate_jd"]
