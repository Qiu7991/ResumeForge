# SPDX-License-Identifier: Apache-2.0
"""BOSS直聘采集适配器（结构实证自 docs/job-hunt-fixtures/boss_list.html / boss_detail.html）。

列表页（Vue，每张卡包在 ``li.job-card-box`` 里）：
- 标题与链接：``<a class="job-name" href="/job_detail/{id}.html">标题</a>``
  —— **相对路径**，要补成 ``https://www.zhipin.com`` 绝对地址；
- 薪资：``<span class="job-salary">`` 内是**字体编码的乱码**（PUA 码点 U+E031..U+E03A），
  必须经 ``boss_font.decode_salary`` 还原；本适配器的 ``parse_list`` 只保留原文
  （``salary_raw``），解码在 ``parse_detail`` 里做——列表页拿不到字体文件，
  解码映射要靠详情页的明文对照或真实字体建立；
- 公司：``<span class="boss-name">``；地区：``<span class="company-location">``；
- 标签：``<ul class="tag-list"><li>1-3年</li><li>学历不限</li></ul>``。

详情页：
- 标题：``<h1 title="..">``；薪资：``<span class="salary">`` 这里是**明文**（如 ``8-12K``），
  可作列表页乱码的 ground-truth 对照；
- 公司：``.company-info`` 区（``a[href*="/gongsi/"]`` 或 ``.company-name``）；
- JD：``<div class="job-sec-text">`` 内是正文（``<br>`` 分条），末尾常有「（任职要求）」。

**为什么 BOSS 的列表解析要单独写**：``services/sites/boss_search.py`` 那套是给投递台
采集用的（带 CDP 点击与滚动、返回 SearchResult），接口不是 ``JobSiteAdapter``。
这里只做「HTML 文本 → JobStub」的纯解析，不碰浏览器。
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote

from ...sites.boss_text import normalize_text
from ..base import HuntCriteria, JobDetail, JobParseError, JobSiteAdapter, JobStub
from . import boss_font

logger = logging.getLogger(__name__)

_BASE = "https://www.zhipin.com"

# 一张卡 = 一个 li.job-card-box（整页 15 张，实测）。
# 注意：卡片内部还有嵌套的 <ul class="tag-list"><li>，所以不能用
# ``<li ...>...</li>`` 做正则（会被第一个内层 </li> 提前截断）。
# 改为按「卡片起点」切段：每张卡取到下一张卡起点为止。
_CARD_START_RE = re.compile(r'<li[^>]*class="job-card-box"[^>]*>')
_TITLE_LINK_RE = re.compile(
    r'<a[^>]*class="job-name"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>'
)
# 少数版本把 href 放在 class 之前。
_TITLE_LINK_RE_ALT = re.compile(
    r'<a[^>]*href="([^"]+)"[^>]*class="job-name"[^>]*>([^<]+)</a>'
)
_SALARY_RE = re.compile(r'<span[^>]*class="job-salary"[^>]*>(.*?)</span>', re.S)
_COMPANY_RE = re.compile(r'<span[^>]*class="boss-name"[^>]*>([^<]{1,60})</span>')
_LOCATION_RE = re.compile(r'<span[^>]*class="company-location"[^>]*>(.*?)</span>', re.S)
_TAGS_RE = re.compile(r'<ul[^>]*class="tag-list"[^>]*>(.*?)</ul>', re.S)
_TAG_ITEM_RE = re.compile(r"<li[^>]*>([^<]{1,20})</li>")

# 搜索筛选参数的**固定顺序**（与 BossHunter 验证过的拼法一致）。
# 站点本身对顺序不敏感，但固定顺序让 URL 可断言、排查时能逐字符 diff。
_FILTER_PARAM_ORDER: tuple[str, ...] = (
    "jobType",
    "experience",
    "degree",
    "scale",
    "salary",
    "industry",
)

# 详情页
_D_TITLE_RE = re.compile(r'<h1[^>]*title="([^"]+)"')
_D_SALARY_RE = re.compile(r'<span[^>]*class="salary"[^>]*>\s*([^<]+?)\s*</span>')
# **工商全名**：详情页「工商信息」区块里的公司名称，是页面上唯一的工商全称。
#
# 它是首选来源。列表页给的是品牌展示名（``示例传媒``）或 BOSS 自己截断的串
# （``广州市示例国际贸...``），而「工商信息」里是 ``广州示例传媒科技有限公司``。
# 夹具实证：``boss_detail.html:824``
#   <li class="company-name"><span>公司名称</span>示例网络科技（广州）有限公司</li>
#
# 用 ``business-info-box`` 定位再取其中的 ``li.company-name``：裸 ``company-name``
# 会同时命中相似职位卡片（``boss_detail.html:664`` → 广州另一家公司），拿错公司比拿不到更糟。
_D_BUSINESS_NAME_RE = re.compile(
    r'class="[^"]*business-info-box[^"]*"[\s\S]{0,4000}?'
    r'<li[^>]*class="[^"]*company-name[^"]*"[^>]*>\s*'
    r'(?:<span>[^<]*</span>)?\s*([^<]{2,80}?)\s*</li>'
)

# 侧栏公司（短名）作为兜底。**限定在 ``sider-company`` 作用域内**：
# 裸 ``a[href*="/gongsi/"]`` 会命中顶部导航「公司」菜单（``boss_detail.html:461``），
# 实测解析结果变成 company == "公司"。
_D_COMPANY_RE = re.compile(
    r'class="[^"]*sider-company[^"]*"[\s\S]{0,1200}?'
    r'<a[^>]*href="[^"]*/gongsi/[^"]*"[^>]*>\s*([^<]{2,60}?)\s*</a>'
)
_D_COMPANY_FALLBACK_RE = re.compile(
    r'class="[^"]*sider-company[^"]*"[\s\S]{0,1200}?'
    r'class="[^"]*company-name[^"]*"[^>]*>\s*([^<]{2,60}?)\s*<'
)
# 正文容器的**开标签**。闭合位置不能用非贪婪 ``(.*?)</div>`` 去找：JD 正文里常带
# 嵌套 div（分组小标题、折叠块），那样会在第一个内层 ``</div>`` 处截断，解析出的
# JD 只剩开头一段——2026-11-11 实测 266 号岗位就是这样只剩 70 字
# （"工作内容：1、利用AI编程工具…" 正好截在第一个内层 div 之前）。
# 所以先只匹配开标签，再用 ``_extract_div_inner`` 按深度配对找真正的闭合位置。
_D_SECTION_OPEN_RE = re.compile(r'<div[^>]*class="job-sec-text"[^>]*>', re.S)
_DIV_TAG_RE = re.compile(r"<div\b[^>]*>|</div\s*>", re.I)
# 经验/学历标签的判定。用正则而不是枚举：站点会加「仅限在校生」这类变体，
# 枚举一旦漏了就静默不识别。这两条只用于**本地二次筛选兜底**，认错也不会影响主路径。
_EXPERIENCE_TAG_RE = re.compile(r"^(经验不限|在校生|应届生|\d+[\-~]\d+年|\d+年以内|\d+年以上|\d+年)$")
_EDUCATION_TAG_RE = re.compile(r"^(学历不限|初中及以下|中专/中技|中专|中技|高中|大专|本科|硕士|博士|MBA/EMBA)$")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")


def _extract_div_inner(html: str, open_end: int) -> str:
    """从开标签结束处（``open_end``）按 div 深度配对，返回容器内部的 HTML。

    纯正则做不到这件事：``(.*?)</div>`` 遇到嵌套就提前收尾，而贪婪 ``(.*)</div>``
    又会把容器后面的整页内容都吞进来。只有数深度才知道哪个 ``</div>`` 属于本容器。

    深度不平衡（页面被截断、或标签本身不配对）时返回能取到的全部内容——宁可给
    一段可能不完整的正文，也不要因为一个残缺标签把整条 JD 丢掉。
    """
    depth = 1
    for match in _DIV_TAG_RE.finditer(html, open_end):
        if match.group(0).lower().startswith("</div"):
            depth -= 1
            if depth == 0:
                return html[open_end : match.start()]
        else:
            depth += 1
    return html[open_end:]


# 滚动加载用到的三个 DOM 脚本。与 ``services/sites/boss_search_scripts`` 同源思路，
# 但这里是**独立实现**：那边返回结构化抽取结果，这边只要"滚一下 + 数卡片"，
# 抽取仍走本模块的 `parse_list`（正则），两套口径不能混。

_CARD_COUNT_JS = """(() => {
  return document.querySelectorAll('li.job-card-box, .job-card-wrapper, .job-card-box').length;
})()"""

_SCROLL_JS = """(() => {
  const card = document.querySelector('li.job-card-box, .job-card-wrapper, .job-card-box');
  let el = card ? card.parentElement : null;
  let scrolled = '';
  while (el && el !== document.body) {
    if (el.scrollHeight > el.clientHeight + 4) {
      el.scrollTop = el.scrollHeight;
      scrolled = 'container';
      break;
    }
    el = el.parentElement;
  }
  if (!scrolled) { window.scrollTo(0, document.body.scrollHeight); scrolled = 'window'; }
  return scrolled;
})()"""


def _card_count(client: Any) -> int | None:
    """当前搜索页上的岗位卡片数量；读不到返回 None。"""
    try:
        value = client.evaluate(_CARD_COUNT_JS)
    except Exception:  # noqa: BLE001 — 读不到就当没有更多
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _scroll_list(client: Any) -> None:
    """把岗位列表滚到底部，触发站点的「下滑加载更多」。"""
    try:
        client.evaluate(_SCROLL_JS)
    except Exception:  # noqa: BLE001 — 滚动失败由下一步的数量检查兜底
        logger.info("BOSS 滚动列表失败", exc_info=True)


def _wait_card_growth(
    client: Any, baseline: int, *, timeout: float = 12.0, poll: float = 0.4
) -> bool:
    """滚动后等新卡片渲染：数量超过基线即成功；预算用完仍没长 → 到底了。

    12 秒是保守值：BOSS 的"加载更多"是一次 XHR + 渲染，弱网下也在几秒内完成。
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = _card_count(client)
        if count is not None and count > baseline:
            return True
        time.sleep(poll)
    return False


