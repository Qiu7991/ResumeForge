# SPDX-License-Identifier: Apache-2.0
"""采集来源 source=interest 的编排测试（离线：假 adapter/client）。

钉四件事：interest 请求必须走「感兴趣」列表路径（不碰关键词搜索、不解析站点筛选）、
翻页终止与去重/上限口径正确、适配器不支持时显式失败、source=search 的原路径零变化
（回归守门——搜索分支是从 run() 整段搬迁出来的，这里确认搬迁没有改变行为）。
"""
import json
import re

import pytest
from app.models.apply import TASK_KIND_COLLECT, ApplyTask
from app.models.job import Job
from app.models.material import CandidateJob
from app.schemas.apply import CollectConfigIn
from app.services.apply.collector import Collector
from app.services.sites.base import (
    ApplyOutcome,
    CollectQuery,
    FilterResolution,
    RiskProfile,
    SearchPage,
    SearchResult,
    SiteAdapter,
    SiteFailure,
)


class _FakeClock:
    """每次读表都大步前进，让限速循环立即结束（离线测试不真等）。"""

    def __init__(self) -> None:
        self._t = 0.0

    def __call__(self) -> float:
        self._t += 100.0
        return self._t


def _card(index: int, *, valid: int = 1) -> dict:
    return {
        "encryptJobId": f"jobid{index:04d}00000000000000000000",
        "securityId": f"sec{index}",
        "jobName": f"感兴趣岗位{index}",
        "salaryDesc": "10-15K",
        "jobExperience": "1-3年",
        "jobDegree": "本科",
        "cityName": "广州",
        "areaDistrict": "天河区",
        "unifyLocationDetail": "广州·天河区",
        "brandName": f"公司{index}",
        "jobValidStatus": valid,
    }


def _interest_payload(page: int, jobs: list[dict], *, has_more: bool, total: int) -> dict:
    return {
        "code": 0,
        "message": "Success",
        "zpData": {"cardList": jobs, "hasMore": has_more, "page": page, "totalCount": total},
    }


class _ScriptedClient:
    """geekGetJob 的页面内 fetch 脚本按 page 参数应答；其它 evaluate（就绪探针）回"已就绪"。"""

    def __init__(self, pages: dict[int, dict]) -> None:
        self._pages = pages
        self.requested_pages: list[int] = []
        self.navigated: list[str] = []

    def evaluate(self, expression: str, *, timeout: float | None = None) -> str:
        if "geekGetJob" in expression:
            match = re.search(r"[?&]page=(\d+)", expression)
            page = int(match.group(1)) if match else 1
            self.requested_pages.append(page)
            payload = self._pages.get(page) or {
                "code": 0,
                "zpData": {"cardList": [], "hasMore": False, "totalCount": 0},
            }
            return json.dumps(payload, ensure_ascii=False)
        return json.dumps({"matched": 1})

    def navigate(self, url: str, *, timeout: float | None = None) -> dict:
        self.navigated.append(url)
        return {}


class _InterestAdapter(SiteAdapter):
    key = "fake"
    display_name = "示例站点"
    hosts = ("example.com",)

    def __init__(self, pages: list[SearchPage] | None = None) -> None:
        self._pages = pages or []
        self.opened = 0
        self.filter_calls = 0
        self.searched_pages: list[int] = []

    def risk_profile(self) -> RiskProfile:
        return RiskProfile(key=self.key)

    def collect_search(self, client, query: CollectQuery, page: int) -> SearchPage:
        self.searched_pages.append(page)
        if self._pages:
            return self._pages[min(page - 1, len(self._pages) - 1)]
        return SearchPage(page=page, has_next=False)

    def open_apply(self, client, job):  # pragma: no cover - 采集不用
        raise AssertionError("采集不应调用投递")

    def fill_and_submit(self, client, data, greeting) -> ApplyOutcome:  # pragma: no cover
        raise AssertionError("采集不应调用投递")

    def fetch_job_detail(self, client, url):  # type: ignore[override]
        return {"description": f"岗位详情正文（{url}）", "requirements": "任职要求正文"}

    def prepare_collect_filters(
        self, selected, client=None
    ) -> FilterResolution:  # type: ignore[override]
        self.filter_calls += 1
        return FilterResolution()

    def open_interest_page(self, client) -> None:
        self.opened += 1


class _PlainAdapter(_InterestAdapter):
    """没有「感兴趣」能力的适配器（用户把来源切成 interest 但站点不是 BOSS 的形态）。"""

    open_interest_page = None  # type: ignore[assignment]


def _task(db_session) -> ApplyTask:
    task = ApplyTask(kind=TASK_KIND_COLLECT, status="running", total=20, config={})
    db_session.add(task)
    db_session.commit()
    return task


def _config(**overrides) -> CollectConfigIn:
    data = {
        "keywords": [],
        "per_task_limit": 50,
        "interval_seconds": 1,
        "interval_jitter_seconds": 0,
    }
    data.update(overrides)
    return CollectConfigIn(**data)


def _run(db_session, task, client, adapter, config):
    return Collector().run(
        session=db_session,
        task=task,
        client=client,
        adapter=adapter,
        config=config,
        checkpoint=lambda: None,
        sleeper=lambda _seconds: None,
        clock=_FakeClock(),
    )


