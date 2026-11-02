# SPDX-License-Identifier: Apache-2.0
"""岗位广场城市筛选：列表、跨页全选同吃一份筛选器，城市选项按岗位数排序。"""

from app.models.job import Job


def _seed_cities(db_session) -> None:
    rows = [
        ("广州前端", "广州·天河区"),
        ("广州后端", "广州·南沙区"),
        ("深圳算法", "深圳·南山区"),
        ("北京产品", "北京"),
        ("无城市", ""),
    ]
    for title, location in rows:
        db_session.add(Job(title=title, company="示例公司", location=location))
    db_session.commit()


def test_job_list_filters_by_city(client, db_session):
    _seed_cities(db_session)

    items = client.get("/api/jobs", params={"city": "广州"}).json()["items"]
    assert [item["title"] for item in items] == ["广州后端", "广州前端"]


def test_select_all_ids_respects_the_city_filter(client, db_session):
    _seed_cities(db_session)

    ids = client.get("/api/jobs/ids", params={"city": "深圳"}).json()
    assert len(ids) == 1
    assert client.get(f"/api/jobs/{ids[0]}").json()["title"] == "深圳算法"


def test_city_options_are_deduplicated_and_ordered_by_job_count(client, db_session):
    _seed_cities(db_session)

    cities = client.get("/api/jobs/cities").json()

    assert cities[0] == "广州"  # 两条，排最前
    assert set(cities[1:]) == {"深圳", "北京"}
    assert "" not in cities
