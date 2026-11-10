# SPDX-License-Identifier: Apache-2.0
"""投递队列：准入、去重、排序，以及简历 / 招呼语解析。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, get_args

from sqlalchemy import func
from sqlalchemy.orm import Session

from ...models.apply import (
    ADMISSION_BLOCK,
    HARD_GATES,
    QUEUE_STATUS_PENDING,
    ApplyQueueItem,
)
from ...models.job import Job
from ...models.profile import utcnow
from ...models.resume import ResumeRecord, saved_only
from ...schemas.apply import ApplyConfigIn, ApplyQueueItemOut, QueueStatus
from .. import trash
from ..profile.profile_service import project_legacy_profile
from ..sites.base import SiteAdapter
from ..sites.registry import get_registry
from ._base import ApplyConflict, ApplyNotFound, ApplyServiceError, _clip_greeting
from ._config import get_apply_config
from ._match import _admission_of_match, _blocking_gaps, _match_requires_confirm, latest_match

# 队列列表的兜底上限（P2-2）：超过后前端按 total/truncated 如实提示。
MAX_QUEUE_LIST = 500

_QUEUE_STATUS_VALUES: tuple[QueueStatus, ...] = get_args(QueueStatus)


def _as_queue_status(value: str) -> QueueStatus:
    """模型层 ``status`` 是 ``str``，出口处收窄为 schema 的 ``Literal``。

    取值由入队 / 回写链路用常量写入，正常不会走到兜底；万一库里出现未知值，在这里
    大声失败（与 pydantic Literal 字段的校验语义一致），不悄悄把非法状态发给前端。
    """
    if value not in _QUEUE_STATUS_VALUES:
        raise ValueError(f"未知的队列状态：{value!r}")
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


def _queue_out(db: Session, item: ApplyQueueItem, job: Job | None) -> ApplyQueueItemOut:
    match = latest_match(db, item.job_id)
    admission = _admission_of_match(match) if match is not None else None
    hard_gate = match.hard_gate if match is not None and match.hard_gate in HARD_GATES else None
    # 这个条目**实际会投哪份**简历：岗位专属 → 默认简历。输出的 id 也用它，
    # 编辑弹窗据此直接预选（不用逐条手点）；未保存前不写回队列，解析始终跟着设置走。
    effective_resume = resolve_resume(db, item.job_id, item.resume_id)
    return ApplyQueueItemOut(
        id=item.id,
        job_id=item.job_id,
        job_title=item.job_title,
        company=item.company,
        resume_id=(
            item.resume_id
            if item.resume_id is not None
            else (effective_resume.id if effective_resume is not None else None)
        ),
        resume_title=effective_resume.title if effective_resume is not None else "",
        greeting=item.greeting,
        greeting_confirmed=bool(item.greeting_confirmed),
        sort_order=item.sort_order,
        status=_as_queue_status(item.status),
        admission=admission,
        hard_gate=hard_gate,
        requires_confirm=_match_requires_confirm(match) if match is not None else False,
        # 「能不能自动投」由来源决定，与匹配结论无关；界面上据此禁用勾选并说明原因。
        apply_supported=job_apply_site(job) is not None,
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
    # job_id 在模型层可空（岗位删除后置空）；_jobs_by_id 只收非空 id，这里对 None 直接给 None。
    return [
        _queue_out(db, item, jobs.get(item.job_id) if item.job_id is not None else None)
        for item in items
    ]


def count_queue(db: Session) -> int:
    """队列总条数：与 ``list_queue`` 的上限无关的全量口径。"""
    return int(db.query(func.count(ApplyQueueItem.id)).scalar() or 0)


def _jobs_by_id(db: Session, job_ids: Sequence[int | None]) -> dict[int, Job]:
    """按 id 批量取岗位；缺失（已删除）的不在返回里。"""
    ids = sorted({job_id for job_id in job_ids if job_id})
    if not ids:
        return {}
    return {job.id: job for job in db.query(Job).filter(Job.id.in_(ids)).all()}


def add_to_queue(db: Session, request: Any) -> list[ApplyQueueItemOut]:
    """加入队列；命中"来源不支持 / 已在队列 / 真实缺口 / 未分析"时抛 409 并回传原因。

    整批要么全部成功、要么全部回滚：任一岗位不满足准入就中断，避免"加了一半"。
    """
    config = get_apply_config(db)
    next_order = db.query(func.coalesce(func.max(ApplyQueueItem.sort_order), 0)).scalar() or 0
    created: list[ApplyQueueItem] = []
    created_jobs: list[Job] = []
    try:
        for entry in request.items:
            job = db.get(Job, entry.job_id)
            if job is None:
                raise ApplyNotFound(f"岗位不存在或已被删除：{entry.job_id}")
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
    """
    total = len(order)
    for index, item_id in enumerate(order):
        item = db.get(ApplyQueueItem, item_id)
        if item is None:
            continue
        item.sort_order = total - index
        item.updated_at = utcnow()
    db.commit()
    return list_queue(db)


