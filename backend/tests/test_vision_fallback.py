"""看图模型兜底：只在"带图且失败指向视觉能力"时换模型重试一次。

这条兜底要修的是真实事故：服务商把纯文本模型接在同一个 /chat/completions 上，
图片被静默忽略 → 抄录为空 → 识别失败 → 本地规则也读不了图 → 用户看到空表单。
"""

from __future__ import annotations

import pytest

from app.schemas.setting import LLMConfig
from app.services import vision_fallback
from app.services.llm.base import LLMError


def _config(model: str = "deepseek-v4.1-flash-1017") -> LLMConfig:
    return LLMConfig(base_url="https://example.com/v1", api_key="k", model=model)


def test_pick_vision_model_uses_preference_order_and_skips_current():
    assert (
        vision_fallback.pick_vision_model(["seed-2.1-pro", "mimo-v2.6-pro"], "deepseek")
        == "mimo-v2.6-pro"
    )
    # 已经是看图模型就别自己重试自己
    assert vision_fallback.pick_vision_model(["mimo-v2.6-pro"], "mimo-v2.6-pro") is None
    # 列表里没有认识的模型名：不乱猜
    assert vision_fallback.pick_vision_model(["some-private-model"], "deepseek") is None


def test_looks_like_vision_failure_only_matches_vision_hints():
    assert vision_fallback.looks_like_vision_failure(
        "模型未抄录图片中的文字，无法核对识别结果，请重试"
    )
    assert vision_fallback.looks_like_vision_failure(
        '当前模型不支持该能力：vision'
    )
    # 超时是同一个问题重跑一遍，不该换模型
    assert not vision_fallback.looks_like_vision_failure("模型响应超时，请稍后重试")


async def test_retries_with_vision_model_and_reports_the_switch(monkeypatch):
    used: list[str] = []

    async def fake_resolve(config):  # noqa: ANN001
        return "mimo-v2.6-pro"

    def fake_create(config):  # noqa: ANN001
        used.append(config.model)
        return object()

    monkeypatch.setattr(vision_fallback, "resolve_vision_model", fake_resolve)
    monkeypatch.setattr(vision_fallback, "create_provider", fake_create)

    async def run(provider):  # noqa: ANN001
        if len(used) == 1:
            raise LLMError("模型未抄录图片中的文字，无法核对识别结果，请重试")
        return "识别成功"

    result, note = await vision_fallback.run_with_vision_fallback(
        _config(), run, has_images=True
    )

    assert result == "识别成功"
    assert used == ["deepseek-v4.1-flash-1017", "mimo-v2.6-pro"]
    assert "mimo-v2.6-pro" in note and "读不了图片" in note


async def test_does_not_retry_without_images(monkeypatch):
    called: list[str] = []

    async def fake_resolve(config):  # noqa: ANN001
        called.append("resolve")
        return "mimo-v2.6-pro"

    monkeypatch.setattr(vision_fallback, "resolve_vision_model", fake_resolve)
    monkeypatch.setattr(vision_fallback, "create_provider", lambda config: object())

    async def run(provider):  # noqa: ANN001
        raise LLMError("模型未抄录图片中的文字，无法核对识别结果，请重试")

    with pytest.raises(LLMError):
        await vision_fallback.run_with_vision_fallback(_config(), run, has_images=False)
    assert called == []


async def test_does_not_retry_on_unrelated_failures(monkeypatch):
    called: list[str] = []

    async def fake_resolve(config):  # noqa: ANN001
        called.append("resolve")
        return "mimo-v2.6-pro"

    monkeypatch.setattr(vision_fallback, "resolve_vision_model", fake_resolve)
    monkeypatch.setattr(vision_fallback, "create_provider", lambda config: object())

    async def run(provider):  # noqa: ANN001
        raise LLMError("模型响应超时，请稍后重试或调大超时时间")

    with pytest.raises(LLMError):
        await vision_fallback.run_with_vision_fallback(_config(), run, has_images=True)
    assert called == []


async def test_no_vision_model_available_keeps_original_error(monkeypatch):
    async def fake_resolve(config):  # noqa: ANN001
        return None

    monkeypatch.setattr(vision_fallback, "resolve_vision_model", fake_resolve)
    monkeypatch.setattr(vision_fallback, "create_provider", lambda config: object())

    async def run(provider):  # noqa: ANN001
        raise LLMError("模型未抄录图片中的文字，无法核对识别结果，请重试")

    with pytest.raises(LLMError):
        await vision_fallback.run_with_vision_fallback(_config(), run, has_images=True)
