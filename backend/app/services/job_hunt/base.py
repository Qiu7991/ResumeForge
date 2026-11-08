# SPDX-License-Identifier: Apache-2.0
"""自研求职采集的平台适配器抽象：统一「搜什么 / 怎么解析」的接口。

分工与 ``services/sites/`` 的思路一致：**通用层**（``runner.py``）负责翻页、去重、
进度与断点，平台无关；**平台适配器**只做「这个站点特有的事」——拼搜索 URL、从列表页
HTML 抠出岗位卡片、从详情页抠出 JD。

解析输入一律是**本地 HTML 夹具或页面快照的文本**（夜间无登录态，测试不连真实网站）。
解析失败抛 ``JobParseError``，携带可展示的中文诊断；缺字段返回空串而不是 None，让上层
不用到处判空。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class JobParseError(Exception):
    """一次解析失败：``detail`` 是可直接展示的中文诊断（页面改版 / 结构不符）。"""

    def __init__(self, detail: str, *, site_key: str = "") -> None:
        super().__init__(detail)
        self.detail = detail
        self.site_key = site_key


@dataclass
class JobStub:
    """列表页抠出的岗位卡片（够入队、够展示，详情字段留空）。"""

    title: str = ""
    company: str = ""
    location: str = ""
    # 站点原样薪资文本（BOSS 是字体编码的乱码，还原见 sites/boss_font.py）。
    salary_raw: str = ""
    # 还原后的薪资。列表页就能给出（BOSS 有已知字体映射），不必等详情页；
    # 无法还原时与 salary_raw 相同、decoded_ok 为 False。
    salary_decoded: str = ""
    salary_decoded_ok: bool = False
    url: str = ""
    # 发布时间原文（"昨天"、"3 天前" 等）；解析不出就空串。
    posted_at: str = ""


@dataclass
class JobDetail(JobStub):
    """详情页抠出的完整岗位（列表字段 + JD 正文 + 解码后的薪资）。"""

    description: str = ""
    # 岗位要求（部分站点的 JD 分「职责 / 要求」两段；不分就与 description 相同）。
    requirements: str = ""
    # 还原后的薪资（如 "8-12K·14薪"）；无法还原时与 salary_raw 相同。
    salary_decoded: str = ""
    # 薪资是否完成了字体/编码还原；False 表示 salary_decoded 只是原文兜底。
    salary_decoded_ok: bool = False


@dataclass
class HuntCriteria:
    """一次采集的搜索条件。字段是各平台搜索 URL 的**公共交集**，放不下的平台特有
    条件由适配器自行从 ``extra`` 取。"""

    keywords: str = ""
    city: str = ""
    page_size: int = 0  # 0 = 用平台默认
    extra: dict = field(default_factory=dict)


class JobSiteAdapter(ABC):
    """平台适配器接口。加一个平台 = 加一个子类 + 注册一行，通用层一行不改。"""

    # 站点标识（'boss' | 'zhilian' | 'job51' | 'liepin'）与显示名，子类必填。
    key: str = ""
    name: str = ""

    @abstractmethod
    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        """把搜索条件 + 页码拼成该平台的搜索 URL（只拼 URL，不发请求）。"""

    @abstractmethod
    def parse_list(self, html: str) -> list[JobStub]:
        """从搜索结果页 HTML 抠出岗位卡片列表；一个都抠不出时抛 ``JobParseError``。"""

    @abstractmethod
    def parse_detail(self, html: str) -> JobDetail:
        """从岗位详情页 HTML 抠出完整 JD；结构不符时抛 ``JobParseError``。"""

    @abstractmethod
    def supports(self, url: str) -> bool:
        """该 URL 是否属于本平台（按主机名判断，供注册表分发）。"""

    def max_pages(self) -> int:
        """该平台允许抓的最大页数（防呆上限；子类可覆盖）。"""
        return 10


__all__ = ["JobSiteAdapter", "JobStub", "JobDetail", "HuntCriteria", "JobParseError"]
