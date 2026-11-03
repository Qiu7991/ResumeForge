# SPDX-License-Identifier: Apache-2.0
"""生成收口：同名项目合并要点，并按页数保留前 N 条。"""

from app.services.resume.resume_dedupe import dedupe_and_limit_resume


def test_v1_merges_same_project_and_limits_by_page():
    content = {
        "projects": [
            {"name": "AI 简历工作台", "description": ["闭环"]},
            {"name": "民生账号", "description": ["选题"]},
            {"name": "AI 简历工作台", "highlights": ["20 个 API"]},
            {"name": "项目 3"},
            {"name": "项目 4"},
        ],
        "experience": [
            {"company": "A 公司", "description": ["调试"]},
            {"company": "A 公司", "description": ["文档"]},
            {"company": "B 公司"},
            {"company": "C 公司"},
        ],
    }

    result = dedupe_and_limit_resume(content, page_limit=1)

    assert [item["name"] for item in result["projects"]] == ["AI 简历工作台", "民生账号", "项目 3"]
    assert result["projects"][0]["description"] == ["闭环"]
    assert result["projects"][0]["highlights"] == ["20 个 API"]
    assert [item["company"] for item in result["experience"]] == ["A 公司", "B 公司"]
    assert result["experience"][0]["description"] == ["调试", "文档"]


def test_v2_merges_duplicate_entries_and_caps():
    def entry(entry_id: str, name: str, points: list[str]):
        return {
            "id": entry_id,
            "hidden": False,
            "items": [
                {"kind": "field", "key": "name", "value": name},
                *[{"kind": "text", "text": point} for point in points],
            ],
        }

    content = {
        "version": 2,
        "sections": [
            {
                "key": "projects",
                "entries": [
                    entry("a", "AI 简历工作台", ["闭环"]),
                    entry("b", "AI 简历工作台", ["20 个 API"]),
                    entry("c", "项目 2", []),
                    entry("d", "项目 3", []),
                    entry("e", "项目 4", []),
                ],
            }
        ],
    }

    result = dedupe_and_limit_resume(content, page_limit=1)

    entries = result["sections"][0]["entries"]
    assert [item["id"] for item in entries] == ["a", "c", "d"]
    texts = [item["text"] for item in entries[0]["items"] if item["kind"] == "text"]
    assert texts == ["闭环", "20 个 API"]
