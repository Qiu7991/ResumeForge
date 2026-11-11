# SPDX-License-Identifier: Apache-2.0
"""备选岗位（candidate_job）的评分输入拼装。

为什么要单独一层：备选岗位的 JD 散在四列里，而正式岗位只有一个 ``Job.description``。
评分提示词只认一段「JD 正文」，所以必须有一处**唯一**的拼装规则——采集候选有
``description``/``requirements``/``additional_info`` 三段（服务端已按小标题切好），
手动粘贴的候选只有 ``raw_text``。两处各拼一次，模型看到的输入就会分叉。

判「有没有 JD」与拼 JD 必须同源：如果 ``has_jd`` 说"有"而拼出来是空串，评分会拿
空正文去问模型，得到一个看起来正常但没有依据的分数——比直接报「缺 JD」更糟。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from ...models.material import CandidateJob

logger = logging.getLogger(__name__)

# 拼接顺序即重要性：职责 → 要求 → 其他信息。``raw_text`` 放最后当兜底，
# 只在前面三段全空时用（手动粘贴的候选走这条）。
_SECTION_ATTRS = ("description", "requirements", "additional_info", "raw_text")


def _section(candidate: Any, name: str) -> str:
    value = getattr(candidate, name, "") or ""
    return str(value).strip()


def candidate_jd(candidate: Any) -> str:
    """把备选岗位的 JD 四列拼成评分用的正文（空段跳过，段间空一行）。"""
    parts = [text for text in (_section(candidate, name) for name in _SECTION_ATTRS) if text]
    return "\n\n".join(parts)


def candidate_has_jd(candidate: Any) -> bool:
    """是否有可评分的正文。

    与 :func:`candidate_jd` 同源：直接判拼接结果非空，避免"判定说有、拼出来是空"。
    """
    return bool(candidate_jd(candidate))


def migrate_candidate_score(db: Session, candidate: CandidateJob, job_id: int) -> None:
    """把候选阶段评出来的分数搬到新岗位的语义评分里。

    不迁移的后果：用户按分数挑完导入，回到岗位广场看到的却是「未评分」，等于白评——
    而重评要再花一次 LLM 调用。

    **失败不阻断导入**：分数是辅助信息，一条评分写不进去不该让"岗位没建成"。
    写不进去只记日志，导入照常完成。

    用 service 层的 ``persist_semantic_for_job``（与单岗评分端点同一份实现），
    而不是自己拼 SQL：那样「不覆盖五类结论」这条语义会有两份容易分叉的代码。
    """
    payload = candidate.score_payload
    if not payload or candidate.score_total is None:
        return
    try:
        from .scoring_service import persist_semantic_for_job

        persist_semantic_for_job(db, job_id, payload, model=candidate.score_model or "")
    except Exception as exc:  # noqa: BLE001 — 分数是增强项，不该连累导入
        logger.warning(
            "候选 %s 的评分迁移到岗位 %s 失败（导入照常完成）：%s: %s",
            candidate.id,
            job_id,
            type(exc).__name__,
            exc,
        )


__all__ = ["candidate_has_jd", "candidate_jd", "migrate_candidate_score"]
