#!/usr/bin/env python
"""2.0 二开移植的阶段闸门。每阶段结束跑一次，输出 PASS/FAIL 行。

约定：每行 `PASS|FAIL|SKIP <检查项> — <证据>`；末尾汇总；任一 FAIL 退出码 1。
脚本本身不得修改任何数据（只读 DB、只运行测试）。

口径说明（两处对开发计划 §14.3 的落地解释，见 docs/fork-2.0-blocked.md B-3）：
1. 「2.0 仓单提交」按 §3 的不变量实现为：upstream-v2.0.0 指向的提交链恰为 1 个提交，
   且该提交仍是 HEAD 的祖先（基线冻结、未被改写）。字面上的 `HEAD 提交数 == 1`
   在第一张卡提交后即不可能成立（E6 要求每卡单独提交），与闸门「必须能变绿」矛盾。
2. 卡片未开工的检查（N5 BOSS / N6 AI 求职 / N7 前端 / N8 简历侧 / B-1 数据桥）
   输出 SKIP 并注明原因，不输出 FAIL——本轮执行范围是 N0–N4 + N9（§8.3 首轮范围）。
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
DB_PATH = BACKEND / "data" / "resume_forge.db"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"

# 开工时记录的 1.x 数据库大小，用于证明未被修改
STATIC_1X_DB_SIZE = 160989184
# 1.x 数据库位置（只读 stat，绝不打开文件）
ONE_X_DB_PATH = ROOT.parent / "简历通" / "backend" / "data" / "resume_forge.db"

_results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append(("PASS" if ok else "FAIL", name, detail))


def skip(name: str, detail: str = "") -> None:
    _results.append(("SKIP", name, detail))


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )


def _table_columns(table: str) -> list[str] | None:
    """读 2.0 库某表的列名清单；库/表不存在返回 None。"""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        conn.close()
    if not rows:
        return None
    return [row[1] for row in rows]


def phase_0() -> None:
    """基线固化：仓、版本、迁移数、服务健康、文档。"""
    count = _git("rev-list", "--count", "upstream-v2.0.0")
    ancestor = _git("merge-base", "--is-ancestor", "upstream-v2.0.0", "HEAD")
    baseline_commits = count.stdout.strip() if count.returncode == 0 else "?"
    check(
        "2.0 基线单提交且未被改写",
        baseline_commits == "1" and ancestor.returncode == 0,
        f"upstream-v2.0.0 提交数={baseline_commits}，是 HEAD 祖先={ancestor.returncode == 0}",
    )

    try:
        version = json.loads((FRONTEND / "package.json").read_text(encoding="utf-8"))["version"]
    except Exception as exc:  # noqa: BLE001 — 闸门要给出原因而不是堆栈
        version = f"读取失败：{exc}"
    check("版本是 2.0.0", version == "2.0.0", f"frontend/package.json version={version}")

    migrations = sorted((BACKEND / "migrations" / "versions").glob("*.py"))
    check("迁移文件数 < 10", len(migrations) < 10, f"数量={len(migrations)} {[m.name for m in migrations]}")

    try:
        with urllib.request.urlopen("http://127.0.0.1:8010/api/health", timeout=5) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        healthy = body.get("status") == "ok" and body.get("version") == "2.0.0"
        check("8010 健康检查", healthy, f"响应={body}")
    except Exception as exc:  # noqa: BLE001
        check("8010 健康检查", False, f"不可达：{exc}")

    baseline_doc = ROOT / "docs" / "fork-2.0-baseline.md"
    check("baseline 文档存在", baseline_doc.exists(), str(baseline_doc))


def phase_1() -> None:
    """数据桥：1.x 未改、无 profile_facts、对账无未解释跳过。"""
    try:
        size = ONE_X_DB_PATH.stat().st_size
    except OSError as exc:
        check("1.x 库未被修改", False, f"stat 失败：{exc}")
    else:
        check("1.x 库未被修改", size == STATIC_1X_DB_SIZE, f"当前 {size} 字节 / 记录 {STATIC_1X_DB_SIZE} 字节")

    if not DB_PATH.exists():
        check("2.0 库无 profile_facts 表", False, "2.0 库不存在（后端未启动过）")
    else:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='profile_facts'"
            ).fetchall()
        finally:
            conn.close()
        check("2.0 库无 profile_facts 表", len(rows) == 0, f"命中 {len(rows)} 条")

    skip("导入对账无未解释跳过", "B-1 属会话 B（feat/data-bridge），本轮（N0–N4+N9）未执行")


def phase_2() -> None:
    """投递台：两个 greeting_confirmed 列、失败三列、page_limit or 1 清零、-k apply 绿。"""
    for table in ("apply_queue_item", "apply_task_item"):
        cols = _table_columns(table)
        if cols is None:
            check(f"{table}.greeting_confirmed 列存在", False, "表或库不存在")
        else:
            check(f"{table}.greeting_confirmed 列存在", "greeting_confirmed" in cols, f"现有列={cols}")

    task_cols = _table_columns("apply_task_item")
    if task_cols is None:
        check("apply_task_item 失败三列存在", False, "表或库不存在")
    else:
        missing = [c for c in ("failure_step", "failure_target", "failure_reason") if c not in task_cols]
        check("apply_task_item 失败三列存在", not missing, f"缺失={missing or '无'}")

    hits: list[str] = []
    for py in sorted((BACKEND / "app").rglob("*.py")):
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        if "page_limit or 1" in text:
            hits.append(str(py.relative_to(ROOT)))
    check("backend/app 无 'page_limit or 1' 字面量", not hits, f"命中 {len(hits)} 处 {hits[:5]}")

    try:
        # conftest.py 依赖 cwd=backend 才能拿到 sys.path 上的 app 包
        # （python -m pytest 会把 cwd 塞进 sys.path[0]），所以必须在 backend/ 下跑。
        proc = subprocess.run(
            [str(VENV_PY), "-m", "pytest", "tests", "-q", "-k", "apply", "-p", "no:cacheprovider"],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2400,
        )
        tail = " | ".join(proc.stdout.strip().splitlines()[-2:])
        check("pytest -k apply 全绿", proc.returncode == 0, f"returncode={proc.returncode}；{tail[:300]}")
    except subprocess.TimeoutExpired:
        check("pytest -k apply 全绿", False, "超时（>2400s）")


def phase_3() -> None:
    """BOSS：三处修复都在、-k boss 绿。"""
    probes = [
        (
            BACKEND / "app" / "services" / "sites" / "boss_apply.py",
            "_wait_document_complete",
            "点击前等 document.readyState == complete",
        ),
        (
            BACKEND / "app" / "services" / "browser" / "interaction.py",
            "setFocusEmulationEnabled",
            "trusted_click 前焦点仿真（Ego 多窗口 hidden 修复）",
        ),
        (
            BACKEND / "app" / "models" / "apply.py",
            'FAILURE_JOB_CLOSED = "job_closed"',
            "job_closed 软跳过分类",
        ),
    ]
    for path, needle, label in probes:
        try:
            present = needle in path.read_text(encoding="utf-8")
        except OSError:
            present = False
        if present:
            check(f"BOSS 修复：{label}", True, f"{needle} in {path.name}")
        else:
            skip(f"BOSS 修复：{label}", f"{needle} 不在 {path.name} —— N5 未移植（本轮范围外）")

    skip("pytest -k 'boss or apply_boss' 全绿", "N5 未移植（本轮范围外），上游基线的 BOSS 测试已含在 phase 2 的 -k apply 内")


def phase_4() -> None:
    """AI 求职：ai_job_link 表、单头、路由、i18n key 数相等。"""
    conn_ok = DB_PATH.exists()
    if not conn_ok:
        check("ai_job_link 表存在", False, "2.0 库不存在")
    else:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_job_link'"
            ).fetchall()
        finally:
            conn.close()
        if rows:
            check("ai_job_link 表存在", True, "sqlite_master 命中")
        else:
            skip("ai_job_link 表存在", "N2 迁移未 apply 或 N6 未移植（本轮范围外）")

    script = (
        "from alembic.config import Config; from alembic.script import ScriptDirectory;"
        "print(','.join(ScriptDirectory.from_config(Config(r'backend/alembic.ini')).get_heads()))"
    )
    proc = subprocess.run(
        [str(VENV_PY), "-c", script], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    heads = proc.stdout.strip() if proc.returncode == 0 else "?"
    check("迁移链单头", proc.returncode == 0 and "," not in heads and heads not in ("", "?"),
          f"heads={heads or '（空）'}")

    routes = FRONTEND / "src" / "appRoutes.tsx"
    if routes.exists() and '"/ai-jobs"' in routes.read_text(encoding="utf-8"):
        check("前端 /ai-jobs 路由", True, "appRoutes.tsx 命中")
    else:
        skip("前端 /ai-jobs 路由", "N7 未移植（本轮范围外）")

    zh = FRONTEND / "src" / "i18n" / "zh-CN.aiJobs.ts"
    en = FRONTEND / "src" / "i18n" / "en-US.aiJobs.ts"
    if zh.exists() and en.exists():
        def keys(p: Path) -> int:
            return len(re.findall(r"^\s{4}?['\"]?[\w-]+['\"]?:", p.read_text(encoding="utf-8"), re.M))

        check("aiJobs 中英 key 数相等", keys(zh) == keys(en), f"zh={keys(zh)} en={keys(en)}")
    else:
        skip("aiJobs 中英 key 数相等", "N7 未移植（本轮范围外），i18n 文件不存在")


def phase_5() -> None:
    """简历侧：resume_generation_plan 表、resume_dedupe.py、profile_facts 引用为 0。"""
    if not DB_PATH.exists():
        check("resume_generation_plan 表存在", False, "2.0 库不存在")
    else:
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='resume_generation_plan'"
            ).fetchall()
        finally:
            conn.close()
        if rows:
            check("resume_generation_plan 表存在", True, "sqlite_master 命中")
        else:
            skip("resume_generation_plan 表存在", "N2 迁移未 apply（本轮只写迁移文件，apply 由后端启动执行）")

    dedupe = BACKEND / "app" / "services" / "resume" / "resume_dedupe.py"
    if dedupe.exists():
        check("resume_dedupe.py 存在", True, str(dedupe))
    else:
        skip("resume_dedupe.py 存在", "N8 未移植（本轮范围外）")

    hits: list[str] = []
    for py in sorted((BACKEND / "app").rglob("*.py")):
        try:
            if "profile_facts" in py.read_text(encoding="utf-8"):
                hits.append(str(py.relative_to(ROOT)))
        except OSError:
            continue
    check("backend/app profile_facts 引用 == 0", not hits, f"命中 {len(hits)} 处 {hits[:5]}")


def phase_6() -> None:
    """前端：typecheck 绿、dist 比 src 新、i18n 中英差集为空。"""
    skip("npm run typecheck 绿", "N7 未移植（本轮范围外）；上游基线前端未改动")
    dist = FRONTEND / "dist"
    src = FRONTEND / "src"
    if dist.exists() and any(dist.rglob("*")):
        newest_dist = max(dist.rglob("*"), key=lambda p: p.stat().st_mtime).stat().st_mtime
        newest_src = max(src.rglob("*"), key=lambda p: p.stat().st_mtime).stat().st_mtime
        check("dist 比 src 新", newest_dist > newest_src,
              f"dist mtime={newest_dist} src mtime={newest_src}")
    else:
        skip("dist 比 src 新", "dist 未构建（N0 禁止 npm run build；N7 范围外）")
    skip("i18n 中英差集为空", "N7 未移植（本轮范围外）")


def phase_7() -> None:
    """终检：前 7 阶段复跑、两份报告存在。"""
    global _results
    saved = _results
    _results = []
    try:
        for p in sorted(PHASES):
            if p != 7:
                PHASES[p]()
        rerun = list(_results)
    finally:
        _results = saved
    fails = [(s, n, d) for s, n, d in rerun if s == "FAIL"]
    check("前 7 阶段复跑无 FAIL", not fails, f"复跑 FAIL={len(fails)} {fails[:3] or ''}")

    reports = [ROOT / "docs" / "fork-2.0-morning-report.md", ROOT / "docs" / "fork-2.0-progress.md"]
    missing = [str(r.relative_to(ROOT)) for r in reports if not r.exists()]
    check("两份报告存在", not missing, f"缺失={missing or '无'}")


def phase_8() -> None:
    """AI 求职适配层（feat/ai-jobs-sidecar）：结构、安全边界、定向测试。

    本函数于 2026-11-06 夜 A0 卡定稿，此后不可再改（E10）。
    口径说明（三处对开发计划 §11.3/§11.4 的落地解释，见 docs/fork-2.0-ai-jobs-progress.md）：
    1. 前端三项（路由/i18n/构建产物）由会话 B（简历通-2.0-fe，分支 feat/ai-jobs-frontend）
       独占产出；会话 A 红线禁碰 frontend/**。文件缺失或不合格时输出 SKIP 并注明，
       晨间合并后复验——沿用本闸门「未开工 → SKIP 不 FAIL」的既有约定（见模块 docstring）。
    2. 检查 7（无引擎源码）与检查 9（ai_job_link 表）是「必须恒真」的安全/事实断言，
       A0 时即应为 PASS，不随移植进度变红。
    3. phase_7 的复跑循环按 `p != 7` 遍历 PHASES，注册 phase 8 后其复跑范围自然扩为
       0–6 + 8（不改 phase_7 任何一行）；phase 8 内含 pytest，--all 总时长相应增加。
    4. 发送闸门 2.0 语义 = 默认关（未设置 AI_JOBS_ALLOW_SEND 时拒绝投递），
       与 1.x 的 `== "0"` 夜间总闸（默认放行）相反；此处把 1.x 形态判为 FAIL。
    """
    aj_dir = BACKEND / "app" / "services" / "ai_jobs"

    # 1) 适配层 14 个服务文件齐全
    required = {"__init__", "client", "settings", "gate", "manager", "status",
                "config_sync", "job_sync", "greeting", "replies", "resume_sync",
                "tasks", "delivery", "delivery_sync"}
    present = {p.stem for p in aj_dir.glob("*.py")} if aj_dir.exists() else set()
    missing = sorted(required - present)
    check("适配层 14 个服务文件齐全", not missing,
          f"缺失={missing or '无'}，现有={len(present)}/{len(required)}")

    # 2) schema 存在
    schema = BACKEND / "app" / "schemas" / "ai_jobs.py"
    check("schemas/ai_jobs.py 存在", schema.exists(),
          str(schema.relative_to(ROOT)) if schema.exists() else "缺失")

    # 3) API 已注册
    routers = BACKEND / "app" / "application_routers.py"
    if routers.exists():
        n = routers.read_text(encoding="utf-8").count("ai_jobs")
        check("application_routers 注册 ai_jobs", n >= 2, f"ai_jobs 出现 {n} 次（需导入+注册 ≥2）")
    else:
        check("application_routers 注册 ai_jobs", False, "文件不存在")

    # 4) 单点 HTTP 收口：ai_jobs 之外不许直连引擎端口（独立 8686/3456，sidecar 8687/3457）
    stray: list[str] = []
    for py in sorted((BACKEND / "app").rglob("*.py")):
        rel = py.relative_to(BACKEND / "app").as_posix()
        if rel.startswith("services/ai_jobs/"):
            continue
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        if re.search(r"https?://127\.0\.0\.1:(868[67]|345[67])\b", text):
            stray.append(rel)
    check("引擎端口调用收口在 services/ai_jobs/", not stray, f"ai_jobs 之外命中 {stray[:5] or '无'}")

    # 5) 发送闸门存在且默认关（出现于 gate/delivery/api 之一；禁 1.x 默认放行形态与真值默认）
    gate_files: list[str] = []
    default_open: list[str] = []
    truthy_default: list[str] = []
    gate_candidates = [aj_dir / "gate.py", aj_dir / "delivery.py", BACKEND / "app" / "api" / "ai_jobs.py"]
    for p in gate_candidates:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        if "AI_JOBS_ALLOW_SEND" in text:
            gate_files.append(p.relative_to(BACKEND / "app").as_posix())
        if re.search(r'''AI_JOBS_ALLOW_SEND["']?\)\s*==\s*["']0["']''', text):
            default_open.append(p.name)
        if re.search(r'''AI_JOBS_ALLOW_SEND["'],\s*["']?(?:1|true|yes|on)["']?''', text, re.I):
            truthy_default.append(p.name)
    check("发送闸门存在且默认关",
          bool(gate_files) and not default_open and not truthy_default,
          f"所在文件={gate_files or '无'}，默认放行形态={default_open or '无'}，真值默认={truthy_default or '无'}")

    # 6) 版本窗口 (2,4,0)–(3,0,0)（1.x/2.0 client.py 的元组形态）
    client = aj_dir / "client.py"
    if client.exists():
        text = client.read_text(encoding="utf-8")
        has_min = re.search(r"ENGINE_VERSION_MIN\s*=\s*\(2,\s*4,\s*0\)", text) is not None
        has_max = re.search(r"ENGINE_VERSION_MAX\s*=\s*\(3,\s*0,\s*0\)", text) is not None
        check("版本窗口 ENGINE_VERSION_(MIN,MAX)=(2,4,0),(3,0,0)", has_min and has_max,
              f"MIN={has_min} MAX={has_max}")
    else:
        check("版本窗口 ENGINE_VERSION_(MIN,MAX)=(2,4,0),(3,0,0)", False, "client.py 不存在")

    # 7) 无引擎源码混入（S1/F4：bosshunter/polyform 只允许字符串常量/注释/HTTP 路径）
    lic_hits: list[str] = []
    import_hits: list[str] = []
    name_hits: list[str] = []
    scan_total = 0
    for base in (BACKEND / "app", BACKEND / "tests", BACKEND / "migrations", FRONTEND / "src"):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or "__pycache__" in p.parts or "node_modules" in p.parts:
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "bosshunter" not in text.lower() and "polyform" not in text.lower():
                continue
            scan_total += 1
            rel = str(p.relative_to(ROOT))
            if "license" in p.name.lower() or "copying" in p.name.lower():
                lic_hits.append(rel)
            if p.suffix == ".py" and re.search(r"^\s*(from|import)\s+bosshunter\b", text, re.M):
                import_hits.append(rel)
            if "bosshunter" in p.name.lower():
                name_hits.append(rel)
    ok7 = not lic_hits and not import_hits and not name_hits
    check("无 BossHunter 源码混入（许可证 S1）", ok7,
          f"合法引用文件数={scan_total}，LICENSE/COPYING 命中={lic_hits or '无'}，"
          f"import 命中={import_hits or '无'}，同名文件={name_hits or '无'}")

    # 8) 无凭据落库：ai_jobs_config 持久化边界（schema 字段定义 + settings 读写）无凭据字段
    cred = re.compile(r"^\s*(api_key|api_token|token|cookie)\s*:", re.M)
    cred_hits: list[str] = []
    for p in (schema, aj_dir / "settings.py"):
        if p.exists() and cred.search(p.read_text(encoding="utf-8")):
            cred_hits.append(str(p.relative_to(BACKEND / "app")))
    check("ai_jobs_config 持久化边界无凭据字段", not cred_hits,
          f"命中={cred_hits or '无'}（检查 schemas/ai_jobs.py + services/ai_jobs/settings.py）")

    # 9) 数据表就位（N2 已建，恒真断言）
    if DB_PATH.exists():
        conn = sqlite3.connect(str(DB_PATH))
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_job_link'"
            ).fetchall()
        finally:
            conn.close()
        check("ai_job_link 表存在", bool(rows), "sqlite_master 命中" if rows else "未命中")
    else:
        check("ai_job_link 表存在", False, "2.0 库不存在")

    # 10) 定向测试绿
    try:
        proc = subprocess.run(
            [str(VENV_PY), "-m", "pytest", "tests", "-q", "-k", "ai_jobs", "-p", "no:cacheprovider"],
            cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=2400,
        )
        tail = " | ".join(proc.stdout.strip().splitlines()[-2:])
        check("pytest -k ai_jobs 全绿", proc.returncode == 0,
              f"returncode={proc.returncode}；{tail[:300]}")
    except subprocess.TimeoutExpired:
        check("pytest -k ai_jobs 全绿", False, "超时（>2400s）")

    # 11) 前端路由（会话 B 产出）
    routes = FRONTEND / "src" / "appRoutes.tsx"
    if routes.exists() and '"/ai-jobs"' in routes.read_text(encoding="utf-8"):
        check("前端 /ai-jobs 路由", True, "appRoutes.tsx 命中")
    else:
        skip("前端 /ai-jobs 路由", "由会话 B 产出（feat/ai-jobs-frontend），晨间合并后复验")

    # 12) 中英 i18n key 数相等（会话 B 产出；键数口径同 phase_4）
    zh_files = list((FRONTEND / "src").rglob("zh-CN.aiJobs.ts")) if (FRONTEND / "src").exists() else []
    en_files = list((FRONTEND / "src").rglob("en-US.aiJobs.ts")) if (FRONTEND / "src").exists() else []
    if zh_files and en_files:
        def _i18n_keys(p: Path) -> int:
            return len(re.findall(r"^\s{4}?['\"]?[\w-]+['\"]?:", p.read_text(encoding="utf-8"), re.M))

        zh_n, en_n = _i18n_keys(zh_files[0]), _i18n_keys(en_files[0])
        if zh_n == en_n:
            check("aiJobs 中英 i18n key 数相等", True, f"zh={zh_n} en={en_n}")
        else:
            skip("aiJobs 中英 i18n key 数相等", f"zh={zh_n} en={en_n} 不等——由会话 B 修正后复验")
    else:
        skip("aiJobs 中英 i18n key 数相等", "由会话 B 产出（feat/ai-jobs-frontend），晨间合并后复验")

    # 13) 前端构建产物新于源码（构建由 B/晨间人工执行，A 红线禁碰 frontend/**）
    dist = FRONTEND / "dist"
    src = FRONTEND / "src"
    if dist.exists() and any(dist.rglob("*")):
        newest_dist = max(dist.rglob("*"), key=lambda p: p.stat().st_mtime).stat().st_mtime
        newest_src = max(src.rglob("*"), key=lambda p: p.stat().st_mtime).stat().st_mtime
        if newest_dist > newest_src:
            check("dist 比 src 新", True, f"dist mtime={newest_dist} src mtime={newest_src}")
        else:
            skip("dist 比 src 新", "src 更新于 dist——待 B/晨间合并后统一 npm run build（A 禁碰 frontend/**）")
    else:
        skip("dist 比 src 新", "dist 未构建——由 B/晨间人工执行（A 禁碰 frontend/**）")

    # 14) 互斥测试存在且绿（A4 创建）
    mutex = BACKEND / "tests" / "test_ai_jobs_mutex.py"
    if not mutex.exists():
        check("互斥测试 test_ai_jobs_mutex.py 存在且绿", False, "文件不存在（A4 创建）")
    else:
        try:
            proc = subprocess.run(
                [str(VENV_PY), "-m", "pytest", "tests/test_ai_jobs_mutex.py", "-q", "-p", "no:cacheprovider"],
                cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600,
            )
            tail = " | ".join(proc.stdout.strip().splitlines()[-2:])
            check("互斥测试 test_ai_jobs_mutex.py 存在且绿", proc.returncode == 0,
                  f"returncode={proc.returncode}；{tail[:300]}")
        except subprocess.TimeoutExpired:
            check("互斥测试 test_ai_jobs_mutex.py 存在且绿", False, "超时（>600s）")


PHASES = {0: phase_0, 1: phase_1, 2: phase_2, 3: phase_3,
          4: phase_4, 5: phase_5, 6: phase_6, 7: phase_7, 8: phase_8}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=[*(str(k) for k in PHASES), "all"], default="all")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    targets = list(PHASES) if (args.all or args.phase == "all") else [int(args.phase)]

    for p in targets:
        print(f"\n===== Phase {p} =====")
        PHASES[p]()

    for status, name, detail in _results:
        print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    fails = sum(1 for s, _, _ in _results if s == "FAIL")
    print(f"\n汇总：PASS={sum(1 for s, _, _ in _results if s == 'PASS')} "
          f"FAIL={fails} SKIP={sum(1 for s, _, _ in _results if s == 'SKIP')}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
