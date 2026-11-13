# SPDX-License-Identifier: Apache-2.0
"""回复监测（只读，不发送）：把 HR 回复分类成意向，汇总成简报。

**红线：本模块只做"看"，不做"说"**——没有任何发送消息的代码路径，夜间测试全用
假数据，不登录、不连真实网站。

意向分类是**确定性关键词规则**（不调 LLM：夜里要能跑、结果要可复现、错了能查），
按「拒绝 > 约面 > 要简历 > 普通」的优先级判定——"简历不合适"必须落在拒绝而不是
要简历，所以拒绝最优先。规则是**白名单起步**：宁可分到"普通"让人工看，不要为了
覆盖率瞎猜。

BOSS 聊天页的**抓取**侧（DOM → ``Conversation``）需要聊天页夹具才能实现并验证
（夜间未采集）——见 docs/job-hunt-blocked.md BLOCKED-REPLIES-FIXTURE；本模块先把
"拿到会话之后"的部分做扎实。
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    """一次 HR 回复的意向分类。"""

    INTERVIEW = "interview"  # 约面
    WANT_RESUME = "want_resume"  # 要简历/作品集
    REJECTION = "rejection"  # 拒绝
    NEUTRAL = "neutral"  # 普通（寒暄/追问/无法判定）

    @property
    def label(self) -> str:
        return _LABELS[self]


_LABELS = {
    Intent.INTERVIEW: "约面",
    Intent.WANT_RESUME: "要简历",
    Intent.REJECTION: "拒绝",
    Intent.NEUTRAL: "普通",
}

# 优先级即列表顺序：拒绝 > 约面 > 要简历。
_INTENT_RULES: tuple[tuple[Intent, tuple[str, ...]], ...] = (
    (
        Intent.REJECTION,
        (
            "不合适", "不太合适", "不太匹配", "不匹配", "暂不考虑", "不考虑", "已招到",
            "已经招到", "招满了", "招满", "人员已满", "人才库", "下次机会", "暂缓",
            "我们先看看",
        ),
    ),
    (
        Intent.INTERVIEW,
        (
            "面试", "约个时间", "约个方便", "方便聊聊", "方便沟通", "电话聊", "视频聊",
            "到公司", "来公司", "来现场", "什么时候方便", "有空聊聊", "有空吗",
        ),
    ),
    (
        Intent.WANT_RESUME,
        (
            "简历", "作品集", "发一份", "发我一份", "发一下", "发过来", "发我看看",
        ),
    ),
)


def classify_intent(text: str) -> Intent:
    """按关键词规则给一段 HR 文本判意向（确定性，可复现）。"""
    if not text:
        return Intent.NEUTRAL
    for intent, keywords in _INTENT_RULES:
        if any(kw in text for kw in keywords):
            return intent
    return Intent.NEUTRAL


@dataclass
class ChatMessage:
    """一条聊天消息。``from_me``= 求职者本人发的（分类只看对方的消息）。"""

    text: str
    from_me: bool = False
    at: str = ""  # 时间原文（"14:32" / "昨天"），只展示不参与分类


@dataclass
class Conversation:
    """一个会话（一位 HR / 一个岗位）。"""

    peer: str  # 对方标识（HR 名或公司名，展示用）
    job_title: str = ""  # 关联岗位（可空）
    messages: list[ChatMessage] = field(default_factory=list)

    def last_from_peer(self) -> ChatMessage | None:
        """对方**最后一条**消息（时间序）。"""
        for message in reversed(self.messages):
            if not message.from_me:
                return message
        return None


def classify_conversation(conversation: Conversation) -> Intent:
    """会话的当前意向 = 对方最后一条消息的意向；对方没说过话 → 普通。"""
    last = conversation.last_from_peer()
    if last is None:
        return Intent.NEUTRAL
    return classify_intent(last.text)


@dataclass
class ReplySummary:
    """一次回复监测的汇总。``intent`` 记的是**对方最后一条消息**的意向。"""

    conversations: list[tuple[Conversation, Intent]] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        out = {intent.value: 0 for intent in Intent}
        for _, intent in self.conversations:
            out[intent.value] += 1
        return out

    def of(self, intent: Intent) -> list[tuple[Conversation, Intent]]:
        return [(c, i) for c, i in self.conversations if i is intent]


def monitor_reply(conversations: Iterable[Conversation]) -> ReplySummary:
    """把一批会话分类汇总。纯函数：给同样的会话，永远给同样的结论。"""
    return ReplySummary(
        conversations=[(conv, classify_conversation(conv)) for conv in conversations]
    )


__all__ = [
    "Intent",
    "ChatMessage",
    "Conversation",
    "ReplySummary",
    "classify_intent",
    "classify_conversation",
    "monitor_reply",
]
