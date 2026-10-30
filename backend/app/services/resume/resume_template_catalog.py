"""Built-in resume template catalog and lookup helpers."""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
DEFAULT_TEMPLATE = "classic"
DEFAULT_PAGE_LIMIT = 1

# 模板分类：选择器与工作台按这个顺序分组展示。`category` 只影响展示分组，
# 不影响渲染与解析（模板仍按 name 查找）。新增模板时必须给 category，
# 否则它会落进「其他」分组。
CATEGORY_GENERAL = "通用"
CATEGORY_TECH = "技术研发"
CATEGORY_BACKEND = "后端开发"
CATEGORY_FRONTEND = "前端开发"
CATEGORY_MOBILE = "移动开发"
CATEGORY_SYSTEMS = "系统与底层"
CATEGORY_ARCHITECT = "架构与管理"

CATEGORY_ORDER: tuple[str, ...] = (
    CATEGORY_GENERAL,
    CATEGORY_TECH,
    CATEGORY_BACKEND,
    CATEGORY_FRONTEND,
    CATEGORY_MOBILE,
    CATEGORY_SYSTEMS,
    CATEGORY_ARCHITECT,
)

RESUME_TEMPLATES: dict[str, dict] = {
    "classic": {
        "name": "classic",
        "label": "经典",
        "category": CATEGORY_GENERAL,
        "file": "resume.html.j2",
        "description": "深蓝标题与左侧色条，稳重的通用款式",
    },
    "modern": {
        "name": "modern",
        "label": "现代",
        "category": CATEGORY_GENERAL,
        "file": "resume_modern.html.j2",
        "description": "青绿配色与圆角标签，适合互联网岗位",
    },
    "compact": {
        "name": "compact",
        "label": "精简",
        "category": CATEGORY_GENERAL,
        "file": "resume_compact.html.j2",
        "description": "细线分隔、排版紧凑，适合内容多、想压在一页",
    },
    "elegant": {
        "name": "elegant",
        "label": "优雅",
        "category": CATEGORY_GENERAL,
        "file": "resume_elegant.html.j2",
        "description": "居中标题与衬线字，留白舒展，适合文商科与管理岗位",
    },
    "technical": {
        "name": "technical",
        "label": "技术",
        "category": CATEGORY_TECH,
        "file": "resume_technical.html.j2",
        "description": "色块标题与等宽辅助信息，信息密度高，适合研发岗位",
    },
    "minimal": {
        "name": "minimal",
        "label": "极简",
        "category": CATEGORY_GENERAL,
        "file": "resume_minimal.html.j2",
        "description": "只用黑灰与字号层级，没有任何色块与装饰",
    },
    "editorial": {
        "name": "editorial",
        "label": "社论",
        "category": CATEGORY_GENERAL,
        "file": "resume_editorial.html.j2",
        "description": "衬线字体与细线分隔，适合文商科、内容与管理岗位",
    },
    "split": {
        "name": "split",
        "label": "分栏",
        "category": CATEGORY_GENERAL,
        "file": "resume_split.html.j2",
        "description": "正文双栏、信息密度高，适合经历与技能较多的简历",
    },
    # ===== ResumeSample 方向模板（源自 geekcompany/ResumeSample 的内容框架，
    # 重绘为简历通的样式模板：配色/标题形状/技能标签按各技术方向区分）=====
    "php": {
        "name": "php",
        "label": "PHP 后端",
        "category": CATEGORY_BACKEND,
        "file": "resume_php.html.j2",
        "description": "紫罗兰强调色与浅色块标题，适合 PHP / 后端开发岗位",
    },
    "java": {
        "name": "java",
        "label": "Java 开发",
        "category": CATEGORY_BACKEND,
        "file": "resume_java.html.j2",
        "description": "砖红强调色与左侧色条标题，稳重的企业级风格，适合 Java / 服务端岗位",
    },
    "node": {
        "name": "node",
        "label": "Node.js 开发",
        "category": CATEGORY_BACKEND,
        "file": "resume_node.html.j2",
        "description": "草绿强调色与下划线标题，等宽辅助信息，适合 Node.js / 全栈岗位",
    },
    "web": {
        "name": "web",
        "label": "Web 前端",
        "category": CATEGORY_FRONTEND,
        "file": "resume_web.html.j2",
        "description": "靛蓝强调色与左侧色条标题，清爽通用，适合 Web 前端 / 客户端岗位",
    },
    "ios": {
        "name": "ios",
        "label": "iOS 开发",
        "category": CATEGORY_MOBILE,
        "file": "resume_ios.html.j2",
        "description": "石墨灰极简风、留白舒展，纯文字技能清单，适合 iOS / 移动端岗位",
    },
    "android": {
        "name": "android",
        "label": "Android 开发",
        "category": CATEGORY_MOBILE,
        "file": "resume_android.html.j2",
        "description": "安卓绿实心色块标题与浅绿页头，适合 Android / 移动端岗位",
    },
    "cpp": {
        "name": "cpp",
        "label": "C/C++ 系统",
        "category": CATEGORY_SYSTEMS,
        "file": "resume_cpp.html.j2",
        "description": "钢青强调色、等宽辅助信息与实心色块标题，信息密度高，适合 C/C++ / 嵌入式 / 系统岗位",
    },
    "architect": {
        "name": "architect",
        "label": "架构师",
        "category": CATEGORY_ARCHITECT,
        "file": "resume_architect.html.j2",
        "description": "深紫强调色、居中衬线标题，稳重舒展，适合架构师与技术管理岗位",
    },
    "dev": {
        "name": "dev",
        "label": "通用技术",
        "category": CATEGORY_TECH,
        "file": "resume_dev.html.j2",
        "description": "中性蓝灰、浅色块标题，不挑方向的通用技术岗款式，适合转岗与技术通用投递",
    },
}


def template_spec(name: str) -> dict:
    return RESUME_TEMPLATES.get((name or "").strip()) or RESUME_TEMPLATES[DEFAULT_TEMPLATE]


def template_options() -> list[dict]:
    """列出可选样式模板（含分类，按 CATEGORY_ORDER 稳定排序）。"""
    return [
        {
            "name": item["name"],
            "label": item["label"],
            "category": item.get("category", ""),
            "description": item["description"],
        }
        for item in RESUME_TEMPLATES.values()
    ]


def template_options_with_custom(custom: list[dict]) -> list[dict]:
    """内置模板 + 用户自制模板（自制排在后面，用 ``custom`` 标记区分）。"""
    options = [
        {**item, "custom": False, "id": None} for item in template_options()
    ]
    for item in custom:
        options.append(
            {
                "name": item["name"],
                "id": item.get("id"),
                "label": item.get("label") or item["name"],
                "category": item.get("category", "自制"),
                "description": item.get("description", ""),
                "custom": True,
            }
        )
    return options


__all__ = [
    "CATEGORY_ORDER",
    "DEFAULT_PAGE_LIMIT",
    "DEFAULT_TEMPLATE",
    "RESUME_TEMPLATES",
    "TEMPLATES_DIR",
    "template_options",
    "template_options_with_custom",
    "template_spec",
]
