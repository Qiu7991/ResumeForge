# SPDX-License-Identifier: Apache-2.0
"""模拟面试：提示词构造、解析归一化与接口流程。

重点验证"流程由代码控制"这条设计：轮数到了必须收尾、报告结构不对时要能容错、
模型返回残缺 JSON 时要给出可读的错误，而不是把半成品写进界面。
"""

import json

import pytest
from app.models.interview import InterviewSession
from app.schemas.interview import InterviewCreate
from app.services.interview.interview import (
    answered_rounds,
    build_interview_messages,
    build_report_messages,
    parse_report,
    parse_turn,
)
from app.services.llm.base import LLMError
from tests.interview_target_support import start_interview as _start

_DEFAULT_REPORT = {
    "score": 80,
    "dimensions": [{"name": "技术", "score": 80, "comment": "细节到位"}],
    "strengths": ["结构清楚"],
    "improvements": ["补充数据"],
    "summary": "整体不错",
}


def _session(**overrides) -> InterviewSession:
    values = {
        "title": "后端开发 模拟面试",
        "job_title": "后端开发工程师",
        "company": "示例公司",
        "interview_type": "技术面",
        "difficulty": "中级",
        "interviewer_style": "持续追问",
        "rounds": 3,
        "focus": "Go 并发",
        "persona": "",
    }
    values.update(overrides)
    return InterviewSession(**values)


def _turn_jsons(count: int, *, done: bool = False) -> list[str]:
    return [
        json.dumps({"question": f"第 {index} 题", "feedback": "点评", "done": done})
        for index in range(1, count + 1)
    ]


def _configure_provider(monkeypatch, replies: list[str]) -> None:
    """只把 provider 换成按顺序返回预设 JSON 的假实现，其余流程全走真实代码。

    与 `_configure` 的区别很关键：那个把 `_ask_next_question` 整个换掉，连同它里面的
    轮次越界检查一起绕过了，凡是"检查发生在那一层"的用例都会变成假绿。
    """

    class _Provider:
        def __init__(self) -> None:
            self.replies = list(replies)

        async def chat(self, _messages, *, thinking: bool = True):
            return (
                self.replies.pop(0)
                if self.replies
                else json.dumps({"question": "收尾", "feedback": "", "done": True})
            )

    async def build_report(_provider, _session_):
        return _DEFAULT_REPORT

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_Provider(), "test-model")
    )
    monkeypatch.setattr("app.api.interview.generate_report", build_report)


def _configure(monkeypatch, turns: list[dict], report: dict | None = None) -> None:
    """把面试官与报告都换成按顺序返回预设内容的假实现（不联网、不解析模型输出）。"""
    queue = list(turns)

    async def ask(_db, _session_, _provider):
        payload = queue.pop(0) if queue else {"question": "", "feedback": "", "done": True}
        question = str(payload.get("question") or "")
        if not question:
            raise LLMError("面试官没有给出下一个问题")
        return question, str(payload.get("feedback") or ""), bool(payload.get("done"))

    async def build_report(_provider, _session_):
        return report or _DEFAULT_REPORT

    monkeypatch.setattr("app.api.interview._require_provider", lambda _db: (None, "test-model"))
    monkeypatch.setattr("app.api.interview._ask_next_question", ask)
    monkeypatch.setattr("app.api.interview.generate_report", build_report)


def test_parse_turn_requires_a_question():
    question, feedback, done = parse_turn(
        json.dumps({"question": "讲讲你做过的高并发项目", "feedback": "开头不错", "done": False})
    )
    assert question.startswith("讲讲")
    assert feedback == "开头不错"
    assert done is False

    # 没有问题时必须报错：静默通过会让界面停在"等面试官提问"。
    with pytest.raises(LLMError):
        parse_turn(json.dumps({"feedback": "还不错"}))


def test_parse_report_normalizes_messy_output():
    report = parse_report(
        json.dumps(
            {
                "score": "78",  # 字符串分数
                "dimensions": [
                    {"name": "技术", "score": 120, "comment": "超出范围"},  # 夹到 100
                    {"score": 60},  # 缺 name → 丢掉
                    "不是对象",  # 丢掉
                ],
                "strengths": "只写了一条字符串",  # 字符串 → 单元素数组
                "improvements": ["a", "b"],
                "summary": "总评",
            }
        )
    )
    assert report["score"] == 78
    assert [item["name"] for item in report["dimensions"]] == ["技术"]
    assert report["dimensions"][0]["score"] == 100
    assert report["strengths"] == ["只写了一条字符串"]


