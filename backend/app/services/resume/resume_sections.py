"""简历正文的分区（板块）定义与顺序。

**为什么要有这个模块**：正文的七个分区在四处独立渲染——HTML 模板（预览、HTML 导出、
浏览器打印）、服务端 PDF、Word、Markdown。顺序一旦被写死在四处，用户改了一处看到的效果
就只对那一处生效，另外三处会**悄悄地**保持旧顺序——而"导出的和预览的不一样"是那种
用户会怀疑整个工具的问题。所以顺序在这里定义一次，四个渲染器都从这里取。

存储位置：简历的 `format_config`（按简历的版式覆盖）里的 `section_order` 与
`hidden_sections`。放在版式配置里而不是新增数据库列，是因为它本来就是"内容怎么排"
的一部分，而且 `format_config` 已经是按简历存的一份 JSON 覆盖，不需要迁移。

一条刻意的约束：**存下来的顺序永远是七个键的一个完整排列**（`normalized_section_order`
负责补齐）。隐藏是另一个维度：`hidden_sections` 只记"不要显示的那几个"，顺序本身保持
完整。这样用户隐藏某个板块再放开，它仍回到自己原来的位置，而不是跑到最后面。
"""

from __future__ import annotations

# 默认顺序 = 内置模板沿用至今的顺序。**不要**因为「我的资料」那边改了默认顺序就顺手改这里：
# 简历是有历史记录的产物，改默认顺序等于把用户已经导出过的简历悄悄换了一个样子。
DEFAULT_SECTION_ORDER: tuple[str, ...] = (
    "summary",
    "education",
    "experience",
    "campus_experience",
    "projects",
    "skills",
    "awards",
)

SECTION_LABELS: dict[str, str] = {
    "summary": "个人总结",
    "education": "教育经历",
    "experience": "实习/工作经历",
    "campus_experience": "校园经历",
    "projects": "项目经历",
    "skills": "专业技能",
    "awards": "荣誉奖项",
}

# 页眉（姓名 / 求职意向 / 联系方式 / 照片）不在可排序的七个分区里，它永远在最前面。
# 这里显式写下来，是为了让"为什么列表里没有它"这个问题有一个能搜到的答案。


def section_label(key: str) -> str:
    return SECTION_LABELS.get(key, key)


def normalized_section_order(raw: object) -> list[str]:
    """把任意输入归一化成"七个键齐全、无重复、只含已知键"的顺序。

    未出现在输入里的键按默认顺序补在后面：用户只调了前两项，不应该让其余五项消失。
    """
    if isinstance(raw, (list, tuple)):
        candidates = raw
    elif isinstance(raw, str):
        # 查询串里传过 "summary,education" 这种写法；按逗号拆开照样认。
        candidates = raw.split(",")
    else:
        return list(DEFAULT_SECTION_ORDER)

    ordered: list[str] = []
    for item in candidates:
        key = str(item).strip()
        if key in SECTION_LABELS and key not in ordered:
            ordered.append(key)
    for key in DEFAULT_SECTION_ORDER:
        if key not in ordered:
            ordered.append(key)
    return ordered


def resolved_section_order(format_config: dict | None) -> list[str]:
    """从版式覆盖里取分区顺序；没设过就用默认顺序。"""
    if not isinstance(format_config, dict):
        return list(DEFAULT_SECTION_ORDER)
    if "section_order" not in format_config:
        return list(DEFAULT_SECTION_ORDER)
    return normalized_section_order(format_config.get("section_order"))


def normalized_hidden_sections(raw: object) -> list[str]:
    """把任意输入归一化成"只含已知分区键、无重复"的隐藏列表。

    与顺序不同，这个列表**允许为空**（= 一个都不藏），也允许不完整——没提到的分区
    就是显示的。未知键直接丢弃：它来自 JSON 字段，抛异常会让整份版式失效。
    """
    if isinstance(raw, (list, tuple)):
        candidates = raw
    elif isinstance(raw, str):
        candidates = raw.split(",")
    else:
        return []

    hidden: list[str] = []
    for item in candidates:
        key = str(item).strip()
        if key in SECTION_LABELS and key not in hidden:
            hidden.append(key)
    return hidden


def resolved_hidden_sections(format_config: dict | None) -> list[str]:
    """从版式覆盖里取被隐藏的分区；没设过就是一个都不藏。"""
    if not isinstance(format_config, dict):
        return []
    return normalized_hidden_sections(format_config.get("hidden_sections"))


def resolved_visible_sections(format_config: dict | None) -> list[str]:
    """渲染器真正应该输出的分区：顺序里去掉被隐藏的那些。

    四个渲染器（HTML/PDF/Word/Markdown）都从这里取，避免"预览里藏了、导出的还在"。
    """
    hidden = set(resolved_hidden_sections(format_config))
    return [key for key in resolved_section_order(format_config) if key not in hidden]


__all__ = [
    "DEFAULT_SECTION_ORDER",
    "SECTION_LABELS",
    "normalized_hidden_sections",
    "normalized_section_order",
    "resolved_hidden_sections",
    "resolved_section_order",
    "resolved_visible_sections",
    "section_label",
]
