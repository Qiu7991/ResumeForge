"""批量匹配的失败重试与「AI 对比选岗」降级/存储。

重试只认 ``LLMError.retryable``：模型这一次产出不合格（JSON/证据核对）再要一次通常就好；
传输层错误与硬配置错误不重试。对比在未配置模型时按参考分本地降级，并把结论存进
``app_setting``（不新增表列）。
"""

from __future__ import annotations

import pytest
from app.schemas.job_comparison import JobComparisonResult
from app.schemas.job_match import JobMatchResult
from app.services.job.job_comparison_store import load_comparison, save_comparison
from app.services.job.job_match import finalize_match_result
from app.services.llm.base import LLMError
from app.schemas.setting import LLMConfig

CONFIGURED = LLMConfig(base_url="https://model.example/v1", model="test-model")
UNCONFIGURED = LLMConfig(base_url="", model="")


def _input(job_id: int = 1):
    from app.services.job.job_match_batch import BatchMatchInput

    return BatchMatchInput(
        job_id=job_id,
        job_title="后端开发",
        company="示例公司",
        payload={"title": "后端开发", "requirements": "熟悉 Python"},
        profile_text='{"summary":"Python 后端开发"}',
        resume_text="",
        existing_result=None,
        existing_model="",
    )


def _ok_result() -> JobMatchResult:
    return finalize_match_result(JobMatchResult(notes=["证据齐备"]))


@pytest.mark.asyncio
async def test_retryable_failure_is_retried_once_and_can_succeed(monkeypatch):
    from app.services.job import job_match_batch

    calls = {"count": 0}

    async def fake_analyze(_provider, _payload, _profile, _resume):
        calls["count"] += 1
        if calls["count"] == 1:
            raise LLMError("模型返回的匹配证据无法在资料或简历中核对，请重试", retryable=True)
        return _ok_result()

    monkeypatch.setattr("app.services.job.job_match.analyze_match", fake_analyze)
    monkeypatch.setattr(job_match_batch, "create_provider", lambda _config: object())

    run = await job_match_batch.run_batch_match([_input()], CONFIGURED)

    assert calls["count"] == 2, "可重试的失败应当只重试一次"
    assert run.items[0].status == "completed"
    assert run.items[0].analysis_source == "new"


@pytest.mark.asyncio
async def test_non_retryable_failure_is_not_retried(monkeypatch):
    from app.services.job import job_match_batch

    calls = {"count": 0}

    async def fake_analyze(_provider, _payload, _profile, _resume):
        calls["count"] += 1
        raise LLMError("模型返回错误：model not found")

    monkeypatch.setattr("app.services.job.job_match.analyze_match", fake_analyze)
    monkeypatch.setattr(job_match_batch, "create_provider", lambda _config: object())

    run = await job_match_batch.run_batch_match([_input()], CONFIGURED)

    assert calls["count"] == 1
    assert run.items[0].status == "failed"
    assert "model not found" in run.items[0].error


@pytest.mark.asyncio
async def test_retry_stops_when_cancelled(monkeypatch):
    from app.services.job import job_match_batch

    state = {"count": 0, "cancel": False}

    async def fake_analyze(_provider, _payload, _profile, _resume):
        state["count"] += 1
        state["cancel"] = True
        raise LLMError("模型返回的匹配证据无法在资料或简历中核对，请重试", retryable=True)

    monkeypatch.setattr("app.services.job.job_match.analyze_match", fake_analyze)
    monkeypatch.setattr(job_match_batch, "create_provider", lambda _config: object())

    run = await job_match_batch.run_batch_match(
        [_input()], CONFIGURED, should_cancel=lambda: state["cancel"]
    )

    assert state["count"] == 1, "收到取消信号后不许再发请求"
    assert run.items[0].status == "failed"


@pytest.mark.asyncio
async def test_comparison_without_model_falls_back_to_reference_score():
    from app.services.job.job_match_batch import run_batch_comparison, run_batch_match

    run = await run_batch_match([_input(1), _input(2)], UNCONFIGURED)
    comparison = await run_batch_comparison([_input(1), _input(2)], run, UNCONFIGURED)

    assert [item.rank for item in comparison.items] == [1, 2]
    assert comparison.items[0].verdict == "best"
    assert "未接入大模型" in comparison.notes[0]


@pytest.mark.asyncio
async def test_comparison_needs_at_least_two_completed_items():
    from app.services.job.job_match_batch import run_batch_comparison, run_batch_match

    run = await run_batch_match([_input(1)], UNCONFIGURED)
    comparison = await run_batch_comparison([_input(1)], run, UNCONFIGURED)

    assert comparison.items == []
    assert "不足 2 个" in comparison.error


def test_comparison_round_trips_through_app_setting(db_session):
    comparison = JobComparisonResult(
        summary="更适合岗位 1",
        items=[
            {
                "job_id": 1,
                "rank": 1,
                "verdict": "best",
                "headline": "条件最贴合",
                "reasons": ["硬性条件全部满足"],
            }
        ],
        notes=["仅供比较"],
    )

    save_comparison(db_session, 42, comparison)
    db_session.commit()

    loaded = load_comparison(db_session, 42)

    assert loaded is not None
    assert loaded.summary == "更适合岗位 1"
    assert loaded.items[0].job_id == 1


def test_batch_api_rejects_invalid_compare_size(client):
    one = client.post(
        "/api/jobs/match-batches", json={"job_ids": [1], "mode": "compare"}
    )
    assert one.status_code == 400
    assert "至少选择 2 个" in one.json()["detail"]

    too_many = client.post(
        "/api/jobs/match-batches",
        json={"job_ids": list(range(1, 14)), "mode": "compare"},
    )
    assert too_many.status_code == 400
    assert "最多 12 个" in too_many.json()["detail"]


def test_compare_batch_returns_local_ranking_and_persists(client, db_session):
    """未配置模型时：逐岗走本地降级，对比按参考分排序并随批次保存。"""
    from app.models.job import JOB_STATUS_OPEN, Job
    from app.models.profile import UserProfile

    db_session.add(UserProfile(name="张示例", summary="Python 后端开发"))
    first = Job(
        title="后端开发",
        company="示例公司",
        status=JOB_STATUS_OPEN,
        description="负责 Python 服务开发",
        requirements="熟悉 Python；本科及以上",
    )
    second = Job(
        title="产品助理",
        company="示例公司",
        status=JOB_STATUS_OPEN,
        description="负责用户访谈与需求整理",
        requirements="具备沟通能力",
    )
    db_session.add_all([first, second])
    db_session.commit()
    db_session.refresh(first)
    db_session.refresh(second)

    response = client.post(
        "/api/jobs/match-batches",
        json={"job_ids": [second.id, first.id], "mode": "compare"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "compare"
    assert body["comparison"] is not None
    assert [item["rank"] for item in body["comparison"]["items"]] == [1, 2]
    assert "未接入大模型" in body["comparison"]["notes"][0]
    # 条目顺序按对比名次；参考分在本地降级里就是排序依据。
    assert [item["job_id"] for item in body["items"]] == [
        item["job_id"] for item in body["comparison"]["items"]
    ]

    history = client.get("/api/jobs/match-batches").json()
    assert history[0]["mode"] == "compare"
    detail = client.get(f"/api/jobs/match-batches/{body['id']}").json()
    assert detail["comparison"]["summary"] == body["comparison"]["summary"]
