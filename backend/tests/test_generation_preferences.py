# SPDX-License-Identifier: Apache-2.0
"""资料页生成偏好：默认不显示技术栈；关闭时确定性清掉项目技术栈与标签行。"""

from __future__ import annotations

from app.services.resume.resume_tech_stack import strip_resume_tech_stack


def test_generation_preferences_default_off_and_can_be_turned_on(client):
    initial = client.get("/api/profile/generation-preferences")
    assert initial.status_code == 200
    assert initial.json() == {"include_tech_stack": False}

    saved = client.put(
        "/api/profile/generation-preferences",
        json={"include_tech_stack": True},
    )
    assert saved.status_code == 200
    assert saved.json() == {"include_tech_stack": True}
    assert client.get("/api/profile/generation-preferences").json() == {
        "include_tech_stack": True
    }


def test_strip_resume_tech_stack_clears_field_and_label_lines():
    content = {
        "projects": [
            {
                "name": "边缘 AI 跌倒检测",
                "tech_stack": ["YOLO", "ONNX", "树莓派"],
                "description": [
                    "技术栈：YOLO、ONNX、树莓派",
                    "把跌倒检测模型部署到树莓派，端侧延迟 120ms。",
                ],
                "highlights": ["Tech Stack: Python / FastAPI", "召回率 93%"],
            }
        ]
    }

    result = strip_resume_tech_stack(content)

    project = result["projects"][0]
    assert project["tech_stack"] == []
    assert project["description"] == ["把跌倒检测模型部署到树莓派，端侧延迟 120ms。"]
    assert project["highlights"] == ["召回率 93%"]


def test_strip_resume_tech_stack_tolerates_missing_projects():
    assert strip_resume_tech_stack({"summary": "x"}) == {"summary": "x"}
    assert strip_resume_tech_stack({"projects": "bad"}) == {"projects": "bad"}
