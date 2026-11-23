# SPDX-License-Identifier: Apache-2.0
"""投递队列：准入、去重、排序，以及简历 / 招呼语解析。"""

from __future__ import annotations

from typing import Any, get_args

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.apply import (
    ADMISSION_BLOCK,
    HARD_GATES,
    QUEUE_STATUS_PENDING,
    ApplyQueueItem,
    ApplyTaskItem,
    JobMatchAnalysis,
)
from ...models.job import Job
from ...models.profile import utcnow
from ...models.resume import ResumeRecord
from ...schemas.apply import ApplyQueueItemOut, ApplyQueueListOut, QueueStatus, TaskItemStatus
from ..sites.base import SiteAdapter
from ..sites.registry import get_registry
from ._base import ApplyConflict, ApplyNotFound, ApplyServiceError, _clip_greeting
from ._config import get_apply_config
from ._match import _admission_of_match, _blocking_gaps, _match_requires_confirm, latest_match
from ._queue_resolve import (
    _job_specific_resume,
    _jobs_by_id,
    _last_apply_results,
    _matches_by_job_id,
    _resume_titles,
    build_apply_data,
    queued_job_ids,
    resolve_greeting,
    resolve_resume,
)
from .blocklist import load_blocklist
from .lifecycle import job_history
from .signals import favorite_of, reference_score

__all__ = [
    "MAX_QUEUE_LIST",
    "add_to_queue",
    "build_apply_data",
    "count_queue",
    "job_apply_site",
    "list_queue",
    "queue_overview",
    "queued_job_ids",
    "remove_queue_item",
    "reorder_queue",
    "resolve_greeting",
    "resolve_resume",
    "unsupported_site_message",
    "update_queue_item",
]

# 队列列表的兜底上限（P2-2）：超过后前端按 total/truncated 如实提示。
MAX_QUEUE_LIST = 500

_QUEUE_STATUS_VALUES: tuple[QueueStatus, ...] = get_args(QueueStatus)
_TASK_ITEM_STATUS_VALUES: tuple[TaskItemStatus, ...] = get_args(TaskItemStatus)


def _as_queue_status(value: str) -> QueueStatus:
    """模型层 ``status`` 是 ``str``，出口处收窄为 schema 的 ``Literal``。

    取值由入队 / 回写链路用常量写入，正常不会走到兜底；万一库里出现未知值，在这里
    大声失败（与 pydantic Literal 字段的校验语义一致），不悄悄把非法状态发给前端。
    """
    if value not in _QUEUE_STATUS_VALUES:
        raise ValueError(f"未知的队列状态：{value!r}")
    return value


def _as_task_item_status(value: str) -> TaskItemStatus:
    """模型层 ``ApplyTaskItem.status`` 收窄为 schema 的 ``TaskItemStatus``。"""
    if value not in _TASK_ITEM_STATUS_VALUES:
        raise ValueError(f"未知的投递子项状态：{value!r}")
    return value


def job_apply_site(job: Job | None) -> SiteAdapter | None:
    """这个岗位能不能自动投递：能则返回对应站点适配器，不能则返回 ``None``。

    **唯一判据**：岗位的来源 / 投递链接必须能落到某个已注册站点上。纯手动录入、来源与链接
    都指不到站点的岗位，在投递时定位不到任何站点适配器，强行投只会得到一条「未知失败」的
    记录——所以"入队校验、开始投递前的拦截、列表上的能否投递标记"三处都走这一个函数，
    不各自判一遍。岗位已被删除（``None``）同样视为不可投递。
    """
    if job is None:
        return None
    return get_registry().resolve_for_job(job)


def unsupported_site_message(job: Job) -> str:
    """不可投递时的中文说明：入队被拒、开始投递被拦、单条失败诊断三处共用同一句。"""
    return (
        f"「{job.title or '该岗位'}」的来源不是投递台支持的招聘网站"
        f"（当前支持：{get_registry().supported_names()}），无法自动投递。"
        "请到对应的招聘网站里手动投递。"
    )


