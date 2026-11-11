# SPDX-License-Identifier: Apache-2.0
"""备选岗位的「助手可读文本」拼装。

从 ``services/candidate_jobs.py`` 拆出来的（2026-11-12）：那个文件已经顶到 500 行
预算，而这段是**纯展示层**——把一条候选折成给助手/文本导出看的段落，不碰数据库、
不做业务判断，和增删改查不是一类东西。

之所以留在 service 层而不是放 API：助手工具（``assistant_tools``）也直接调它，
不经过 HTTP。
"""

from __future__ import annotations

from ..models.material import CANDIDATE_JOB_IMPORTED, CandidateJob

MAX_CANDIDATE_TOOL_CHARS = 6_000


def candidate_detail_text(
    candidate: CandidateJob, max_chars: int = MAX_CANDIDATE_TOOL_CHARS
) -> str:
    """备选岗位的详情文本（供助手读取）：采集来的 JD 两段与粘贴来的原文都要带上。"""
    parts = [
        f"岗位：{candidate.title or '（未填写）'}",
        f"公司：{candidate.company or '（未填写）'}",
        f"状态：{'已导入' if candidate.status == CANDIDATE_JOB_IMPORTED else '待处理'}",
    ]
    if candidate.location:
        parts.append(f"城市：{candidate.location}")
    if candidate.salary:
        parts.append(f"薪资：{candidate.salary}")
    if candidate.note:
        parts.append(f"备注：{candidate.note}")
    # 采集回来的候选把 JD 存在 description / requirements 两段里，粘贴来的候选存在 raw_text。
    # 两者都要读——只读 raw_text 会让助手对采集来的岗位"什么都看不到"。
    if candidate.description:
        parts.append(f"岗位描述：\n{candidate.description}")
    if candidate.requirements:
        parts.append(f"任职要求：\n{candidate.requirements}")
    if candidate.raw_text:
        parts.append(f"招聘原文：\n{candidate.raw_text}")
    if candidate.images:
        parts.append(f"附有 {len(candidate.images)} 张招聘截图（图片内容未提取）")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        text = f"{text[:max_chars].rstrip()}…"
    return text


__all__ = ["MAX_CANDIDATE_TOOL_CHARS", "candidate_detail_text"]
