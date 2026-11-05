# SPDX-License-Identifier: Apache-2.0
"""默认简历：岗位没有专属简历时自动用它，不用逐条手选。

优先级固定为「显式指定 → 该岗位最近的岗位版 → 设置里的默认简历 → 没有」。
队列条目**不把默认简历固化进库**：用户换默认后，已入队的条目要跟着变。
"""

from __future__ import annotations

from app.models.job import Job
from app.models.resume import ResumeRecord
from app.schemas.apply import ApplyConfigIn, ApplyQueueAddRequest
from app.services.apply import apply_service


def _job(db_session, title: str = "AI落地工程师") -> Job:
    job = Job(title=title, company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.flush()
    return job


def test_resolution_order_prefers_job_resume_then_default(db_session):
    job = _job(db_session)
    general = ResumeRecord(title="通用版", job_id=None, content={})
    explicit = ResumeRecord(title="手动指定版", job_id=None, content={})
    db_session.add_all([general, explicit])
    db_session.commit()
    apply_service.save_apply_config(
        db_session, ApplyConfigIn(default_resume_id=general.id)
    )

    # 没有岗位版简历 → 默认简历
    assert apply_service.resolve_resume(db_session, job.id, None).id == general.id
    # 显式指定永远优先
    assert apply_service.resolve_resume(db_session, job.id, explicit.id).id == explicit.id

    # 有岗位版简历 → 岗位版压过默认
    specific = ResumeRecord(title="岗位版", job_id=job.id, content={})
    db_session.add(specific)
    db_session.commit()
    assert apply_service.resolve_resume(db_session, job.id, None).id == specific.id


def test_queue_does_not_freeze_the_default_resume(db_session):
    """入队只固化岗位版；默认简历是运行时解析，换了默认老条目也跟着换。"""
    job = _job(db_session, "AI应用运营")
    general = ResumeRecord(title="通用版", job_id=None, content={})
    db_session.add(general)
    db_session.commit()
    apply_service.save_apply_config(
        db_session, ApplyConfigIn(default_resume_id=general.id)
    )

    created = apply_service.add_to_queue(
        db_session, ApplyQueueAddRequest(items=[{"job_id": job.id, "confirm_unanalyzed": True}])
    )
    # 库里不写默认简历的 id
    from app.models.apply import ApplyQueueItem

    stored = db_session.get(ApplyQueueItem, created[0].id)
    assert stored.resume_id is None
    # 出口按运行时规则给出"实际会投的那份"，编辑器据此预选
    listed = apply_service.list_queue(db_session)[0]
    assert listed.resume_id == general.id
    assert listed.resume_title == "通用版"

    # 用户换默认 → 已入队条目的解析结果跟着变
    another = ResumeRecord(title="新的通用版", job_id=None, content={})
    db_session.add(another)
    db_session.commit()
    apply_service.save_apply_config(
        db_session, ApplyConfigIn(default_resume_id=another.id)
    )
    listed_again = apply_service.list_queue(db_session)[0]
    assert listed_again.resume_id == another.id
    assert listed_again.resume_title == "新的通用版"
