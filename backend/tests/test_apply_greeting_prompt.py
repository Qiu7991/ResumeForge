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

    assert "必须以「您好，」开头" in system
    assert "正好五句话" in system
    assert "一段话" in system
    assert "简历已附" in system  # 作为禁止项出现
    assert "140–220 字" in system
    assert "只写 1 个项目" in system
    assert "不得照抄示例" in system
    assert "不要编造" in system


def test_parse_greeting_adds_polite_opening_when_model_omits_it():
    assert parse_greeting("计算机本科在读，做过提示词工程。").startswith("您好，")
    assert parse_greeting("你好，计算机本科在读。").startswith("您好，")
    assert parse_greeting("尊敬的HR您好，计算机本科在读。").startswith("您好，")


def test_parse_greeting_keeps_an_existing_polite_opening():
    assert parse_greeting("您好，计算机本科在读。") == "您好，计算机本科在读。"


def test_custom_greeting_baseline_is_injected_as_style_guidance():
    messages = build_greeting_messages(
        {"title": "AI应用赋能专员"},
        "{}",
        greeting_baseline="BASELINE-SENTINEL：先您好，再一句匹配，最后一句沟通请求。",
    )
    system = messages[0]["content"]
    assert "BASELINE-SENTINEL" in system
    assert "USER_GREETING_BASELINE" in system
    assert "不得把基准里的示例" in system


def test_focus_project_is_pinned_to_the_third_sentence():
    """手动指定项目：只锁第 3 句的选材，并要求项目不在简历时忽略、不得编造。"""
    messages = build_greeting_messages(
        {"title": "AI落地工程师"},
        "{}",
        focus_project="CreatorDistill 创作者内容分析系统",
    )
    system = messages[0]["content"]
    assert "第 3 句只能写「CreatorDistill 创作者内容分析系统」" in system
    assert "如果简历里找不到这个项目" in system
    assert "不要编造" in system
    # 没指定时不出现这段，避免污染默认生成。
    plain = build_greeting_messages({"title": "AI落地工程师"}, "{}")[0]["content"]
    assert "本次指定项目" not in plain


def test_greeting_prompt_no_longer_requires_education_intro():
    system = build_greeting_messages({"title": "AI应用赋能专员"}, "{}")[0]["content"]
    assert "不要介绍学校、专业、年级、届别、学历、毕业时间" in system


# ===== 2026-11-10：不要问候语的开关 + 第 1 句必须随岗位变 =====


def test_salutation_toggle_off_overrides_the_prompt_rule():
    """关掉问候时，提示词里那条「必须以『您好，』开头」必须被显式作废。

    为什么必须在提示词层就作废：代码侧还会再把开头的问候剥掉（见
    `normalize_greeting_opening`），但如果模型仍然写「您好」，那段字数就被白花了——
    用户关它的目的正是"省下开头 3 个字给能力标签"。
    """
    messages = build_greeting_messages({"title": "测试岗"}, "{}", greeting_with_salutation=False)
    system = messages[0]["content"]

    assert "本次由用户明确关闭" in system
    assert "本次不适用" in system
    # 原规则仍在（不删），但被上面那段覆盖。
    assert "必须以「您好，」开头" in system


def test_salutation_toggle_on_keeps_default_behavior():
    """默认（开）不追加覆盖段：用户规定的礼貌开场原样保留。"""
    messages = build_greeting_messages({"title": "测试岗"}, "{}")
    system = messages[0]["content"]

    assert "本次由用户明确关闭" not in system
    assert "必须以「您好，」开头" in system


def test_parse_greeting_strips_salutation_when_disabled():
    from app.services.job.job_match import parse_greeting

    assert parse_greeting("您好，做过多模型应用的功能验证。", with_salutation=False) == (
        "做过多模型应用的功能验证。"
    )
    assert parse_greeting("你好，做过数据管道。", with_salutation=False) == "做过数据管道。"
    assert parse_greeting("尊敬的HR您好，做过数据管道。", with_salutation=False) == "做过数据管道。"
    # 正文里的「您好」不动：那可能是引用 JD 或客户场景。
    kept = parse_greeting("做过客户对接，常说您好。", with_salutation=False)
    assert "常说您好" in kept


def test_first_sentence_guidance_no_longer_recommends_ai_positioning():
    """第 1 句的指引里，「用 AI 工具端到端交付」不能是推荐写法（它是第 4 句的事）。

    用户实测：连续多条招呼语第 1 句都是「做过用 AI 工具端到端交付的 AI 应用」，
    因为旧提示词把它写成了一条"可以单独说的定位"，模型就当成了固定开场。
    """
    messages = build_greeting_messages({"title": "测试岗"}, "{}")
    system = messages[0]["content"]

    assert "不要放在第 1 句" in system
    assert "定位归这里" in system  # 第 4 句的小标题
