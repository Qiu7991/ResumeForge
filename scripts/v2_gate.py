#!/usr/bin/env python
r"""v2 整改的**阶段闸门**：每个 Phase 结束跑一次，输出 PASS/FAIL 行。

为什么要有这个脚本：整改方案里大量验收标准写成"看起来正常""四种导出一致"，
这类判断对执行模型（尤其是便宜模型）不可复现。这里把所有能机器判定的部分固化成
检查项，模型的唯一任务就是让闸门变绿——它不再需要"理解"不变量。

用法（仓库根，任一 Python 3.11+ 均可；需要读 DB 时用 backend/.venv）：

    backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --backup      # Phase 0：安全备份
    backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 0
    backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --phase 1
    ...
    backend\.venv\Scripts\python.exe -I scripts\v2_gate.py --all

约定：输出每行 `PASS|FAIL|SKIP <检查项> — <证据>`；末尾汇总；任一 FAIL 退出码 1。
**脚本本身不得修改任何数据**（只读 DB、只运行测试）——唯一例外是 `--backup`
（只新建一个 .bak 文件，不碰库）。
"""

from __future__ import annotations

import argparse
import ast
import datetime
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DB_PATH = BACKEND / "data" / "resume_forge.db"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"
APP = BACKEND / "app"
TESTS = BACKEND / "tests"