def test_messages_include_resume_job_and_rules():
    session = _session()
    messages = build_interview_messages(
        session, index=2, resume_text="张三，3 年经验", job_text="岗位：后端开发"
    )
    system = messages[0]["content"]
    assert "当前是第 2 轮" in system
    assert "持续追问" in system
    assert "Go 并发" in system
    # 占位符必须全部被替换掉：留在提示词里等于把模板语法交给模型。
    assert "{{" not in system
    user = messages[1]["content"]
    assert "不可信" in user
    # 进度同时给模型一份：它需要知道还剩几轮来决定是否收尾。
    assert "第 2 / 3 轮" in user
    assert "张三，3 年经验" in user
    # 信息边界（0066）：面试官只拿「简历 + 岗位」，个人资料这一类字段不再出现。
    assert "候选人的简历" in user
    assert "个人资料" not in user


def test_report_prompt_carries_rules():
    messages = build_report_messages(_session())
    assert "评分报告" in messages[0]["content"]
    assert "不得" in messages[0]["content"] or "不要" in messages[0]["content"]


def test_rounds_and_choice_validation():
    assert InterviewCreate(job_id=1, resume_id=1).rounds == 6
    assert answered_rounds(_session()) == 0
    with pytest.raises(Exception):
        InterviewCreate(interview_type="不存在的类型")
    with pytest.raises(Exception):
        InterviewCreate(rounds=99)


def test_api_flow_finishes_after_planned_rounds(client, db_session, monkeypatch):
    """三轮的计划：最后一答只**收盘**，报告由 /finish 生成（需求 4 的新契约）。

    以前这里一答完就出报告；现在"面试结束"和"报告已生成"是两件事——用户可能还想先
    追问几轮，报告一旦先生成就再也追不进评分了。
    """
    _configure(
        monkeypatch,
        [
            {"question": "第一个问题：介绍一个你做过的项目", "feedback": "", "done": False},
            {"question": "第二个问题：这个项目里最难的地方", "feedback": "讲得清楚", "done": False},
            {"question": "结束语：面试到此结束", "feedback": "可以更具体些", "done": True},
        ],
    )

    created = _start(client, db_session, interview_type="技术面", rounds=3)
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["messages"][0]["content"].startswith("第一个问题")
    assert session["status"] == "active"

    first = client.post(f"/api/interview/{session['id']}/answers", json={"content": "我做过 A"})
    assert first.status_code == 200
    assert first.json()["finished"] is False
    assert first.json()["needs_report"] is False
    assert first.json()["feedback"] == "讲得清楚"
    # 进度是代码算出来的，不是模型说的。
    assert first.json()["session"]["answered_rounds"] == 1

    second = client.post(f"/api/interview/{session['id']}/answers", json={"content": "最难的是 B"})
    assert second.status_code == 200
    body = second.json()
    assert body["finished"] is True
    # 收尾了，但报告**还没**生成：界面据此显示决策卡。
    assert body["needs_report"] is True
    assert body["session"]["status"] == "finished"
    assert body["session"]["report"] == {}

    # 结束之后再提交回答应被拒绝，而不是静默追加到已完成的面试里。
    again = client.post(f"/api/interview/{session['id']}/answers", json={"content": "再补一句"})
    assert again.status_code == 409

    # 决策卡上点「结束并生成报告」：只补报告，不再重复插收尾说明。
    finished = client.post(f"/api/interview/{session['id']}/finish")
    assert finished.status_code == 200
    assert finished.json()["report"]["score"] == 80
    notes = [item for item in finished.json()["messages"] if item["role"] == "note"]
    assert notes == [], "自动收尾的那场不该再补一条「候选人主动结束」"


def test_api_finish_early_requires_an_answer(client, db_session, monkeypatch):
    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]

    # 一题都没答就出报告没有意义。
    assert client.post(f"/api/interview/{session_id}/finish").status_code == 400
    client.post(f"/api/interview/{session_id}/answers", json={"content": "我的回答"})
    finished = client.post(f"/api/interview/{session_id}/finish")
    assert finished.status_code == 200
    assert finished.json()["status"] == "finished"
    # 已经结束的会话再点结束是幂等的。
    assert client.post(f"/api/interview/{session_id}/finish").status_code == 200