def _clean(fragment: str) -> str:
    """把 HTML 片段折成纯文本：<br> 变换行、去标签，再做文本还原。

    文本还原交给 ``services.sites.boss_text.normalize_text``——**不要在这里自己写一份**。
    它已经处理了 BOSS 反爬的三件事，而且三者是同时出现在同一段正文里的（2026-11-11 实测）：

    1. **康熙部首**（U+2F00–U+2FDF）：正文里是 ⽤/⼈/⼯/⼒/⾔ 而不是 用/人/工/力/言，
       字形几乎一样但码位不同，关键词匹配与评分会全部漏掉（「能⼒」搜「能力」搜不到）。
    2. **私用区数字**（U+E030–E039）：薪资里的数字被换成 PUA 字符。
    3. **水印**：「岗kanzhun位职责」「来自BOSS直聘实现基于LLM…」——水印被**插进词中间**，
       不处理会把正文读成断句。实测 177 条采集中 24 条带水印。

    它只对反爬用到的几个区做 NFKC，**不做全量**——全量会把全角标点（：（））折成半角，
    而中文 JD 的标点本来就该是全角。这个取舍在那边已经写清楚了，这里直接复用。
    """
    text = _BR_RE.sub("\n", fragment)
    text = _TAG_STRIP_RE.sub("", text)
    return normalize_text(text)


