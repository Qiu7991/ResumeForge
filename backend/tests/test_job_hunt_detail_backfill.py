# SPDX-License-Identifier: Apache-2.0
"""JD 补抓测试：只补空 JD、限速、单条失败不中断、详情页薪资覆盖列表页。"""
from __future__ import annotations

import pytest

from app.models.job import JOB_STATUS_OPEN, Job
from app.services.job_hunt.base import JobParseError, JobDetail
from app.services.job_hunt.detail_backfill import backfill_details


class FakeAdapter:
    """假适配器：按 URL 返回预设详情。"""

    def __init__(self, details: dict[str, JobDetail], raise_on: set[str] | None = None):
        self._details = details
        self._raise_on = raise_on or set()

    def parse_detail(self, html: str) -> JobDetail:
        if html in self._raise_on:
            raise JobParseError("详情页结构不符", site_key="boss")
        if html not in self._details:
            raise JobParseError("未知页面", site_key="boss")
        return self._details[html]


def _job(db_session, *, title: str, url: str, description: str = "", salary: str = "8-12K") -> Job:
    job = Job(
        title=title,
        company="测试公司",
        location="广州",
        salary=salary,
        description=description,
        source_url=url,
        status=JOB_STATUS_OPEN,
    )
    db_session.add(job)
    db_session.commit()
    return job


def test_fills_empty_jd(db_session):
    job = _job(db_session, title="AI 工程师", url="u1")
    adapter = FakeAdapter({"u1": JobDetail(title="AI 工程师", description="负责 AI 应用开发。", salary_decoded="10-15K", salary_decoded_ok=True)})

    report = backfill_details(
        db_session, [job.id], fetch=lambda url: "u1", adapter=adapter, interval=0
    )

    assert report.attempted == 1
    assert report.filled == 1
    assert report.errors == []
    db_session.refresh(job)
    assert job.description == "负责 AI 应用开发。"
    # 详情页薪资是明文，应覆盖列表页解码结果
    assert job.salary == "10-15K"


def test_skips_jobs_that_already_have_jd(db_session):
    job = _job(db_session, title="已有 JD", url="u2", description="原有正文")
    adapter = FakeAdapter({})

    report = backfill_details(db_session, [job.id], fetch=lambda u: u, adapter=adapter, interval=0)

    assert report.skipped_has_jd == 1
    assert report.attempted == 0
    db_session.refresh(job)
    assert job.description == "原有正文"  # 不被覆盖


def test_single_failure_does_not_stop_batch(db_session):
    ok = _job(db_session, title="正常岗位", url="ok-url")
    bad = _job(db_session, title="解析失败岗位", url="bad-url")
    adapter = FakeAdapter({"ok-url": JobDetail(description="正文")}, raise_on={"bad-url"})

    report = backfill_details(
        db_session, [bad.id, ok.id], fetch=lambda u: u, adapter=adapter, interval=0
    )

    assert report.attempted == 2
    assert report.filled == 1
    assert len(report.errors) == 1
    assert "解析失败" in report.errors[0]
    db_session.refresh(ok)
    assert ok.description == "正文"  # 后面那条仍然补上了


def test_missing_url_reported(db_session):
    job = _job(db_session, title="无链接", url="")
    adapter = FakeAdapter({})

    report = backfill_details(db_session, [job.id], fetch=lambda u: u, adapter=adapter, interval=0)

    assert report.attempted == 0
    assert any("没有来源链接" in e for e in report.errors)


def test_respects_limit(db_session):
    jobs = [_job(db_session, title=f"岗位{i}", url=f"u{i}") for i in range(5)]
    adapter = FakeAdapter({f"u{i}": JobDetail(description=f"正文{i}") for i in range(5)})

    report = backfill_details(
        db_session, [j.id for j in jobs], fetch=lambda u: u, adapter=adapter, interval=0, limit=2
    )

    assert report.attempted == 2
    assert report.filled == 2


def test_overwrite_refetches_jobs_that_already_have_jd(db_session):
    """``overwrite=True`` 必须重抓已有 JD 的岗位。

    回归背景（2026-11-11）：抓取层错用列表页的就绪选择器，导致入库的 JD 普遍残缺。
    修好抓取层后，存量那些行的 description 非空，默认路径（只补空 JD）会全部跳过，
    等于修不了——所以必须有这条强制重抓的路径。
    """
    job = _job(db_session, title="AI 工程师", url="u-old", description="工作内容：1、做A")
    adapter = FakeAdapter(
        {"u-old": JobDetail(title="AI 工程师", description="完整 JD：" + "很长的正文。" * 30)}
    )

    report = backfill_details(
        db_session, [job.id], fetch=lambda url: url, adapter=adapter, overwrite=True
    )

    assert report.filled == 1
    assert report.skipped_has_jd == 0, "overwrite 时不该跳过已有 JD"
    db_session.refresh(job)
    assert job.description.startswith("完整 JD：")
    assert len(job.description) > 100


def test_default_still_skips_existing_jd(db_session):
    """默认行为不变：已有 JD 的不重抓（日常语义，避免重复访问引来风控）。"""
    job = _job(db_session, title="AI 工程师", url="u2", description="已有正文")
    adapter = FakeAdapter({"u2": JobDetail(title="AI 工程师", description="新正文")})

    report = backfill_details(db_session, [job.id], fetch=lambda url: url, adapter=adapter)

    assert report.skipped_has_jd == 1
    assert report.filled == 0
    db_session.refresh(job)
    assert job.description == "已有正文"
