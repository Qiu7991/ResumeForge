# SPDX-License-Identifier: Apache-2.0
"""「同一职位被 HR 重新发布」的判重（2026-11-10）。

真实场景（用户报的）：他在 BOSS 上投递过「AI 应用运营（AI 提示词 / 智能对话方向）」，
之后又把这个岗位收藏了；采集收藏时，同一个职位因为**重新发布**换了新的 encryptJobId，
标题也变成「AI应用运营（AI提示词/智能对话）双休」——链接不同、标题不完全相同，
精确判重抓不到，于是在岗位广场里多出一条看着一样的记录。
"""

import pytest

from app.models.job import Job
from app.services.job.job_title_match import (
    is_placeholder_company,
    normalize_company,
    normalize_title,
    same_posting,
)
from app.services.job.job_service import find_job_by_identity


class TestNormalize:
    def test_title_drops_trailing_noise_but_keeps_brackets(self):
        """末尾的「双休」去掉，**括号内容保留**。

        括号是区分的要害：`AI产品专员（互动小说）` 与 `AI产品专员（AIGC应用方向）`
        是两个不同岗位，去掉括号就会把它们并成一条。
        """
        assert normalize_title("AI应用运营（AI提示词/智能对话） 双休") == (
            "ai应用运营ai提示词智能对话"
        )
        assert normalize_title("AI 应用运营（AI 提示词 / 智能对话方向）") == (
            "ai应用运营ai提示词智能对话方向"
        )
        # 括号不同的两条必须归一化成不同结果。
        assert normalize_title("AI产品专员（互动小说）") != normalize_title(
            "AI产品专员（AIGC应用方向）"
        )

    def test_title_drops_trailing_salary_suffix(self):
        assert normalize_title("AI应用开发工程师 15-25K·14薪") == "ai应用开发工程师"
        assert normalize_title("前端开发 13薪") == "前端开发"

    def test_company_normalization_only_collapses_case_and_punctuation(self):
        assert normalize_company("广东超腾科技有限公司") == normalize_company("广东超腾科技有限公司")
        # 不做相似度：带"分公司"的是另一家公司，必须不相等。
        assert normalize_company("广东超腾（深圳）分公司") != normalize_company("广东超腾科技有限公司")


class TestSamePosting:
    def test_the_real_regression_both_forms_match(self):
        """用户实际遇到的那一对——括号内容被剥掉后两者归一化完全相同。"""
        assert same_posting(
            "AI 应用运营（AI 提示词 / 智能对话方向）",
            "AI应用运营（AI提示词/智能对话） 双休",
        )

    def test_similar_but_different_roles_do_not_match(self):
        """宁可漏判也不误判：这两个确实是不同岗位，不能判成重复。"""
        assert not same_posting("AI应用工程师", "AI应用架构师")
        assert not same_posting("AI产品经理", "AI项目经理")

    def test_short_titles_require_exact_equality(self):
        """4 字以内的标题没有区分度，只认完全相等（避免「后端」吞掉「后端开发」）。"""
        assert not same_posting("后端", "后端开发")
        assert same_posting("后端", "后端")

    def test_containment_needs_a_long_enough_shorter_side(self):
        assert same_posting("AI应用运营", "AI应用运营专员")  # 6 字，够长
        assert not same_posting("后端开发", "后端开发工程师")  # 4 字，太短

    def test_placeholder_companies_are_recognised(self):
        """猎头/匿名雇主的公司名不能当"同公司"依据。"""
        assert is_placeholder_company(normalize_company("猎头代招（雇主未公开）"))
        assert is_placeholder_company(normalize_company("保密企业"))
        assert not is_placeholder_company(normalize_company("广东超腾科技有限公司"))


class TestFindByIdentity:
    def _job(self, db, title, company, url):
        job = Job(title=title, company=company, source_url=url)
        db.add(job)
        db.commit()
        return job

    def test_exact_url_still_wins(self, db_session):
        """原有判据不能退化：链接相同永远命中，且优先于标题相似。"""
        existing = self._job(db_session, "任意标题", "A公司", "https://x/1")

        found = find_job_by_identity(
            db_session, title="完全不同的标题", company="B公司", source_url="https://x/1"
        )

        assert found is not None and found.id == existing.id

    def test_reposted_job_with_new_url_is_matched_by_title(self, db_session):
        """用户遇到的那条：新链接 + 标题带修饰差异，仍要判成同一个职位。"""
        existing = self._job(
            db_session,
            "AI 应用运营（AI 提示词 / 智能对话方向）",
            "广东超腾",
            "https://x/old",
        )

        found = find_job_by_identity(
            db_session,
            title="AI应用运营（AI提示词/智能对话） 双休",
            company="广东超腾",
            source_url="https://x/new",
        )

        assert found is not None and found.id == existing.id

    def test_same_title_at_a_different_company_is_not_a_match(self, db_session):
        """跨公司绝不能判成重复——那是把用户真正想投的岗位悄悄跳过。"""
        self._job(db_session, "AI应用运营", "A公司", "https://x/1")

        found = find_job_by_identity(
            db_session,
            title="AI应用运营",
            company="B公司",
            source_url="https://x/2",
        )

        assert found is None