def test_report_failure_keeps_the_session_usable(client, db_session, monkeypatch):
    """报告生成失败时留下说明，而不是让整场面试不可用或接口 500。"""

    async def broken(_provider, _session_):
        raise LLMError("模型超时")

    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    monkeypatch.setattr("app.api.interview.generate_report", broken)

    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "我的回答"})
    finished = client.post(f"/api/interview/{session_id}/finish")

    assert finished.status_code == 200
    report = finished.json()["report"]
    assert report["error"] is True
    assert "报告生成失败" in report["summary"]
    # 记录仍在，可以存进资料箱复盘。
    assert finished.json()["messages"]


def test_api_requires_model_configuration(client, db_session):
    # 没有配置模型时不该创建一个空的面试会话（关联目标齐备，卡在模型配置这一步）。
    assert _start(client, db_session).status_code == 400
    assert client.get("/api/interview").json() == []


def test_report_to_material_creates_a_review(client, db_session, monkeypatch):
    _configure(monkeypatch, [{"question": "第一题：自我介绍", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "我是张三"})
    client.post(f"/api/interview/{session_id}/finish")

    created = client.post(f"/api/interview/{session_id}/to-material")
    assert created.status_code == 201
    body = created.json()
    assert body["category"] == "面试复盘"
    assert "面试官" in body["content"] and "我是张三" in body["content"]


def test_delete_and_missing_session(client):
    assert client.get("/api/interview/999").status_code == 404
    assert client.delete("/api/interview/999").status_code == 404
    assert client.post("/api/interview/999/answers", json={"content": "x"}).status_code == 404


def test_the_last_answer_does_not_produce_a_dangling_question(
    client, db_session, monkeypatch
):
    """答满轮数后不该再问一道没人会回答的题。

    此前是"先生成下一题、再判断是否满轮"，于是 6 轮的面试会存下 7 道面试官消息，
    多出来的那道还会进报告和存进资料箱的转录里。
    """
    _configure(
        monkeypatch,
        [
            {"question": f"第 {index} 题", "feedback": "点评", "done": False}
            for index in range(1, 10)
        ],
    )
    session_id = _start(client, db_session, rounds=3).json()["id"]

    for _round_index in range(1, 4):
        response = client.post(f"/api/interview/{session_id}/answers", json={"content": "回答"})
        assert response.status_code == 200

    detail = client.get(f"/api/interview/{session_id}").json()
    questions = [item for item in detail["messages"] if item["role"] == "interviewer"]
    answers = [item for item in detail["messages"] if item["role"] == "user"]
    assert len(answers) == 3
    assert len(questions) == 3, "最后一道题不该存在"
    assert detail["status"] == "finished"


def test_the_maximum_round_count_can_actually_be_finished(
    client, db_session, monkeypatch
):
    """轮数取到上限时最后一答不能报错。

    之前 generate_question 的 index 会算成 13 > MAX_INTERVIEW_ROUNDS，最后一答直接 502，
    面试卡在 active 状态：用户只能手动点"结束并出报告"才能脱身。
    """
    from app.schemas.interview import MAX_INTERVIEW_ROUNDS

    # 这里**不能**像别的用例那样替换 _ask_next_question：越界检查就在它调用的
    # generate_question 里面，替换掉就等于把要测的那行代码删了（这个用例第一版
    # 正是这样写的，去掉修复后依然通过）。改成只替换 provider，让真实流程跑起来。
    _configure_provider(monkeypatch, _turn_jsons(30))
    session_id = _start(client, db_session, rounds=MAX_INTERVIEW_ROUNDS).json()["id"]

    for _ in range(MAX_INTERVIEW_ROUNDS):
        response = client.post(f"/api/interview/{session_id}/answers", json={"content": "回答"})
        assert response.status_code == 200, response.text

    detail = client.get(f"/api/interview/{session_id}").json()
    assert detail["status"] == "finished"
    # 收尾与出报告分开（需求 4）：上限到点只收盘，报告由 /finish 补。
    assert detail["report"] == {}
    finished = client.post(f"/api/interview/{session_id}/finish")
    assert finished.status_code == 200
    assert finished.json()["report"]["score"] == 80


def test_prompt_conditionals_are_actually_rendered():
    """提示词里的 `{% if %}` 必须被渲染掉，不能原样发给模型。

    渲染器原来只替换 `{{ key }}`、不处理条件块，于是人设段落即使为空也会出现，
    首轮与后续轮的两套输出骨架连同 `{% if %}` / `{% else %}` 一起塞给模型——
    "首轮 feedback 必须为空"这条约定实际上从未传达。
    """
    with_persona = _session(persona="你要刻意打断候选人")
    without = _session(persona="")

    rendered_with = build_interview_messages(with_persona, index=1)[0]["content"]
    rendered_without = build_interview_messages(without, index=1)[0]["content"]

    for text in (rendered_with, rendered_without):
        assert "{%" not in text
        assert "{{" not in text
    assert "你要刻意打断候选人" in rendered_with
    # 没填人设时整段不出现，而不是留一个空标题。
    assert "你要刻意打断候选人" not in rendered_without

    # 首轮只给一套骨架（feedback 必须为空），后续轮才给点评那一套。
    later = build_interview_messages(_session(), index=2)[0]["content"]
    assert later.count('"feedback"') >= 1
    assert rendered_with.count('"question"') == 1


# ===== 自动轮数（rounds_min）：AI 按表现判断收尾，区间上限强制收尾 =====


def test_auto_rounds_validation():
    from app.schemas.interview import MAX_INTERVIEW_ROUNDS, MIN_INTERVIEW_ROUNDS

    assert InterviewCreate(job_id=1, resume_id=1).rounds_min is None
    # 下限必须小于上限，否则区间退化成一个数，"未知感"无从谈起。
    with pytest.raises(Exception):
        InterviewCreate(job_id=1, resume_id=1, rounds=6, rounds_min=6)
    with pytest.raises(Exception):
        InterviewCreate(job_id=1, resume_id=1, rounds=3, rounds_min=5)
    assert InterviewCreate(job_id=1, resume_id=1, rounds=9, rounds_min=3).rounds_min == 3
    # 前端「自动」档的实际提交对：rounds=硬性保险上限、rounds_min=产品允许的最小轮数
    # （曾经提交过模式开关值 1，被这里的 ge=MIN_INTERVIEW_ROUNDS 拦成 422）。
    assert InterviewCreate(
        job_id=1, resume_id=1, rounds=MAX_INTERVIEW_ROUNDS, rounds_min=MIN_INTERVIEW_ROUNDS
    )


def test_prompt_auto_rounds_branch_hides_exact_total():
    """自动轮数模式：提示词改走"自动收尾"分支——不出现任何轮数范围或精确计划，
    何时收尾完全交给模型判断。"""
    auto = _session(rounds=9, rounds_min=3)
    fixed = _session(rounds=3)

    auto_system = build_interview_messages(auto, index=2)[0]["content"]
    fixed_system = build_interview_messages(fixed, index=2)[0]["content"]

    assert "自动收尾" in auto_system
    assert "什么时候结束完全由你判断" in auto_system
    # 任何轮数范围/上限都不再进提示词（3 是 rounds_min，9 是 rounds，都不许出现）。
    assert "最早第 3 轮" not in auto_system
    assert "最迟第 9 轮" not in auto_system
    assert "9 轮" not in auto_system
    # 角色设定里的"计划轮数：N 轮"行不再出现（done 字段说明里的措辞共用，不算暴露）。
    assert "- 计划轮数" not in auto_system
    # 固定模式一切照旧。
    assert "计划轮数：3 轮" in fixed_system
    assert "自动收尾" not in fixed_system
    for text in (auto_system, fixed_system):
        assert "{%" not in text
        assert "{{" not in text

    # 用户消息里的进度同理：自动模式不暴露"第 2 / 9 轮"，也不报区间。
    auto_user = build_interview_messages(auto, index=2)[1]["content"]
    fixed_user = build_interview_messages(fixed, index=2)[1]["content"]
    assert "第 2 轮（自动收尾" in auto_user
    assert "最早第" not in auto_user
    assert "第 2 / 9 轮" not in auto_user
    assert "第 2 / 3 轮" in fixed_user


def test_api_auto_rounds_model_driven_finish(client, db_session, monkeypatch):
    """自动轮数：到了最早收尾轮数之后，AI 置 done 就收尾；rounds_min 原样落库并随详情返回。

    0066 起 ``rounds_min`` 是**硬性下限**（见 ``test_api_auto_rounds_ignores_early_done``），
    所以这里必须先把 ``rounds_min`` 轮答满，AI 的 done 才会被接受。
    """
    _configure(
        monkeypatch,
        [
            {"question": "第一题", "feedback": "", "done": False},
            {"question": "第二题", "feedback": "不错", "done": False},
            {"question": "第三题", "feedback": "继续", "done": False},
            {"question": "收尾语：面试结束", "feedback": "可以", "done": True},
        ],
    )
    created = _start(client, db_session, rounds=9, rounds_min=3)
    assert created.status_code == 201, created.text
    session = created.json()
    assert session["rounds_min"] == 3
    assert session["status"] == "active"

    for index in range(3):
        result = client.post(f"/api/interview/{session['id']}/answers", json={"content": "回答"})
        assert result.status_code == 200
        assert result.json()["finished"] is (index == 2)
        # 自动收尾同样只收盘：needs_report 让界面切到决策卡，而不是等一份不存在的报告。
        assert result.json()["needs_report"] is (index == 2)
    detail = client.get(f"/api/interview/{session['id']}").json()
    assert detail["status"] == "finished"
    assert detail["rounds_min"] == 3


def test_api_auto_rounds_ignores_early_done(client, db_session, monkeypatch):
    """AI 在 rounds_min 之前就置 done：忽略这次收尾，面试继续。

    真实场景：选「自动」后模型第 2 轮就说"聊得差不多了"，用户看到的就是"He 只问了两个
    问题"。提示词已经要求别过早收束，但提示词拦不住，所以接口层必须有这层兜底。
    """
    _configure(
        monkeypatch,
        [
            {"question": "第一题", "feedback": "", "done": False},
            {"question": "收尾语：今天先到这里", "feedback": "可以", "done": True},
            {"question": "第二题", "feedback": "继续", "done": False},
        ],
    )
    session_id = _start(client, db_session, rounds=9, rounds_min=3).json()["id"]

    first = client.post(f"/api/interview/{session_id}/answers", json={"content": "回答"})
    assert first.status_code == 200
    # 第 1 个回答之后远未到 rounds_min=3：done 被忽略，会话仍是 active。
    assert first.json()["finished"] is False
    assert first.json()["session"]["status"] == "active"

    # 模型给的那句话仍然作为下一题存下来，用户不会卡在"没有问题可答"。
    detail = client.get(f"/api/interview/{session_id}").json()
    assert detail["messages"][-1]["content"] == "收尾语：今天先到这里"
    assert detail["answered_rounds"] == 1


def test_api_auto_rounds_cap_forces_finish(client, db_session, monkeypatch):
    """AI 一直不置 done：答满区间上限（rounds）时代码强制收尾，不会无限问下去。"""
    _configure(
        monkeypatch,
        [
            {"question": f"第 {index} 题", "feedback": "继续", "done": False}
            for index in range(1, 5)
        ],
    )
    session_id = _start(client, db_session, rounds=4, rounds_min=3).json()["id"]

    for index in range(1, 5):
        result = client.post(f"/api/interview/{session_id}/answers", json={"content": "回答"})
        assert result.status_code == 200
        assert result.json()["finished"] is (index == 4)

    detail = client.get(f"/api/interview/{session_id}").json()
    assert detail["status"] == "finished"
    assert detail["answered_rounds"] == 4


# ===== 面试教练：答不上来时的参考答案（2026-11-08）=====
#
# 与面试官是两条独立轨道：教练读候选人的全部资料，教他怎么答；
# 参考答案**不进评分**，也不写任何消息（候选人仍要自己作答）。


def test_parse_coach_answer_keeps_fields_and_defaults_grounded_false():
    """缺 grounded 时按 false：宁可保守标注"不完全有据"，也不谎称全来自资料。"""
    from app.services.interview.interview_coach import parse_coach_answer

    parsed = parse_coach_answer(
        '{"answer": "我做过 A 项目", "outline": ["先说结论"], "sources": ["A 项目"]}'
    )
    assert parsed["answer"] == "我做过 A 项目"
    assert parsed["outline"] == ["先说结论"]
    assert parsed["sources"] == ["A 项目"]
    assert parsed["grounded"] is False


def test_parse_coach_answer_survives_non_json_output():
    """模型偶尔不回 JSON：按纯文本答案兜底，绝不把异常抛给前端。"""
    from app.services.interview.interview_coach import parse_coach_answer

    parsed = parse_coach_answer("这道题你可以先讲结论，再举项目。")
    assert parsed["answer"].startswith("这道题你可以")
    assert parsed["grounded"] is False
    assert parsed["gaps"] == []


def test_coach_prompt_reads_profile_not_only_resume(db_session):
    """教练必须能读到资料库与事实台账——只喂简历等于把用户最真实的弹药丢掉。

    这是本功能的核心契约：参考答案要"从他自己的资料里长出来"，
    资料库里有大量没写进简历的真实经历（简历受篇幅限制写不全）。
    """
    from app.services.interview.interview_coach import build_coach_messages

    class _FakeSession:
        interview_type = "技术面"
        difficulty = "中级"
        job_title = "AI 应用工程师"
        company = "示例公司"
        messages = []

    messages = build_coach_messages(
        db_session, _FakeSession(), resume_text="简历内容", job_text="JD 内容"
    )
    payload = json.loads(messages[1]["content"])
    assert "简历内容" in payload["候选人的简历"]
    # 三个数据源都必须出现在提示词里（资料库/台账为空时是占位文案，但键必须在）
    assert "候选人的资料库（全部条目，未写入简历的也在里面）" in payload
    assert "已确认的事实台账" in payload
    # JD 只用于判断角度，提示词里必须写清"不要据此编造经历"
    jd_key = "目标岗位的招聘信息（只用于判断该答哪个角度，不要据此编造经历）"
    assert jd_key in payload


def test_api_coach_answer_returns_reference_without_touching_transcript(
    client, db_session, monkeypatch
):
    """教练接口不写消息、不改状态、不影响已答轮数——它只是"给一份参考答案"。"""
    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})

    before = client.get(f"/api/interview/{session_id}").json()

    reference = json.dumps(
        {
            "answer": "我在 A 项目里用 ComfyUI 搭了 7 套工作流，产出 20 部成片。",
            "outline": ["先说做过什么", "再给数字"],
            "sources": ["AIGC 短视频生产体系"],
            "gaps": [],
            "grounded": True,
        }
    )

    class _CoachProvider:
        async def chat(self, _messages, *, thinking: bool = True):
            return reference

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_CoachProvider(), "test-model")
    )

    result = client.post(f"/api/interview/{session_id}/coach-answer")
    assert result.status_code == 200
    body = result.json()
    assert body["answer"].startswith("我在 A 项目里")
    assert body["grounded"] is True
    assert body["sources"] == ["AIGC 短视频生产体系"]

    after = client.get(f"/api/interview/{session_id}").json()
    # 2026-11-08 口径更新：参考答案**会**落一条 coach 消息（报告末尾附录要取它），
    # 但它不是候选人说的话——轮次与状态都不该变。
    coach = [item for item in after["messages"] if item["role"] == "coach"]
    assert len(coach) == 1
    assert after["answered_rounds"] == before["answered_rounds"]
    assert after["status"] == before["status"]


