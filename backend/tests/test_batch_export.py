"""简历批量导出（POST /api/resumes/batch-export）的用例。

钉住四件事：
1. 选中多份 → 一个 zip，条目数 = 成功份数，文件名不重名；
2. 重复 id 去重（同一份简历不会在 zip 里出现两次）；
3. 有 id 不存在/在回收站 → 整批 404（不做"导一半"）；
4. 单份失败（正文仍带【待补】）只跳过它，其余照常导出，跳过原因随响应头带回。
"""

from __future__ import annotations

import urllib.parse
import zipfile
from io import BytesIO

import pytest

from app.models.resume import ResumeRecord

pytestmark = pytest.mark.usefixtures("client")


def _content(name: str = "张三", summary: str = "五年后端开发经验。") -> dict:
    return {
        "name": name,
        "phone": "13800001234",
        "email": "zhangsan@example.com",
        "city": "广州",
        "job_intent": "后端开发工程师",
        "summary": summary,
        "education": [
            {
                "school": "示例大学",
                "major": "计算机科学与技术",
                "degree": "本科",
                "start_date": "2016-09",
                "end_date": "2020-06",
            }
        ],
        "experience": [
            {
                "company": "示例科技有限公司",
                "role": "后端工程师",
                "start_date": "2020-07",
                "end_date": "至今",
                "description": ["负责订单服务的设计与维护。"],
            }
        ],
    }


def _insert(db_session, title: str, summary: str = "五年后端开发经验。") -> int:
    row = ResumeRecord(title=title, content=_content(summary=summary))
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    return row.id


def _zip_names(response) -> list[str]:
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        return archive.namelist()


def test_batch_export_packs_selected_resumes(client, db_session):
    ids = [_insert(db_session, f"后端版 {n}") for n in range(1, 4)]

    response = client.post("/api/resumes/batch-export", json={"resume_ids": ids})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    names = _zip_names(response)
    assert len(names) == 3
    assert len(set(names)) == 3
    assert all(name.endswith(".pdf") for name in names)
    assert response.headers["X-Batch-Exported"] == "3"
    assert response.headers["X-Batch-Skipped"] == "0"
    disposition = urllib.parse.unquote(response.headers["Content-Disposition"])
    assert "简历批量导出-" in disposition


def test_batch_export_deduplicates_ids(client, db_session):
    resume_id = _insert(db_session, "只导一份")

    response = client.post(
        "/api/resumes/batch-export", json={"resume_ids": [resume_id, resume_id]}
    )

    assert response.status_code == 200
    assert len(_zip_names(response)) == 1
    assert response.headers["X-Batch-Exported"] == "1"


def test_batch_export_missing_resume_is_404(client, db_session):
    resume_id = _insert(db_session, "存在的")

    response = client.post(
        "/api/resumes/batch-export", json={"resume_ids": [resume_id, 999999]}
    )

    assert response.status_code == 404
    assert "999999" in response.json()["detail"]


def test_batch_export_skips_incomplete_resume_but_keeps_others(client, db_session):
    good = _insert(db_session, "完整版")
    draft = _insert(db_session, "草稿版", summary="【待补】量化业绩。")

    response = client.post(
        "/api/resumes/batch-export", json={"resume_ids": [good, draft]}
    )

    assert response.status_code == 200
    assert len(_zip_names(response)) == 1
    assert response.headers["X-Batch-Exported"] == "1"
    assert response.headers["X-Batch-Skipped"] == "1"
    detail = urllib.parse.unquote(response.headers["X-Batch-Skipped-Detail"])
    assert "草稿版" in detail


def test_batch_export_all_incomplete_is_409(client, db_session):
    draft = _insert(db_session, "全是草稿", summary="【待补】量化业绩。")

    response = client.post("/api/resumes/batch-export", json={"resume_ids": [draft]})

    assert response.status_code == 409
    assert "没有可导出的简历" in response.json()["detail"]


def test_batch_export_format_is_selectable(client, db_session):
    resume_id = _insert(db_session, "Word 版")

    response = client.post(
        "/api/resumes/batch-export",
        json={"resume_ids": [resume_id], "format": "docx"},
    )

    assert response.status_code == 200
    assert _zip_names(response)[0].endswith(".docx")


def test_batch_export_rejects_unknown_format(client, db_session):
    resume_id = _insert(db_session, "格式非法")

    response = client.post(
        "/api/resumes/batch-export",
        json={"resume_ids": [resume_id], "format": "exe"},
    )

    assert response.status_code == 422
