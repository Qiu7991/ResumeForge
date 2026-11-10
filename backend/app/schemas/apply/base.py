# SPDX-License-Identifier: Apache-2.0
"""共享常量、Literal 类型别名与校验辅助（``schemas/apply`` 各子模块的公共底座）。

从 ``schemas/apply.py`` 拆出：出厂默认常量、状态字符串（与 ``models/apply`` 逐字一致）、
``default_site_key``（延迟导入注册表解环，原样保留）与失败分类校验。
"""
from typing import Literal

from ...config import DEFAULT_BROWSER_PORT as DEFAULT_BROWSER_PORT
from ...models.apply import FAILURE_CATEGORIES

# ===== 配置默认值（出厂默认，键与 app_setting 一致）=====
DEFAULT_INTERVAL_SECONDS = 25
DEFAULT_INTERVAL_JITTER_SECONDS = 8
DEFAULT_DAILY_LIMIT = 60
DEFAULT_PER_TASK_LIMIT = 20
DEFAULT_BREAKER_THRESHOLD = 3
DEFAULT_GREETING = "您好，我对该岗位很感兴趣，期待进一步沟通。"

#: 出厂默认的「打招呼语写作基准」（2026-11-10）。
#:
#: 为什么给出厂默认：这套写法是实测有效的（第 1 句跟着岗位职责走、AI 工具定位放第 4 句、
#: 项目按 JD 相关度选），但原本只存在于作者的本地数据库里——别人装上项目后拿到的是**空基准**，
#: 效果完全不同。写进代码让"用这个项目的人"开箱就是同一套写法。
#:
#: 刻意**不写具体项目名**：作者的原版里点名了 CreatorDistill / PixelBeads / ESP-SparkBot，
#: 那是"该挑哪类项目"的例子，只对作者自己的简历成立。这里改写成**按类别描述**——
#: 别人装上后模型会用他自己的项目，但判断逻辑与作者一致。
#:
#: 用户仍可在设置里整段覆盖（这个默认值只在用户没填时生效）。
DEFAULT_GREETING_BASELINE = """【写作定位】招呼语不是自我介绍，是让 HR 在几十条消息里愿意点开你。
写的时候：
1. 第 1 句按这份岗位的具体职责写，不要每条都用同一句。测试/验证岗写验证与迭代，运营岗写内容或账号的全流程，交付/实施岗写从需求到落地，产品岗写需求梳理到上线，嵌入式岗写设备调试到量产。判断依据是 JD 里这份岗位到底要人干什么。
2. 第 3 句挑简历里**最能证明 JD 要的那件事**的项目：先提炼 JD 的核心能力词，再逐个过项目问"它能证明这件事吗"，按匹配度选第 1 名。不要选简历里排第一或篇幅最长的项目；如果 JD 要的是测试/验证，就挑有评测、回归、问题复现环节的项目，而不是话题沾边的项目。
3. 「用 AI 编程工具端到端交付」这类方法层面的定位放在第 4 句（方法与能力），不要放第 1 句——它挤掉的是更重要的岗位匹配信息，而且放在第 1 句会让 HR 看出是群发。
4. 不写学校、学历、届别；不照抄本段的任何公司名、项目名与数字，事实只能来自简历。"""

DEFAULT_COLLECT_KEYWORDS: list[str] = []
DEFAULT_COLLECT_PER_TASK_LIMIT = 20
DEFAULT_COLLECT_INTERVAL_SECONDS = 6
DEFAULT_COLLECT_INTERVAL_JITTER_SECONDS = 3

# 投递专用浏览器的选择方式与自定义路径长度上限。
DEFAULT_BROWSER_CHOICE = "auto"
BROWSER_PATH_MAX_CHARS = 512


def default_site_key() -> str:
    """当前站点的出厂默认值：注册表里第一个站点的标识。

    延迟导入注册表，避免"schemas ← services.sites ← ..."在导入期形成不必要的耦合；
    注册表本身缓存且轻量，这里按需取即可。取不到（注册表为空）时返回空串，由业务层兜底。
    """
    from ...services.sites.registry import get_registry

    try:
        return get_registry().default_key()
    except Exception:  # noqa: BLE001 - 默认值计算失败不该让配置模型无法实例化
        return ""

# 招呼语落库时的截断上限：记用户写给 HR 的全文，但不让单条无限增长。
GREETING_RECORD_MAX_CHARS = 500
GREETING_INPUT_MAX_CHARS = 1000

MAX_QUEUE_BATCH = 200
MAX_TASK_TARGETS = 500
MAX_COLLECT_KEYWORDS = 10
# 站点侧筛选项的规模上限。选项是站点提供的、数量有限（BOSS 一共 7 组），给一个宽松但
# 明确的上界挡住畸形请求体即可；真正"这个编码能不能用"由适配器在采集前逐个校验。
MAX_COLLECT_FILTERS = 16
COLLECT_FILTER_KEY_MAX_CHARS = 32
COLLECT_FILTER_CODE_MAX_CHARS = 32

# 「补齐详情」的单批上限。补详情要逐个打开岗位页面（详情页是整个采集里最慢的一步），几百条一批
# 会让一次任务跑很久、也更容易被风控盯上，所以超过就让用户分批。这个上限由**业务层**给出可操作的
# 中文说明；schema 这层只用一个更大的硬上限挡住明显异常的请求体——阈值若设成一样，友好提示会被
# 校验挡在外面，用户只会拿到一条 Pydantic 报错，看不到"要分批"的理由。
MAX_BACKFILL_JOBS = 200
MAX_BACKFILL_REQUEST_ITEMS = 1000

BrowserState = Literal["stopped", "starting", "running", "unknown"]
# 浏览器选择：auto=自动（优先 Chrome，未装回退 Edge）/ chrome / edge / custom=自定义路径。
BrowserChoice = Literal["auto", "chrome", "edge", "ego", "custom"]
QueueStatus = Literal["pending", "skipped", "done"]
TaskStatus = Literal[
    "pending",
    "running",
    "paused",
    "breaker_paused",
    "completed",
    "stopped",
    "failed",
]
TaskKind = Literal["collect", "apply"]
TaskItemStatus = Literal["pending", "running", "success", "failed", "skipped"]
FailureCategory = Literal[
    "selector_invalid",
    "login_required",
    "captcha_required",
    "greeting_missing",
    "greeting_unconfirmed",
    "network_timeout",
    "file_upload_failed",
    "site_unsupported",
    "profile_insufficient",
    "unconfirmed",
    "job_closed",
    "unknown",
]


def _check_failure_category(value: str) -> str:
    cleaned = (value or "").strip()
    if cleaned and cleaned not in FAILURE_CATEGORIES:
        raise ValueError(f"无效的失败分类，可选值：{'、'.join(FAILURE_CATEGORIES)}")
    return cleaned

