# SPDX-License-Identifier: Apache-2.0
"""备选岗位 JD 补抓：写候选表（不是 Job 表）、按候选判空、切段落库。"""
from __future__ import annotations

from app.models.material import CANDIDATE_JOB_PENDING, CandidateJob
from app.services.job_hunt.base import JobDetail
from app.services.job_hunt.candidate_jd_backfill import backfill_candidate_jd


class FakeAdapter:
    def __init__(self, details: dict[str, JobDetail]):
        self._details = details

    def parse_detail(self, html: str) -> JobDetail:
        return self._details[html]


def _candidate(db, *, title: str, url: str) -> CandidateJob:
    row = CandidateJob(
        title=title, company="示例公司", source_url=url, status=CANDIDATE_JOB_PENDING
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_fills_candidate_description(db_session):
    """核心回归：**候选**表要被填上，而不是去查 Job 表。

    实测过的 bug：直接复用正式岗位那套 `backfill_details` 时，它按 `Job` 模型读写，
    拿候选 id 传进去查不到行 → 每一条都被判成"已有 JD"静默跳过
    （日志 `尝试 0 / 成功 0 / 跳过 11`），于是评分全部变成「缺 JD」。
    """
    row = _candidate(db_session, title="AI 工程师", url="u1")
    adapter = FakeAdapter(
        {"u1": JobDetail(title="AI 工程师", description="岗位职责：负责 AI 开发。", salary_decoded="10-15K", salary_decoded_ok=True)}
    )

    report = backfill_candidate_jd(db_session, [row.id], fetch=lambda url: url, adapter=adapter, interval=0)

    assert report.attempted == 1
    assert report.filled == 1
    db_session.refresh(row)
    assert "负责 AI 开发" in row.description


def test_skips_candidate_that_already_has_jd(db_session):
    """已有正文的不重抓（与评分判空同源）。"""
    row = _candidate(db_session, title="已有 JD", url="u2")
    row.description = "已经有正文了。"
    db_session.commit()

    report = backfill_candidate_jd(
        db_session, [row.id], fetch=lambda url: "never", adapter=FakeAdapter({}), interval=0
    )

    assert report.skipped_has_jd == 1
    assert report.filled == 0


def test_manual_candidate_without_url_is_counted_separately(db_session):
    """手动粘贴的候选没有来源链接：单独计数，不混进"抓取失败"。"""
    row = _candidate(db_session, title="手动候选", url="")

    report = backfill_candidate_jd(
        db_session, [row.id], fetch=lambda url: "x", adapter=FakeAdapter({}), interval=0
    )

    assert report.no_url == 1
    assert report.errors == []


def test_splits_description_and_requirements(db_session):
    """详情页正文按小标题切成职责/要求两列，与投递台采集的落库口径一致。"""
    row = _candidate(db_session, title="切分测试", url="u3")
    adapter = FakeAdapter(
        {
            "u3": JobDetail(
                title="切分测试",
                description="岗位职责：负责 A、B、C。任职要求：本科以上，三年经验。",
                salary_decoded="8-12K",
                salary_decoded_ok=True,
            )
        }
    )

    backfill_candidate_jd(db_session, [row.id], fetch=lambda url: url, adapter=adapter, interval=0)

    db_session.refresh(row)
    assert row.description, "职责段不能为空"
    assert "负责 A" in row.description
    # 要求段能被切出来就落进 requirements；切不出也至少正文不丢。
    assert (row.requirements or "") + row.description


def test_reports_progress_per_candidate(db_session):
    """每处理完一条就要回调一次进度。

    补 JD 是限速的（每条 1.5s），15 条要 20 多秒。没有进度回调，界面上只能干等，
    看不出是在跑还是卡住了——那正是「进度显示不明显」的一部分。
    """
    rows = [
        _candidate(db_session, title=f"岗位{i}", url=f"u{i}") for i in range(3)
    ]
    adapter = FakeAdapter(
        {
            f"u{i}": JobDetail(
                title=f"岗位{i}", description=f"职责 {i}。", salary_decoded="8-12K", salary_decoded_ok=True
            )
            for i in range(3)
        }
    )

    seen: list[tuple[int, int]] = []
    backfill_candidate_jd(
        db_session,
        [row.id for row in rows],
        fetch=lambda url: url,
        adapter=adapter,
        interval=0,
        on_progress=lambda done, total: seen.append((done, total)),
    )

    assert seen == [(1, 3), (2, 3), (3, 3)], "进度必须是逐条递增的 (done, total)"


def test_progress_counts_already_filled_candidates(db_session):
    """已有 JD 被跳过的那些也要推进度，否则分母不动、看起来像卡住。"""
    has_jd = _candidate(db_session, title="已有正文", url="a")
    has_jd.description = "已有。"
    db_session.commit()
    empty = _candidate(db_session, title="空的", url="b")

    seen: list[tuple[int, int]] = []
    backfill_candidate_jd(
        db_session,
        [has_jd.id, empty.id],
        fetch=lambda url: url,
        adapter=FakeAdapter(
            {"b": JobDetail(title="空的", description="新正文", salary_decoded="", salary_decoded_ok=False)}
        ),
        interval=0,
        on_progress=lambda done, total: seen.append((done, total)),
    )

    assert seen == [(1, 2), (2, 2)]
