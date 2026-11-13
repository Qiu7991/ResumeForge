# SPDX-License-Identifier: Apache-2.0
"""关键词搜索采集路径（2026-11-09 随 interest 分支的引入从 ``Collector.run`` 纯搬迁、
后又拆出成独立模块；逻辑零改动）。

为什么独立成模块：``collector.py`` 受 500 行生产文件预算约束，搜索路径是三态分支里
最长的一段，整段搬来这里；``query`` / ``unmapped`` / ``tally`` 由 ``Collector.run`` 持有并
传入——结尾的 summary 组装还要用它们，两段共享同一份状态。
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from ...schemas.apply import CollectConfigIn
from ..sites.base import CollectQuery, SearchResult, SiteAdapter
from .blocklist import drop_if_blocked, load_blocklist
from .collect_filters import FilterTally, evaluate_filters
# 去重判据与「采样留痕」都在 collector_history（15A/15B，上游 2.1.0）：
# 重采不再"跳过即无痕"。
from .collector_history import already_known, known_job_of, record_sighting

if TYPE_CHECKING:
    from .collector import Collector, CollectReport

logger = logging.getLogger(__name__)


def collect_search(
    collector: Collector,
    *,
    session: Session,
    task: Any,
    client: Any,
    adapter: SiteAdapter,
    config: CollectConfigIn,
    checkpoint: Callable[[], None],
    sleeper: Callable[[float], None],
    clock: Callable[[], float],
    report: CollectReport,
    query: CollectQuery,
    unmapped: set[str],
    tally: FilterTally,
) -> None:
    """关键词搜索路径（2026-11-09 从 ``run`` 整段**纯搬迁**成方法，逻辑零改动）：
    循环 keywords × page 读列表 → 本地筛选 → 统一抓详情 → 写暂存区。

    ``query`` / ``unmapped`` / ``tally`` 由 ``run`` 持有并传入：结尾的 summary 组装
    （unmapped_conditions / filter_reasons 等）还要用它们，两段共享同一份状态。
    """
    limit = config.per_task_limit
    # 本轮采集任务 id：写进 job_seen.run_id（"哪一轮见到的"）。取不到（离线/单测里的
    # 轻量 task 对象）就记空，采样本身仍然有效。
    run_id = getattr(task, "id", None)
    # 本地筛选只对**适配器声明过**的条件生效。这份声明是有约束力的：没声明就说明该站点的
    # 接口不保证返回对应字段，硬筛会变成"凭缺失的字段做判断"——那正是要避免的误杀。
    declared = set(adapter.post_filter_conditions)
    # 14E 闸门①：屏蔽清单一次读出、整轮复用（每条命中都要丢弃，不能只拦手动入队）。
    blocklist = load_blocklist(session)
    keywords = list(config.keywords) or [""]
    seen_results: set[tuple[str, str, str]] = set()
    for keyword_index, keyword in enumerate(keywords):
        if report.collected >= limit:
            break
        page = 1
        # 连续两页"整页都是已见过的结果"即判定翻页饱和：站点开始重复推送（筛选组合下
        # 岗位总量就这么多，再翻只会原样重复到页数上限）。
        saturated_pages = 0
        # ===== 阶段一：把这一关键词的**列表**读完，攒齐"新面孔" =====
        # 两阶段的原因：BOSS 搜索页靠**向下滑动**加载更多（不吃 URL 的 page 参数），
        # 而抓详情会把共享标签页导航走——滚动加载的进度就丢了。所以先滚动读列表、
        # 再统一抓详情；详情失败的条目仍会暂存（见 _stage_candidate）。
        pending: list[SearchResult] = []
        while report.collected + len(pending) < limit and page <= collector._max_pages:
            checkpoint()
            # 一次站点搜索只带一个关键词。这样适配器无须猜列表里的多个词应当如何组合，
            # 同时让每个用户配置的关键词都真正执行；只填城市时用一个空关键词跑一次。
            page_query = replace(query, keywords=[keyword], page=page)
            # 页级步骤先落库再读取：界面上的"正在读取第 N 页"与浏览器动作同帧可见。
            task.current_step = (
                f"正在读取搜索结果：第 {page} 页（已就绪 {len(pending)} 个）"
            )
            session.commit()
            page_result = adapter.collect_search(client, page_query, page)
            report.pages += 1
            unmapped.update(page_result.unmapped_conditions)
            # 本页"新面孔"计数：通过了重复判定（无论后面有没有被本地筛掉）就算新；
            # 整页一个新面孔都没有 → 站点在重复推送。
            page_new = 0

            for result in page_result.results:
                if report.collected + len(pending) >= limit:
                    break
                checkpoint()
                if not result.url:
                    continue
                identity = (
                    result.url.strip(),
                    result.title.strip().casefold(),
                    result.company.strip().casefold(),
                )
                if identity in seen_results:
                    report.skipped += 1
                    continue
                seen_results.add(identity)
                # 15A/15B：**每一条**结果都记一次采样（已知岗位也记，新岗位 job_id 为空）。
                # 没有这一步，重采就只是一次 `continue`——"这条岗位挂了半年""JD 改过"
                # 永远没有证据。岗位只查一次，两处复用（见 collector_history 的纪律②）。
                known_job = known_job_of(session, result)
                record_sighting(session, result, known_job=known_job, run_id=run_id)
                known = already_known(session, result, job=known_job)
                if known:
                    report.skipped += 1
                    if known == "trashed":
                        # 单独计数：这是"你之前删过它"，不是"早就在库里了"。
                        report.skipped_trashed += 1
                    continue
                page_new += 1
                # 条件筛选放在抓详情**之前**：按列表字段就能判定的不符合项，没必要再为它
                # 打开一次详情页（那是整个采集里最慢的一步）。
                decision = evaluate_filters(
                    salary_min=query.salary_min if "薪资" in declared else None,
                    experience=query.experience if "经验" in declared else "",
                    education=query.education if "学历" in declared else "",
                    job_type=query.job_type if "岗位类型" in declared else "",
                    extra=result.extra,
                )
                tally.unapplied.update(decision.unapplied)
                if not decision.keep:
                    report.filtered += 1
                    tally.filtered += 1
                    tally.reasons.update(decision.rejected_by)
                    continue
                if decision.undecided:
                    # 岗位没给这个字段 → **保留**（判断不了就不误杀），但要记账。
                    tally.undecided.update(decision.undecided)
                    tally.undecided_count += 1
                if drop_if_blocked(report, blocklist, result.company, result.title):
                    continue
                pending.append(result)

            # 翻页饱和判定：这一页有结果但全是已见过的 → 记一次饱和；
            # 连续两页饱和就提前停（给一页宽限，防"个别页恰好全重复"误判）。
            if page_result.results and page_new == 0:
                saturated_pages += 1
                if saturated_pages >= 2:
                    report.pagination_stopped_at = page
                    logger.info(
                        "第 %s 页起结果与之前完全重复，提前停止翻页", page
                    )
                    break
            else:
                saturated_pages = 0
            if not page_result.has_next:
                break
            page += 1
            collector._pace(
                config.interval_seconds, config.interval_jitter_seconds, checkpoint, sleeper, clock
            )

        # ===== 阶段二：统一抓详情并暂存（只对通过筛选的"新面孔"）=====
        if pending:
            task.current_step = f"正在读取岗位详情（共 {len(pending)} 个）"
            session.commit()
        for index, result in enumerate(pending):
            checkpoint()
            detail = collector._fetch_detail(adapter, client, result.url)
            if not str(detail.get("description") or "").strip():
                # "应该是详情的地方没拿到详情"：详情正文（description）去空白后为空即计一条。
                # 这是站点漂移的早期信号——列表字段还在、正文却读不出来了。
                report.detail_missing += 1
            collector._stage_candidate(
                session, adapter, result, detail, getattr(task, "id", None),
                job_type=config.job_type,
            )
            report.collected += 1
            task.current_step = f"正在读取岗位详情 {index + 1}/{len(pending)}"
            collector._update_task_progress(session, task, report)
            collector._pace(
                config.interval_seconds,
                config.interval_jitter_seconds,
                checkpoint,
                sleeper,
                clock,
            )
        if keyword_index < len(keywords) - 1 and report.collected < limit:
            collector._pace(
                config.interval_seconds, config.interval_jitter_seconds, checkpoint, sleeper, clock
            )
