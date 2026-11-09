# SPDX-License-Identifier: Apache-2.0
"""面试教练：候选人答不上来时，基于**他自己的资料**给一份能说出口的参考答案。

## 为什么单独成模块，而不是塞进面试官链路

模拟面试里其实有**两个角色**，目标相反：

- **面试官**（`interview.py`）：只读简历 + JD，如实打分。这是「评估」轨道。
- **教练**（本模块）：读候选人的**全部真实资料**，教他怎么答。这是「学习」轨道。

把它们混在一起会两头不讨好：教练读到的资料会让面试官问出简历里没有的东西
（`interview_system.md` 的信息边界会被破坏），而面试官的打分逻辑又会污染教练
该给的「可迁移回答」。

所以本模块**故意不复用** `build_interview_messages`，走独立上下文。

## 不给参考答案打分

参考答案只进对话与报告，不进评分。否则候选人抄一遍就满分，模拟面试失去意义。
`InterviewAnswerResult` 里不含任何由本模块产生的分数，报告提示词也明确要求
只依据候选人自己的回答评分。

## 数据范围（写死在这里，是产品口径不是实现细节）

简历 + 资料库条目 + 已确认事实台账。**不含 JD 反推**：JD 只用于判断"该答哪个角度"，
不用来生成候选人没做过的事实。理由：吹出来的答案在真实面试第二轮追问里必崩，
比说"不知道"更伤。

资料里答不了时，`grounded=false` + `gaps` 如实说明，并给一个基于真实经历的
可迁移回答——这本身就是有价值的教学。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from ...models.interview import InterviewSession
from ...services.profile.ai_profile import load_ai_consumed_profile
from ...services.profile.paper_projection import project_paper_content
from .interview_context import _claims_json

logger = logging.getLogger(__name__)

#: 参考答案的字数上限由提示词约束（60-200 字），这里只做兜底截断。
MAX_ANSWER_CHARS = 2000
#: 资料库内容进提示词的字符预算：够覆盖主要经历，又不至于让一次教练调用失控。
MAX_PROFILE_CHARS = 6000
#: 事实台账进提示词的字符预算。
MAX_CLAIMS_CHARS = 4000


def _profile_text(db: Session) -> str:
    """资料库的纸面投影（与简历生成链同一份投影，含全部条目）。"""
    try:
        consumed = load_ai_consumed_profile(db)
        projected = project_paper_content(consumed)
        data = projected.model_dump(mode="json") if hasattr(projected, "model_dump") else {}
    except Exception:  # noqa: BLE001 - 资料读取失败不该让整个教练功能挂掉
        logger.warning("面试教练：读取资料库失败，本次只用简历与事实台账", exc_info=True)
        return ""
    text = json.dumps(data, ensure_ascii=False)
    return text[:MAX_PROFILE_CHARS]


def previous_question(session: InterviewSession) -> str:
    """候选人没答上来的那道题：最后一条面试官消息。

    公开导出（API 层要用它把"这条参考答案对应哪道题"写进消息 context）：
    复盘时如果只看答案、不知道它答的是哪个问题，等于没有价值。
    """
    for message in reversed(session.messages or []):
        if message.role == "interviewer":
            return str(message.content or "").strip()
    return ""


def _previous_question(session: InterviewSession) -> str:
    """兼容旧调用名（模块内部用）。"""
    return previous_question(session)


def _previous_answer(session: InterviewSession) -> str:
    """候选人刚才怎么回的（通常是"不知道"），让教练知道该补什么。"""
    for message in reversed(session.messages or []):
        if message.role == "candidate":
            return str(message.content or "").strip()
    return ""


def build_coach_messages(
    db: Session,
    session: InterviewSession,
    *,
    resume_text: str = "",
    job_text: str = "",
) -> list[dict[str, str]]:
    """构造教练调用的消息。

    与面试官消息的区别只有一处：**多喂资料库与事实台账**，并且明确要求
    「只从资料里长出来」。简历与 JD 仍然给，因为答案要贴合岗位角度。
    """
    from ...services.interview.interview import _load_prompt, _render  # 局部导入避免循环

    system = _render(
        _load_prompt("interview_coach_answer.md"),
        {
            "interview_type": session.interview_type,
            "difficulty": session.difficulty,
            "job_title": session.job_title or "未指定",
            "company": session.company,
        },
    )
    payload = {
        "候选人的简历": resume_text or "（没有简历内容）",
        "候选人的资料库（全部条目，未写入简历的也在里面）": _profile_text(db)
        or "（资料库为空）",
        "已确认的事实台账": (_claims_json(db) or "（没有已确认事实）")[:MAX_CLAIMS_CHARS],
        "目标岗位的招聘信息（只用于判断该答哪个角度，不要据此编造经历）": job_text
        or "（未关联岗位）",
        "刚才面试官问的问题": _previous_question(session) or "（取不到题目）",
        "候选人刚才的回答": _previous_answer(session) or "（没有回答）",
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def parse_coach_answer(raw: str) -> dict[str, Any]:
    """解析模型输出。任何字段缺失都退回安全默认值，绝不抛给前端。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        # 模型偶尔会裹 Markdown 代码块，剥掉。
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("面试教练：模型输出不是合法 JSON，按纯文本答案处理")
        return {
            "answer": text[:MAX_ANSWER_CHARS],
            "outline": [],
            "sources": [],
            "gaps": [],
            "grounded": False,
        }
    if not isinstance(data, dict):
        return {
            "answer": str(data)[:MAX_ANSWER_CHARS],
            "outline": [],
            "sources": [],
            "gaps": [],
            "grounded": False,
        }

    def _str_list(value: Any) -> list[str]:
        if not isinstance(value, (list, tuple)):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    return {
        "answer": str(data.get("answer") or "")[:MAX_ANSWER_CHARS],
        "outline": _str_list(data.get("outline"))[:4],
        "sources": _str_list(data.get("sources"))[:8],
        "gaps": _str_list(data.get("gaps"))[:6],
        # 缺省按 false：宁可保守标注"不完全有据"，也不谎称答案全来自资料。
        "grounded": data.get("grounded") is True,
    }


__all__ = [
    "build_coach_messages",
    "parse_coach_answer",
    "previous_question",
    "MAX_ANSWER_CHARS",
    "MAX_PROFILE_CHARS",
    "MAX_CLAIMS_CHARS",
]
