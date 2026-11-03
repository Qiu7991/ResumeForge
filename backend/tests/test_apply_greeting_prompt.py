# SPDX-License-Identifier: Apache-2.0
"""招呼语提示词：必须看到 JD 正文与完整简历（照片 base64 不能挤掉真实内容）。"""

import json

from app.services.job.job_match import build_greeting_messages, parse_greeting


def _resume_with_photo() -> str:
    return json.dumps(
        {
            "title": "赵岚柯-AI应用赋能专员",
            "content": {
                "name": "赵岚柯",
                "photo": "data:image/jpeg;base64," + "A" * 5000,
                "summary": "计算机本科在读，关注 AI 工具实际应用。",
                "education": [
                    {"school": "哈尔滨信息工程学院", "major": "计算机科学与技术", "degree": "本科"}
                ],
                "projects": [{"name": "AI 简历工作台", "role": "个人独立项目"}],
                "skills": [{"name": "RAG 与 Function Calling"}],
            },
        },
        ensure_ascii=False,
    )


def test_greeting_payload_includes_full_jd_and_real_resume_text():
    job = {
        "title": "AI应用赋能专员",
        "company": "萤火虫动漫游戏嘉年华",
        "location": "广州",
        "job_type": "社招",
        "description": "JD-DESCRIPTION-SENTINEL：分部门 AI 工作流搭建与提示词沉淀。",
        "requirements": "REQ-SENTINEL：熟悉主流 AI 工具。",
        "additional_info": "ADD-SENTINEL：二次元 IP 版权风控。",
    }

    messages = build_greeting_messages(job, _resume_with_photo())
    user_message = messages[-1]["content"]

    # description 才是 JD 正文：只给 requirements 会让模型只看到岗位名。
    assert "JD-DESCRIPTION-SENTINEL" in user_message
    assert "REQ-SENTINEL" in user_message
    assert "ADD-SENTINEL" in user_message
    # 照片 base64 必须被剥离，否则 8000 字预算全被它吃掉。
    assert "data:image/jpeg;base64" not in user_message
    assert "图片数据已省略" in user_message
    assert "AI 简历工作台" in user_message
    assert "RAG 与 Function Calling" in user_message


def test_greeting_prompt_requires_polite_opening_and_length_rules():
    messages = build_greeting_messages({"title": "AI应用赋能专员"}, "{}")
    system = messages[0]["content"]

    assert "必须以「您好」开头" in system
    assert "当前情况" in system
    assert "岗位匹配" in system
    assert "简历已附" in system  # 作为禁止项出现
    assert "150–260 字" in system
    assert "不得编造" in system


def test_parse_greeting_adds_polite_opening_when_model_omits_it():
    assert parse_greeting("计算机本科在读，做过提示词工程。").startswith("您好，")
    assert parse_greeting("你好，计算机本科在读。").startswith("您好，")
    assert parse_greeting("尊敬的HR您好，计算机本科在读。").startswith("您好，")


def test_parse_greeting_keeps_an_existing_polite_opening():
    assert parse_greeting("您好，计算机本科在读。") == "您好，计算机本科在读。"
