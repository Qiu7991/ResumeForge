# SPDX-License-Identifier: Apache-2.0
"""备选岗位的批量语义评分任务（后台、串行、可取消）。

为什么要有它：用户要「采集后自动评分，我再决定导入」。采集一轮 15-18 条，每条
LLM 调用 3-5 秒，合计约一分钟——挂在 HTTP 请求上必然超时，所以必须后台跑，前端轮询。

与 ``job_match_background`` 的关系：**模式照抄，代码不共用**。那份的入参是
``job_ids: list[int]`` 且结果写 ``job_match_batch`` 表（``items[].job_id`` 语义是
正式岗位）；备选岗位没有 job 行，写进去会污染准入数据。所以这里新建一套，但沿用
同一组已验证的取舍：

1. **单线程 + 全局单任务**：同一时刻只允许一个评分任务，两个并发会抢 LLM 配额，
   进度也会互相覆盖。
2. **串行逐条**：不并发。判定理由是速率与可观测性——并发只是把一分钟压到二十秒，
   却让"卡在第几条"变得不可解释。
3. **快照存 ``app_setting`` 单键**：与 ``job_match_background_task`` 同样的做法。
   任务生命周期就几分钟，建表不值得；进程重启后任务丢失是**预期**行为，启动自检
   会把遗留的活跃任务标成失败。
4. **取消用独立 ``threading.Event``**：每个任务一个全新 Event，不与上一次共享。
5. **单条失败不中断**：把原因写进该候选的 ``score_error``，继续下一条。评分是
   增强信息，一条失败不该让整批白跑。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...database import SessionLocal
from ...models.material import CandidateJob
from ...models.profile import utcnow
from ...models.setting import AppSetting
from .candidate_scoring import candidate_has_jd, candidate_jd
from .scoring_service import ScoringFailed, ScoringUnavailable, score_texts

logger = logging.getLogger(__name__)

_TASK_KEY = "candidate_score_task"
_CANCEL_POLL_SECONDS = 0.2
# 错误清单只留前 20 条：任务可能几千条，全留会让快照 JSON 无限膨胀。
_MAX_ERRORS = 20


class CandidateScoreTask(BaseModel):
    """一次批量评分的可序列化快照。"""

    task_id: str
    status: str = "running"  # running / completed / failed / cancelled
    requested: int = 0
    completed: int = 0
    failed: int = 0
    current_candidate_id: int | None = None
    current_title: str = ""
    message: str = ""
    error: str = ""
    errors: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


ACTIVE_STATUSES = {"running"}


def _read_task(db: Session) -> CandidateScoreTask | None:
    row = db.get(AppSetting, _TASK_KEY)
    if row is None:
        return None
    try:
        return CandidateScoreTask.model_validate(json.loads(row.value))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.warning("备选评分任务状态损坏，已忽略")
        return None


def _write_task(db: Session, task: CandidateScoreTask) -> CandidateScoreTask:
    serialized = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
    row = db.get(AppSetting, _TASK_KEY)
    if row is None:
        db.add(AppSetting(key=_TASK_KEY, value=serialized))
    else:
        row.value = serialized
    db.commit()
    return task


def get_candidate_score_task(db: Session) -> CandidateScoreTask | None:
    return _read_task(db)


class CandidateScoreRunner:
    """单线程 runner；任务快照负责跨请求保存进度。"""

    def __init__(self, *, session_factory: Callable[[], Any] = SessionLocal) -> None:
        self._session_factory = session_factory
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._current_task_id: str | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, candidate_ids: list[int], *, resume_id: int | None = None) -> CandidateScoreTask:
        with self._lock:
            if self.is_running():
                raise CandidateScoreBusy("已有备选岗位评分任务在后台运行，请等它结束")
            # 每个任务一个全新 Event（同 job_match_background 的理由）：
            # 上一次的取消状态不能被这一次读到。
            self._stop = threading.Event()
            task_id = uuid.uuid4().hex

            session = self._session_factory()
            try:
                task = CandidateScoreTask(
                    task_id=task_id,
                    status="running",
                    requested=len(candidate_ids),
                    message="准备评分…",
                    started_at=utcnow(),
                )
                _write_task(session, task)
            finally:
                session.close()

            self._current_task_id = task_id
            self._thread = threading.Thread(
                target=self._run,
                args=(task_id, list(candidate_ids), resume_id),
                name=f"rf-candidate-score-{task_id[:8]}",
                daemon=True,
            )
            self._thread.start()
            return task

    def cancel(self, task_id: str) -> None:
        with self._lock:
            if self._current_task_id != task_id or not self.is_running():
                raise CandidateScoreBusy("该评分任务当前未在运行，无法取消")
            self._stop.set()

    def fail_orphaned_task(self, db: Session) -> None:
        """启动自检：把上次进程退出时遗留的活跃任务标成失败。"""
        task = _read_task(db)
        if task is None or task.status not in ACTIVE_STATUSES:
            return
        _write_task(
            db,
            task.model_copy(
                update={
                    "status": "failed",
                    "error": "后端上次退出时任务被中断，请重新评分",
                    "message": "任务已中断",
                    "current_candidate_id": None,
                    "current_title": "",
                    "finished_at": utcnow(),
                }
            ),
        )

    def _run(self, task_id: str, candidate_ids: list[int], resume_id: int | None) -> None:
        stop = self._stop
        session = self._session_factory()
        completed = 0
        failed = 0
        errors: list[str] = []
        cancelled = False
        try:
            for candidate_id in candidate_ids:
                if stop.is_set():
                    cancelled = True
                    break
                candidate = session.get(CandidateJob, candidate_id)
                if candidate is None:
                    failed += 1
                    continue

                self._update(
                    session,
                    task_id,
                    current_candidate_id=candidate_id,
                    current_title=candidate.title or "",
                    completed=completed,
                    failed=failed,
                    errors=errors,
                    message=f"正在评分：{candidate.title or '(未命名)'}",
                )

                try:
                    self._score_one(session, candidate, resume_id=resume_id)
                    completed += 1
                except ScoringUnavailable as exc:
                    detail = str(exc) or type(exc).__name__
                    errors.append(f"{candidate.title}: {detail}")
                    if detail.startswith("jd_missing"):
                        # **单条问题**：这一条没有 JD 正文，其余候选照样能评。
                        # 以前这里一律当"环境不可用"整批退出——实测第一条缺 JD 就
                        # 让 11 条候选全部作废（requested=11 / failed=1 / 其余没跑）。
                        failed += 1
                        self._mark_error(session, candidate, detail)
                        session.commit()
                        continue
                    # 真正环境问题（没配模型 / 个人资料为空）：后面每一条都会同样失败，
                    # 直接收尾，不用把剩下的都跑一遍刷同样的错。
                    failed += 1
                    session.commit()
                    self._finish(
                        session,
                        task_id,
                        status="failed",
                        error=detail,
                        completed=completed,
                        failed=failed,
                        errors=errors,
                    )
                    return
                except (ScoringFailed, Exception) as exc:  # noqa: BLE001 — 单条失败不中断
                    failed += 1
                    detail = str(exc) or type(exc).__name__
                    errors.append(f"{candidate.title}: {detail}")
                    self._mark_error(session, candidate, detail)
                session.commit()

                if stop.is_set():
                    cancelled = True
                    break

            self._finish(
                session,
                task_id,
                status="cancelled" if cancelled else "completed",
                message=(
                    f"已取消（完成 {completed} 条）"
                    if cancelled
                    else f"评分完成：{completed} 条成功，{failed} 条失败"
                ),
                completed=completed,
                failed=failed,
                errors=errors,
            )
        except Exception as exc:  # noqa: BLE001 — 工作线程必须把异常落成可读状态
            logger.exception("备选评分任务失败 task_id=%s", task_id)
            self._finish(
                session,
                task_id,
                status="failed",
                error=str(exc) or "后台评分失败",
                completed=completed,
                failed=failed,
                errors=errors,
            )
        finally:
            session.close()
            with self._lock:
                if self._current_task_id == task_id:
                    self._current_task_id = None
                    self._thread = None

    def _score_one(self, session: Session, candidate: CandidateJob, *, resume_id: int | None) -> None:
        """对一条候选评分并写回五列。缺 JD 时抛 ScoringUnavailable（不调模型）。"""
        if not candidate_has_jd(candidate):
            # 协议值前缀 ``jd_missing``：前端据此决定显示「缺 JD」还是「失败」。
            # 不用中文串匹配——后端改一次文案，前端的判断就静默失效。
            raise ScoringUnavailable("jd_missing: 缺 JD 正文")

        # score_texts 内部会 close 传入的 session（调用期间不占连接池），
        # 所以这里传的是**新开**的 session，评完再回到本循环的 session 写回结果。
        scoring_session = self._session_factory()
        try:
            score, model = asyncio.run(
                score_texts(
                    scoring_session,
                    title=candidate.title,
                    company=candidate.company,
                    city=candidate.location,
                    salary=candidate.salary,
                    jd=candidate_jd(candidate),
                    resume_id=resume_id,
                )
            )
        finally:
            scoring_session.close()

        payload = score.as_dict()
        candidate.score_total = int(payload.get("total") or 0)
        candidate.score_payload = payload
        candidate.score_model = model
        candidate.scored_at = utcnow()
        candidate.score_error = ""

    def _mark_error(self, session: Session, candidate: CandidateJob, detail: str) -> None:
        candidate.score_total = None
        candidate.score_payload = None
        candidate.score_error = detail[:255]

    def _update(self, session: Session, task_id: str, **fields: Any) -> None:
        task = _read_task(session)
        if task is None or task.task_id != task_id:
            return
        _write_task(session, task.model_copy(update=fields))

    def _finish(
        self,
        session: Session,
        task_id: str,
        *,
        status: str,
        message: str = "",
        error: str = "",
        completed: int,
        failed: int,
        errors: list[str],
    ) -> None:
        task = _read_task(session)
        if task is None or task.task_id != task_id:
            return
        _write_task(
            session,
            task.model_copy(
                update={
                    "status": status,
                    "message": message,
                    "error": error,
                    "completed": completed,
                    "failed": failed,
                    "errors": errors[:_MAX_ERRORS],
                    # 终态必须清空「正在评分：X」，否则界面会挂着一条早已结束的岗位。
                    "current_candidate_id": None,
                    "current_title": "",
                    "finished_at": utcnow(),
                }
            ),
        )


class CandidateScoreBusy(Exception):
    """已有评分任务在跑 / 任务不在跑（不可取消）。"""


_runner = CandidateScoreRunner()


def get_candidate_score_runner() -> CandidateScoreRunner:
    return _runner


__all__ = [
    "CandidateScoreBusy",
    "CandidateScoreRunner",
    "CandidateScoreTask",
    "get_candidate_score_runner",
    "get_candidate_score_task",
]
