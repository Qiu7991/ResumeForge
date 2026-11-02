"""招呼语闸门：没有确认过的招呼语，绝不替用户发出去。

用户的要求是"每个岗位打招呼前都给我看一下，我说没问题再发"，不是快速群发。
所以队列条目里的 greeting 就是"已确认"的唯一凭据：空着就跳过，并把原因分类成
greeting_missing（软跳过，不计失败、不触发熔断）。
"""

from __future__ import annotations

from app.models.apply import ApplyTaskItem
from app.schemas.apply.config import DEFAULT_GREETING
from app.services.sites.base import ApplyOutcome
from test_apply_task_runner import (
    FakeAdapter,
    _item_statuses,
    _runner,
    _setup_task,
    _task_status,
    _wait,
    _wait_db,
)


class RecordingAdapter(FakeAdapter):
    """记下实际发出去的招呼语文本。"""

    def __init__(self) -> None:
        super().__init__()
        self.greetings: list[str] = []

    def fill_and_submit(self, client, data, greeting) -> ApplyOutcome:
        self.greetings.append(greeting)
        return super().fill_and_submit(client, data, greeting)


def _items(db_session, task_id: int) -> list[ApplyTaskItem]:
    return (
        db_session.query(ApplyTaskItem)
        .filter_by(task_id=task_id)
        .order_by(ApplyTaskItem.id)
        .all()
    )


def test_items_without_a_confirmed_greeting_are_skipped(db_session):
    task = _setup_task(db_session, 2, require_greeting_review=True)
    adapter = RecordingAdapter()
    runner = _runner(adapter)

    runner.start(task.id)
    _wait(runner)
    _wait_db(db_session, lambda: _task_status(db_session, task.id), "completed", "任务状态")

    db_session.expire_all()
    assert _item_statuses(db_session, task.id) == ["skipped", "skipped"]
    for item in _items(db_session, task.id):
        assert item.failure_category == "greeting_missing"
        # 跳过原因落在 failure_detail：界面直接展示这句话，用户知道该去补什么
        assert "招呼语未确认" in (item.failure_detail or "")
    # 一条都没发出去
    assert adapter.calls == 0
    assert adapter.greetings == []


def test_a_confirmed_greeting_is_sent_verbatim(db_session):
    task = _setup_task(db_session, 2, require_greeting_review=True)
    first = _items(db_session, task.id)[0]
    confirmed = "计算机本科，做过 LLM 结构化抽取，想聊下这个岗位的落地场景"
    first.greeting = confirmed
    first.greeting_confirmed = True
    db_session.commit()

    adapter = RecordingAdapter()
    runner = _runner(adapter)

    runner.start(task.id)
    _wait(runner)
    _wait_db(db_session, lambda: _task_status(db_session, task.id), "completed", "任务状态")

    db_session.expire_all()
    # 确认过的那条发出去了（原文发出，不被改写），没确认的那条仍然跳过
    assert _item_statuses(db_session, task.id) == ["success", "skipped"]
    assert adapter.greetings == [confirmed]


def test_a_generated_but_unconfirmed_greeting_is_still_skipped(db_session):
    """有字不等于确认过：批量生成的草稿没经用户保存，绝不能发出去。"""
    task = _setup_task(db_session, 1, require_greeting_review=True)
    item = _items(db_session, task.id)[0]
    item.greeting = "AI 生成的一段话，用户还没看过"
    item.greeting_confirmed = False
    db_session.commit()

    adapter = RecordingAdapter()
    runner = _runner(adapter)

    runner.start(task.id)
    _wait(runner)
    _wait_db(db_session, lambda: _task_status(db_session, task.id), "completed", "任务状态")

    db_session.expire_all()
    assert _item_statuses(db_session, task.id) == ["skipped"]
    assert _items(db_session, task.id)[0].failure_category == "greeting_missing"
    assert "待确认" in (_items(db_session, task.id)[0].failure_detail or "")
    assert adapter.greetings == []


def test_review_off_falls_back_to_the_default_greeting(db_session):
    task = _setup_task(db_session, 1, require_greeting_review=False)
    adapter = RecordingAdapter()
    runner = _runner(adapter)

    runner.start(task.id)
    _wait(runner)
    _wait_db(db_session, lambda: _task_status(db_session, task.id), "completed", "任务状态")

    db_session.expire_all()
    assert _item_statuses(db_session, task.id) == ["success"]
    assert adapter.greetings == [DEFAULT_GREETING]
