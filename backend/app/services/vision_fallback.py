"""带图识别失败时，自动换一个「能看图」的模型重试。

**要解决的问题**：兼容 OpenAI 的服务商常把纯文本模型接在同一个 ``/chat/completions`` 上。
图片附件发过去既不报错也不生效——只是被静默忽略，于是抄录为空、应用判定识别失败，
最后退回本地规则（本地规则读不了图片），用户看到的是"表单全空 + 识别失败"。

**策略**：只在**带图片**且**失败原因指向视觉能力**时兜底一次，从**同一服务商**的
``/models`` 列表里挑一个已知的看图模型重试，并把"换了哪个模型"写进结果提示。
跨服务商乱猜模型名只会换来 404，所以候选名必须真的出现在对方的模型列表里。

**为什么不一失败就重试**：纯文本识别失败该照旧走本地规则（省钱，也不掩盖真实错误）；
网络超时之类的失败也不该换模型重试——那是同一个问题再来一遍。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from ..schemas.setting import LLMConfig
from .llm import LLMError, create_provider
from .llm.model_catalog import list_available_models

logger = logging.getLogger(__name__)

T = TypeVar("T")

# 顺序即优先级：先试同门里较稳的模型，再退到常见通用多模态名字。
# 只有出现在服务商 /models 列表里的条目才会被选中——这里列多了无害。
VISION_MODEL_PREFERENCE: tuple[str, ...] = (
    "mimo-v2.6-pro",
    "mimo-v2.6-flash",
    "seed-2.1-pro",
    "seed-2.1-turbo",
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4.1",
    "qwen-vl-max",
    "qwen2.5-vl-72b-instruct",
    "glm-4.5v",
    "claude-3-5-sonnet",
    "gemini-2.0-flash",
)

# 判定"这次失败值得换看图模型"的线索：
# - 自家校验抛的「模型未抄录图片中的文字」= 模型没看到图，最典型；
# - 服务商明说 vision/图片不支持；
# - 一些服务商把图当成非法参数，报错里带 image。
_VISION_ERROR_HINTS = ("未抄录图片中的文字", "vision", "image", "图片")


def looks_like_vision_failure(message: str) -> bool:
    text = (message or "").lower()
    return any(hint.lower() in text for hint in _VISION_ERROR_HINTS)


def pick_vision_model(models: Sequence[str], current: str) -> str | None:
    """从服务商给出的模型列表里挑一个看图模型；没有就返回 None。"""
    available = {str(model).strip() for model in models if str(model).strip()}
    for name in VISION_MODEL_PREFERENCE:
        if name in available and name != current:
            return name
    return None


async def resolve_vision_model(config: LLMConfig) -> str | None:
    try:
        models = await list_available_models(config.base_url, config.api_key)
    except Exception:  # noqa: BLE001 - 拿不到列表就安静放弃，让原错误继续往上抛
        logger.info("读取模型列表失败，跳过看图模型兜底", exc_info=True)
        return None
    return pick_vision_model(models, config.model)


def attach_warning(result: Any, text: str) -> Any:
    """把一条提示追加到结果的 warnings（去重保序）；不支持的结果原样返回。"""
    if not text or not hasattr(result, "model_copy"):
        return result
    warnings = list(dict.fromkeys([*getattr(result, "warnings", []), text]))
    return result.model_copy(update={"warnings": warnings})


async def run_with_vision_fallback(
    config: LLMConfig,
    run: Callable[[Any], Awaitable[T]],
    *,
    has_images: bool,
    make_provider: Callable[[LLMConfig], Any] | None = None,
) -> tuple[T, str]:
    """先按配置的模型跑；带图且像是"看不见图"的失败，就换看图模型再跑一次。

    ``make_provider`` 由调用方传入自己的 ``create_provider``：各 API 模块都有测试在
    自己的命名空间里打桩它，助手若直接引用服务层函数，那些桩就形同虚设。
    返回 ``(结果, 提示)``。提示为空表示没有换模型；非空时调用方应把它并进 warnings，
    让用户知道这次是谁识别的（不同模型结果可能有差异，不写出来等于藏信息）。
    """
    factory = make_provider or create_provider
    try:
        return await run(factory(config)), ""
    except LLMError as exc:
        if not has_images or not looks_like_vision_failure(str(exc)):
            raise
        vision_model = await resolve_vision_model(config)
        if not vision_model:
            raise
        logger.info("图片识别失败（%s），自动改用看图模型 %s 重试", exc, vision_model)
        result = await run(factory(config.model_copy(update={"model": vision_model})))
        return result, f"当前模型（{config.model}）读不了图片，已自动改用 {vision_model} 识别。"


__all__ = [
    "VISION_MODEL_PREFERENCE",
    "attach_warning",
    "looks_like_vision_failure",
    "pick_vision_model",
    "resolve_vision_model",
    "run_with_vision_fallback",
]
