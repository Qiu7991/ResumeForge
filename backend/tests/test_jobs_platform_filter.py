# SPDX-License-Identifier: Apache-2.0
"""岗位平台：从来源 URL / 备注派生，列表可筛选，不新增数据库列。"""

from __future__ import annotations

from app.models.job import Job


def _seed(db):
    rows = [
        Job(
            title="BOSS 岗位",
            source="岗位采集",
            source_url="https://www.zhipin.com/job_detail/a.html",
            note="BOSS；1-3年",
            location="广州·天河区",
        ),
        Job(
            title="智联岗位",
            source="手动添加",
            source_url="https://www.zhaopin.com/jobdetail/CC1.htm",
            note="智联",
            location="广州·天河区",
        ),
        Job(
            title="手填岗位",
            source="手动添加",
            source_url="",
            note="朋友内推",
            location="深圳·南山区",
        ),
        Job(
            title="未识别岗位",
            source="岗位采集",
            source_url="https://example.com/job/1",
            note="",
            location="深圳·南山区",
        ),
    ]
    db.add_all(rows)
    db.commit()
    return rows


def test_platform_is_exposed_and_filterable(client, db_session):
    rows = _seed(db_session)

    all_jobs = client.get("/api/jobs", params={"page_size": 100})
    assert all_jobs.status_code == 200
    platforms = {item["title"]: item["platform"] for item in all_jobs.json()["items"]}
    assert platforms["BOSS 岗位"] == "BOSS直聘"
    assert platforms["智联岗位"] == "智联招聘"
    assert platforms["手填岗位"] == "手动添加"
    assert platforms["未识别岗位"] == "其他平台"

    zhilian = client.get("/api/jobs", params={"platform": "智联招聘"})
    assert zhilian.status_code == 200
    assert zhilian.json()["total"] == 1
    assert zhilian.json()["items"][0]["id"] == rows[1].id

    boss = client.get("/api/jobs/ids", params={"platform": "BOSS直聘"})
    assert boss.status_code == 200
    assert boss.json() == [rows[0].id]

    manual = client.get("/api/jobs", params={"platform": "手动添加"})
    assert manual.status_code == 200
    assert [item["id"] for item in manual.json()["items"]] == [rows[2].id]

    options = client.get("/api/jobs/platforms")
    assert options.status_code == 200
    assert {"BOSS直聘", "智联招聘", "手动添加", "其他平台"} <= set(options.json())
