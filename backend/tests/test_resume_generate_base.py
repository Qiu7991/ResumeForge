"""以某份简历为底稿生成：复制底稿 + 按 JD 修订。

两条纪律：
1. 底稿被**复制后修订**，不是被"重新生成"越过——模型提示里必须带着底稿正文，
   底稿本身不改，派生记录指回底稿（parent_revision_id）。
2. 底稿不存在时任务立刻失败，不白跑模型、不落半成品。

这里覆盖 ``resume_base_derive``（纯函数，无后台线程）与任务侧的失败前置；成功路径的
线程/落库一致性与普通生成共用同一套 runner 逻辑，由 test_resume_generate_task 覆盖。
"""

from __future__ import annotations

import json

import pytest

from app.models.resume import ResumeRecord
from app.runtime.operation_budget import OperationBudget
from app.services.llm.base import BaseLLMProvider
from app.services.resume import resume_base_derive
from test_resume_generate_task import (  # noqa: F401 - _isolate_runner 是 autouse fixture
    _configure,
    _isolate_runner,
    _job,
    _seed_profile,
    _wait_terminal,
)


def _wait_runner_idle(timeout: float = 5.0) -> None:
    """等后台线程真正退出（任务状态先于线程收尾可见，直接清理会撞写锁）。"""
    import time as _time

    from app.services.resume.resume_generate_runner import get_resume_generate_runner

    deadline = _time.monotonic() + timeout
    runner = get_resume_generate_runner()
    while runner.is_running() and _time.monotonic() < deadline:
        _time.sleep(0.01)


class CapturingProvider(BaseLLMProvider):
    """一次性对话：记录提示词，返回按 JD 调整后的简历 JSON。"""

    def __init__(self, config, captured: list):
        super().__init__(config)
        self._captured = captured

    async def chat(self, messages, *, thinking: bool = True):
        self._captured.append(messages)
        return json.dumps(
            {"summary": "按 JD 调整后的总结", "projects": [{"name": "简历通"}]},
            ensure_ascii=False,
        )

    async def stream_chat(self, _messages):
        raise AssertionError("底稿模式不应走流式生成")


def _base_record(db_session) -> ResumeRecord:
    record = ResumeRecord(
        title="母版",
        source="manual",
        content={
            "name": "张三",
            "summary": "母版里的定稿总结",
            "projects": [{"name": "简历通", "role": "核心开发"}],
        },
    )
    db_session.add(record)
    db_session.commit()
    return record


def test_derive_from_base_keeps_the_draft_and_reports_provenance(db_session):
    base = _base_record(db_session)
    captured: list = []
    provider = CapturingProvider(None, captured)
    budget = OperationBudget.start(60)

    content, warnings = __import__("asyncio").run(
        resume_base_derive.derive_from_base(
            provider,
            base,
            None,
            "",  # 没写额外要求 → 用默认"保留事实、只调取舍与表达"的口径
            budget=budget,
        )
    )

    assert content["summary"] == "按 JD 调整后的总结"
    assert "母版里的定稿总结" in json.dumps(captured[0], ensure_ascii=False)
    assert "底稿" in warnings[0]
    # 默认口径必须写清楚"不改事实"——这是底稿模式的安全边界。
    prompt_text = json.dumps(captured[0], ensure_ascii=False)
    assert "不要新增底稿里没有的事实" in prompt_text


def test_load_base_resume_rejects_missing_or_deleted(db_session):
    from app.services import trash

    with pytest.raises(resume_base_derive.BaseResumeMissing):
        resume_base_derive.load_base_resume(db_session, 999999, is_deleted=trash.is_deleted)

    base = _base_record(db_session)
    base.deleted_at = __import__("datetime").datetime.now()
    db_session.commit()
    with pytest.raises(resume_base_derive.BaseResumeMissing):
        resume_base_derive.load_base_resume(db_session, base.id, is_deleted=trash.is_deleted)


def test_generate_task_rejects_missing_base_resume(client, monkeypatch):
    """底稿 id 不存在：任务直接失败，给出可读原因，且不写任何简历记录。"""
    _seed_profile(client)
    _configure(client)
    job = _job(client)

    class UnusedProvider(BaseLLMProvider):
        async def chat(self, _messages, *, thinking: bool = True):
            raise AssertionError("底稿不存在时不应调用模型")

        async def stream_chat(self, _messages):
            raise AssertionError("底稿不存在时不应调用模型")

    monkeypatch.setattr(
        "app.services.resume.resume_generate_runner.create_provider",
        lambda resolved: UnusedProvider(resolved),
    )

    started = client.post(
        "/api/resumes/generate/tasks",
        json={"job_id": job["id"], "options": {"base_resume_id": 999999}},
    )
    assert started.status_code == 201
    final = _wait_terminal(client, started.json()["id"])
    _wait_runner_idle()
    assert final["status"] == "failed"
    assert "底稿" in (final.get("error") or "")
    assert final["resume_id"] is None
