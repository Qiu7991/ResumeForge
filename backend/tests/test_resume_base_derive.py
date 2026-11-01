# SPDX-License-Identifier: Apache-2.0
"""以某份简历为底稿生成：复制底稿 + 按 JD 修订（本地二开回放）。

纪律：
1. 底稿被**复制后修订**，不是被"重新生成"越过——模型提示里必须带着底稿正文，
   底稿本身不改，派生记录指回底稿（runner 里写 `parent_revision_id`）。
2. 底稿不存在时立刻失败，不白跑模型。
"""

from __future__ import annotations

import json

import pytest

from app.models.resume import ResumeRecord
from app.runtime.operation_budget import OperationBudget
from app.services.llm.base import BaseLLMProvider
from app.services.resume.resume_base_derive import (
    BaseResumeMissing,
    derive_from_base,
    load_base_resume,
)


class CapturingProvider(BaseLLMProvider):
    """一次性对话：记录提示词，返回按 JD 调整后的简历 JSON。"""

    def __init__(self, captured: list):
        super().__init__(None)  # type: ignore[arg-type] - 测试假 Provider 不需要真实配置
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


@pytest.mark.asyncio
async def test_derive_from_base_copies_draft_and_reports_provenance(db_session):
    base = _base_record(db_session)
    captured: list = []
    provider = CapturingProvider(captured)
    budget = OperationBudget.start(60)

    content, warnings = await derive_from_base(
        provider, base, None, "", budget=budget
    )

    assert content["summary"] == "按 JD 调整后的总结"
    # 提示里带着底稿正文：模型是在底稿上改，而不是从资料重新抽取事实。
    prompt = "\n".join(message["content"] for message in captured[0])
    assert "母版里的定稿总结" in prompt
    assert warnings and "母版" in warnings[0]

    db_session.refresh(base)
    assert base.content["summary"] == "母版里的定稿总结"


def test_load_base_resume_rejects_missing_or_deleted(db_session):
    with pytest.raises(BaseResumeMissing):
        load_base_resume(db_session, 999_999, is_deleted=lambda record: False)

    base = _base_record(db_session)
    with pytest.raises(BaseResumeMissing):
        load_base_resume(db_session, base.id, is_deleted=lambda record: True)