def _queue_out(
    db: Session,
    item: ApplyQueueItem,
    job: Job | None,
    last_apply: ApplyTaskItem | None = None,
    *,
    cache: dict[str, Any] | None = None,
    resume_titles: dict[int, str] | None = None,
    matches: dict[int, JobMatchAnalysis] | None = None,
) -> ApplyQueueItemOut:
    """队列条目的出口结构：准入摘要 + 能否投递 + 参考分/收藏（14B）+ 生命周期（15A/15B）。

    ``cache`` 只用于列表批量出口时复用"资料文本"（见 ``signals.reference_score``）与
    "采样序列"（见 ``lifecycle.job_history``）；单条出口（入队、改招呼语）不传，
    省一次字典分配也不影响正确性。

    ``resume_titles`` / ``matches`` 是**批量出口专用**的预取字典（见 :func:`_resume_titles`
    与 :func:`_matches_by_job_id`）：传了就只查字典，不传就按单条口径各查一次。
    两者都**不改变结果**——批量版与单条版读的是同一份数据、同一个唯一约束。
    """
    if matches is not None:
        match = matches.get(item.job_id) if item.job_id is not None else None
    else:
        match = latest_match(db, item.job_id)
    admission = _admission_of_match(match) if match is not None else None
    hard_gate = match.hard_gate if match is not None and match.hard_gate in HARD_GATES else None
    # 15A/15B：僵尸分与 JD 变更都来自同一份采集历史，一次读库（见 lifecycle.job_history）。
    history = job_history(db, job, cache=cache)
    # 这个条目**实际会投哪份**简历：岗位专属 → 默认简历。已显式选定且命中预取字典时直接用预取标题。
    if item.resume_id is not None and resume_titles is not None and item.resume_id in resume_titles:
        effective_resume_id: int | None = item.resume_id
        effective_resume_title = resume_titles[item.resume_id]
    else:
        effective_resume = resolve_resume(db, item.job_id, item.resume_id)
        effective_resume_id = (
            item.resume_id
            if item.resume_id is not None
            else (effective_resume.id if effective_resume is not None else None)
        )
        effective_resume_title = effective_resume.title if effective_resume is not None else ""
    return ApplyQueueItemOut(
        id=item.id,
        job_id=item.job_id,
        job_title=item.job_title,
        company=item.company,
        resume_id=effective_resume_id,
        resume_title=effective_resume_title,
        greeting=item.greeting,
        greeting_confirmed=bool(item.greeting_confirmed),
        sort_order=item.sort_order,
        status=_as_queue_status(item.status),
        admission=admission,
        hard_gate=hard_gate,
        requires_confirm=_match_requires_confirm(match) if match is not None else False,
        # 「能不能自动投」由来源决定，与匹配结论无关；界面上据此禁用勾选并说明原因。
        apply_supported=job_apply_site(job) is not None,
        match_score=reference_score(db, job, match, cache=cache),
        favorite=favorite_of(job),
        ghost_score=history["score"],
        ghost_evidence=history["evidence"],
        # 15A：忽略开关随行走（前端据此决定显示「忽略」还是「恢复」，以及徽标是否静音）。
        ghost_ignored=bool(getattr(job, "ghost_ignored", False)),
        jd_changed=history["jd_changed"],
        last_apply_status=_as_task_item_status(last_apply.status)
        if last_apply is not None
        else None,
        last_apply_at=last_apply.finished_at if last_apply is not None else None,
        last_failure_category=(last_apply.failure_category if last_apply is not None else ""),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def list_queue(db: Session, limit: int = MAX_QUEUE_LIST) -> list[ApplyQueueItemOut]:
    """按排序列出投递队列，每行带准入结论与能否投递标记。

    **后导入的排最上**（用户实测反馈：海投场景新加入的岗位应该最先看到）。``sort_order``
    大的是新条目，所以倒序取；重排序（``reorder_queue``）写值时与此口径配对。

    列表默认按 :data:`MAX_QUEUE_LIST` 兜底上限（P2-2）：海投千级队列时 HTTP 响应不再
    全量下发；总数走 :func:`count_queue`，由端点拼上 ``truncated`` 如实告知前端。
    """
    items = (
        db.query(ApplyQueueItem)
        .order_by(ApplyQueueItem.sort_order.desc(), ApplyQueueItem.id.desc())
        .limit(max(1, limit))
        .all()
    )
    # 岗位一次性取回，避免每行一次查询（队列条数不多，但这属于该顺手做对的事）。
    jobs = _jobs_by_id(db, [item.job_id for item in items])
    # 简历标题与匹配结论同样整页一次取回（原先每行各一次 db.get / latest_match）：
    # 500 条队列 = 1000 次多余的主键/单行查询，而这两份数据在出口处只用于填充字段。
    resume_titles = _resume_titles(db, [item.resume_id for item in items])
    matches = _matches_by_job_id(db, [item.job_id for item in items])
    # 参考分要现算：资料文本整页只读一次，简历文本逐岗位不同（见 signals.reference_score）。
    cache: dict[str, Any] = {}
    # 最近一次投递结果同样批量取：每行都回答"投了没有、成没成、什么时候投的"。
    last_applies = _last_apply_results(db, [item.job_id for item in items])
    # job_id 在模型层可空（岗位删除后置空）；_jobs_by_id 只收非空 id，这里对 None 直接给 None。
    return [
        _queue_out(
            db,
            item,
            jobs.get(item.job_id) if item.job_id is not None else None,
            last_applies.get(item.job_id) if item.job_id is not None else None,
            cache=cache,
            resume_titles=resume_titles,
            matches=matches,
        )
        for item in items
    ]


def count_queue(db: Session) -> int:
    """队列总条数：与 ``list_queue`` 的上限无关的全量口径。"""
    return int(db.query(func.count(ApplyQueueItem.id)).scalar() or 0)


def queue_overview(db: Session) -> ApplyQueueListOut:
    """队列列表的响应体：一页条目 + 全量总数 + 是否被上限截断。

    ``GET /api/apply/queue`` 与助手动作 ``list_apply_queue`` 都调这里：截断判据
    （``len(items) < total``）只有一处实现，不会出现"一侧如实标记、另一侧静默全量"的
    两种口径。
    """
    items = list_queue(db)
    total = count_queue(db)
    return ApplyQueueListOut(items=items, total=total, truncated=len(items) < total)


def add_to_queue(db: Session, request: Any) -> list[ApplyQueueItemOut]:
    """加入队列；命中"屏蔽清单 / 来源不支持 / 已在队列 / 真实缺口 / 未分析"时抛 409 并回传原因。

    整批要么全部成功、要么全部回滚：任一岗位不满足准入就中断，避免"加了一半"。
    """
    config = get_apply_config(db)
    # 14E 闸门②：屏蔽清单整批读一次（不再是每条一次查询）。
    blocklist = load_blocklist(db)
    next_order = db.query(func.coalesce(func.max(ApplyQueueItem.sort_order), 0)).scalar() or 0
    created: list[ApplyQueueItem] = []
    created_jobs: list[Job] = []
    try:
        for entry in request.items:
            job = db.get(Job, entry.job_id)
            if job is None:
                raise ApplyNotFound(f"岗位不存在或已被删除：{entry.job_id}")
            # 屏蔽清单**最先判**：它是用户的显式意愿（"这家/这类我不要"），排在其他任何
            # 准入判断之前——否则用户会先被"未分析，确认加入？"问一遍，确认完才被告知屏蔽。
            blocked_hit = blocklist.hit(job.company, job.title)
            if blocked_hit:
                raise ApplyConflict(
                    {
                        "message": (
                            f"「{job.title or '该岗位'}」命中屏蔽清单（{blocked_hit}），未加入队列。"
                            "要去掉这条限制，请到「投递设置 → 屏蔽清单」里删除它。"
                        ),
                        "job_id": job.id,
                        "blocked_by_blacklist": True,
                        "blocked_hit": blocked_hit,
                    }
                )
            # 来源闸门**放最前**：这是"这个岗位本来就走不到投递"的硬前提，不是用户确认一下
            # 就能放行的事（与下面的未分析 / 真实缺口不同，那两类可以由用户显式确认）。
            if job_apply_site(job) is None:
                raise ApplyConflict(
                    {
                        "message": unsupported_site_message(job),
                        "job_id": job.id,
                        "site_unsupported": True,
                    }
                )
            existing = (
                db.query(ApplyQueueItem).filter(ApplyQueueItem.job_id == job.id).one_or_none()
            )
            if existing is not None:
                raise ApplyConflict(
                    {"message": f"「{job.title or '该岗位'}」已在投递队列中", "job_id": job.id}
                )
            match = latest_match(db, job.id)
            if match is None:
                if not entry.confirm_unanalyzed:
                    raise ApplyConflict(
                        {
                            "message": f"「{job.title or '该岗位'}」尚未做过匹配分析，确认继续加入？",
                            "job_id": job.id,
                            "unanalyzed": True,
                        }
                    )
            else:
                admission = _admission_of_match(match)
                if admission == ADMISSION_BLOCK and not (
                    entry.confirm_real_gap or config.confirm_real_gap
                ):
                    raise ApplyConflict(
                        {
                            "message": f"「{job.title or '该岗位'}」存在真实缺口，需确认后再加入",
                            "job_id": job.id,
                            "gaps": _blocking_gaps(match.result),
                        }
                    )
                # 「需确认」（needs_confirm）与「读不出可用结论」（admission is None，即空结果 /
                # 未知取值 / hard_gate=unknown 且无标记）**同级处理**：都不阻断入队，但该条目被视为
                # 未获授权自动投递——`_match_requires_confirm` 会据此算出 requires_confirm=True，
                # 投递前仍要用户逐条确认。未知/空结论绝不默认放行。
            next_order += 1
            greeting = _clip_greeting(entry.greeting)
            # 入队即把「这个岗位用哪份简历」定下来：显式指定优先，否则绑定该岗位最近一份
            # 岗位版简历。招呼语随后按这份简历生成，避免运行时规则变化导致"说的和投的不是同一份"。
            resume_id = entry.resume_id
            if resume_id is None:
                # 只固化**岗位专属**简历；默认简历不写进队列——用户在设置里换了默认，
                # 已经入队的条目要跟着变（运行时 resolve_resume 再回落）。
                fallback = _job_specific_resume(db, job.id)
                resume_id = fallback.id if fallback is not None else None
            queue_item = ApplyQueueItem(
                job_id=job.id,
                job_title=job.title,
                company=job.company,
                resume_id=resume_id,
                greeting=greeting,
                # 入队时自带文案 = 调用方已经确认过这段字（界面上没有这条路径，保留给 API）。
                greeting_confirmed=bool(greeting),
                sort_order=next_order,
                status=QUEUE_STATUS_PENDING,
            )
            db.add(queue_item)
            created.append(queue_item)
            created_jobs.append(job)
        db.commit()
    except ApplyServiceError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise
    # created 与 created_jobs 在同一循环里成对 append，长度恒等：strict=True 让
    # "两表错位"这种不可能的状态在发生时立刻炸出来，而不是悄悄产出错位队列。
    return [_queue_out(db, item, job) for item, job in zip(created, created_jobs, strict=True)]


def update_queue_item(db: Session, item_id: int, payload: Any) -> ApplyQueueItemOut:
    """更新队列条目的招呼语/简历，并回填准入结论与能否投递标记。"""
    item = db.get(ApplyQueueItem, item_id)
    if item is None:
        raise ApplyNotFound("投递队列条目不存在或已被移除")
    resume_changed = payload.resume_id is not None and payload.resume_id != item.resume_id
    if payload.greeting is not None:
        item.greeting = _clip_greeting(payload.greeting)
        # 默认语义：能在编辑弹窗里保存，就说明用户看过这段字。批量生成显式传 False，
        # 让文案先落库、但不越过"发送前确认"的闸门。
        item.greeting_confirmed = payload.confirm_greeting is not False and bool(item.greeting)
    elif payload.confirm_greeting is not None:
        item.greeting_confirmed = bool(payload.confirm_greeting) and bool(item.greeting.strip())
    if payload.resume_id is not None:
        resume = db.get(ResumeRecord, payload.resume_id)
        if resume is None:
            raise ApplyNotFound("指定的简历不存在")
        item.resume_id = resume.id
    # 换简历 = 招呼语对不上新简历了，默认回到未确认。例外是同一次请求里**显式确认了
    # 一段非空招呼语**（编辑弹窗的「保存并确认」，通常发生在换完简历、刚重新生成之后）：
    # 用户确认的就是眼前这段字，再强制他保存第二次只会让人觉得"保存了还是不行"。
    # 只换简历、文案原样带回来的请求（confirm 未置真）仍然会被打回未确认。
    keeps_confirmation = (
        payload.confirm_greeting is True
        and payload.greeting is not None
        and bool(item.greeting.strip())
    )
    if resume_changed and not keeps_confirmation:
        item.greeting_confirmed = False
    item.updated_at = utcnow()
    db.commit()
    db.refresh(item)
    return _queue_out(db, item, db.get(Job, item.job_id) if item.job_id else None)


def remove_queue_item(db: Session, item_id: int) -> None:
    item = db.get(ApplyQueueItem, item_id)
    if item is None:
        raise ApplyNotFound("投递队列条目不存在或已被移除")
    db.delete(item)
    db.commit()


def reorder_queue(db: Session, order: list[int]) -> list[ApplyQueueItemOut]:
    """按给定 id 顺序重排队列。

    ``order`` 是**界面显示顺序**（从上到下）。与 ``list_queue`` 的倒序口径配对：
    显示在越前面的 ``sort_order`` 越大，这样后导入（``sort_order`` 取最大）的条目
    才会自然排到最上面。

    **条目一次批量取回**（原先逐条 ``db.get``：拖 50 行就是 50 条 SELECT，而这只为了在
    内存里写一个整数）。语义逐条保持：

    - 缺失的 id 跳过，但 ``total`` 仍是 ``len(order)``（含缺失项）——序号按界面给的槽位算；
    - 重复 id 由**靠后的那次**覆盖（与逐条 ``db.get`` 拿到同一对象、后写覆盖前写一致）；
    - ``updated_at`` 逐行刷新、单次 commit、出口仍是 :func:`list_queue`。
    """
    total = len(order)
    # ``order`` 为空时不发查询：``in_([])`` 会退化成恒假条件，白跑一次还多一条 SQL。
    by_id: dict[int, ApplyQueueItem] = {}
    if order:
        ids = sorted({int(item_id) for item_id in order})
        by_id = {
            row.id: row for row in db.query(ApplyQueueItem).filter(ApplyQueueItem.id.in_(ids)).all()
        }
    for index, item_id in enumerate(order):
        item = by_id.get(item_id)
        if item is None:
            continue
        item.sort_order = total - index
        item.updated_at = utcnow()
    db.commit()
    return list_queue(db)
