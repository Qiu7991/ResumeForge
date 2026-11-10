# SPDX-License-Identifier: Apache-2.0
"""显示技术栈开关（默认关）。

锁住四件事：
1. 默认值就是 False（老板的明确要求：生成的简历不要带技术栈）；
2. 关闭时 v2 的技术栈项变成 placement=hidden（**保留数据**，不是删除）；
3. 关闭时 description/highlights 里单独成行的「技术栈：…」也会被去掉；
4. 作用范围是**纸面显示**，不是资料事实——资料库里的 tech_stack 一个字符都不动。
"""

from app.schemas.generation_preferences import GenerationPreferences
from app.services.resume.resume_tech_stack import (
    strip_resume_tech_stack,
    visible_tech_stack_count,
)


def _v2_with_tech_stack() -> dict:
    return {
        "version": 2,
        "sections": [
            {
                "key": "projects",
                "entries": [
                    {
                        "id": "a",
                        "hidden": False,
                        "items": [
                            {"kind": "field", "key": "name", "value": "AI 简历工作台"},
                            {"kind": "text", "text": "闭环交付一份可投的简历。"},
                            {
                                "kind": "list",
                                "key": "tech_stack",
                                "values": ["React", "FastAPI"],
                                "placement": "trail",
                            },
                        ],
                    }
                ],
            }
        ],
    }


def test_default_is_hidden():
    """默认关闭——不配置任何东西时，新生成的简历不显示技术栈。"""
    assert GenerationPreferences().show_tech_stack is False


def test_switch_off_hides_v2_tech_stack_items_but_keeps_data():
    content = _v2_with_tech_stack()

    strip_resume_tech_stack(content)

    item = content["sections"][0]["entries"][0]["items"][2]
    # 只是不上纸面：placement 变 hidden，values 原样保留（编辑器还能拖回来）。
    assert item["placement"] == "hidden"
    assert item["hidden_from"] == "trail"
    assert item["values"] == ["React", "FastAPI"]
    assert visible_tech_stack_count(content) == 0


def test_switch_off_strips_inline_tech_stack_lines():
    """模型会把「技术栈：…」写进正文；关闭时这类整行/行内标签要一起清掉。"""
    projects = [
        {
            "name": "AI 简历工作台",
            "tech_stack": ["React", "FastAPI"],
            "description": [
                "技术栈：React、FastAPI",
                "闭环交付一份可投的简历。",
                "做过端到端交付。技术栈：Docker、Caddy。",
            ],
            "highlights": ["Tech Stack: Postgres", "20 个 API"],
        }
    ]
    content = {"projects": projects}

    strip_resume_tech_stack(content)

    assert content["projects"][0]["tech_stack"] == []
    # 整行标签整行删；行内标签删「技术栈：…」连同其前后标点，前半句原样保留。
    # 这两个字面量是 1.x resume_tech_stack 的实测输出（1.x / 2.0 逐字一致）。
    assert content["projects"][0]["description"] == [
        "闭环交付一份可投的简历。",
        "做过端到端交付",
    ]
    # 英文标签同样识别，但正文里自然提到的技术名词不动。
    assert content["projects"][0]["highlights"] == ["20 个 API"]


def test_switch_on_keeps_tech_stack_untouched():
    """开关打开时不调用 strip：技术栈原样上纸面。"""
    content = _v2_with_tech_stack()
    preferences = GenerationPreferences(show_tech_stack=True)

    if not preferences.show_tech_stack:
        strip_resume_tech_stack(content)

    item = content["sections"][0]["entries"][0]["items"][2]
    assert item["placement"] == "trail"
    assert visible_tech_stack_count(content) == 1


def test_strip_is_idempotent():
    """重复保存不该反复改写：已经是 hidden 的项原样返回。"""
    content = _v2_with_tech_stack()

    strip_resume_tech_stack(content)
    first = content["sections"][0]["entries"][0]["items"][2]["placement"]
    strip_resume_tech_stack(content)
    second = content["sections"][0]["entries"][0]["items"][2]["placement"]

    assert first == second == "hidden"


def test_tech_stack_detected_by_source_field_id():
    """v2 里技术栈也可能带着 source.field_id；按来源也要认得出。"""
    content = {
        "sections": [
            {
                "key": "projects",
                "entries": [
                    {
                        "items": [
                            {
                                "kind": "field",
                                "key": "custom_1",
                                "value": "React、FastAPI",
                                "source": {"field_id": "projects.tech_stack"},
                                "placement": "trail",
                            }
                        ]
                    }
                ],
            }
        ]
    }

    strip_resume_tech_stack(content)

    assert content["sections"][0]["entries"][0]["items"][0]["placement"] == "hidden"


# ===== 从 1.x test_generation_preferences.py 补齐的三条（容错 / v2 文本项 / API 往返）=====


def test_strip_tolerates_missing_or_malformed_projects():
    """没有 projects、或 projects 不是列表时原样返回（不能把生成打挂）。"""
    assert strip_resume_tech_stack({"summary": "x"}) == {"summary": "x"}
    assert strip_resume_tech_stack({"projects": "bad"}) == {"projects": "bad"}


def test_strip_cleans_v2_text_items_with_tech_stack_lines():
    """底稿模式返回的 v2 文档：列表项要 hidden，正文文本行里的「技术栈/工具：」也要删。"""
    content = {
        "version": 2,
        "sections": [
            {
                "key": "projects",
                "entries": [
                    {
                        "items": [
                            {
                                "kind": "list",
                                "key": "tech_stack",
                                "placement": "trail",
                                "values": ["Docker", "Caddy"],
                            },
                            {
                                "kind": "text",
                                "text": "技术栈/工具：Docker、Caddy\n独立搭建家庭网络。",
                            },
                        ]
                    }
                ],
            }
        ],
    }

    strip_resume_tech_stack(content)
    items = content["sections"][0]["entries"][0]["items"]

    assert items[0]["placement"] == "hidden"
    assert items[0]["values"] == ["Docker", "Caddy"]
    assert items[1]["text"] == "独立搭建家庭网络。"


# ===== 创建手写/底稿简历也是写路径（R7 对抗审查 B③ 打出来的缺口）=====


def test_manual_creation_strips_tech_stack_when_off(client):
    """新建一份手写简历（`source=manual`，含 draft）不能绕过技术栈开关。

    这条路走 `create_manual_resume_record` → `_validated_content`，**不经过**
    `document_save.save_content`（那条是给已存在记录的 PUT）。只挂 save_content 的话，
    「新建手写简历 → 技术栈照样出现」就是漏的。
    """
    created = client.post(
        "/api/resumes/manual",
        json={
            "content": {
                "name": "林致远",
                "projects": [
                    {
                        "name": "AI 简历工作台",
                        "tech_stack": ["React", "FastAPI"],
                        "description": ["闭环交付。"],
                    }
                ],
            },
            "draft": True,
        },
    )
    assert created.status_code == 201, created.text

    detail = client.get(f"/api/resumes/{created.json()['id']}")
    assert detail.status_code == 200
    document = detail.json()["content"]
    assert visible_tech_stack_count(document) == 0
    # 数据仍在（hidden 而非删除），编辑器可拖回。
    stored = [
        item
        for section in document.get("sections") or []
        for entry in section.get("entries") or []
        for item in entry.get("items") or []
        if item.get("key") == "tech_stack"
    ]
    assert stored and stored[0].get("placement") == "hidden"