def test_api_coach_answer_reports_model_failure_as_502(client, db_session, monkeypatch):
    """模型挂了给 502，而不是把空答案当成功返回（用户会以为"我没资料"）。"""
    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})

    class _BrokenProvider:
        async def chat(self, _messages, *, thinking: bool = True):
            raise RuntimeError("模型超时")

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_BrokenProvider(), "test-model")
    )

    assert client.post(f"/api/interview/{session_id}/coach-answer").status_code == 502


def test_coach_answer_is_stored_but_never_enters_the_transcript(client, db_session, monkeypatch):
    """参考答案落库（供报告附录与复盘），但**绝不**进 transcript / 评分。

    这是双轨设计的核心不变量：教练说的话不是候选人说的话。
    落库后消息数会 +1，但 answered_rounds 不变、面试官上下文里看不到它。
    """
    from app.models.interview import MESSAGE_PHASE_COACH
    from app.services.interview.interview import _transcript

    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})

    reference = json.dumps(
        {
            "answer": "我在 A 项目里搭了 7 套工作流。",
            "outline": ["先说做过什么"],
            "sources": ["A 项目"],
            "gaps": [],
            "grounded": True,
        }
    )

    class _CoachProvider:
        async def chat(self, _messages, *, thinking: bool = True):
            return reference

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_CoachProvider(), "test-model")
    )
    assert client.post(f"/api/interview/{session_id}/coach-answer").status_code == 200

    detail = client.get(f"/api/interview/{session_id}").json()
    coach_messages = [item for item in detail["messages"] if item["role"] == "coach"]
    assert len(coach_messages) == 1
    # 参考答案对应哪道题，必须记下来（复盘要看）
    assert coach_messages[0]["content"].startswith("我在 A 项目里")

    session = db_session.get(InterviewSession, session_id)
    db_session.refresh(session)
    assert session is not None
    stored = [m for m in session.messages if m.phase == MESSAGE_PHASE_COACH]
    assert stored and stored[0].context["question"] == "第一题"
    # 关键：面试官看到的 transcript 里没有教练的话
    transcript = _transcript(session)
    assert "我在 A 项目里搭了 7 套工作流" not in transcript
    # 轮次也不受影响
    assert detail["answered_rounds"] == 1


