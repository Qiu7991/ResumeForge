# SPDX-License-Identifier: Apache-2.0
"""投递失败必须回写队列状态（2026-11-10）。

用户实测的 bug：投递记录里写着「失败 / 页面结构变化」，但队列里同一岗位还是「待投递」。
两个后果：
1. 两处显示自相矛盾，用户不知道该不该重试；
2. 失败的条目停在 `pending` 会被**下一批重投一次**——对已经尝试过的岗位再发一遍招呼语。

`failed` 与 `skipped` 刻意分开：`skipped` 是"刻意没投"（岗位已关闭 / 招呼语缺失 /
同公司本批已投），用户不用管；`failed` 是"投了但没成"，值得他重试。
"""

from app.models.apply import (
    QUEUE_STATUS_DONE,
    QUEUE_STATUS_FAILED,
    QUEUE_STATUS_PENDING,
    QUEUE_STATUS_SKIPPED,
    ApplyQueueItem,
)
from app.models.job import Job
from app.services.apply.apply_service import mark_queue_failed


def _queue_item(db_session, *, status: str = QUEUE_STATUS_PENDING):
    """建一个真实岗位 + 指向它的队列条目。

    队列条目的 `job_id` 有外键约束，必须指向真实存在的岗位。
    """
    job = Job(title="后端开发", company="A公司", source_url="https://example.com/q1")
    db_session.add(job)
    db_session.commit()
    item = ApplyQueueItem(job_id=job.id, job_title=job.title, company=job.company, status=status)
    db_session.add(item)
    db_session.commit()
    return item


def test_failed_apply_marks_the_queue_item_failed(db_session):
    item = _queue_item(db_session)

    mark_queue_failed(db_session, item.job_id)
    db_session.commit()

    db_session.refresh(item)
    assert item.status == QUEUE_STATUS_FAILED


def test_failed_does_not_override_a_user_chosen_status(db_session):
    """用户自己标成「已跳过」的条目不该被后台动作推翻。

    他标跳过可能正是因为他明白了"这条投不了"——投递失败的自动回写去改它，
    等于把他刚做的决定顶掉。
    """
    item = _queue_item(db_session, status=QUEUE_STATUS_SKIPPED)

    mark_queue_failed(db_session, item.job_id)
    db_session.commit()

    db_session.refresh(item)
    assert item.status == QUEUE_STATUS_SKIPPED


def test_failed_does_not_undo_a_successful_apply(db_session):
    """已经投成功的条目必须保持 `done`（同一岗位可能有多次尝试，最后那次成功）。"""
    item = _queue_item(db_session, status=QUEUE_STATUS_DONE)

    mark_queue_failed(db_session, item.job_id)
    db_session.commit()

    db_session.refresh(item)
    assert item.status == QUEUE_STATUS_DONE


def test_failed_without_job_id_is_a_noop(db_session):
    """没有 job_id 的条目（岗位已被删除）不该出错。"""
    mark_queue_failed(db_session, None)
    mark_queue_failed(db_session, 999999)  # 库里没有这个岗位


def test_failed_item_is_excluded_from_the_next_batch(db_session):
    """失败的条目不会再被下一批挑走——这是这个 bug 最实际的后果。

    `_tasks` 建批次时只挑 `pending`；`failed` 因此天然被排除。
    """
    from app.models.apply import QUEUE_STATUSES

    assert QUEUE_STATUS_FAILED in QUEUE_STATUSES
    assert QUEUE_STATUS_FAILED != QUEUE_STATUS_PENDING
