# SPDX-License-Identifier: Apache-2.0
"""生成结果去重：只合并完全相同的条目，绝不裁剪篇幅（E15）。

三个场景对应卡片 R2 的三条硬约束：
1. 两条完全相同的项目 → 只留一条（要点取并集，内容不丢）；
2. 内容相似但不相同 → 都保留（不做模糊判断，宁可多一条）；
3. 认不出身份的条目 / 用户手动加的条目 → 一条都不删、顺序不变。
"""

from app.services.resume.resume_dedupe import dedupe_resume


def test_v1_identical_projects_merge_into_one():
    content = {
        "projects": [
            {"name": "AI 简历工作台", "description": ["闭环"]},
            {"name": "民生账号", "description": ["选题"]},
            {"name": "AI 简历工作台", "highlights": ["20 个 API"]},
        ],
    }

    result = dedupe_resume(content)

    # ① 只留一条，且位置沿用首次出现；要点取并集（内容一个字都不丢）。
    assert [item["name"] for item in result["projects"]] == ["AI 简历工作台", "民生账号"]
    assert result["projects"][0]["description"] == ["闭环"]
    assert result["projects"][0]["highlights"] == ["20 个 API"]


def test_v1_similar_but_different_projects_both_kept():
    content = {
        "projects": [
            {"name": "CreatorDistill 创作者内容分析系统"},
            {"name": "CreatorDistill 爆款拆解语料库"},
            {"name": "AI 简历工作台"},
            {"name": "AI 简历工作台 V2"},
        ],
    }

    result = dedupe_resume(content)

    # ② 相似但不相同 → 全保留（共享品牌名不等于同一个项目）。
    assert [item["name"] for item in result["projects"]] == [
        "CreatorDistill 创作者内容分析系统",
        "CreatorDistill 爆款拆解语料库",
        "AI 简历工作台",
        "AI 简历工作台 V2",
    ]


def test_v1_entries_without_identity_are_never_dropped():
    content = {
        "projects": [
            {"name": "", "description": ["用户在编辑器里还没填名字的半成品"]},
            {"name": "   ", "description": ["只有空白名字"]},
            {"name": "正常项目"},
        ],
    }

    result = dedupe_resume(content)

    # ③ 认不出是谁的条目原样保留——"匹配不上"绝不等于"该删"。
    assert len(result["projects"]) == 3
    assert result["projects"][0]["description"] == ["用户在编辑器里还没填名字的半成品"]
    assert result["projects"][2]["name"] == "正常项目"


def test_dedupe_does_not_truncate_quantity():
    """E15 回归：去重绝不能顺手按页数裁条目（1.x 曾因此"修订一次少一个项目"）。"""
    content = {
        "projects": [{"name": f"项目 {index}"} for index in range(8)],
        "experience": [{"company": f"公司 {index}"} for index in range(6)],
    }

    result = dedupe_resume(content)

    assert len(result["projects"]) == 8
    assert len(result["experience"]) == 6


def test_v2_duplicate_entries_merge_and_keep_count():
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
                ],
            }
        ],
    }

    result = dedupe_resume(content)

    entries = result["sections"][0]["entries"]
    # 只合并好的那两条，其它一条不少（4 条 → 3 条，不是被裁到 N 条）。
    assert [item["id"] for item in entries] == ["a", "c", "d"]
    texts = [item["text"] for item in entries[0]["items"] if item["kind"] == "text"]
    assert texts == ["闭环", "20 个 API"]


def test_v2_experience_identity_is_composite():
    """同公司两段不同职位 → 两条都保留（只按 company 合并会让晋升经历消失）。"""

    def entry(entry_id: str, company: str, role: str, period: str):
        return {
            "id": entry_id,
            "hidden": False,
            "items": [
                {"kind": "field", "key": "company", "value": company},
                {"kind": "field", "key": "role", "value": role},
                {"kind": "field", "key": "period", "value": period},
            ],
        }

    content = {
        "version": 2,
        "sections": [
            {
                "key": "experience",
                "entries": [
                    entry("a", "蓝粤", "测试工程师", "2023-2024"),
                    entry("b", "蓝粤", "高级测试工程师", "2024-2026"),
                    entry("c", "蓝粤", "测试工程师", "2023-2024"),
                ],
            }
        ],
    }

    result = dedupe_resume(content)

    entries = result["sections"][0]["entries"]
    assert [item["id"] for item in entries] == ["a", "b"]