def test_report_appends_coach_references_only_when_used(client, db_session, monkeypatch):
    """报告末尾附参考答案；没点过就不出现这个键（旧报告形状逐字节不变）。"""
    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})

    # 没点过参考答案：报告里不该有这个键
    finished = client.post(f"/api/interview/{session_id}/finish").json()
    assert "coach_references" not in (finished.get("report") or {})


def test_report_carries_coach_reference_with_question(client, db_session, monkeypatch):
    """点过参考答案后，报告里要能读到「哪道题 + 参考答案」。"""
    reference = json.dumps(
        {
            "answer": "我在 A 项目里搭了 7 套工作流。",
            "outline": ["先说做过什么"],
            "sources": ["A 项目"],
            "gaps": ["没有 To B 客户对接"],
            "grounded": False,
        }
    )

    class _Provider:
        """同一个 provider 既当面试官（出题）又当教练（给答案）。"""

        async def chat(self, messages, *, thinking: bool = True):
            system = messages[0]["content"] if messages else ""
            if "面试教练" in system:
                return reference
            return json.dumps({"question": "第一题", "feedback": "点评", "done": False})

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_Provider(), "test-model")
    )

    async def build_report(_provider, _session_):
        return _DEFAULT_REPORT

    monkeypatch.setattr("app.api.interview.generate_report", build_report)

    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})
    assert client.post(f"/api/interview/{session_id}/coach-answer").status_code == 200

    finished = client.post(f"/api/interview/{session_id}/finish").json()
    refs = (finished.get("report") or {}).get("coach_references") or []
    assert len(refs) == 1
    assert refs[0]["question"] == "第一题"
    assert refs[0]["answer"].startswith("我在 A 项目里")
    assert refs[0]["gaps"] == ["没有 To B 客户对接"]
    assert refs[0]["grounded"] is False