_results: list[tuple[str, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append(("PASS" if ok else "FAIL", name, detail))


def skip(name: str, detail: str = "") -> None:
    _results.append(("SKIP", name, detail))


def pytest(*targets: str) -> tuple[bool, str]:
    """跑一组测试，返回 (是否全绿, 末行输出)。

    目标文件不存在时直接报“文件不存在”——pytest 对“无测试收集”也返回非 0，
    但它的输出是 “1 warning in 0.01s”，对执行模型是误导（看起来像测试跑过且通过）。
    """
    missing = [t for t in targets if not (BACKEND / t).exists()]
    if missing:
        return False, f"测试文件不存在：{', '.join(missing)}"
    python = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    cmd = [str(python), "-m", "pytest", *targets, "-q"]
    proc = subprocess.run(
        cmd, cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=1800,
    )
    tail = (proc.stdout or proc.stderr or "").strip().splitlines()
    last = tail[-1] if tail else "no output"
    if proc.returncode == 5:
        return False, f"没有收集到测试（{last}）"
    return proc.returncode == 0, last


def read_db_rows() -> list[tuple[int, str | None, str | None, str]]:
    """(id, content, format_config, deleted_at) —— 只读打开。"""
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        return list(
            con.execute("select id, content, format_config, deleted_at from resume_record order by id")
        )
    finally:
        con.close()


def _cfg(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _doc(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------- phase 0


def make_backup() -> int:
    """Phase 0 的安全备份（`--backup`）。

    为什么不让执行模型手敲那段 Python：SQLite 在线备份是**唯一**在 WAL 模式下
    可靠的复制方式，而它需要多行脚本；便宜模型在 cmd/PowerShell 里粘贴多行
    heredoc 会失败，退化成 `cp`——那正好会丢 WAL 里的已提交事务（实测极端情况
    备份出来的库连表都没有）。把它做成一条命令，错误就消失了。

    只新建文件，不改库。应用运行中也能备份（SQLite 备份 API 会处理并发快照）。
    """
    if not DB_PATH.exists():
        print(f"FAIL 数据库不存在 — {DB_PATH}")
        return 1
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    target = DB_PATH.with_name(f"resume_forge.db.pre-v2-normalize-{stamp}.bak")
    try:
        with sqlite3.connect(DB_PATH) as source, sqlite3.connect(target) as dest:
            source.backup(dest)
            integrity = dest.execute("pragma integrity_check").fetchone()[0]
            rows = dest.execute("select count(*) from resume_record").fetchone()[0]
    except sqlite3.Error as exc:
        target.unlink(missing_ok=True)
        print(f"FAIL 备份失败 — {exc}")
        return 1
    wal = DB_PATH.with_name(DB_PATH.name + "-wal")
    print(f"PASS 备份已创建 — {target}")
    print(f"     integrity={integrity} resume_record={rows} 源库大小={DB_PATH.stat().st_size}")
    if wal.exists():
        print(f"     注：源库有活跃 WAL（{wal.stat().st_size} 字节），已由 backup API 合并进备份")
    return 0 if integrity == "ok" and rows >= 0 else 1


def alembic_heads() -> list[str]:
    """不依赖 alembic 包，直接解依赖图算 heads（down_revision 可能为空/字符串/元组）。"""
    revisions: dict[str, tuple[str, ...]] = {}
    for path in (BACKEND / "migrations" / "versions").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rev = down = None
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name, value = node.target.id, node.value
            elif isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                name = target.id if isinstance(target, ast.Name) else ""
                value = node.value
            else:
                continue
            if name == "revision" and isinstance(value, ast.Constant):
                rev = str(value.value)
            elif name == "down_revision":
                if isinstance(value, ast.Constant):
                    down = () if value.value is None else (str(value.value),)
                elif isinstance(value, (ast.Tuple, ast.List)):
                    down = tuple(
                        str(el.value) for el in value.elts if isinstance(el, ast.Constant)
                    )
        if rev:
            revisions[rev] = down or ()
    parents = {parent for downs in revisions.values() for parent in downs}
    return sorted(rev for rev in revisions if rev not in parents)


def phase0() -> None:
    doc = ROOT / "docs" / "quality" / "fork-baseline.md"
    if not doc.exists():
        check("基线文档存在", False, "缺少 docs/quality/fork-baseline.md")
    else:
        text = doc.read_text(encoding="utf-8")
        required = ["## 1. 环境", "## 2. 后端", "## 3. 前端", "## 4. 预存量失败清单"]
        missing = [m for m in required if m not in text]
        check("基线文档结构完整", not missing, f"缺少章节 {missing}" if missing else "ok")

    backups = sorted((BACKEND / "data").glob("resume_forge.db.pre-v2-normalize-*.bak"))
    if not backups:
        check("WAL 安全备份存在", False, "缺少 resume_forge.db.pre-v2-normalize-*.bak")
    else:
        newest = backups[-1]
        try:
            con = sqlite3.connect(f"file:{newest.as_posix()}?mode=ro", uri=True)
            integrity = con.execute("pragma integrity_check").fetchone()[0]
            count = con.execute("select count(*) from resume_record").fetchone()[0]
            con.close()
            ok = integrity == "ok" and count > 0
            check("备份可用（integrity=ok 且有数据）", ok, f"{newest.name} rows={count} {integrity}")
        except sqlite3.Error as exc:
            check("备份可用（integrity=ok 且有数据）", False, f"{newest.name}: {exc}")

    heads = alembic_heads()
    check("alembic 单头", len(heads) == 1, f"heads={heads}")


# ---------------------------------------------------------------- phase 1


def phase1() -> None:
    rows = read_db_rows()
    live = [(rid, raw) for rid, raw, _cfg_raw, deleted in rows if deleted is None]
    versions = {}
    for _rid, raw, _cfg_raw, _deleted in rows:
        version = _doc(raw).get("version")
        versions[version] = versions.get(version, 0) + 1
    check(
        "全部记录 content.version == 2（含软删）",
        set(versions) == {2},
        f"version 分布={versions}",
    )

    legacy = [
        (rid, key)
        for rid, _raw, cfg_raw, _deleted in rows
        for key in ("hidden_sections", "section_order")
        if key in _cfg(cfg_raw)
    ]
    check("format_config 不再含旧版式键", not legacy, f"残留={legacy[:10]}")

    script = ROOT / "scripts" / "normalize_resume_documents.py"
    if not script.exists():
        check("归一化脚本 dry-run 幂等", False, "缺少 scripts/normalize_resume_documents.py")
        skip("归一化脚本可执行", "脚本尚未创建")
        return
    python = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    proc = subprocess.run(
        [str(python), str(script), "--dry-run", "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    if proc.returncode != 0:
        check("归一化脚本 dry-run 幂等", False, (proc.stderr or proc.stdout).strip()[-300:])
        return
    try:
        report = json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        check("归一化脚本 dry-run 幂等", False, "stdout 末行不是 JSON（契约见文档 Phase 1）")
        return
    ok = report.get("v1", -1) == 0 and report.get("v2_normalized", -1) == 0
    check("归一化脚本 dry-run 幂等", ok, json.dumps(report, ensure_ascii=False)[:300])

    # 结构校验用后端自己的 parse_document（只读，不写库）。
    try:
        sys.path.insert(0, str(BACKEND))
        from app.schemas.resume_document import parse_document  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001 - 闸门要给出可读原因而不是栈
        skip("parse_document 全量通过", f"无法导入后端：{exc}")
        return
    bad = []
    for rid, raw in live:
        try:
            parse_document(_doc(raw))
        except Exception as exc:  # noqa: BLE001
            bad.append((rid, str(exc)[:80]))
    check("parse_document 全量通过（live）", not bad, f"失败={bad[:5]} rows={len(live)}")


# ---------------------------------------------------------------- phase 2


def _function(path: Path, name: str) -> ast.FunctionDef | None:
    if not path.exists():
        return None
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def phase2() -> None:
    invariants = APP / "services" / "resume" / "document_invariants.py"
    finalize = _function(invariants, "finalize_ai_document") if invariants.exists() else None
    check("存在 finalize_ai_document", finalize is not None, str(invariants.relative_to(ROOT)))

    record_py = APP / "services" / "resume" / "resume_record.py"
    save_record = _function(record_py, "save_record")
    if save_record is None:
        check("save_record 无 document= 旁路", False, "找不到 save_record")
    else:
        args = {a.arg for a in save_record.args.args + save_record.args.kwonlyargs}
        check("save_record 无 document= 旁路", "document" not in args, f"入参={sorted(args)}")

    callers = 0
    for path in APP.rglob("*.py"):
        if path == invariants:
            continue
        callers += path.read_text(encoding="utf-8").count("finalize_ai_document(")
    check("finalize 至少接入 2 处写入", callers >= 2, f"调用点={callers}")

    if finalize is None:
        skip("finalize 行为测试", "函数尚不存在")
    else:
        probe = """
import json, sys
sys.path.insert(0, r"{backend}")
from app.services.resume.document_invariants import finalize_ai_document
from app.schemas.resume_document import parse_document, MAX_LIST_VALUES
content = {{
  "name": "闸门探针",
  "projects": [
    {{"name": "同名", "tech_stack": ["Python"] * {limit}, "description": ["a"]}},
    {{"name": "同名", "tech_stack": ["Go"] * {limit}, "description": ["b"]}},
    {{"name": "P2", "tech_stack": ["Go"], "description": ["c"]}},
    {{"name": "P3", "tech_stack": ["Go"], "description": ["d"]}},
    {{"name": "P4", "tech_stack": ["Go"], "description": ["e"]}},
  ],
}}
doc = finalize_ai_document(
    content, language="zh-CN", format_config={{}}, custom_fields=None,
    page_limit=1, include_tech_stack=False,
)
parsed = parse_document(doc)  # 必须能再次解析（校验在流水线最后）
proj = next(s for s in doc["sections"] if s["key"] == "projects")
names = []
visible_tech = 0
for entry in proj["entries"]:
    for item in entry["items"]:
        if item.get("kind") == "field" and item.get("key") == "name":
            names.append(item.get("value"))
        if item.get("kind") == "list" and item.get("key") == "tech_stack":
            if item.get("placement") != "hidden" and item.get("values"):
                visible_tech += 1
print(json.dumps({{"entries": len(proj["entries"]), "names": names, "visible_tech": visible_tech}}))
assert len(proj["entries"]) == 3, names
assert visible_tech == 0, visible_tech
""".format(backend=str(BACKEND), limit=500)
        python = VENV_PY if VENV_PY.exists() else Path(sys.executable)
        proc = subprocess.run(
            [str(python), "-I", "-c", probe], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120
        )
        ok = proc.returncode == 0 and '"entries": 3' in proc.stdout
        check(
            "finalize 行为：去重+限量+技术栈+可再解析",
            ok,
            (proc.stdout.strip() or proc.stderr.strip())[-300:],
        )

    ok, tail = pytest("tests/test_ai_write_invariants.py")
    check("test_ai_write_invariants.py 全绿", ok, tail)


# ---------------------------------------------------------------- phase 3


def phase3() -> None:
    dead = ROOT / "frontend" / "src" / "components" / "resume" / "ResumeHiddenSectionsControl.tsx"
    check("旧隐藏控件已删除", not dead.exists(), str(dead.relative_to(ROOT)))

    try:
        sys.path.insert(0, str(BACKEND))
        from app.services.resume.resume_sections import persistable_format_config

        kept = persistable_format_config({"hidden_sections": ["awards"], "section_order": ["a"]})
        check("persistable 丢弃旧版式键", kept == {}, f"返回={kept}")
    except Exception as exc:  # noqa: BLE001
        skip("persistable 丢弃旧版式键", f"无法导入：{exc}")

    hits = []
    for path in APP.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r'(result|values)\["hidden_sections"\]', text):
            hits.append(str(path.relative_to(ROOT)))
    check("后端无 hidden_sections 写入点", not hits, f"命中={hits}")

    ok, tail = pytest("tests/test_section_visibility_exports.py")
    check("四格式对拍测试全绿", ok, tail)

    ok, tail = pytest("tests/test_resume_hidden_sections.py")
    check("旧隐藏板块测试全绿", ok, tail)


# ---------------------------------------------------------------- phase 4


def phase4() -> None:
    guard = ROOT / "scripts" / "check_v2_boundary.py"
    if not guard.exists():
        check("静态守卫脚本存在", False, "缺少 scripts/check_v2_boundary.py")
        return
    python = VENV_PY if VENV_PY.exists() else Path(sys.executable)
    proc = subprocess.run(
        [str(python), str(guard)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=600,
    )
    check("静态守卫通过", proc.returncode == 0, (proc.stdout or proc.stderr).strip()[-400:])

    # 迁移文件名前缀唯一（revision 字符串本来就唯一，重复的是文件名数字）。
    prefixes: dict[str, list[str]] = {}
    for path in (BACKEND / "migrations" / "versions").glob("*.py"):
        match = re.match(r"^(\d{4})_", path.name)
        if match:
            prefixes.setdefault(match.group(1), []).append(path.name)
    dupes = {key: names for key, names in prefixes.items() if len(names) > 1}
    check("迁移文件名前缀唯一", not dupes, f"重复={dupes}")


# ---------------------------------------------------------------- phase 5


def phase5() -> None:
    ok, tail = pytest("tests/test_document_shape_invariants.py")
    check("同形不变量测试全绿", ok, tail)
    ok, tail = pytest("tests/test_fork_regression.py")
    check("二开回归包全绿", ok, tail)
    ok, tail = pytest(
        "tests/test_resume_coverage.py",
        "tests/test_resume_dedupe.py",
        "tests/test_document_save_prune.py",
    )
    check("核心二开测试全绿", ok, tail)


PHASES = {
    "0": ("基线固化", phase0),
    "1": ("数据归一", phase1),
    "2": ("写路径收口", phase2),
    "3": ("板块统一", phase3),
    "4": ("静态守卫", phase4),
    "5": ("回归包", phase5),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="v2 整改阶段闸门（只读）")
    parser.add_argument("--phase", choices=[*PHASES, "all"], default="all")
    # 文档里两种写法都出现过，两种都接受：--all 等价于 --phase all。
    parser.add_argument("--all", action="store_true", help="等价于 --phase all")
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Phase 0：用 SQLite 在线备份 API 生成 .bak（只新建文件，不改库）",
    )
    args = parser.parse_args()
    if args.backup:
        return make_backup()
    phase_arg = "all" if args.all else args.phase

    if not DB_PATH.exists():
        print(f"FAIL 数据库不存在 — {DB_PATH}")
        return 1

    targets = list(PHASES) if phase_arg == "all" else [phase_arg]
    for phase in targets:
        name, fn = PHASES[phase]
        print(f"\n=== Phase {phase} {name} ===")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - 闸门自身崩溃也要给出一行结论
            check(f"Phase {phase} 闸门执行", False, f"{type(exc).__name__}: {exc}")

    failures = [item for item in _results if item[0] == "FAIL"]
    for status, name, detail in _results:
        line = f"{status} {name}"
        print(f"{line} — {detail}" if detail else line)
    print(f"\n汇总：{len(_results) - len(failures)} 通过 / {len(failures)} 失败 / "
          f"{sum(1 for s, *_ in _results if s == 'SKIP')} 跳过")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
