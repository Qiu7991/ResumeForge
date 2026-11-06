# SPDX-License-Identifier: Apache-2.0
"""回复监测测试：意向分类 + 汇总（全假数据，红线：只读不发送）。"""
from __future__ import annotations

import pytest

from app.services.job_hunt.replies import (
    ChatMessage,
    Conversation,
    Intent,
    classify_conversation,
    classify_intent,
    monitor_reply,
)


def test_classify_interview():
    for text in ("方便的话约个面试吧", "明天有空聊聊吗", "我们约个时间视频聊",
                 "来公司当面聊聊？", "什么时候方便，电话聊一下"):
        assert classify_intent(text) is Intent.INTERVIEW, text


def test_classify_want_resume():
    for text in ("方便发一份简历吗", "把作品集发我看看", "简历发我一份",
                 "先发一下简历哈"):
        assert classify_intent(text) is Intent.WANT_RESUME, text


def test_classify_rejection_beats_resume():
    # "简历" + "不合适" 同时命中：拒绝必须优先于要简历
    assert classify_intent("看了简历，感觉不太合适") is Intent.REJECTION
    assert classify_intent("不好意思，岗位已经招到了") is Intent.REJECTION
    assert classify_intent("暂时不考虑，简历放人才库了") is Intent.REJECTION


def test_classify_neutral_and_empty():
    assert classify_intent("您好，看了您的经验很有兴趣，聊一下薪资期望？") is Intent.NEUTRAL
    assert classify_intent("") is Intent.NEUTRAL
    assert classify_intent("👍") is Intent.NEUTRAL


def test_conversation_last_from_peer():
    conv = Conversation(peer="张HR", messages=[
        ChatMessage(text="你好，看到你投递了", from_me=False),
        ChatMessage(text="您好！很高兴认识", from_me=True),
        ChatMessage(text="方便发一份简历吗", from_me=False),
    ])
    assert conv.last_from_peer() is not None
    assert conv.last_from_peer().text == "方便发一份简历吗"
    # 只算对方最后一条：我方消息不参与
    assert classify_conversation(conv) is Intent.WANT_RESUME


def test_conversation_no_peer_message_is_neutral():
    conv = Conversation(peer="李HR", messages=[ChatMessage(text="您好！", from_me=True)])
    assert conv.last_from_peer() is None
    assert classify_conversation(conv) is Intent.NEUTRAL
    assert classify_conversation(Conversation(peer="空会话")) is Intent.NEUTRAL


def test_monitor_reply_summary_counts():
    conversations = [
        Conversation(peer="A", messages=[ChatMessage(text="约个面试吧")]),
        Conversation(peer="B", messages=[ChatMessage(text="发一份简历")]),
        Conversation(peer="C", messages=[ChatMessage(text="不太合适")]),
        Conversation(peer="D", messages=[ChatMessage(text="薪资范围多少")]),
        Conversation(peer="E", messages=[]),
    ]
    summary = monitor_reply(conversations)
    assert summary.counts == {"interview": 1, "want_resume": 1, "rejection": 1, "neutral": 2}
    interviews = summary.of(Intent.INTERVIEW)
    assert len(interviews) == 1 and interviews[0][0].peer == "A"


def test_no_send_anything():
    """红线自检：replies 模块不得出现任何发送行为的实现（词边界匹配，防误伤函数名）。"""
    import inspect
    import re

    import app.services.job_hunt.replies as replies

    banned = re.compile(
        r"\bsend\w*\s*\(|\bsend_message|\bpost_message|\brequests\.(get|post)"
        r"|\bhttpx\.|\bemit\b|\bsendmsg"
    )
    for name, fn in vars(replies).items():
        if callable(fn) and not name.startswith("_") and inspect.isfunction(fn):
            source = inspect.getsource(fn)
            assert not banned.search(source), f"{name} 里出现了疑似发送行为"