def test_coach_answer_backfills_appendix_into_existing_report(client, db_session, monkeypatch):
    """已出报告的会话再点参考答案：附录要就地补进报告，不用重新生成报告。

    赛后复盘是最常见的使用时机——用户翻回一场结束的面试，哪题没答上就点一下。
    如果此时报告不更新，他回看报告会找不到刚看到的答案。
    """
    _configure(monkeypatch, [{"question": "第一题", "feedback": "", "done": False}])
    session_id = _start(client, db_session, rounds=3).json()["id"]
    client.post(f"/api/interview/{session_id}/answers", json={"content": "不知道"})

    # 先出报告（此时还没点过参考答案 → 没有附录）
    finished = client.post(f"/api/interview/{session_id}/finish").json()
    assert "coach_references" not in (finished.get("report") or {})

    reference = json.dumps(
        {
            "answer": "我在 A 项目里搭了 7 套工作流。",
            "outline": ["先说做过什么"],
            "sources": ["A 项目"],
            "gaps": [],
            "grounded": True,
        }
    )

    class _CoachProvider:
        async def chat(self, _messages, *, thinking: bool = True):
            return reference

    monkeypatch.setattr(
        "app.api.interview._require_provider", lambda _db: (_CoachProvider(), "test-model")
    )
    assert client.post(f"/api/interview/{session_id}/coach-answer").status_code == 200

    # 报告已被就地补上附录，且原有评分不变
    detail = client.get(f"/api/interview/{session_id}").json()
    report = detail["report"] or {}
    assert report.get("coach_references"), "报告应被补上参考答案附录"
    assert report["coach_references"][0]["answer"].startswith("我在 A 项目里")
    assert report["score"] == _DEFAULT_REPORT["score"]
    assert report["summary"] == _DEFAULT_REPORT["summary"]
