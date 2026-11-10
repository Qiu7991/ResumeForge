# SPDX-License-Identifier: Apache-2.0
"""BOSS「感兴趣」列表解析的离线测试。

夹具 ``fixtures/boss_interest_page1.json`` 来自 2026-11-09 对真实接口
（``GET /wapi/zprelation/interaction/geekGetJob?page=1&tag=4&isActive=true``）响应的
脱敏摘录：只保留 3 张卡、删掉头像/Logo 等长 URL。常量断言（tag=4、每页 15 条）钉住
的是实测结论——tag 搞反会采到「沟通过」列表，是这条链路最容易犯的错。
"""
import json
from pathlib import Path

import pytest
from app.models.apply import FAILURE_SELECTOR_INVALID, FAILURE_UNKNOWN
from app.services.sites.base import SiteFailure
from app.services.sites.boss_interest import (
    INTEREST_PAGE_SIZE,
    INTEREST_PATH,
    INTEREST_TAG,
    _fetch_script,
    fetch_interest_page,
    parse_interest_card,
    parse_interest_response,
)

_FIXTURE = Path(__file__).parent / "fixtures" / "boss_interest_page1.json"


def _payload() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


class _FakeInterestClient:
    """返回预设响应的假 CDP 客户端（记录全部 evaluate 调用）。"""

    def __init__(self, payload: dict) -> None:
        self._payload = json.dumps(payload, ensure_ascii=False)
        self.expressions: list[str] = []

    def evaluate(self, expression: str, *, timeout: float | None = None) -> str:
        self.expressions.append(expression)
        return self._payload


def test_interest_constants_are_the_probed_ones():
    """tag=4 才是「感兴趣」（tag=5 是沟通过）、每页固定 15 条——2026-11-09 实测。"""
    assert INTEREST_TAG == 4
    assert INTEREST_PAGE_SIZE == 15
    assert INTEREST_PATH.startswith("/web/geek/recommend")


def test_fetch_script_targets_interest_endpoint():
    script = _fetch_script(2)
    assert "geekGetJob?page=2" in script
    assert "tag=4" in script
    assert "isActive=true" in script
    assert "X-Requested-With" in script
    assert "credentials: 'include'" in script


def test_parse_interest_response_maps_all_fields():
    page = parse_interest_response(_payload())

    assert page.total_count == 134
    assert page.has_more is True
    assert page.invalid == 0
    assert len(page.results) == 3

    first = page.results[0]
    assert first.title == "AI项目助理"
    assert first.company == "广州示例医疗科技"
    assert first.salary == "8-9K"
    assert first.location == "广州·黄埔区·东圃"
    assert first.url == "https://www.zhipin.com/job_detail/FAKEencryptJobId0000000000000000000.html"
    assert first.source == "BOSS直聘"
    assert first.extra["encrypt_job_id"] == "FAKEencryptJobId0000000000000000000"
    # fixture 里的 securityId 是脱敏假值（真值是用户登录态令牌，绝不能进仓库）；
    # 这里只验"卡片上的 securityId 被原样带进 extra"，不验具体值。
    assert first.extra["security_id"].startswith("FAKEsecurityIdForFixtureOnly")
    assert first.extra["experience"] == "1年以内"
    assert first.extra["degree"] == "本科"
    assert first.extra["city"] == "广州"
    assert first.extra["industry"] == "医疗健康"
    assert first.extra["scale"] == "100-499人"
    assert first.extra["hr_name"] == "谢女士"
    assert first.extra["hr_title"] == "招聘经理"


def test_parse_interest_skips_invalid_jobs():
    """``jobValidStatus != 1`` 的卡计入 invalid、不进 results——差额要如实报，不能悄悄丢。"""
    payload = _payload()
    invalid_id = payload["zpData"]["cardList"][1]["encryptJobId"]
    payload["zpData"]["cardList"][1]["jobValidStatus"] = 0

    page = parse_interest_response(payload)

    assert page.invalid == 1
    assert len(page.results) == 2
    assert all(item.extra["encrypt_job_id"] != invalid_id for item in page.results)


def test_parse_interest_skips_closed_jobs_status_two():
    """``jobValidStatus == 2`` = 职位已关闭，必须跳过（2026-11-09 实测钉死的语义）。

    为什么单独钉一条：状态 2 的岗位**详情接口仍会返回缓存的 JD**（实测 493 字），
    所以"能抓到 JD"不能当成"这岗位还能投"。真实数据里 134 条「感兴趣」中有 45 条是
    状态 2——把它们放进暂存区，用户会白花一次招呼语去投一个已关闭的岗位。
    """
    payload = _payload()
    closed_id = payload["zpData"]["cardList"][0]["encryptJobId"]
    payload["zpData"]["cardList"][0]["jobValidStatus"] = 2

    page = parse_interest_response(payload)

    assert page.invalid == 1
    assert all(item.extra["encrypt_job_id"] != closed_id for item in page.results)


def test_parse_interest_treats_missing_status_as_invalid():
    """状态字段缺失按失效处理（安全侧）：宁可漏采一条，也不把可疑岗位塞进暂存区。"""
    payload = _payload()
    missing_id = payload["zpData"]["cardList"][2]["encryptJobId"]
    payload["zpData"]["cardList"][2].pop("jobValidStatus", None)

    page = parse_interest_response(payload)

    assert page.invalid == 1
    assert all(item.extra["encrypt_job_id"] != missing_id for item in page.results)


def test_parse_interest_raises_on_business_error():
    """code=121（请求不合法）与其它非零码都要显式失败，绝不静默当空列表。"""
    with pytest.raises(SiteFailure) as excinfo:
        parse_interest_response({"code": 121, "message": "请求不合法"})
    assert excinfo.value.category == FAILURE_SELECTOR_INVALID
    assert "121" in excinfo.value.detail

    with pytest.raises(SiteFailure) as excinfo:
        parse_interest_response({"code": 7, "message": "服务器开小差"})
    assert excinfo.value.category == FAILURE_UNKNOWN


def test_interest_job_url_shape():
    card = {"jobName": "后端开发", "encryptJobId": "abc123XYZ", "jobValidStatus": 1}

    result = parse_interest_card(card)

    assert result is not None
    assert result.url == "https://www.zhipin.com/job_detail/abc123XYZ.html"


def test_parse_interest_handles_empty_card_list():
    payload = {
        "code": 0,
        "message": "Success",
        "zpData": {"cardList": [], "hasMore": False, "startIndex": 0, "page": 1, "totalCount": 0},
    }

    page = parse_interest_response(payload)

    assert page.results == []
    assert page.has_more is False
    assert page.total_count == 0
    assert page.invalid == 0


def test_fetch_interest_page_rejects_totalcount_without_cards():
    """第一页 totalCount>0 但一条卡都没有 → 显式失败，不许伪装成"真的没岗位"。"""
    payload = {
        "code": 0,
        "message": "Success",
        "zpData": {"cardList": [], "hasMore": True, "totalCount": 134},
    }
    client = _FakeInterestClient(payload)

    with pytest.raises(SiteFailure) as excinfo:
        fetch_interest_page(client, 1)

    assert "134" in excinfo.value.detail
