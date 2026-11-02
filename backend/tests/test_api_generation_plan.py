# SPDX-License-Identifier: Apache-2.0
"""生成计划接口：创建 → 读取 → 人工换项目，且计划只引用真实资料。"""

from __future__ import annotations

import json

from app.models.claim import CLAIM_CATEGORY_PROJECT, VERIFICATION_CONFIRMED, ClaimRecord
from app.models.job import Job
from app.schemas.setting import LLMConfig
from app.services.profile import entry_store


class FakeProvider:
    def __init__(self, response: dict):
        self.config = LLMConfig(
            base_url="https://api.example.com/v1",
            api_key="test",
            model="fake-plan-model",
        )
        self.response = response

    async def chat(self, messages, *, thinking=False):  # noqa: ARG002
        return json.dumps(self.response, ensure_ascii=False)


def _seed(db):
    job = Job(
        title="嵌入式 AI 工程师",
        company="示例公司",
        location="广州",
        description="负责端侧模型部署与优化。",
        requirements="熟悉 ONNX / 树莓派 / 提示词工程。",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    rows = entry_store.bulk_save_entries(
        db,
        [
            {
                "section_key": "projects",
                "values": {
                    "projects.name": "边缘 AI 跌倒检测",
                    "projects.role": "算法与部署",
                    "projects.tech_stack": "YOLO、ONNX、树莓派",
                    "projects.description": "把跌倒检测模型部署到树莓派，端侧推理延迟 120ms。",
                },
            }
        ],
    )
    project = rows[0]
    claim = ClaimRecord(
        title="边缘 AI 跌倒检测 · 项目事实",
        category=CLAIM_CATEGORY_PROJECT,
        subject="边缘 AI 跌倒检测",
        source_fact="把模型转成 ONNX 部署到树莓派，端侧延迟从 800ms 降到 120ms。",
        sources=[
            {"type": "reference", "location": project.entry_id, "public": False}
        ],
        verification_status=VERIFICATION_CONFIRMED,
        responsibility_level="负责模块",
    )
    db.add(claim)
    db.commit()
    return job, project


def test_generation_plan_create_read_and_select(client, db_session, monkeypatch):
    job, project = _seed(db_session)
    response = {
        "requirements": [
            {
                "id": "R1",
                "text": "端侧模型部署",
                "type": "hard_skill",
                "weight": 5,
                "keywords": ["ONNX", "树莓派"],
            }
        ],
        "evidence": [
            {
                "requirement_id": "R1",
                "ref_type": "project",
                "ref_id": project.entry_id,
                "match": "direct",
                "rationale": "项目里有树莓派部署",
                "fact_quotes": ["把跌倒检测模型部署到树莓派，端侧推理延迟 120ms。"],
                "selected": True,
            }
        ],
    }
    provider = FakeProvider(response)
    monkeypatch.setattr(
        "app.api.resumes.get_llm_config",
        lambda db: LLMConfig(
            base_url="https://api.example.com/v1", api_key="test", model="cfg-model"
        ),
    )
    monkeypatch.setattr("app.api.resumes.create_provider", lambda config: provider)

    created = client.post(
        "/api/resumes/generation-plan",
        json={"job_id": job.id, "custom_instruction": "优先端侧部署"},
    )
    assert created.status_code == 201, created.text
    plan = created.json()
    assert plan["job_id"] == job.id
    assert plan["model"] == "fake-plan-model"
    assert plan["requirements"][0]["id"] == "R1"
    assert plan["evidence"][0]["selected"] is True
    assert plan["coverage"]["by_requirement"]["R1"]["status"] == "direct"

    fetched = client.get(f"/api/resumes/generation-plan/{plan['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == plan["id"]

    # 人工取消选择 → 覆盖回到缺口。
    updated = client.patch(
        f"/api/resumes/generation-plan/{plan['id']}",
        json={"selected_evidence_ids": []},
    )
    assert updated.status_code == 200
    assert updated.json()["coverage"]["by_requirement"]["R1"]["status"] == "gap"

    # 不属于计划的 id 必须被拒绝，不能借 PATCH 注入证据。
    bad = client.patch(
        f"/api/resumes/generation-plan/{plan['id']}",
        json={"selected_evidence_ids": ["R1:project:forged"]},
    )
    assert bad.status_code == 400
