# SPDX-License-Identifier: Apache-2.0
"""「求职助手工具集修复批」的守卫测试。

覆盖两件事：

1. **目录纠偏**：能力地图要如实写「放宽模式」（默认关、怎么开、代点+确认制、
   日期文件除外、助手无此工具），数据集备份的 API Key 措辞要与 README 对齐；
   README 表行与目录映射由 ``test_assistant_knowledge_audit`` 双向校验，这里不重复。
2. **新工具的真实行为**：每条都打到 service 层落库/查询，再看注册表里 writes
   标志有没有标对——工具描述说得再好，落库错了照样是假话。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from app.models.apply import (
    FAILURE_CAPTCHA_REQUIRED,
    FAILURE_CATEGORY_LABELS,
    TASK_KIND_APPLY,
    ApplyTask,
    ApplyTaskItem,
)
from app.models.job import Job
from app.models.resume import ResumeRecord
from app.models.resume_template import TEMPLATE_KIND_FORMAT
from app.schemas.reminder import ReminderCreate
from app.services.assistant_tools import _TOOLS, execute_tool, tool_names
from app.services.feature_catalog import build_capability_map
from app.services.reminder_service import create_reminder
from app.services.resume.resume_template_store import create_user_template


def _payload(db_session, name: str, arguments: dict) -> dict:
    return json.loads(execute_tool(db_session, name, arguments).text)


# ===== 1/2：目录渲染 =====


def test_capability_map_describes_the_relaxed_mode():
    """web_form_fill 条目必须写清放宽模式的边界，助手才不会要么瞒着、要么夸大。"""
    rendered = build_capability_map()
    assert "放宽模式" in rendered
    assert "默认关闭" in rendered, "必须说明默认是关的"
    assert "设置 → 助手与 AI 行为" in rendered, "必须说明在哪里开"
    assert "回读" in rendered, "必须提到代点后回读验证"
    assert "逐条确认" in rendered, "同意/声明类勾选必须说明确认制"
    assert "日期选择器" in rendered and "文件上传" in rendered, "必须说明日期与文件仍不代做"
    assert "没有开关这个模式的工具" in rendered, "必须如实说明助手自己开不了它"


def test_capability_map_dataset_wording_matches_readme():
    """备份的 API Key 措辞要与 README.md「更新而不丢失数据」一致：默认包含、可取消勾选。"""
    rendered = build_capability_map()
    assert "备份默认包含大模型 API Key，导出前可取消勾选剔除" in rendered
    assert "导入导出不含大模型 API Key" not in rendered


# ===== 3：update_job 的 favorite 参数 =====


def test_update_job_can_toggle_favorite_and_leaves_it_alone_when_absent(db_session):
    job = Job(title="目标岗位", company="某司")
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    result = execute_tool(db_session, "update_job", {"job_id": job.id, "favorite": True})
    assert result.changed is True
    db_session.refresh(job)
    assert job.favorite is True

    # 不传 favorite 时行为不变：只改给出的字段，收藏状态原样保留。
    execute_tool(db_session, "update_job", {"job_id": job.id, "note": "改个备注"})
    db_session.refresh(job)
    assert job.favorite is True
    assert job.note == "改个备注"


def test_update_job_declares_the_favorite_parameter():
    spec = next(tool for tool in _TOOLS if tool.name == "update_job")
    assert "favorite" in spec.parameters["properties"]
    assert spec.writes is True


# ===== 4：list_format_templates =====


def test_list_format_templates_lists_user_format_templates(db_session):
    created = create_user_template(
        db_session,
        name="紧凑一页",
        kind=TEMPLATE_KIND_FORMAT,
        description="压进一页用",
        config={"accent": "#2f6feb"},
    )
    payload = _payload(db_session, "list_format_templates", {})

    assert payload["总数"] == 1
    row = payload["版式"][0]
    assert row["id"] == created.id
    assert row["name"] == "紧凑一页"
    assert row["config"]["accent"] == "#2f6feb"

    spec = next(tool for tool in _TOOLS if tool.name == "list_format_templates")
    assert spec.writes is False, "列表工具是只读的，不能标 writes"


# ===== 5：list_apply_records =====


def _apply_batch(db_session) -> ApplyTask:
    task = ApplyTask(
        kind=TASK_KIND_APPLY,
        status="completed",
        total=2,
        processed=2,
        succeeded=1,
        failed=1,
        skipped=0,
        message="",
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(
        ApplyTaskItem(
            task_id=task.id,
            job_title="后端工程师",
            company="成功公司",
            status="success",
        )
    )
    db_session.add(
        ApplyTaskItem(
            task_id=task.id,
            job_title="前端工程师",
            company="失败公司",
            status="failed",
            failure_category=FAILURE_CAPTCHA_REQUIRED,
            failure_detail="投递页要求滑块验证",
        )
    )
    db_session.commit()
    db_session.refresh(task)
    return task


def test_list_apply_records_reports_failure_categories_per_job(db_session):
    task = _apply_batch(db_session)

    payload = _payload(db_session, "list_apply_records", {})

    assert payload["总批次数"] == 1
    batch = payload["投递记录"][0]
    assert batch["批次"] == task.id
    assert batch["状态"] == "completed"
    assert (batch["成功"], batch["失败"]) == (1, 1)

    by_status = {row["company"]: row for row in batch["岗位结果"]}
    assert by_status["成功公司"]["status"] == "success"
    failed = by_status["失败公司"]
    assert failed["failure_category"] == FAILURE_CAPTCHA_REQUIRED
    assert failed["failure_label"] == FAILURE_CATEGORY_LABELS[FAILURE_CAPTCHA_REQUIRED]
    assert failed["failure_detail"] == "投递页要求滑块验证"

    spec = next(tool for tool in _TOOLS if tool.name == "list_apply_records")
    assert spec.writes is False


def test_list_apply_records_filters_by_result(db_session):
    _apply_batch(db_session)

    payload = _payload(db_session, "list_apply_records", {"result": "failed"})

    assert payload["总批次数"] == 1
    companies = [row["company"] for row in payload["投递记录"][0]["岗位结果"]]
    assert companies == ["失败公司"]


# ===== 6：update_reminder =====


def _reminder(db_session, title: str):
    return create_reminder(
        db_session,
        ReminderCreate(
            title=title,
            remind_at=datetime.now() + timedelta(days=1),
            kind="interview",
        ),
    )


@pytest.mark.parametrize("status", ["done", "dismissed"])
def test_update_reminder_marks_done_or_dismissed(db_session, status):
    reminder = _reminder(db_session, f"参加二面-{status}")

    result = execute_tool(
        db_session, "update_reminder", {"reminder_id": reminder.id, "status": status}
    )
    assert result.changed is True
    db_session.refresh(reminder)
    assert reminder.status == status


def test_update_reminder_rejects_unknown_status(db_session):
    reminder = _reminder(db_session, "状态不合法的提醒")

    with pytest.raises(ValueError):
        execute_tool(
            db_session,
            "update_reminder",
            {"reminder_id": reminder.id, "status": "cancelled"},
        )

    spec = next(tool for tool in _TOOLS if tool.name == "update_reminder")
    assert spec.writes is True


# ===== 7：update_resume =====


def _resume(db_session) -> ResumeRecord:
    record = ResumeRecord(
        title="标记用简历",
        job_title="后端开发工程师",
        company="某科技",
        source="ai",
        content={"name": "张三"},
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def test_update_resume_persists_favorite_and_note(db_session):
    record = _resume(db_session)

    result = execute_tool(
        db_session,
        "update_resume",
        {"resume_id": record.id, "favorite": True, "note": "主投版本"},
    )
    assert result.changed is True
    db_session.refresh(record)
    assert record.favorite is True
    assert record.note == "主投版本"


def test_update_resume_requires_at_least_one_field(db_session):
    record = _resume(db_session)

    with pytest.raises(ValueError):
        execute_tool(db_session, "update_resume", {"resume_id": record.id})


def test_update_resume_cannot_touch_a_trashed_record(db_session):
    from app.services import trash

    record = _resume(db_session)
    trash.soft_delete(db_session, "resume", record)
    db_session.commit()

    with pytest.raises(ValueError):
        execute_tool(db_session, "update_resume", {"resume_id": record.id, "favorite": True})

    spec = next(tool for tool in _TOOLS if tool.name == "update_resume")
    assert spec.writes is True


# ===== 注册表整体断言 =====


def test_new_tools_are_registered_in_order_with_correct_flags():
    names = tool_names()
    for name in ("list_format_templates", "list_apply_records", "update_resume", "update_reminder"):
        assert name in names, f"{name} 没有注册进 _TOOLS"
    # 新工具按域追加：格式模板在 data 段，其余三个在 report 段（core → data → report → search）。
    assert names.index("list_format_templates") < names.index("list_apply_records")
    assert names.index("list_apply_records") < names.index("update_resume")
    assert names.index("update_resume") < names.index("update_reminder")
    writes = {tool.name: tool.writes for tool in _TOOLS}
    assert [writes[name] for name in ("list_format_templates", "list_apply_records")] == [False, False]
    assert [writes[name] for name in ("update_resume", "update_reminder")] == [True, True]


# ===== v2 文档结构下助手读简历的两处致命缺陷（2026-11-08）=====
#
# 症状：用户让助手「改写项目经历」，助手连试 11 次工具、4 次失败后放弃。
# 根因有两层，都是 v1→v2 迁移遗留：
#   1. 照片在 v2 里存在 header.items，而代码只 pop 顶层 "photo"（v1 写法），
#      400KB base64 一起进上下文 → 请求超限 → provider 报错；
#   2. _RESUME_CONTENT_DROP_ORDER 按 v1 扁平结构写，v2 顶层没有那些键，
#      裁剪一次都没生效；而一旦生效又把 projects 先摘掉（用户要改的正是它）。


def _v2_document_with_photo() -> dict:
    """造一份 v2 文档：header 里带 base64 照片，sections 里 5 个板块都有内容。"""
    big_photo = "data:image/jpeg;base64," + ("A" * 200_000)
    return {
        "version": 2,
        "language": "zh-CN",
        "header": {
            "contact_breaks": [],
            "items": [
                {"id": "it_name", "key": "name", "kind": "field", "value": "张三"},
                {"id": "it_photo", "key": "photo", "kind": "field", "value": big_photo},
            ],
        },
        "sections": [
            {"key": "education", "title": "教育经历", "entries": [{"id": "ob_e1", "items": []}]},
            {"key": "experience", "title": "实习/工作经历", "entries": [{"id": "ob_x1", "items": []}]},
            {"key": "projects", "title": "项目经历", "entries": [{"id": "ob_p1", "items": []}]},
            {"key": "summary", "title": "个人总结", "entries": [{"id": "ob_s1", "items": []}]},
            {"key": "skills", "title": "专业技能", "entries": [{"id": "ob_k1", "items": []}]},
        ],
    }


def test_strip_photo_removes_v2_header_photo_but_keeps_the_item():
    """v2 的照片在 header.items 里，必须摘值而不是只 pop 顶层键。

    只 pop 顶层会留下 400KB base64 → 请求超限 → 助手整场任务失败。
    保留 item 本身：模型仍知道"有照片位"，`header.photo` 路径也仍然可解析。
    """
    from app.services.assistant_tools.job_tools import _strip_photo_from_content

    doc = _v2_document_with_photo()
    assert len(json.dumps(doc, ensure_ascii=False)) > 200_000

    stripped = _strip_photo_from_content(doc)
    assert len(json.dumps(stripped, ensure_ascii=False)) < 5_000, "照片必须被摘掉"
    photo_items = [i for i in stripped["header"]["items"] if i.get("key") == "photo"]
    assert len(photo_items) == 1, "item 本身要保留"
    assert photo_items[0]["value"] == ""


def test_resume_content_trimming_handles_v2_sections():
    """v2 结构下裁剪必须真的生效（旧实现比较的是顶层键，永远为假）。"""
    from app.services.assistant_tools._shared import _resume_content_for_model

    doc = _v2_document_with_photo()
    # 塞满内容，确保超预算
    doc["sections"][0]["entries"][0]["items"] = [
        {"id": f"it_{i}", "key": "school", "kind": "field", "value": "X" * 500}
        for i in range(40)
    ]
    trimmed, dropped = _resume_content_for_model(doc, 3_000)
    assert dropped, "v2 结构下裁剪必须生效，否则整份正文会塞爆上下文"
    remaining = [s.get("key") for s in trimmed.get("sections") or []]
    assert len(remaining) < 5
    # 体积下界只看 sections：header 里的照片由 `_strip_photo_from_content` 负责
    # （生产链路先摘照片、再裁正文），两个函数各管一件事，不在这里重复断言总大小。
    sections_size = len(json.dumps(trimmed.get("sections") or [], ensure_ascii=False))
    assert sections_size < 3_000


def test_projects_is_dropped_last_because_it_is_usually_the_target():
    """projects / experience 是改写主体，必须最后才丢。

    旧顺序把 projects 排在 education 前面，实测导致"用户要改项目经历、
    模型拿到的简历里却没有项目"，只能瞎猜路径。
    """
    from app.services.assistant_tools._shared import _RESUME_CONTENT_DROP_ORDER

    order = list(_RESUME_CONTENT_DROP_ORDER)
    assert order.index("projects") > order.index("education")
    assert order.index("projects") > order.index("skills")
    assert order.index("experience") > order.index("awards")


def test_resume_content_budget_fits_a_real_resume():
    """预算要够装一份正常简历的正文（实测去照片后约 11KB）。

    4500 的旧预算会把 skills/projects/education 整段摘掉。
    """
    from app.services.assistant_tools._shared import _RESUME_CONTENT_BUDGET

    assert _RESUME_CONTENT_BUDGET >= 20_000


def test_sample_paths_covers_every_section():
    """报错时给的路径样例必须覆盖**每个板块**，不能被第一个板块占满。

    旧实现塞满 limit 就返回，education 的一个条目 + 四个字段就吃光 6 个名额，
    模型据此以为其它板块没有条目，于是反复试错路径。
    """
    from app.services.assistant_tools.document_support import sample_paths

    doc = _v2_document_with_photo()
    # education 条目下塞满字段，模拟"第一个板块就吃光名额"
    doc["sections"][0]["entries"] = [
        {"id": "ob_e1", "items": [{"id": f"it_{i}", "key": "f", "kind": "field", "value": "v"} for i in range(10)]}
    ]
    samples = sample_paths(doc, limit=6)
    heads = {s.split(".", 1)[0] for s in samples}
    for key in ("education", "experience", "projects", "summary", "skills"):
        assert key in heads, f"样例里缺少板块 {key}，模型会找不到它"