# ===== 简历与招呼语解析 =====


def _job_specific_resume(db: Session, job_id: int | None) -> ResumeRecord | None:
    """该岗位最近一份岗位版简历（不含"默认简历"回落）。"""
    if job_id is None:
        return None
    return (
        db.query(ResumeRecord)
        # 只挑**已保存**的简历：草稿里的内容用户还没认可，拿去投递是不可接受的（0051）。
        .filter(trash.live_only(ResumeRecord), saved_only(), ResumeRecord.job_id == job_id)
        .order_by(ResumeRecord.created_at.desc(), ResumeRecord.id.desc())
        .first()
    )


def resolve_resume(db: Session, job_id: int | None, resume_id: int | None) -> ResumeRecord | None:
    """确定本岗位用哪份简历：显式指定 → 该岗位最近一份岗位版 → 设置里的默认简历。

    「默认简历」是为了不用逐条手选：绝大多数岗位没有专属简历时，自动落到用户指定的
    那份通用简历上；它在投递设置里随时可改，已经入队的条目也跟着走（解析在运行时做，
    不把默认值固化进队列）。
    """
    if resume_id is not None:
        return db.get(ResumeRecord, resume_id)
    specific = _job_specific_resume(db, job_id)
    if specific is not None:
        return specific
    default_id = get_apply_config(db).default_resume_id
    if default_id is None:
        return None
    return (
        db.query(ResumeRecord)
        .filter(
            trash.live_only(ResumeRecord),
            saved_only(),
            ResumeRecord.id == default_id,
        )
        .first()
    )


def resolve_greeting(item: ApplyQueueItem | None, config: ApplyConfigIn) -> str:
    """本岗位招呼语：条目值优先，为空则退回默认招呼语。"""
    if item is not None and item.greeting.strip():
        return item.greeting.strip()
    return config.default_greeting.strip()


def build_apply_data(db: Session, resume: ResumeRecord | None) -> dict[str, Any]:
    """构造供通用表单引擎映射的字段数据（只取投递必需的展示字段，不含完整资料）。"""
    profile = project_legacy_profile(db)
    data: dict[str, Any] = {
        "name": profile.name,
        "phone": profile.phone,
        "email": profile.email,
        "city": profile.target_city or profile.city,
        "job_intent": profile.job_intent,
        "summary": profile.summary,
    }
    if resume is not None and resume.title:
        data["job_intent"] = data.get("job_intent") or resume.job_title
    return {key: value for key, value in data.items() if value}


def queued_job_ids(db: Session, job_ids: Sequence[int | None]) -> set[int]:
    """这批岗位里**哪些已经在投递队列里**（2026-11-10）。

    调用方是采集结果面板：它要标出"这条岗位是不是已经在投递台了"。

    一次 `WHERE job_id IN (...)` 查完，不在 Python 里逐条查：采集结果一次可能列上百条，
    逐条查询会让"打开采集结果"这个动作随条数线性变慢。

    为什么不复用候选的 `imported_job_id` 判断：那只说明"导入过岗位广场"，而用户关心的是
    "有没有进投递台"。导入之后被移出队列的岗位必须显示成"没进队列"，这个差别只有
    队列表能答。

    ``None`` 与假值一律忽略（手动粘贴的候选没有 ``imported_job_id``；队列条目的
    ``job_id`` 也可空，表示岗位已被删除）。
    """
    wanted = {int(job_id) for job_id in job_ids if job_id}
    if not wanted:
        return set()
    rows = (
        db.query(ApplyQueueItem.job_id).filter(ApplyQueueItem.job_id.in_(wanted)).all()
    )
    return {int(row[0]) for row in rows if row[0] is not None}
