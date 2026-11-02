# SPDX-License-Identifier: Apache-2.0
"""底稿模式版式继承：选底稿是为了少改，新简历不能又换回默认模板。"""

from types import SimpleNamespace

from app.schemas.resume import GenerateOptions
from app.services.resume.resume_generate_runner import resolve_record_layout


def _base() -> SimpleNamespace:
    return SimpleNamespace(
        template="modern",
        format_name="compact",
        page_limit=2,
        font_scale="large",
        language="en-US",
        format_config={"section_order": ["education", "projects"]},
    )


def test_base_layout_is_inherited_by_default():
    options = GenerateOptions(template="classic", page_limit=1, font_scale="standard")

    layout = resolve_record_layout(options, _base())

    assert layout == {
        "template": "modern",
        "format_name": "compact",
        "page_limit": 2,
        "font_scale": "large",
        "language": "en-US",
        "format_config": {"section_order": ["education", "projects"]},
    }


def test_base_layout_can_be_disabled():
    options = GenerateOptions(
        template="classic",
        page_limit=1,
        font_scale="standard",
        inherit_base_layout=False,
    )

    layout = resolve_record_layout(options, _base())

    assert layout["template"] == "classic"
    assert layout["page_limit"] == 1
    assert layout["format_config"] == {}


def test_empty_base_format_name_still_means_follow_template():
    base = _base()
    base.format_name = ""
    options = GenerateOptions(template="classic", format_name="compact")

    layout = resolve_record_layout(options, base)

    # 底稿的 format_name 为空是"跟随模板默认"的有效值，不能被请求值覆盖。
    assert layout["format_name"] == ""
