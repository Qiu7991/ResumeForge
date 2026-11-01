"""以已有简历为底稿生成岗位版：复制底稿正文，再按岗位 JD 修订。

第一性上，一份简历 = 事实（学历/经历/项目/数字）+ 表达（措辞/取舍/排序）。事实的权威来源
是用户已经确认过的简历；"从资料重新生成"会把润色过的表达冲掉。所以底稿模式不重新抽取事实，
而是走既有的修订管线：底稿不动，只按 JD 调整取舍与表达。

这段逻辑从生成运行器里拆出来，一是让运行器只保留编排，二是底稿模式可以脱离线程单独测。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from ...models.resume import ResumeRecord
from ...runtime.operation_budget import OperationBudget
from ...schemas.job import JobOut
from ...schemas.resume import ResumeContent
from .resume_revision import revise_resume

logger = logging.getLogger(__name__)

# 底稿模式没有填写额外要求时的默认口径：只做取舍与表达调整，不重新"生成"事实。
BASE_RESUME_INSTRUCTION = (
    "这是一份已经定稿的简历。请在严格保留其事实、时间、公司/学校/项目名称与既有数字的前提下，"
    "按目标岗位的 JD 做取舍与表达调整：把与 JD 最相关的经历与能力放在更显眼的位置，"
    "弱化与岗位无关的细节，必要时重排项目顺序；不要新增底稿里没有的事实、成果或数字。"
)


class BaseResumeMissing(Exception):
    """底稿不存在或已删除：任务应立刻失败，而不是白跑一次模型。"""


def load_base_resume(session: Session, resume_id: int, *, is_deleted: Callable[[Any], bool]):
    record = session.get(ResumeRecord, resume_id)
    if record is None or is_deleted(record):
        raise BaseResumeMissing("所选底稿简历不存在或已被删除，请重新选择")
    return record


async def derive_from_base(
    provider: Any,
    base_record: ResumeRecord,
    job: JobOut | None,
    custom_instruction: str,
    *,
    budget: OperationBudget,
    on_progress: Callable[[str], None] | None = None,
) -> tuple[dict, list[str]]:
    """返回 ``(正文, 提示)``；提示会随记录落库，告知用户"这份是从哪份改出来的"。"""
    if on_progress is not None:
        on_progress(f"正在以《{base_record.title}》为底稿，按岗位要求修订…")
    provider.request_budget = budget
    revised = await revise_resume(
        provider,
        ResumeContent.model_validate(base_record.content),
        job,
        custom_instruction.strip() or BASE_RESUME_INSTRUCTION,
    )
    budget.raise_if_stopped()
    return revised.model_dump(), [
        f"本简历以《{base_record.title}》为底稿，按岗位要求修订；底稿本身未被修改。"
    ]


__all__ = [
    "BASE_RESUME_INSTRUCTION",
    "BaseResumeMissing",
    "derive_from_base",
    "load_base_resume",
]
