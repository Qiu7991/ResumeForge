"""岗位广场排序：默认按收录时间倒序，可切正序 / 发布时间。"""

from __future__ import annotations


def _create(client, title: str, posted_at: str = "") -> int:
    payload = {"title": title, "company": "示例公司", "description": "岗位职责"}
    if posted_at:
        payload["posted_at"] = posted_at
    response = client.post("/api/jobs", json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def test_list_sorts_by_created_time_both_directions(client):
    _create(client, "岗位A")
    _create(client, "岗位B")
    newest_first = client.get("/api/jobs?page=1&page_size=10").json()["items"]
    oldest_first = client.get("/api/jobs?page=1&page_size=10&sort=created_asc").json()["items"]

    assert [j["title"] for j in newest_first] == ["岗位B", "岗位A"]
    assert [j["title"] for j in oldest_first] == ["岗位A", "岗位B"]


def test_list_rejects_unknown_sort(client):
    response = client.get("/api/jobs?sort=whatever")
    assert response.status_code == 422