def _clean_salary(fragment: str) -> str:
    """薪资单元格的清理：只去标签、压空白，**保留私用区数字原文**。

    薪资不能走 ``_clean``：``normalize_text`` 会把 PUA 数字（U+E030–U+E039）折成
    普通数字，而列表页的 ``salary_raw`` 必须保持编码原文——字体解密要靠它比对，
    折掉之后 ``encoded_chars_in()`` 就认不出这是密文，也就无从解密了
    （实测：折过之后列表薪资直接变成 "9-23K"，父子对照建不出映射）。

    水印不在这里处理：水印规则要求 token 紧贴汉字，薪资是数字串，天然不命中。
    """
    text = _BR_RE.sub(" ", fragment)
    text = _TAG_STRIP_RE.sub("", text)
    return text.replace("\u00a0", " ").strip()


def _abs(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if raw.startswith("http"):
        return raw
    if raw.startswith("/"):
        return _BASE + raw
    return f"{_BASE}/{raw}"


class BossAdapter(JobSiteAdapter):
    key = "boss"
    name = "BOSS直聘"

    def build_search_url(self, criteria: HuntCriteria, page: int = 1) -> str:
        """``zhipin.com/web/geek/job?query=..&city=..&<筛选>..&sortType=2&page=n``。

        参数顺序与 BossHunter 验证过的一致（``collection/platforms/boss.py:563-567``）：

            query → city → jobType → experience → degree → scale → salary → industry
                  → sortType → page

        **四个容易拼错的点**（都是实测踩过的）：

        1. 路径是 ``/web/geek/job``（**单数**）。曾经写成 ``jobs``，站点不报错但返回的不是
           搜索结果——那种"看起来成功"的错最难查。
        2. 参数名是 ``query``，不是 ``keyword``。
        3. 多值筛选是**单个参数 + 逗号**（``experience=102,103,104``），不是重复 key。
        4. ``sortType=2`` 只在「最新优先」时出现；默认排序下**完全不出现**该参数。

        ``city`` 支持两种写法：纯数字按 city 码传；城市名走 ``cityName``（站点会重定向
        到对应 city 码）——后者只是兜底，正式入口应传 city_code。

        筛选与排序从 ``criteria.extra`` 读（``filters`` / ``sort``），编码由调用方
        按 ``services/sites/boss_filters_catalog`` 的已验证快照解析好。
        """
        params: list[str] = []
        kw = (criteria.keywords or "").strip()
        if kw:
            params.append(f"query={quote(kw)}")
        city = (criteria.city or "").strip()
        if city:
            if city.isdigit():
                params.append(f"city={city}")
            else:
                # 城市名兜底：站点会重定向到 city 码。生产路径应传 city_code（见上）。
                params.append(f"cityName={quote(city)}")

        extra = criteria.extra or {}

        # 筛选：{参数名: "编码,编码"}，编码已在调用方校验过。**顺序固定**——
        # 站点对参数顺序不敏感，但固定的顺序让 URL 可断言、可对比（排查时能逐字符 diff）。
        filters = extra.get("filters")
        if isinstance(filters, dict):
            for name in _FILTER_PARAM_ORDER:
                value = filters.get(name)
                if not value:
                    continue
                # 逗号也编码成 %2C（与 BossHunter 的实测形态一致）。裸逗号站点也认，
                # 但统一成编码形态让 URL 可与参考实现逐字符比对。
                encoded = quote(str(value), safe="")
                params.append(f"{quote(str(name), safe='')}={encoded}")

        # 最新优先：只有显式要 newest 才加。默认排序不带这个参数。
        if (extra.get("sort") or "") == "newest":
            params.append("sortType=2")

        if page and int(page) > 1:
            params.append(f"page={int(page)}")
        return f"{_BASE}/web/geek/job?" + "&".join(params)

    def parse_list(self, html: str) -> list[JobStub]:
        starts = list(_CARD_START_RE.finditer(html))
        if not starts:
            raise JobParseError(
                "页面里没有岗位卡片（li.job-card-box 缺失：可能未登录或被风控拦截）",
                site_key=self.key,
            )
        stubs: list[JobStub] = []
        for i, match in enumerate(starts):
            begin = match.end()
            end = starts[i + 1].start() if i + 1 < len(starts) else len(html)
            card = html[begin:end]
            link_m = _TITLE_LINK_RE.search(card) or _TITLE_LINK_RE_ALT.search(card)
            if link_m is None:
                continue
            url, title = _abs(link_m.group(1)), _clean(link_m.group(2))
            if not title:
                continue
            salary_m = _SALARY_RE.search(card)
            company_m = _COMPANY_RE.search(card)
            loc_m = _LOCATION_RE.search(card)
            tags_m = _TAGS_RE.search(card)
            tags = _TAG_ITEM_RE.findall(tags_m.group(1)) if tags_m else []
            location = _clean(loc_m.group(1)) if loc_m else ""
            if not location and tags:
                # 标签里有时混着地区/经验，地区优先取含「·」的那条
                location = next((t for t in tags if "·" in t), "")
            # 经验/学历标签（"1-3年" "本科"）：标签里本来就是有的，之前只用来兜底地区、
            # 其余丢弃。留着做采集后的本地二次筛选（站点侧参数是主路径，这是兜底）。
            experience = next((tag for tag in tags if _EXPERIENCE_TAG_RE.match(tag)), "")
            education = next((tag for tag in tags if _EDUCATION_TAG_RE.match(tag)), "")
            salary_raw = _clean_salary(salary_m.group(1)) if salary_m else ""
            # 列表页直接给出解码结果：字体映射已实证收敛（见 boss_font.BOSS_TTF_MAP），
            # 不必等详情页的明文对照。解不完整时 decode_salary 会保持 ok=False。
            decoded = boss_font.decode_salary(salary_raw, boss_font.default_mapping())
            stubs.append(
                JobStub(
                    title=title,
                    company=_clean(company_m.group(1)) if company_m else "",
                    location=location,
                    salary_raw=salary_raw,
                    salary_decoded=decoded.text,
                    salary_decoded_ok=decoded.ok,
                    url=url,
                    experience=experience,
                    education=education,
                )
            )
        if not stubs:
            raise JobParseError("岗位卡片存在但没有一张能解析出标题与链接", site_key=self.key)
        return stubs

    def parse_detail(self, html: str) -> JobDetail:
        title_m = _D_TITLE_RE.search(html)
        section_m = _D_SECTION_OPEN_RE.search(html)
        if title_m is None and section_m is None:
            raise JobParseError(
                "详情页缺标题与 JD 正文（可能未登录、岗位已下线或结构改版）",
                site_key=self.key,
            )

        title = _clean(title_m.group(1)) if title_m else ""
        description = (
            _clean(_extract_div_inner(html, section_m.end())) if section_m else ""
        )

        salary_m = _D_SALARY_RE.search(html)
        salary_text = _clean_salary(salary_m.group(1)) if salary_m else ""

        # 公司名三级优先：工商全名 → 侧栏短名 → 侧栏 company-name。
        # 工商全名最完整，而且它是风鸟查询需要的那个名字（见前端 riskbirdUrl）。
        business_m = _D_BUSINESS_NAME_RE.search(html)
        if business_m is not None:
            company = _clean(business_m.group(1))
        else:
            company_m = _D_COMPANY_RE.search(html) or _D_COMPANY_FALLBACK_RE.search(html)
            company = _clean(company_m.group(1)) if company_m else ""

        # 详情页薪资是明文：能直接当 ground-truth，不需要字体解密。
        decoded_ok = bool(salary_text) and not boss_font.encoded_chars_in(salary_text)
        if not decoded_ok and salary_text:
            # 少数情况下详情页也给的是编码文本：这里没有字体映射，如实标记未还原。
            salary_text_out = salary_text
        else:
            salary_text_out = salary_text

        return JobDetail(
            title=title,
            company=company,
            location=_detail_location(html),
            salary_raw=salary_text,
            url="",
            description=description,
            requirements="",
            salary_decoded=salary_text_out,
            salary_decoded_ok=decoded_ok,
        )

    def supports(self, url: str) -> bool:
        return "zhipin.com" in (url or "")

    def content_ready_selector(self) -> str:
        """列表页内容就绪判据：岗位卡片出现。

        实测：BOSS 搜索页 ``readyState=complete`` 时搜索结果尚未渲染（Vue 异步），
        直接取 outerHTML 会拿到空壳；等这个选择器命中再取才稳定。
        """
        return "li.job-card-box"

    def detail_ready_selector(self) -> str:
        """详情页内容就绪判据：JD 正文容器出现。

        用 ``.job-sec-text`` 而不是整页就绪：实测详情页的职位描述也是异步填充的，
        ``readyState=complete`` 时取到的正文可能只有开头一段（或干脆是标签列表）。
        这个类名在真实夹具里出现两次——一次是职位描述、一次是公司介绍
        （``fold-text``）——任一命中都说明正文区已经渲染，可以取了。
        """
        return ".job-sec-text"

    def fetch_page(self, client: Any, url: str, page: int, *, fetch: Any) -> str:
        """BOSS 专用翻页：第 1 页导航，第 2 页起**滚动加载**。

        为什么不能每页都导航（2026-10-09 实测，两处独立验证）：
        ``services/sites/boss_search.py`` 与 BossHunter 都记录同一个结论——BOSS 搜索页
        **不吃 URL 的 page 参数**，换 page 值导航返回的永远是同一批推荐位。站点靠
        「向下滑动列表」加载更多。

        这正是「每轮只采到十几条、再采就全是重复」的根因：我们一直在逐页导航，
        第 2 页拿到的还是第 1 页的内容，全部被去重挡掉。

        实现刻意简单：用页面**已解析出的卡片数**做基线，滚动后等数量增长，然后直接取
        ``outerHTML`` 交给既有的 ``parse_list``。不迁 ``services/sites`` 那套结构化抽取
        ——那会引入第二套卡片解析口径，和本适配器的正则解析分叉。
        """
        if page <= 1:
            return fetch(url)

        baseline = _card_count(client)
        if baseline is None:
            # 读不到卡片数：页面可能不在搜索页。按「没有更多」处理，交给 runner 干净收尾
            # ——报错反而会把已经采到的也拖成整批失败。
            logger.info("BOSS 滚动翻页：读不到卡片数，按没有更多处理")
            return ""

        _scroll_list(client)
        if not _wait_card_growth(client, baseline):
            # 滚到底仍没有新卡片 → 到底了。返回空 HTML，parse_list 会抛"没有卡片"，
            # runner 按 no_results 收尾（与翻满 max_pages 同一种正常结束）。
            logger.info("BOSS 滚动翻页：滚动后没有新卡片，已到底")
            return ""

        html = client.evaluate("document.documentElement.outerHTML")
        return html if isinstance(html, str) else ""

    def max_pages(self) -> int:
        # BOSS 列表页实测一页 15 条；翻页上限按 10 页保守设。
        return 10


def _detail_location(html: str) -> str:
    """详情页地区：``.location``/``.job-area`` 一类的短文本。"""
    m = re.search(r'class="[^"]*(?:location|job-area|text-city)[^"]*"[^>]*>\s*([^<]{1,40}?)\s*<', html)
    return _clean(m.group(1)) if m else ""


__all__ = ["BossAdapter"]
