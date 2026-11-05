# SPDX-License-Identifier: Apache-2.0
"""招呼语/匹配的简历文本必须是**紧凑格式**，不能是 JSON。

回归的是一次真实事故：招呼语生成时把 ``json.dumps(content)`` 当作简历文本喂给模型，
而 v2 文档带 id / layout / placement，一份正常简历序列化后有 3 万字符，调用方的
个人文本预算只有 8000（``job_match._MAX_PERSONAL_CHARS``）——于是只有第一个项目
落在预算内，模型每次招呼语都拿它举例，用户看到的却是"明明有更合适的项目"。

这里钉住三件事：紧凑、完整、且不同板块都没被丢。
"""

from __future__ import annotations

import json

from app.models.resume import ResumeRecord
from app.services.job.job_match import _MAX_PERSONAL_CHARS
from app.services.job.job_match_context import resume_prompt_text
from app.services.resume.document_io import ensure_document_version

#: 七个项目，名字互不包含，便于断言"全部都在"。
PROJECT_NAMES = [
    "内容账号运营",
    "拼豆网站",
    "创作者内容分析系统",
    "桌面机器人复刻",
    "传感节点固件",
    "康养异常检测",
    "家庭网络自托管",
]


def _rich_content() -> dict:
    """一份内容量接近真实简历的 v2 文档（7 个项目 + 教育 + 经历 + 技能 + 总结）。"""
    v1 = {
        "name": "赵示例",
        "job_intent": "AI 产品经理",
        "summary": "计算机专业本科在读，独立完成多个从需求到上线的 AI 产品。",
        "education": [
            {"school": "示例信息工程学院", "major": "计算机科学与技术", "degree": "本科"}
        ],
        "experience": [{"company": "示例科技有限公司", "role": "工程技术人员（实习）"}],
        "projects": [
            {"name": name, "description": [f"{name}的第一条要点写在这里。", f"{name}的第二条要点。"]}
            for name in PROJECT_NAMES
        ],
        "skills": [{"name": name} for name in ("Python", "TypeScript", "Docker", "Git")],
    }
    return ensure_document_version(v1, language="zh-CN", format_config={})


def _record(content: dict) -> ResumeRecord:
    return ResumeRecord(
        title="赵示例-AI 产品经理",
        job_title="AI 产品经理",
        content=content,
        language="zh-CN",
        format_config={},
    )


def test_resume_prompt_text_is_compact_and_keeps_every_section():
    content = _rich_content()
    text = resume_prompt_text(None, _record(content))

    # 1) 紧凑：必须远小于 JSON 序列化（后者是 v2 富结构，动辄数万字符）。
    json_size = len(json.dumps(content, ensure_ascii=False))
    assert len(text) < json_size / 3, f"markdown 应远小于 JSON（{len(text)} vs {json_size}）"

    # 2) 完整：整份文本必须能放进个人文本预算，且**每个项目都还在**。
    assert len(text) <= _MAX_PERSONAL_CHARS, f"超出预算（{len(text)}）"
    for name in PROJECT_NAMES:
        assert name in text, f"项目 {name!r} 被截掉了"

    # 3) 其他板块也没丢。
    assert "示例信息工程学院" in text
    assert "示例科技有限公司" in text
    assert "计算机专业本科在读" in text


def test_resume_prompt_text_survives_render_failure():
    """渲染失败要有兜底，不能让招呼语整条链路因为一份坏文档而报错。"""

    class Broken:
        content = {"version": 999, "whatever": True}
        title = "坏记录"
        job_title = ""
        language = "zh-CN"
        format_config = {}

    text = resume_prompt_text(None, Broken())
    assert "坏记录" in text  # 标题仍在（兜底走 json.dumps）
