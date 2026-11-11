# SPDX-License-Identifier: Apache-2.0
"""采集后补抓岗位详情（JD 正文）。

为什么要这一步
--------------
列表页只给标题/公司/地区/薪资。评分要判断「这个岗位要求什么、候选人有没有对应
证据」，必须有 JD 正文——没有 JD 时评分只能拿标题猜，结果全是中性分（实测 50），
没有参考价值。

设计取舍
--------
1. **不阻塞采集响应**：详情页要逐个访问，15 个岗位就要 30+ 秒，不能挂在采集请求上。
   采集先把卡片入库，详情补抓放到后台线程。
2. **限速**：招聘网站对连续详情页访问敏感。每条之间固定间隔（默认 1.5s），
   且一页最多补 N 条（默认 15，与列表页条数一致）。
3. **只补空 JD**：已有 description 的岗位不重复抓（配合「评一次不重复」）。
4. **失败不清零**：抓不到就保留空 JD 并在返回里如实报告，不假装成功。
5. **不碰浏览器生命周期**：复用已有的 CDP 客户端；拿不到页面就整批跳过。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ...models.job import Job

logger = logging.getLogger(__name__)

# 详情页之间的间隔（秒）。实测 BOSS 对连续访问有风控，1.5s 是保守值。
DETAIL_INTERVAL_SECONDS = 1.5
# 单次补抓上限：与列表页一页条数一致，避免一次跑太久。
DETAIL_BATCH_LIMIT = 15


@dataclass
class DetailBackfillReport:
    """一次补抓的账目。"""

    attempted: int = 0
    filled: int = 0
    skipped_has_jd: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "filled": self.filled,
            "skipped_has_jd": self.skipped_has_jd,
            "errors": self.errors,
        }


def backfill_details(
    db: Session,
    job_ids: list[int],
    *,
    fetch: Any,
    adapter: Any,
    interval: float = DETAIL_INTERVAL_SECONDS,
    limit: int = DETAIL_BATCH_LIMIT,
    overwrite: bool = False,
) -> DetailBackfillReport:
    """为给定岗位补抓 JD 正文。

    ``fetch(url) -> html`` 由调用方注入（生产是 CDP 抓取器，测试是假函数），
    所以本函数不依赖浏览器实现，也不做导航——它只做「取页面 → 解析 → 写库」。

    ``overwrite=True`` 时连已有 JD 的岗位也重抓。默认 ``False``（只补空 JD）是
    日常语义：评过的岗位不该被重复访问，那既慢又容易招风控。但抓取层有过缺陷时
    （2026-11-11：详情错用列表页的就绪选择器，导致入库的 JD 普遍残缺），存量数据
    需要一次强制重抓才能修好——那些岗位的 description 非空，默认路径会全部跳过。
    """
    from .base import JobParseError

    report = DetailBackfillReport()
    if not job_ids:
        return report

    for index, job_id in enumerate(job_ids[:limit]):
        job = db.get(Job, job_id)
        if job is None:
            report.errors.append(f"岗位 {job_id} 不存在")
            continue
        if not overwrite and (job.description or "").strip():
            # 已有 JD：不重复抓（这也是「评一次不重复」的上游保障）。
            report.skipped_has_jd += 1
            continue
        url = (job.source_url or "").strip()
        if not url:
            report.errors.append(f"岗位 {job_id} 没有来源链接")
            continue

        report.attempted += 1
        try:
            html = fetch(url)
            detail = adapter.parse_detail(html)
            if detail.description:
                job.description = detail.description
                if detail.requirements:
                    job.requirements = detail.requirements
                # 详情页的薪资是明文，比列表页解码更可信（列表页靠字体映射推测）。
                if detail.salary_decoded and detail.salary_decoded_ok:
                    job.salary = detail.salary_decoded[:64]
                if detail.location and not (job.location or "").strip():
                    job.location = detail.location
                db.flush()
                report.filled += 1
            else:
                report.errors.append(f"岗位 {job_id} 详情页没有 JD 正文")
        except JobParseError as exc:
            report.errors.append(f"岗位 {job_id} 解析失败：{exc.detail}")
        except Exception as exc:  # noqa: BLE001 — 单条失败不中断整批
            report.errors.append(f"岗位 {job_id} 抓取失败：{type(exc).__name__}: {exc}")

        # 限速：最后一条不用等。
        if index < len(job_ids[:limit]) - 1 and interval > 0:
            time.sleep(interval)

    db.commit()
    logger.info(
        "JD 补抓完成：尝试 %s / 成功 %s / 跳过 %s / 失败 %s",
        report.attempted,
        report.filled,
        report.skipped_has_jd,
        len(report.errors),
    )
    return report


def start_backfill_in_background(
    db_factory: Any,
    job_ids: list[int],
    *,
    fetch_factory: Any,
    adapter: Any,
    overwrite: bool = False,
) -> threading.Thread:
    """后台线程跑补抓。

    ``db_factory()`` 返回一个新的 Session——**不能复用请求线程的 Session**：
    SQLAlchemy 的 Session 不是线程安全的，请求结束后它还会被关闭。

    ``fetch_factory(db)`` 返回抓取器（内部要自己取 CDP 客户端）。

    ``overwrite`` 透传给 ``backfill_details``：修抓取层缺陷后重抓存量 JD 时要传 True。
    """
    thread = threading.Thread(
        target=_run_backfill,
        args=(db_factory, job_ids, fetch_factory, adapter, overwrite),
        daemon=True,
    )
    thread.start()
    return thread


def _run_backfill(
    db_factory: Any,
    job_ids: list[int],
    fetch_factory: Any,
    adapter: Any,
    overwrite: bool = False,
) -> None:
    db = db_factory()
    try:
        fetch = fetch_factory(db)
    except Exception as exc:  # noqa: BLE001 — 浏览器不可用：整批跳过，不报错给用户
        logger.info("JD 补抓跳过（抓取器不可用）：%s: %s", type(exc).__name__, exc)
        return
    try:
        backfill_details(db, job_ids, fetch=fetch, adapter=adapter, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001
        logger.warning("JD 补抓异常：%s: %s", type(exc).__name__, exc)
    finally:
        db.close()


__all__ = [
    "DETAIL_INTERVAL_SECONDS",
    "DETAIL_BATCH_LIMIT",
    "DetailBackfillReport",
    "backfill_details",
    "start_backfill_in_background",
]
