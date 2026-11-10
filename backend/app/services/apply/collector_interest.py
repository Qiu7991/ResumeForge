# SPDX-License-Identifier: Apache-2.0
"""source=interest（BOSS「我的感兴趣」）的采集路径（2026-11-09 从 Collector 拆出）。

为什么独立成模块：``collector.py`` 受 500 行生产文件预算约束（``test_file_size_budget``），
三条采集路径里 interest 是最晚加入的，整段搬来这里；编排（分支选择、summary 组装、
进度收口、去重/暂存/限速这些共享步骤）仍留在 ``Collector``，经第一个参数传进来。
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from ...models.apply import FAILURE_UNKNOWN
from ...schemas.apply import CollectConfigIn
from ..sites.base import SearchResult, SiteAdapter, SiteFailure

if TYPE_CHECKING:
    from .collector import Collector, CollectReport


def collect_interest(
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
) -> None:
    """把 BOSS「感兴趣」个人列表抓进暂存区（source=interest 的专属路径）。

    与搜索路径的三处不同：
    1. 列表来源是个人固定列表（``page`` 参数翻页），不是关键词搜索结果；
    2. 不解析站点筛选（个人列表没有筛选维度，``run`` 里已跳过）；
    3. 详情**全抓**：用户要的就是"把感兴趣列表连同完整 JD 存下来"，不过本地筛选。
    其余（去重、限速、暂停、进度、暂存区写入）与搜索路径完全一致。
    """
    from ..sites.boss_interest import fetch_interest_page

    open_interest = getattr(adapter, "open_interest_page", None)
    if open_interest is None:
        # 站点选错了（interest 列表只有 BOSS 有）：显式失败好过 AttributeError。
        raise SiteFailure(
            FAILURE_UNKNOWN,
            f"当前站点（{adapter.display_name or adapter.key}）没有「感兴趣」列表，"
            "请把采集来源切回关键词搜索",
        )

    # 1) 打开「感兴趣」页（一次）。列表请求必须在这个页面里发（BOSS 会关掉脚本新建的
    #    标签页，见 boss_interest 模块说明），所以先导航到位。
    task.current_step = "正在打开「我的感兴趣」"
    session.commit()
    open_interest(client)
    checkpoint()

    # 2) 逐页读列表，攒齐"新面孔"。与搜索路径的两阶段同一思路：先把列表读完再统一抓
    #    详情——抓详情会把共享标签页导航走，页面内 fetch 的翻页上下文就没了。
    pending: list[SearchResult] = []
    limit = config.per_task_limit
    # 「只看前 N 个收藏」（2026-11-10 用户要求）：按**列表位置**计数，已收藏过的也算一个位置。
    # 0 = 不限（旧语义）。两个上限互相独立：
    #   scan_limit 管"这轮往下翻多远"，limit 管"最多新增几条"。
    # 没有 scan_limit 时，已收藏的因为被跳过而**不占** limit 名额，于是一路翻到很旧的收藏，
    # 用户无法表达"我只要最近收藏的这一批"——这正是这条配置存在的理由。
    scan_limit = config.interest_scan_limit
    scanned = 0          # 已"看过"的收藏位置数（含已跳过、已失效之外的每一条有效卡）
    seen: set[str] = set()
    page = 1
    while page <= config.interest_max_pages and len(pending) < limit:
        if scan_limit and scanned >= scan_limit:
            break
        checkpoint()
        # 页级步骤先落库再读取：界面上的"正在读取第 N 页"与浏览器动作同帧可见。
        # 文案带上扫描进度，用户才知道"限量"生效到哪一步。
        task.current_step = (
            f"正在读取「感兴趣」第 {page} 页"
            f"（已就绪 {len(pending)} 个"
            + (f"，已查看 {scanned}/{scan_limit} 个收藏" if scan_limit else "")
            + "）"
        )
        session.commit()
        page_result = fetch_interest_page(client, page)
        report.pages += 1
        report.interest_invalid += page_result.invalid
        for item in page_result.results:
            if len(pending) >= limit:
                break
            if scan_limit and scanned >= scan_limit:
                break
            key = item.url.strip()
            if key in seen:
                report.skipped += 1
                continue
            seen.add(key)
            # 这一条占掉一个"收藏位置"——不管它后面是被跳过还是被采走。
            scanned += 1
            known = collector._already_known(session, item)
            if known:
                report.skipped += 1
                if known == "trashed":
                    # 单独计数：这是"你之前删过它"，不是"早就在库里了"。
                    report.skipped_trashed += 1
                continue
            pending.append(item)
        if not page_result.has_more:
            break
        page += 1
        collector._pace(
            config.interval_seconds, config.interval_jitter_seconds, checkpoint, sleeper, clock
        )
    # 记账：这轮实际看了多少个收藏位置。用户下次想调 scan_limit 时靠它判断该给多大。
    report.interest_scanned = scanned

    # 3) 统一抓详情并暂存（与搜索路径阶段二同一套）。
    if pending:
        task.current_step = f"正在读取岗位详情（共 {len(pending)} 个）"
        session.commit()
    for index, item in enumerate(pending):
        checkpoint()
        detail = collector._fetch_detail(adapter, client, item.url)
        if not str(detail.get("description") or "").strip():
            report.detail_missing += 1
        collector._stage_candidate(
            session, adapter, item, detail, getattr(task, "id", None),
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
