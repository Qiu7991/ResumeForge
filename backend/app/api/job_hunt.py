# SPDX-License-Identifier: Apache-2.0
"""自研求职采集路由（``/api/job-hunt/*``）：开关、平台清单、native 采集入口。

与 ``/api/ai-jobs/*``（sidecar 旧路径）**并存**：``job_hunt_backend`` = sidecar
（非默认，需外部 BossHunter 引擎）时本路由的采集入口拒绝执行（409），旧路径照常工作；
= native（**默认**）时走 ``services/job_hunt`` 的自研采集（registry 适配器 + runner +
CDP 抓取）。设置页的切换项读写的就是这里的 config。
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.job_hunt import JobHuntConfig
from ..services.job_hunt.cursor_store import clear_cursor, load_cursor, save_cursor
from ..services.job_hunt.registry import get_registry
from ..services.job_hunt.runner import HuntCriteria, JobHuntRunner, cdp_fetcher, hash_criteria
from ..services.job_hunt.settings import get_job_hunt_config, save_job_hunt_config
from .job_hunt_shared import (
    BLOCKLIST_KEY,
    BlocklistConfig,
    acquire_client,
    is_blocked,
    read_blocklist_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/job-hunt", tags=["job-hunt"])


class JobHuntCollectIn(BaseModel):
    """一次 native 采集的入参。``resume=True`` 时从上次的断点续采。"""

    site_key: str
    keywords: str = ""
    city: str = ""
    max_pages: int = Field(default=1, ge=1, le=10)
    # 平台特有参数原样透传（如智联的城市编码 city_code）。
    city_code: str = ""
    resume: bool = False
    # 采到的岗位是否**立即**写进岗位广场。
    # 默认 False：先预览、由用户勾选后再走 /import 导入——采 15 个往往只要 3 个，
    # 自动入库会把垃圾塞满岗位广场。
    persist: bool = False
    # 入库后是否对「本次新增」的岗位触发一次批量分析（预览模式下无新增，自然不触发）。
    # 复用的批量任务传 ``force=False``：已分析过的岗位服务端自动跳过。
    analyze: bool = False
    # 入库后是否后台补抓 JD 正文（预览模式下无入库，自然不触发）。
    backfill_jd: bool = False


@router.get("/status")
def status(db: Session = Depends(get_db)) -> dict:
    """开关状态 + 已注册平台清单（设置页/前端切换依据）。"""
    config = get_job_hunt_config(db)
    registry = get_registry()
    return {
        "backend": config.job_hunt_backend,
        "platforms": [{"key": a.key, "name": a.name} for a in registry.all()],
    }


@router.get("/config")
def read_config(db: Session = Depends(get_db)) -> JobHuntConfig:
    return get_job_hunt_config(db)


@router.put("/config")
def write_config(config: JobHuntConfig, db: Session = Depends(get_db)) -> JobHuntConfig:
    """写开关（非法值由 pydantic Literal 直接 422；默认 native，删除键即回默认）。"""
    return save_job_hunt_config(db, config)


@router.post("/collect")
def collect(req: JobHuntCollectIn, db: Session = Depends(get_db)) -> dict:
    """native 采集入口：registry 选适配器 → runner 翻页 → 返回岗位卡片与账目。

    断点续采：``resume=True`` 时读上次游标（AppSetting KV）续翻；每次跑完都落游标，
    完整跑完（no_results / repeated_page）后清掉。
    """
    config = get_job_hunt_config(db)
    if config.job_hunt_backend != "native":
        raise HTTPException(
            409, "当前仍是 sidecar 模式：请在设置里把「自研求职后端」切到 native 后再采集"
        )
    adapter = get_registry().resolve(req.site_key)
    if adapter is None:
        raise HTTPException(
            404, f"未知平台 {req.site_key}；目前支持：{get_registry().supported_names()}"
        )
    client = acquire_client(db)
    runner = JobHuntRunner(adapter, max_pages=req.max_pages)
    extra = {"city_code": req.city_code} if req.city_code else {}
    criteria = HuntCriteria(keywords=req.keywords, city=req.city, extra=extra)
    cursor = load_cursor(db, adapter.key, hash_criteria(adapter.key, criteria)) \
        if req.resume else None
    report = runner.run(criteria, fetch=cdp_fetcher(client, adapter), cursor=cursor)
    if report.next_cursor is not None:
        if report.stopped_reason in ("no_results", "repeated_page"):
            # 翻到头了：游标使命完成，清掉（下次重开从头）。
            clear_cursor(db, adapter.key, report.next_cursor.criteria_hash)
        else:
            save_cursor(db, report.next_cursor)

    # 黑名单过滤：命中的卡片不返回、不入库（用户不想再看到这些公司/关键词）。
    blocklist = read_blocklist(db)
    kept = [stub for stub in report.stubs if not is_blocked(stub, blocklist)]
    blocked_count = len(report.stubs) - len(kept)
    report.stubs = kept

    persisted = {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    new_job_ids: list[int] = []
    if req.persist and report.stubs:
        persisted, new_job_ids = _persist_stubs(db, report.stubs, origin_source=adapter.name)

    # JD 补抓：列表页没有正文，后台线程逐个抓详情页（限速、不阻塞本次响应）。
    # 评分要靠 JD 才能做语义匹配，没有 JD 只能拿标题猜（实测全是中性分 50）。
    if req.backfill_jd and new_job_ids:
        _start_jd_backfill(new_job_ids, adapter)

    analyze_task_id = _start_analysis(db, new_job_ids) if (req.analyze and new_job_ids) else None

    return {
        "stubs": [asdict(stub) for stub in report.stubs],
        "pages_fetched": report.pages_fetched,
        "duplicates": report.duplicates,
        "stopped_reason": report.stopped_reason,
        "errors": report.errors,
        "resumed_from_page": report.resumed_from_page,
        # 被黑名单挡掉的条数（用户可在黑名单设置里调整）。
        "blocked": blocked_count,
        # 入库账目：inserted + skipped_duplicate 应等于 stubs 总数（errors 除外）。
        "persisted": persisted,
        # 有新增岗位且开启分析时给出后台任务 id（前端可轮询进度）。
        "analyze_task_id": analyze_task_id,
    }


def _persist_stubs(
    db: Session, stubs: list[Any], *, origin_source: str = ""
) -> tuple[dict[str, Any], list[int]]:
    """把采集卡片写进岗位广场。

    去重复用 ``find_job_by_identity``（判据是「同一链接，或同一公司下同名岗位」）——
    与岗位广场手动录入、CSV 导入共用同一份判据，不另写一套。

    ``origin_source`` 是平台显示名（如「BOSS直聘」）：写进岗位的「来源」列，
    岗位广场能直接看到并筛选，用户不用猜这条是从哪采的。

    返回 ``(账目, 新增岗位 id 列表)``。单条失败不中断整批：记进 errors 后继续。
    """
    from sqlalchemy.exc import SQLAlchemyError

    from ..schemas.job import JobCreate
    from ..services.job.job_service import create_job_record, find_job_by_identity

    ledger: dict[str, Any] = {"inserted": 0, "skipped_duplicate": 0, "errors": []}
    new_ids: list[int] = []

    for stub in stubs:
        try:
            existing = find_job_by_identity(
                db,
                title=stub.title,
                company=stub.company,
                source_url=stub.url,
            )
            if existing is not None:
                ledger["skipped_duplicate"] += 1
                continue
            job = create_job_record(
                db,
                JobCreate(
                    title=stub.title or "(未命名岗位)",
                    company=stub.company,
                    location=stub.location,
                    # salary_decoded 已是明文（BOSS 的字体已在适配器里还原）
                    salary=(stub.salary_decoded or stub.salary_raw)[:64],
                    description="",
                    requirements="",
                    source_url=stub.url,
                    posted_at=stub.posted_at,
                    origin_source=origin_source,
                ),
                source="job_hunt",
            )
            db.flush()
            new_ids.append(int(job.id))
            ledger["inserted"] += 1
        except (SQLAlchemyError, ValueError) as exc:
            # 一条脏数据不该让整次采集失败——记下来，继续下一条。
            ledger["errors"].append(f"{stub.title or '(未命名)'}: {exc}")
    db.commit()
    return ledger, new_ids


def _start_jd_backfill(
    job_ids: list[int], adapter: Any, *, overwrite: bool = False, limit: int | None = None
) -> None:
    """后台补抓 JD 正文（限速；``overwrite`` 时连已有 JD 的重抓）。

    不阻塞采集响应：15 条详情页按 1.5s 间隔要 20+ 秒，挂在请求上会超时。
    浏览器不可用时整批跳过，不影响已经入库的卡片。

    ``limit``：本次最多处理多少条，默认沿用 ``DETAIL_BATCH_LIMIT``（与列表页一页
    条数一致）。存量重抓要传更大的值，否则 176 条只会跑前 15 条——实测就是这么
    发现「排了 176 条却只尝试了 44 条」的。

    **同一时刻只能有一个补抓线程**：它们共用同一个浏览器，两条并发的补抓会给
    同一页面互相导航（实测三平台同时跑时，一批 13 条只有 1 条成功）。所以这里的
    调用方必须保证串行——见 ``refetch_jd`` 里把多个平台合成一串。
    """
    try:
        from ..database import SessionLocal
        from ..services.job_hunt.detail_backfill import start_backfill_in_background
        from ..services.job_hunt.runner import cdp_fetcher

        def _fetch_factory(db: Session) -> Any:
            client = acquire_client(db)
            # page_kind="detail"：详情页有自己的就绪判据。用列表页的会等 li.job-card-box
            # ——详情页永远没有它，白等超时后解析半渲染 DOM，JD 残缺（2026-11-11 实测）。
            return cdp_fetcher(client, adapter, page_kind="detail")

        start_backfill_in_background(
            SessionLocal, job_ids, fetch_factory=_fetch_factory, adapter=adapter,
            overwrite=overwrite, limit=limit,
        )
    except Exception as exc:  # noqa: BLE001 — 补抓是增强项，失败不该连累采集
        logger.info("JD 补抓启动失败（不影响入库）：%s: %s", type(exc).__name__, exc)


def _start_analysis(db: Session, job_ids: list[int]) -> str | None:
    """对本次新增岗位启动一次批量分析（复用现有后台任务）。

    ``force=False`` 是「评一次不重复」的全部实现：服务端对已有分析记录的岗位直接跳过，
    所以这里不需要任何新的存储或状态字段。启动失败返回 None，不影响采集本身。
    """
    try:
        from ..services.job.job_match_background import (
            create_job_match_background_task,
            get_job_match_background_runner,
        )

        task = create_job_match_background_task(db, job_ids, force=False, mode="match")
        get_job_match_background_runner().start(task.task_id)
        return str(task.task_id)
    except Exception as exc:  # noqa: BLE001 — 分析是增强项，失败不该连累采集
        logger.info("采集后启动分析失败（不影响入库）：%s: %s", type(exc).__name__, exc)
        return None


# ---------------------------------------------------------------------------
# 预览 → 勾选导入
# ---------------------------------------------------------------------------


class JobHuntImportIn(BaseModel):
    """把预览里勾选的卡片导入岗位广场。"""

    site_key: str
    # 前端回传的完整卡片（就是 collect 返回的 stubs 里勾中的那几条）。
    stubs: list[dict[str, Any]]
    # 导入后是否补抓 JD（详情节流，后台跑）。
    backfill_jd: bool = True


@router.post("/import")
def import_selected(req: JobHuntImportIn, db: Session = Depends(get_db)) -> dict:
    """导入勾选的岗位。

    与 ``collect(persist=True)`` 的区别：这里**只导用户勾中的**，不是采到什么导什么。
    采集 15 个往往只要 3 个，自动入库会把岗位广场塞满垃圾。
    """
    config = get_job_hunt_config(db)
    if config.job_hunt_backend != "native":
        raise HTTPException(409, "当前是 sidecar 模式，无需导入（岗位由引擎管理）")

    adapter = get_registry().resolve(req.site_key)
    if adapter is None:
        raise HTTPException(404, f"未知平台 {req.site_key}")

    stubs = [_stub_from_payload(item) for item in req.stubs]
    stubs = [s for s in stubs if s.title]
    if not stubs:
        raise HTTPException(400, "没有可导入的岗位（标题为空）")

    # 来源标注：用平台显示名，岗位广场「来源」列能直接看到。
    ledger, new_ids = _persist_stubs(db, stubs, origin_source=adapter.name)

    if req.backfill_jd and new_ids:
        _start_jd_backfill(new_ids, adapter)

    return {
        "persisted": ledger,
        "imported_ids": new_ids,
        "origin_source": adapter.name,
    }


def _stub_from_payload(item: dict[str, Any]) -> Any:
    """把前端回传的 dict 还原成 JobStub（只取需要的字段，忽略多余键）。"""
    from ..services.job_hunt.base import JobStub

    return JobStub(
        title=str(item.get("title") or "").strip(),
        company=str(item.get("company") or "").strip(),
        location=str(item.get("location") or "").strip(),
        salary_raw=str(item.get("salary_raw") or "").strip(),
        salary_decoded=str(item.get("salary_decoded") or "").strip(),
        salary_decoded_ok=bool(item.get("salary_decoded_ok")),
        url=str(item.get("url") or "").strip(),
        posted_at=str(item.get("posted_at") or "").strip(),
    )


# ---------------------------------------------------------------------------
# 黑名单（屏蔽公司 / 关键词）：类型与判定在 job_hunt_shared，这里只留读写路由
# ---------------------------------------------------------------------------


@router.get("/blocklist")
def read_blocklist(db: Session = Depends(get_db)) -> BlocklistConfig:
    return read_blocklist_config(db)


@router.put("/blocklist")
def write_blocklist(config: BlocklistConfig, db: Session = Depends(get_db)) -> BlocklistConfig:
    """写黑名单。空列表即清空（不做「只增不减」，用户要能撤销）。"""
    payload = json.dumps(
        {"companies": config.companies, "keywords": config.keywords}, ensure_ascii=False
    )
    from sqlalchemy import text

    db.execute(
        text(
            "INSERT INTO app_setting (key, value) VALUES (:key, :value) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        ),
        {"key": BLOCKLIST_KEY, "value": payload},
    )
    db.commit()
    return config


class JobHuntRefetchIn(BaseModel):
    """重抓指定岗位的 JD（覆盖已有正文）。"""

    job_ids: list[int] = Field(default_factory=list, max_length=200)
    # 不传 job_ids 时：把库里有来源链接、但 JD 短于这个长度的岗位都重抓一遍。
    # 默认 200 字——实测正常 JD 多在 300 字以上，短于这个值基本就是抓到摘要或
    # 半渲染页面（2026-11-11 那次抓取层缺陷留下的存量）。
    short_threshold: int = Field(default=200, ge=0, le=10000)


@router.post("/refetch-jd")
def refetch_jd(req: JobHuntRefetchIn, db: Session = Depends(get_db)) -> dict:
    """重抓 JD 正文——用于修复抓取层缺陷留下的存量残缺数据。

    与采集时的补抓不同，这里 ``overwrite=True``：库里那些岗位已有非空 description，
    默认的「只补空 JD」会全部跳过，修不了。

    只处理能归属到已注册平台的岗位（按 ``source_url`` 主机名判断）；其余平台/手工
    录入的岗位无法重抓，如实跳过。后台线程跑，立刻返回本次排队的数量。
    """
    config = get_job_hunt_config(db)
    if config.job_hunt_backend != "native":
        raise HTTPException(409, "当前是 sidecar 模式：先切到 native 再用重抓")

    from ..models.job import Job

    if req.job_ids:
        candidates = db.query(Job).filter(Job.id.in_(req.job_ids)).all()
    else:
        # 候选 = 有链接、未删除、JD 偏短。长度判断放在 Python 里，因为 SQLite 的
        # LENGTH() 对中文按字符数算而 Python 的 len() 也是字符数，两边一致；
        # 但用 ORM 过滤能让被软删除的行自然排除，不必再写一遍 deleted_at 条件。
        candidates = [
            job
            for job in db.query(Job).filter(Job.deleted_at.is_(None)).all()
            if (job.source_url or "").strip()
            and len((job.description or "").strip()) < req.short_threshold
        ]

    registry = get_registry()
    by_site: dict[str, list[int]] = {}
    skipped: list[int] = []
    for job in candidates:
        url = (job.source_url or "").strip()
        adapter = next((a for a in registry.all() if a.supports(url)), None)
        if adapter is None:
            skipped.append(job.id)
            continue
        by_site.setdefault(adapter.key, []).append(job.id)

    # 把各平台的 id 串成**一条**队列，只起一个后台线程。
    #
    # 不能每个平台各起一个线程：它们共用同一浏览器，两个线程会互相导航
    # （实测三平台并发时，一批 13 条只成功 1 条）。补抓本来就是限速串行的活，
    # 一次一条反而更快——省掉互相踩导致的整批失败和重试。
    #
    # 队列里每条都带着自己的适配器，所以跨平台串行不会解析错。
    plan: list[tuple[int, Any]] = []
    for site_key, ids in by_site.items():
        adapter = registry.resolve(site_key)
        if adapter is None:  # 理论上不会发生：上面就是按 registry 的 key 分的组
            skipped.extend(ids)
            continue
        plan.extend((job_id, adapter) for job_id in ids)

    queued = len(plan)
    if plan:
        _start_serial_backfill(plan, job_ids_total=queued)

    return {
        "queued": queued,
        "skipped": len(skipped),
        "skipped_ids": skipped[:50],
        "by_site": {key: len(ids) for key, ids in by_site.items()},
    }


def _start_serial_backfill(plan: list[tuple[int, Any]], *, job_ids_total: int) -> None:
    """按 ``plan`` 顺序逐条重抓，跨平台也串行（见 ``refetch_jd`` 里的说明）。

    用单个线程 + 单个 Session：补抓是低并发、限速的活，串行最稳。
    ``detail_backfill.backfill_details`` 只接受「一个适配器 + 一批 id」，所以这里
    自己按平台切段调用它，段与段之间同样串行。
    """
    import threading

    from ..database import SessionLocal
    from ..services.job_hunt.detail_backfill import backfill_details
    from ..services.job_hunt.runner import cdp_fetcher

    grouped: list[tuple[Any, list[int]]] = []
    for job_id, adapter in plan:
        if grouped and grouped[-1][0] is adapter:
            grouped[-1][1].append(job_id)
        else:
            grouped.append((adapter, [job_id]))

    def _run() -> None:
        db = SessionLocal()
        try:
            for adapter, ids in grouped:
                client = acquire_client(db)
                fetch = cdp_fetcher(client, adapter, page_kind="detail")
                backfill_details(
                    db, ids, fetch=fetch, adapter=adapter,
                    overwrite=True, limit=len(ids),
                )
        except Exception as exc:  # noqa: BLE001 — 浏览器不可用等：整批放弃并记录
            logger.info("存量 JD 重抓中断：%s: %s", type(exc).__name__, exc)
        finally:
            db.close()

    threading.Thread(target=_run, daemon=True).start()
    logger.info("存量 JD 重抓已排队：%s 条（串行执行）", job_ids_total)


