# SPDX-License-Identifier: Apache-2.0
"""对抗性测试：招呼语截断、空招呼语处理、凭据不落库、投递数据脱敏。

对应 P0-4（招呼语必须能预览且为空即拦截）与 P0-11（不保存任何招聘站点凭据、不记录完整资料）。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from app.database import Base
from app.models.apply import (
    FAILURE_GREETING_MISSING,
    ApplyQueueItem,
    ApplyTask,
    ApplyTaskItem,
    JobMatchAnalysis,
)
from app.models.job import Job
from app.models.resume import ResumeRecord
from app.schemas.apply import (
    GREETING_RECORD_MAX_CHARS,
    ApplyConfigIn,
    ApplyQueueAddRequest,
    ApplyQueueItemUpdate,
)
from app.services.apply import apply_service
from app.services.apply.apply_service import _clip_greeting
from app.services.browser.cdp_client import CdpClient
from app.services.job.job_match import parse_greeting
from app.services.llm.base import LLMError
from app.services.sites.base import SiteFailure
from app.services.sites.boss import BossAdapter

REPO_ROOT = Path(__file__).resolve().parents[2]


# ===== 招呼语截断 =====


def test_clip_greeting_truncates_to_the_record_limit():
    assert len(_clip_greeting("字" * 600)) == GREETING_RECORD_MAX_CHARS
    assert GREETING_RECORD_MAX_CHARS == 500
    # 空白被裁掉，避免把只有空格/换行的"招呼语"当成非空。
    assert _clip_greeting("   \n  ") == ""


def test_parse_greeting_truncates_but_rejects_empty_and_overlong():
    assert len(parse_greeting("a" * 800)) == GREETING_RECORD_MAX_CHARS
    with pytest.raises(LLMError):
        parse_greeting("")
    with pytest.raises(LLMError):
        parse_greeting("a" * 5000)


def test_queue_greeting_is_clipped_on_write(db_session):
    job = Job(title="后端开发", company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.commit()

    created = apply_service.add_to_queue(
        db_session,
        ApplyQueueAddRequest(
            items=[{"job_id": job.id, "confirm_unanalyzed": True, "greeting": "x" * 900}]
        ),
    )
    stored = db_session.get(ApplyQueueItem, created[0].id)
    assert len(stored.greeting) == GREETING_RECORD_MAX_CHARS


def test_queue_greeting_confirmation_follows_the_save_path(db_session):
    """批量生成只落文案（未确认）；编辑弹窗保存才置为已确认。"""
    job = Job(title="后端开发", company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.commit()
    created = apply_service.add_to_queue(
        db_session,
        ApplyQueueAddRequest(items=[{"job_id": job.id, "confirm_unanalyzed": True}]),
    )
    item_id = created[0].id
    assert created[0].greeting_confirmed is False

    generated = apply_service.update_queue_item(
        db_session, item_id, ApplyQueueItemUpdate(greeting="AI 草稿", confirm_greeting=False)
    )
    assert generated.greeting == "AI 草稿"
    assert generated.greeting_confirmed is False

    # 编辑弹窗保存不显式传 confirm_greeting：默认就是人工确认。
    saved = apply_service.update_queue_item(
        db_session, item_id, ApplyQueueItemUpdate(greeting="AI 草稿，我改过")
    )
    assert saved.greeting_confirmed is True

    # 清空文案后不能继续算"已确认"。
    cleared = apply_service.update_queue_item(
        db_session, item_id, ApplyQueueItemUpdate(greeting="")
    )
    assert cleared.greeting_confirmed is False


def test_add_to_queue_binds_the_jobs_latest_resume(db_session):
    """入队即固定"这个岗位用哪份简历"，招呼语才会按对应 JD 的简历来写。"""
    job = Job(title="后端开发", company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.flush()
    older = ResumeRecord(title="旧版", job_id=job.id, content={})
    db_session.add(older)
    db_session.flush()
    latest = ResumeRecord(title="按 JD 改过的那版", job_id=job.id, content={})
    db_session.add(latest)
    db_session.commit()

    created = apply_service.add_to_queue(
        db_session,
        ApplyQueueAddRequest(items=[{"job_id": job.id, "confirm_unanalyzed": True}]),
    )
    stored = db_session.get(ApplyQueueItem, created[0].id)
    assert stored.resume_id == latest.id
    assert created[0].resume_title == "按 JD 改过的那版"


def test_changing_the_resume_invalidates_greeting_confirmation(db_session):
    """招呼语是相对某一份简历写的：换简历后不能继续算"已确认"。"""
    job = Job(title="后端开发", company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.flush()
    resume_a = ResumeRecord(title="A 版", job_id=job.id, content={})
    resume_b = ResumeRecord(title="B 版", job_id=job.id, content={})
    db_session.add_all([resume_a, resume_b])
    db_session.commit()

    created = apply_service.add_to_queue(
        db_session,
        ApplyQueueAddRequest(
            items=[
                {
                    "job_id": job.id,
                    "confirm_unanalyzed": True,
                    "resume_id": resume_a.id,
                }
            ]
        ),
    )
    item_id = created[0].id
    saved = apply_service.update_queue_item(
        db_session, item_id, ApplyQueueItemUpdate(greeting="对 A 版写的招呼语", confirm_greeting=True)
    )
    assert saved.greeting_confirmed is True

    # 编辑弹窗会把整段招呼语一起提交，所以这里模拟"换简历 + 原样提交旧文案"。
    changed = apply_service.update_queue_item(
        db_session,
        item_id,
        ApplyQueueItemUpdate(greeting="对 A 版写的招呼语", resume_id=resume_b.id),
    )
    assert changed.resume_id == resume_b.id
    assert changed.greeting_confirmed is False


def test_greeting_preview_refuses_without_a_resume(client, db_session):
    """队列条目没有可用简历时，预览直接返回 no_resume，不调模型、不编话术。"""
    job = Job(title="后端开发", company="A公司", source="BOSS直聘", source_url="u")
    db_session.add(job)
    db_session.commit()
    created = apply_service.add_to_queue(
        db_session,
        ApplyQueueAddRequest(items=[{"job_id": job.id, "confirm_unanalyzed": True}]),
    )

    response = client.post(
        "/api/apply/greeting/preview",
        json={"job_id": job.id, "item_id": created[0].id},
    )

    assert response.status_code == 200
    assert response.json() == {"greeting": "", "source": "no_resume"}


def test_resolve_greeting_falls_back_to_default_when_item_is_empty():
    config = ApplyConfigIn(default_greeting="您好，我对该岗位很感兴趣。")
    item = ApplyQueueItem(job_id=1, greeting="   ")
    assert apply_service.resolve_greeting(item, config) == "您好，我对该岗位很感兴趣。"


def test_resolve_greeting_returns_empty_when_default_is_empty():
    config = ApplyConfigIn(default_greeting="")
    item = ApplyQueueItem(job_id=1, greeting="")
    assert apply_service.resolve_greeting(item, config) == ""


# ===== 招呼语必填但为空 → 明确失败分类（不静默失败） =====


class _ScriptedCdp(CdpClient):
    """按调用顺序返回脚本化页面状态，模拟 BOSS 适配器的几次 evaluate。"""

    def __init__(self, results: list) -> None:
        self._results = list(results)
        self._i = 0

    def _next(self):
        if self._i < len(self._results):
            value = self._results[self._i]
            self._i += 1
            return value
        return None

    def list_targets(self):
        return []

    def new_tab(self, url: str = "about:blank") -> str:
        return "t1"

    def send(self, method, params=None, *, timeout=None):
        return {}

    def evaluate(self, expression, *, timeout=None):
        return self._next()

    def set_file_input(self, selector, files, *, timeout=None):
        return None

    def navigate(self, url, *, timeout=None):
        return {}

    def close(self):
        return None


def test_required_but_empty_greeting_raises_greeting_missing():
    # 新聊天链路：先取沟通入口坐标（rf:entry-rect，就绪即返回），随后在**点击入口之前**
    # 发现招呼语为空，直接拦截——不会点出任何会话。
    import json

    entry_rect = json.dumps(
        {"found": True, "matched": 1, "label": "立即沟通",
         "x": 500, "y": 200, "width": 120, "height": 40, "url": "u", "title": "t"}
    )
    client = _ScriptedCdp([entry_rect])
    adapter = BossAdapter()
    with pytest.raises(SiteFailure) as exc:
        adapter.fill_and_submit(client, {}, "")
    assert exc.value.category == FAILURE_GREETING_MISSING
    assert "招呼语" in exc.value.detail


def test_empty_greeting_is_always_blocked_in_the_chat_flow():
    """现版 BOSS 投递就是"发一条招呼消息"，不存在无招呼语的通用提交通道。

    无论页面控件是否标 required，空招呼语都必须在点击沟通入口之前拦截，
    避免建立一个没有任何内容的会话（旧版"非必填即可空着提交"的分支已随聊天页改版失效）。
    """
    import json

    entry_rect = json.dumps(
        {"found": True, "matched": 1, "label": "继续沟通",
         "x": 500, "y": 200, "width": 120, "height": 40, "url": "u", "title": "t"}
    )
    client = _ScriptedCdp([entry_rect])
    adapter = BossAdapter()
    with pytest.raises(SiteFailure) as exc:
        adapter.fill_and_submit(client, {}, "   \n  ")
    assert exc.value.category == FAILURE_GREETING_MISSING


# ===== 凭据不落库 =====


def _column_names() -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for table in Base.metadata.sorted_tables:
        columns[table.name] = {column.name for column in table.columns}
    return columns


def test_no_credential_like_column_anywhere():
    """投递相关的表不得出现密码 / Cookie / 令牌 / 验证码字段。

    只针对本次新增的 apply / job_match 表做严格检查（``max_tokens`` 这类合法列名会被
    误伤，所以不在这里用裸 ``token`` 做全局匹配）。
    """
    forbidden = (
        "password",
        "passwd",
        "cookie",
        "secret",
        "credential",
        "captcha",
        "session_key",
        "api_key",
        "access_token",
        "refresh_token",
        "auth_token",
        "verify_code",
    )
    columns = _column_names()
    apply_tables = {"job_match_analysis", "apply_queue_item", "apply_task", "apply_task_item"}
    for table in apply_tables:
        for column in columns[table]:
            lowered = column.lower()
            assert not any(bad in lowered for bad in forbidden), f"{table}.{column} 疑似凭据字段"


def test_apply_tables_match_the_design_contract():
    columns = _column_names()
    assert set(columns["apply_task_item"]) == {
        "id",
        "task_id",
        "job_id",
        "job_title",
        "company",
        "resume_id",
        "resume_title",
        "greeting",
        "greeting_confirmed",
        "status",
        "failure_category",
        "failure_detail",
        # 0073：失败三段稳定码（环节 / 控件 / 原因子码）。
        "failure_step",
        "failure_target",
        "failure_reason",
        "attempt",
        "sort_order",
        "started_at",
        "finished_at",
        "created_at",
        # 投递记录可删：软删标记进回收站，删掉的记录不再计入统计与每日上限。
        "deleted_at",
    }
    # 投递表只保留展示快照，不留完整资料 blob。
    assert "profile" not in columns["apply_task_item"]
    assert "content" not in columns["apply_task_item"]


def test_browser_profile_dir_is_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "backend/data/browser-profile/" in gitignore


def test_config_out_is_exactly_config_in_plus_defaults():
    """`ApplyConfigOut` 只比 `ApplyConfigIn` 多一个 `defaults`，不能再多。

    **两个 schema 形状不一致会变成用户可见的故障**：`GET /apply/config` 返回 Out，
    `PUT` 收 In（`extra="forbid"`），前端"整份取回 → 改两个字段 → 整份提交"的写法
    如果把 Out 的响应体整个回传，就会多出一个 In 不认识的键 → 422
    「Extra inputs are not permitted」。这个报错里**既没有字段名也没有上下文**，
    用户只看到"点保存就报错"，无从自查。

    （真实踩过：`BrowserSettingsModal` 把响应体整个 `{...data}` 回传，
    `defaults` 被送去 PUT，网申页换 Edge 直接报错。前端已改为显式挑字段，
    这里从 schema 一侧钉住"Out 只许比 In 多 defaults"——将来给 Out 加回显字段时
    这条会红，提醒同步前端的提交白名单。）
    """
    from app.schemas.apply import ApplyConfigOut

    input_fields = set(ApplyConfigIn.model_fields)
    output_fields = set(ApplyConfigOut.model_fields)

    extra = output_fields - input_fields
    assert extra == {"defaults"}, (
        f"ApplyConfigOut 比 ApplyConfigIn 多出的字段必须是且仅是 `defaults`，实际多出：{sorted(extra)}。"
        "如果这是有意的，请同步更新前端提交时的字段白名单"
        "（`frontend/src/components/apply/BrowserSettingsModal.tsx` 与它的测试）。"
    )
    missing = input_fields - output_fields
    assert not missing, f"ApplyConfigOut 漏了 ApplyConfigIn 的字段：{sorted(missing)}"


# ===== 投递数据只取必需字段，不含完整资料 =====


def test_build_apply_data_excludes_sensitive_profile_fields(db_session):
    from app.models.profile import UserProfile

    profile = UserProfile(
        name="张三",
        phone="13800000000",
        email="a@b.com",
        city="上海",
        target_city="北京",
        job_intent="后端工程师",
        summary="简介",
        photo="BASE64-IMAGE-DATA",
    )
    db_session.add(profile)
    db_session.commit()

    data = apply_service.build_apply_data(db_session, None)
    assert set(data) <= {"name", "phone", "email", "city", "job_intent", "summary"}
    assert "photo" not in data
    assert "BASE64" not in str(data)


def test_build_apply_data_does_not_leak_resume_content(db_session):
    resume = ResumeRecord(
        title="后端版", job_id=None, job_title="后端", content={"secret": "fULL-RESUME-BODY"}
    )
    db_session.add(resume)
    db_session.commit()

    data = apply_service.build_apply_data(db_session, resume)
    assert "FULL-RESUME-BODY" not in str(data)
    assert "secret" not in data


def test_apply_models_are_the_four_expected_tables():
    for model in (JobMatchAnalysis, ApplyQueueItem, ApplyTask, ApplyTaskItem):
        assert model.__tablename__ in Base.metadata.tables
