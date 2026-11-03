# SPDX-License-Identifier: Apache-2.0
"""一条命令看清简历通 v2 整改的当前状态（全只读，不写库、不改文件）。

用法（仓库根）：
    backend\\.venv\\Scripts\\python.exe -I scripts\\v2_status.py            # 完整状态 + 定向回归
    backend\\.venv\\Scripts\\python.exe -I scripts\\v2_status.py --fast     # 跳过回归（秒级）
    backend\\.venv\\Scripts\\python.exe -I scripts\\v2_status.py --verbose  # 隐藏板块明细
    backend\\.venv\\Scripts\\python.exe -I scripts\\v2_status.py --json     # 机器可读

闸门部分直接运行 ``scripts/v2_gate.py --all`` 并解析其输出——**不复制它的检查逻辑**
（两套真相会漂移）。回归部分跑 4 组固定定向测试，绝不跑全量（全量 44 分钟）。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DB_PATH = BACKEND / "data" / "resume_forge.db"
VENV_PY = BACKEND / ".venv" / "Scripts" / "python.exe"


def _run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    """子进程输出按字节拿，utf-8 解不开就退 gbk（本机闸门实际写 GBK，实测确认）。"""
    proc = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, timeout=timeout
    )
    def _decode(raw: bytes) -> str:
        for encoding in ("utf-8", "gbk"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="replace")

    return subprocess.CompletedProcess(
        proc.args, proc.returncode, stdout=_decode(proc.stdout or b""), stderr=_decode(proc.stderr or b"")
    )


# ---------------------------------------------------------------- git / db


def _git(args: list[str]) -> str:
    proc = _run(["git", *args], cwd=ROOT, timeout=30)
    return (proc.stdout or "").strip()


def _db_state() -> dict:
    state: dict = {"db_exists": DB_PATH.is_file()}
    if not state["db_exists"]:
        return state
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        state["journal_mode"] = cur.execute("pragma journal_mode").fetchone()[0]
        state["integrity"] = cur.execute("pragma integrity_check").fetchone()[0]
        live = {"v1": 0, "v2": 0}
        total = {"v1": 0, "v2": 0}
        hidden: list[dict] = []
        legacy_keys = 0
        for rid, raw_content, raw_cfg, deleted_at in con.execute(
            "select id, content, format_config, deleted_at from resume_record"
        ):
            try:
                content = json.loads(raw_content) if raw_content else {}
                cfg = json.loads(raw_cfg) if raw_cfg else {}
            except ValueError:
                state["bad_json"] = state.get("bad_json", 0) + 1
                continue
            version = "v2" if content.get("version") == 2 else "v1"
            total[version] += 1
            if deleted_at is None:
                live[version] += 1
            if any(
                isinstance(section, dict) and section.get("hidden")
                for section in content.get("sections") or []
            ):
                hidden_keys = [
                    str(section.get("key"))
                    for section in content.get("sections") or []
                    if isinstance(section, dict) and section.get("hidden")
                ]
                hidden.append({"id": rid, "hidden": hidden_keys})
            if "hidden_sections" in cfg or "section_order" in cfg:
                legacy_keys += 1
        state.update({"live": live, "total": total, "hidden": hidden, "legacy_keys": legacy_keys})
    finally:
        con.close()
    return state


def _newest_backup() -> tuple[str, str] | None:
    backups = sorted((BACKEND / "data").glob("resume_forge.db.pre-*.bak"))
    if not backups:
        return None
    newest = backups[-1]
    try:
        con = sqlite3.connect(f"file:{newest.as_posix()}?mode=ro", uri=True)
        try:
            integrity = con.execute("pragma integrity_check").fetchone()[0]
            rows = con.execute("select count(*) from resume_record").fetchone()[0]
        finally:
            con.close()
        return newest.name, f"integrity={integrity} rows={rows}"
    except sqlite3.Error as exc:
        return newest.name, f"打开失败：{exc}"


# ---------------------------------------------------------------- 闸门


def _gate_report() -> tuple[list[dict], dict]:
    """逐阶段运行 v2_gate.py（每阶段单独一次，各自有可靠的汇总行）。

    不用 ``--all`` 解析：实测 --all 会把所有检查行攒到最后统一打印，无法按阶段归组。
    这里只是分次调用同一个裁判，不复制它的检查逻辑。
    """
    python = str(VENV_PY) if VENV_PY.exists() else sys.executable
    report: list[dict] = []
    for phase in range(0, 6):  # 闸门只有 0-5；Phase 6（runbook）的验收是文档本身
        proc = _run([python, "-I", "scripts/v2_gate.py", "--phase", str(phase)], cwd=ROOT, timeout=900)
        text = (proc.stdout or "") + (proc.stderr or "")
        name = ""
        summary: dict | None = None
        for line in text.splitlines():
            header = re.match(r"^=== Phase \d+ (.+?) ===$", line.strip())
            if header:
                name = header.group(1)
            m = re.match(r"^汇总：(\d+) 通过 / (\d+) 失败(?: / (\d+) 跳过)?", line.strip())
            if m:
                summary = {
                    "pass": int(m.group(1)),
                    "fail": int(m.group(2)),
                    "skip": int(m.group(3) or 0),
                }
        if summary is None:
            # 阶段没跑起来（脚本异常等）：按全失败处理，附上尾部输出
            tail = " / ".join(text.strip().splitlines()[-2:])
            summary = {"pass": 0, "fail": 1, "skip": 0}
            report.append({
                "phase": phase, "name": name or "(无输出)", **summary,
                "raw": [f"FAIL 闸门异常 — {tail[:200]}"],
            })
        else:
            report.append({"phase": phase, "name": name, **summary, "raw": []})
    grand_pass = sum(item["pass"] for item in report)
    grand_fail = sum(item["fail"] for item in report)
    return report, {"pass": grand_pass, "fail": grand_fail}


# ---------------------------------------------------------------- 回归


REGRESSION_GROUPS: list[tuple[str, list[str]]] = [
    ("resume 核心", ["tests/test_resume_dedupe.py", "tests/test_document_html.py",
                     "tests/test_generation_preferences.py", "tests/test_resume_coverage.py"]),
    ("write invariants", ["tests/test_ai_write_invariants.py"]),
    ("section visibility", ["tests/test_section_visibility_exports.py",
                            "tests/test_resume_hidden_sections.py"]),
    ("同形不变量+回归包", ["tests/test_document_shape_invariants.py", "tests/test_fork_regression.py"]),
    ("sidecar", ["tests/test_ai_jobs_resume_sync.py", "tests/test_ai_jobs_greeting.py",
                 "tests/test_ai_jobs_e2e.py", "tests/test_ai_jobs_delivery.py",
                 "tests/test_ai_jobs_redteam_fixes.py"]),
]


def _regression_report() -> list[dict]:
    python = str(VENV_PY) if VENV_PY.exists() else sys.executable
    results = []
    for name, files in REGRESSION_GROUPS:
        proc = _run(
            [python, "-m", "pytest", "-q", "--no-header", "--tb=no", *files],
            cwd=BACKEND, timeout=900,
        )
        text = (proc.stdout or "").splitlines()
        tail = next((line for line in reversed(text) if " passed" in line or " failed" in line), "")
        results.append({"group": name, "tail": tail.strip() or proc.returncode and f"exit={proc.returncode}"})
    return results


# ---------------------------------------------------------------- 输出


def main() -> int:
    # Windows 控制台常是 GBK：本脚本与子进程输出统一按 UTF-8 处理，避免中文/替换符炸掉。
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="简历通 v2 整改状态一览（只读）")
    parser.add_argument("--verbose", action="store_true", help="打印隐藏板块的记录明细")
    parser.add_argument("--fast", action="store_true", help="跳过定向回归（只看闸门与数据）")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = parser.parse_args()

    branch = _git(["rev-parse", "--abbrev-ref", "HEAD"]) or "(不是 git 仓库?)"
    head = _git(["rev-parse", "--short", "HEAD"])
    dirty = len(_git(["status", "--porcelain"]).splitlines())
    db = _db_state()
    backup = _newest_backup()
    gate, gate_grand = _gate_report()
    regression = [] if args.fast else _regression_report()

    total_pass = (gate_grand or {}).get("pass", sum(item["pass"] for item in gate))
    total_fail = (gate_grand or {}).get("fail", sum(item["fail"] for item in gate))
    gate_green = total_fail == 0

    payload = {
        "branch": branch, "head": head, "dirty": dirty, "db": db, "backup": backup,
        "gate": gate, "gate_total": {"pass": total_pass, "fail": total_fail},
        "regression": regression,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if gate_green else 1

    print("=== 简历通 v2 状态 ===")
    print(f"分支      {branch} @ {head}")
    print(f"工作树    {dirty} 个未提交改动" + ("（干净）" if dirty == 0 else ""))
    if db.get("db_exists"):
        print(f"数据库    {DB_PATH.name} ({db.get('journal_mode')}, integrity={db.get('integrity')})")
        live, total = db.get("live", {}), db.get("total", {})
        print(f"版本分布  live v1={live.get('v1')} / v2={live.get('v2')}   "
              f"含软删 v1={total.get('v1')} / v2={total.get('v2')}")
        hidden = db.get("hidden", [])
        print(f"隐藏板块  {len(hidden)} 条记录有 section.hidden"
              + ("（明细见 --verbose）" if hidden and not args.verbose else ""))
        if args.verbose:
            for item in hidden:
                print(f"    id={item['id']} hidden={','.join(item['hidden'])}")
        print(f"旧版式键  format_config 里 hidden_sections/section_order 残留 {db.get('legacy_keys')} 条")
    else:
        print("数据库    未找到 resume_forge.db")
    if backup:
        print(f"备份      最近一份 {backup[0]} ({backup[1]})")
    else:
        print("备份      无（跑 v2_gate.py --backup 生成）")

    print("\n=== 闸门 ===")
    for item in gate:
        mark = "PASS" if item["fail"] == 0 else "FAIL"
        print(f"Phase {item['phase']} {item['name']}  {item['pass']}/{item['pass'] + item['fail']} {mark}")
    print(f"合计 {total_pass} 通过 / {total_fail} 失败")

    if regression:
        print("\n=== 回归（定向） ===")
        for item in regression:
            print(f"{item['group']:<18} {item['tail']}")

    print("\n=== 结论 ===")
    if not gate_green:
        print("闸门有红项：先看上面 FAIL 的阶段，不要动数据库，不要继续下一阶段。")
    elif db.get("legacy_keys", 0) > 0 or (db.get("total", {}).get("v1") or 0) > 0:
        print("数据未完全归一（存在 v1 记录或旧版式键）：先跑 Phase 1 的归一脚本。")
    elif dirty > 0:
        print(f"闸门全绿，但工作树有 {dirty} 个未提交改动：先提交（或确认是并行会话在用），再继续。")
    else:
        print("闸门全绿、数据全 v2、工作树干净：可以继续下一阶段；不要动数据库（除非走 runbook 流程）。")
    return 0 if gate_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