def test_run_dispatches_to_interest_when_source_is_interest(db_session):
    client = _ScriptedClient(
        {1: _interest_payload(1, [_card(1), _card(2)], has_more=False, total=2)}
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    report = _run(db_session, task, client, adapter, _config(source="interest"))

    assert adapter.opened == 1
    assert adapter.searched_pages == []  # 关键词路径没走
    assert client.requested_pages == [1]
    assert report.collected == 2
    assert report.pages == 1

    staged = db_session.query(CandidateJob).order_by(CandidateJob.id).all()
    assert [item.title for item in staged] == ["感兴趣岗位1", "感兴趣岗位2"]
    assert staged[0].company == "公司1"
    assert staged[0].source_url == (
        f"https://www.zhipin.com/job_detail/{_card(1)['encryptJobId']}.html"
    )
    # 详情全抓：JD 完整落暂存区
    assert staged[0].description == (
        f"岗位详情正文（https://www.zhipin.com/job_detail/{_card(1)['encryptJobId']}.html）"
    )
    assert staged[0].requirements == "任职要求正文"
    # 采集不写岗位广场（两段式链路：先暂存，用户勾选后才导入）
    assert db_session.query(Job).count() == 0
    assert task.processed == 2 and task.succeeded == 2


def test_interest_mode_skips_station_filters(db_session):
    """个人列表没有筛选维度：绝不能为它去读一次站点筛选清单。"""
    client = _ScriptedClient(
        {1: _interest_payload(1, [_card(1)], has_more=False, total=1)}
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    _run(db_session, task, client, adapter, _config(source="interest"))

    assert adapter.filter_calls == 0


def test_interest_mode_stops_when_has_more_false(db_session):
    client = _ScriptedClient(
        {
            1: _interest_payload(1, [_card(1), _card(2)], has_more=False, total=2),
            2: _interest_payload(2, [_card(3)], has_more=False, total=3),
        }
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    report = _run(
        db_session, task, client, adapter, _config(source="interest", interest_max_pages=3)
    )

    # 第 1 页 hasMore=false → 只读 1 页，绝不翻第 2 页
    assert client.requested_pages == [1]
    assert report.pages == 1
    assert report.collected == 2


def test_interest_mode_dedupes_by_url_across_pages(db_session):
    client = _ScriptedClient(
        {
            1: _interest_payload(1, [_card(1), _card(2)], has_more=True, total=3),
            2: _interest_payload(2, [_card(2), _card(3)], has_more=False, total=3),
        }
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    report = _run(db_session, task, client, adapter, _config(source="interest"))

    assert client.requested_pages == [1, 2]
    assert report.collected == 3
    assert report.skipped == 1
    titles = {item.title for item in db_session.query(CandidateJob).all()}
    assert titles == {"感兴趣岗位1", "感兴趣岗位2", "感兴趣岗位3"}


def test_interest_mode_respects_per_task_limit(db_session):
    client = _ScriptedClient(
        {
            1: _interest_payload(
                1, [_card(1), _card(2), _card(3)], has_more=True, total=6
            ),
            2: _interest_payload(
                2, [_card(4), _card(5), _card(6)], has_more=False, total=6
            ),
        }
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    report = _run(db_session, task, client, adapter, _config(source="interest", per_task_limit=4))

    assert report.collected == 4
    assert db_session.query(CandidateJob).count() == 4
    # 上限在第 2 页内满足：第 2 页只取到需要的条数
    assert client.requested_pages == [1, 2]


def test_interest_mode_counts_invalid_cards(db_session):
    client = _ScriptedClient(
        {
            1: _interest_payload(
                1, [_card(1), _card(2, valid=0), _card(3)], has_more=False, total=3
            )
        }
    )
    adapter = _InterestAdapter()
    task = _task(db_session)

    report = _run(db_session, task, client, adapter, _config(source="interest"))

    assert report.collected == 2
    assert report.interest_invalid == 1
    # 账目进 task.config，界面据此显示"已跳过 N 条失效岗位"
    assert task.config["interest_invalid"] == 1


def test_interest_mode_requires_adapter_support(db_session):
    client = _ScriptedClient({})
    adapter = _PlainAdapter()
    task = _task(db_session)

    with pytest.raises(SiteFailure) as excinfo:
        _run(db_session, task, client, adapter, _config(source="interest"))

    assert "感兴趣" in excinfo.value.detail


def test_search_mode_unchanged(db_session):
    """回归守门：source=search（默认）时行为与搬迁前一致。"""
    pages = [
        SearchPage(
            results=[
                SearchResult(title="后端开发", company="A公司", url="https://example.com/1"),
                SearchResult(title="数据开发", company="B公司", url="https://example.com/2"),
            ],
            page=1,
            has_next=True,
        ),
        SearchPage(
            results=[SearchResult(title="算法工程", company="C公司", url="https://example.com/3")],
            page=2,
            has_next=False,
        ),
    ]
    client = _ScriptedClient({})
    adapter = _InterestAdapter(pages)
    task = _task(db_session)

    report = _run(
        db_session, task, client, adapter, _config(keywords=["后端"], city="北京")
    )

    assert adapter.searched_pages == [1, 2]
    assert adapter.opened == 0  # 搜索模式不开「感兴趣」页
    assert adapter.filter_calls == 1  # 搜索模式照常解析站点筛选
    assert client.requested_pages == []
    assert report.collected == 3
    titles = [item.title for item in db_session.query(CandidateJob).order_by(CandidateJob.id)]
    assert titles == ["后端开发", "数据开发", "算法工程"]
