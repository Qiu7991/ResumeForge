"""岗位类型推断：默认社招，只有明确的应届/在校/实习字样才归校招/实习。"""

from __future__ import annotations

from app.services.job.job_type_infer import infer_job_type


def test_internship_wins_over_campus_wording():
    assert infer_job_type("AI 应用实习生", "面向 2027 届毕业生") == "实习"


def test_campus_when_jd_mentions_fresh_graduates():
    assert infer_job_type("算法工程师", "招聘对象：2026 届毕业生") == "校招"
    assert infer_job_type("管理培训生", "管培生项目") == "校招"


def test_social_by_default_even_with_no_experience_requirement():
    # "经验不限" 不能当校招证据：大量社招岗位也这么写。
    assert infer_job_type("AI 工程师", "经验不限，学历不限") == "社招"
    assert infer_job_type("", "") == "社招"
