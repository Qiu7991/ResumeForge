"""用量账本（0047）：落库、按任务/模型汇总、未知 token 不臆造、隐私边界。

从上游 10-28 的 test_usage_ledger 摘出**不依赖生成任务脚手架**的部分：账本只碰
``LLMUsage`` 与数据库，一条 provider 旁路记录也在这里钉住。
"""

from __future__ import annotations

from app.models.llm_usage import LLMUsageRecord
from app.services.llm import usage_ledger
from app.services.llm.usage import build_usage, summarize_usages

FORBIDDEN_COLUMNS = {
    "prompt",
    "prompt_text",
    "messages",
    "response",
    "completion",
    "content",
    "api_key",
    "password",
    "email",
    "name",
    "request_body",
    "response_body",
}


def _usage(model: str = "synthetic-model"):
    return build_usage(
        model,
        elapsed_ms=120,
        finish_reason="stop",
        prompt_tokens=100,
        completion_tokens=50,
        retries=1,
    )


class _FakeProvider:
    def __init__(self, usage=None) -> None:
        self.last_usage = usage


def test_record_llm_usage_copies_tokens_and_unknown_stays_null(db_session):
    known = usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage())
    assert (known.prompt_tokens, known.completion_tokens, known.total_tokens) == (100, 50, 150)
    assert (known.duration_ms, known.finish_reason, known.retries) == (120, "stop", 1)

    unknown = usage_ledger.record_llm_usage(db_session, task="translate", usage=None)
    assert unknown.prompt_tokens is None
    assert unknown.completion_tokens is None
    assert unknown.total_tokens is None
    assert unknown.finish_reason == usage_ledger.FINISH_UNKNOWN
    assert unknown.retries == 0


def test_record_provider_usage_reads_last_usage(db_session):
    row = usage_ledger.record_provider_usage(
        db_session, task=usage_ledger.TASK_RESUME_REVISE, provider=_FakeProvider(_usage())
    )
    assert row.model == "synthetic-model"
    assert row.total_tokens == 150

    bare = usage_ledger.record_provider_usage(
        db_session, task=usage_ledger.TASK_RESUME_REVISE, provider=object()
    )
    assert bare.total_tokens is None


def test_summary_aggregates_by_task_and_model_without_partial_sums(db_session):
    usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage("model-a"))
    usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage("model-a"))
    usage_ledger.record_llm_usage(db_session, task="translate", usage=None, model="model-b")

    summary = usage_ledger.summarize_usage(db_session)

    assert summary["records"] == 3
    assert summary["unknown_token_records"] == 1
    assert summary["totals"]["total_tokens"] is None
    assert summary["totals"]["calls"] == 3
    buckets = {item["key"]: item for item in summary["tasks"]}
    assert buckets["resume_revise"]["total_tokens"] == 300
    assert buckets["translate"]["unknown_token_calls"] == 1
    assert summary["cost"]["estimated"] is False
    assert summary["cost"]["amount"] is None


def test_summary_filters_by_task(db_session):
    usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage())
    usage_ledger.record_llm_usage(db_session, task="assistant", usage=_usage())

    summary = usage_ledger.summarize_usage(db_session, task="assistant")

    assert summary["records"] == 1
    assert [item["key"] for item in summary["tasks"]] == ["assistant"]


def test_finish_reasons_are_recorded_and_aggregated(db_session):
    usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage())
    usage_ledger.record_llm_usage(
        db_session,
        task="resume_revise",
        usage=build_usage(
            "synthetic-model", elapsed_ms=10, finish_reason="length", prompt_tokens=1
        ),
    )
    usage_ledger.record_llm_usage(db_session, task="translate", usage=None)

    summary = usage_ledger.summarize_usage(db_session)
    buckets = {item["key"]: item for item in summary["tasks"]}

    assert buckets["resume_revise"]["finish_reasons"] == {"length": 1, "stop": 1}
    assert buckets["translate"]["finish_reasons"] == {usage_ledger.FINISH_UNKNOWN: 1}
    assert summary["totals"]["finish_reasons"] == {"length": 1, "stop": 1, "unknown": 1}


def test_records_and_summary_endpoints_expose_only_numbers(client, db_session):
    usage_ledger.record_llm_usage(db_session, task="resume_revise", usage=_usage())

    records = client.get("/api/usage/records")
    assert records.status_code == 200, records.text
    body = records.json()
    assert body["count"] == 1
    item = body["items"][0]
    assert item["finish_reason"] == "stop"
    assert item["retries"] == 1
    assert item["total_tokens"] == 150
    for forbidden in ("prompt_text", "messages", "api_key", "password", "content"):
        assert forbidden not in item

    summary = client.get("/api/usage/summary")
    assert summary.status_code == 200, summary.text
    payload = summary.json()
    assert payload["records"] == 1
    assert payload["totals"]["calls"] == 1
    serialized = str(payload).lower()
    for forbidden in ("prompt_text", "messages", "api_key", "password", "content"):
        assert forbidden not in serialized


def test_usage_table_has_no_prompt_or_secret_columns():
    columns = {column.name for column in LLMUsageRecord.__table__.columns}
    assert columns.isdisjoint(FORBIDDEN_COLUMNS)


def test_summarize_app_usages_reuses_the_existing_in_memory_contract():
    usages = [_usage(), _usage()]
    assert usage_ledger.summarize_app_usages(usages) == summarize_usages(usages)


def test_provider_bypass_records_usage_when_ambient_task_is_set(db_session):
    """provider 的旁路上报：有任务名才落账，且只写数字（无正文/密钥）。"""
    from app.services.llm.usage_tasks import record_ambient_usage, set_ambient_task

    set_ambient_task("job_match")
    try:
        record_ambient_usage(_FakeProvider(_usage("ambient-model")))
    finally:
        set_ambient_task(None)
    db_session.expire_all()

    row = db_session.query(LLMUsageRecord).one()
    assert row.task == "job_match"
    assert row.model == "ambient-model"
    assert row.total_tokens == 150

    # 没有任务名（单测/设置页测试连接）不落账。
    before = db_session.query(LLMUsageRecord).count()
    record_ambient_usage(_FakeProvider(_usage()))
    assert db_session.query(LLMUsageRecord).count() == before
