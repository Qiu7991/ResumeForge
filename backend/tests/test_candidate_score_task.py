# SPDX-License-Identifier: Apache-2.0
"""备选岗位批量评分任务：缺 JD 不中断整批、环境错误才收尾、单条失败继续。"""
from __future__ import annotations

import pytest

from app.models.material import CANDIDATE_JOB_PENDING, CandidateJob
from app.services.job_hunt import candidate_score_task as task_mod
from app.services.job_hunt.candidate_score_task import CandidateScoreRunner
from app.services.job_hunt.scoring import SemanticScore


def _candidate(db, *, title: str, jd: str = "") -> CandidateJob:
    row = CandidateJob(
        title=title,
        company="示例公司",
        description=jd,
        status=CANDIDATE_JOB_PENDING,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _stub_scoring(monkeypatch, behaviours: dict[str, object]) -> list[str]:
    """按标题脚本化 score_texts 的行为，返回被评过的标题（按顺序）。"""
    called: list[str] = []

    async def fake_score_texts(
        db, *, title, company, city="", salary="", jd="", resume_id=None, compact=False
    ):
        called.append(title)
        outcome = behaviours.get(title)
        if isinstance(outcome, Exception):
            raise outcome
        return SemanticScore(ok=True, total=70), "fake-model"

    monkeypatch.setattr(task_mod, "score_texts", fake_score_texts)
    return called


def test_missing_jd_does_not_abort_the_batch(db_session, monkeypatch):
    """回归：第一条缺 JD 时必须跳过它继续评后面的，不能整批作废。

    实测过一次：11 条候选里第一条缺 JD，任务变成 requested=11 / failed=1 就结束，
    剩下 10 条一条都没评。
    """
    blank = _candidate(db_session, title="没 JD 的岗位", jd="")
    good1 = _candidate(db_session, title="有 JD 的岗位一", jd="负责后端开发。")
    good2 = _candidate(db_session, title="有 JD 的岗位二", jd="负责前端开发。")

    called = _stub_scoring(monkeypatch, {})
    runner = CandidateScoreRunner()
    runner._run(
        "task-1",
        [blank.id, good1.id, good2.id],
        None,
    )

    # 「没 JD 的岗位」不会进模型调用（直接判缺 JD），另外两条都评了。
    # **不比顺序**：并发评分下完成顺序不保证，比顺序的断言会随机红。
    assert sorted(called) == sorted(["有 JD 的岗位一", "有 JD 的岗位二"])
    db_session.expire_all()
    assert db_session.get(CandidateJob, blank.id).score_error.startswith("jd_missing")
    assert db_session.get(CandidateJob, good1.id).score_total == 70
    assert db_session.get(CandidateJob, good2.id).score_total == 70


def test_environment_error_marks_failed_when_nothing_scored(db_session, monkeypatch):
    """整批都没评成（例如没配模型）时任务标失败，且原因写进 task.error。

    并发评分（``_SCORE_CONCURRENCY``）之后不再"第一条失败就收尾"——多条同时在飞，
    已经在跑的那几条没必要中途掐掉。关键是**一条都没成功时要如实标失败**，
    不能让用户看到"完成"却没有任何分数。
    """
    first = _candidate(db_session, title="第一条", jd="职责 A。")
    second = _candidate(db_session, title="第二条", jd="职责 B。")

    from app.services.job_hunt.scoring_service import ScoringUnavailable

    _stub_scoring(
        monkeypatch,
        {
            "第一条": ScoringUnavailable("还没有配置大模型"),
            "第二条": ScoringUnavailable("还没有配置大模型"),
        },
    )
    # ``_run`` 的收尾依赖 task 快照存在（``_finish`` 按 task_id 找），
    # 直接调 _run 时要先把快照写进去——正常路径由 ``start()`` 负责这一步。
    task_mod._write_task(
        db_session,
        task_mod.CandidateScoreTask(task_id="task-2", status="running", requested=2),
    )
    runner = CandidateScoreRunner()
    runner._run("task-2", [first.id, second.id], None)

    db_session.expire_all()
    assert db_session.get(CandidateJob, first.id).score_total is None
    assert db_session.get(CandidateJob, second.id).score_total is None
    task = task_mod.get_candidate_score_task(db_session)
    assert task is not None
    assert task.status == "failed", "一条都没评成时不能标完成"
    assert "还没有配置大模型" in (task.error or "")


def test_single_failure_continues(db_session, monkeypatch):
    """单条模型调用失败不该中断整批。"""
    broken = _candidate(db_session, title="会失败的", jd="职责 A。")
    fine = _candidate(db_session, title="正常的", jd="职责 B。")

    from app.services.job_hunt.scoring_service import ScoringFailed

    called = _stub_scoring(monkeypatch, {"会失败的": ScoringFailed("网络超时")})
    runner = CandidateScoreRunner()
    runner._run("task-3", [broken.id, fine.id], None)

    assert sorted(called) == sorted(["会失败的", "正常的"])
    db_session.expire_all()
    broken_row = db_session.get(CandidateJob, broken.id)
    assert broken_row.score_total is None
    assert "网络超时" in broken_row.score_error
    assert db_session.get(CandidateJob, fine.id).score_total == 70
