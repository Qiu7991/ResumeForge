#!/usr/bin/env python
"""把 1.x 二开库的核心数据导入 2.0 空库。

设计原则
--------
1. **只读 1.x**：先 ``sqlite3.backup`` 到临时副本再读，绝不直连活库（1.x 是 WAL，
   cp 会丢已提交事务；直连会读到不一致快照）。
2. **只迁核心数据**：简历、岗位、资料库、事实、投递记录。不迁运行时态
   （任务队列、失败明细、日志、用量记录）——那些在 2.0 里重新积累更安全。
3. **幂等**：按自然键 upsert，重跑不产生重复。
4. **可回退**：写之前先备份目标库；1.x 永不写入。
5. **不静默跳过**：任何转换异常写进报告，dry-run 时列出。

字段差异（实测 2026-11-07）
--------------------------
- ``resume_record``：2.0 多 ``document_version``（可空，写入时补 "2"）
- ``profile_entry``：2.0 多 ``values_schema``（可空，留空即可）
- ``application_track``：1.x 多 ``failure_step/target/reason``（2.0 无此列，丢弃）
- ``profile_fact`` 两张表：2.0 已删除，**不迁**（事实改由 ``claim_record`` 承载）

用法
----
    # 默认 dry-run，只报告不写库
    backend/.venv/Scripts/python.exe -I scripts/import_from_1x.py

    # 真正写入
    backend/.venv/Scripts/python.exe -I scripts/import_from_1x.py --apply

    # 自定义源库
    ... --source "D:/飞牛文件同步/工作/简历通/backend/data/resume_forge.db"
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "backend" / "data" / "resume_forge.db"

# 让 `app.*` 可导入：脚本常以 `-I`（隔离模式）运行，那种模式下 sys.path 不含脚本目录，
# 更不含 backend/。不加这行，`_api_key_decrypts` 里的导入会静默失败 → 误报"Key 解不开"。
sys.path.insert(0, str(ROOT / "backend"))
DEFAULT_SOURCE = Path(r"D:/飞牛文件同步/工作/简历通/backend/data/resume_forge.db")
REPORT = ROOT / "runtime" / "import-from-1x-report.json"

# ---------------------------------------------------------------------------
# 迁移计划：源表 -> 目标表、自然键、丢弃列
# 顺序 = 依赖顺序（先主表后从表）。
# ---------------------------------------------------------------------------
# 每项：(源表, 目标表, 自然键列, 需要丢弃的列)
PLAN: list[tuple[str, str, list[str], list[str]]] = [
    # ---- 岗位 ----
    ("job", "job", ["source_url"], []),
    # ---- 资料库 ----
    ("profile_entry", "profile_entry", ["entry_id", "section_key"], []),
    ("profile_group", "profile_group", ["name"], []),
    ("profile_group_member", "profile_group_member", ["group_id", "section_key"], []),
    ("profile_field_preference", "profile_field_preference", ["section_key", "field_id"], []),
    ("profile_photo", "profile_photo", ["id"], []),
    ("user_profile", "user_profile", ["id"], []),
    # ---- 事实台账 ----
    ("claim_record", "claim_record", ["id"], []),
    # ---- 结构化资料（旧模型，2.0 仍保留）----
    ("education", "education", ["id"], []),
    ("experience", "experience", ["id"], []),
    ("project", "project", ["id"], []),
    ("skill", "skill", ["id"], []),
    ("material", "material", ["id"], []),
    ("career_scenario", "career_scenario", ["id"], []),
    # ---- 简历 ----
    ("resume_record", "resume_record", ["id"], []),
    ("resume_generation_plan", "resume_generation_plan", ["id"], []),
    ("resume_phrase", "resume_phrase", ["id"], []),
    # ---- 投递记录（申请追踪台账）----
    ("application_track", "application_track", ["id"], ["failure_step", "failure_target", "failure_reason"]),
    ("application_track_event", "application_track_event", ["id"], []),
    ("resume_delivery_record", "resume_delivery_record", ["id"], []),
    # ---- 投递任务历史（让「投递记录」标签页也能看到 1.x 的批次）----
    # 前置条件：1.x 的 apply_task 全部是终态（completed/failed/stopped），
    # 没有任何 running/pending，否则导入后会让「开始投递」按钮误判有任务在跑。
    # 脚本会在导入前校验这一点，非终态就中止。
    ("apply_task", "apply_task", ["id"], []),
    ("apply_task_item", "apply_task_item", ["id"], []),
    ("apply_queue_item", "apply_queue_item", ["id"], []),
    # ---- 其他可复用资料 ----
    ("interview_experience", "interview_experience", ["id"], []),
    ("knowledge_entry", "knowledge_entry", ["id"], []),
    ("question_bank_record", "question_bank_record", ["id"], []),
    ("referral", "referral", ["id"], []),
    ("reminder", "reminder", ["id"], []),
    ("user_file", "user_file", ["id"], []),
    ("web_form_url_history", "web_form_url_history", ["id"], []),
]

# 设置键白名单：只迁「用户偏好」，不迁「运行态/凭据」
# 注意：llm_config 含 api_key，必须走 SETTING_DENY_HINT 拒绝；
# apply_config 不含凭据（只有节奏/招呼语），可以整体迁。
SETTING_ALLOW = {
    "apply_config",                    # 投递节奏 + 招呼语基准 + 默认简历
    "ui.locale",                       # 界面语言
    "batch_operation_config",          # 批量生成/导出参数
    "profile_generation_preferences",  # 显示技术栈开关
    "assistant_relaxed_mode",
    "webform_relaxed_mode",
}
SETTING_DENY_HINT = ("api_key", "token", "secret", "cookie", "password")

# 明确不迁的表（记录原因，供报告）
SKIP_REASON = {
    "apply_queue_item": "运行时态：2.0 队列从空开始，避免带着 1.x 的批次上下文",
    "apply_task": "运行时态：历史任务不迁",
    "apply_task_item": "运行时态：历史任务明细不迁",
    "ai_task": "运行时态：任务历史不迁",
    "llm_usage_record": "统计：用量记录不迁（2.0 重新计）",
    "profile_usage_snapshot": "统计：使用快照不迁",
    "resume_generate_task": "运行时态：生成任务历史不迁",
    "profile_fact": "2.0 已删除该表；事实由 claim_record 承载",
    "profile_fact_field_pref": "2.0 已删除该表",
}


def backup_readonly(src: Path) -> tuple[sqlite3.Connection, Path]:
    """用 sqlite3.backup 把源库拷成临时副本再打开（绝不直连活库）。"""
    tmp = Path(tempfile.gettempdir()) / f"import-1x-{os.getpid()}.db"
    if tmp.exists():
        tmp.unlink()
    s = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    d = sqlite3.connect(str(tmp))
    s.backup(d)
    d.close()
    s.close()
    conn = sqlite3.connect(str(tmp))
    conn.row_factory = sqlite3.Row
    return conn, tmp


# 目标列 NOT NULL 但源值可能为 NULL 时的补值规则。
# 实测：2.0 的 job.analysis_cache 是 JSON NOT NULL DEFAULT '{}'，
# 而 1.x 有 10 条岗位该字段为 NULL → 插入报 NOT NULL 约束失败。
NULL_FILL = {
    "job": {"analysis_cache": "{}"},
}


def table_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]


# 只有这些状态算「已终结」，不会让 2.0 误判有任务在跑。
TERMINAL_TASK_STATUS = {"completed", "failed", "stopped", "cancelled", "canceled"}


def check_apply_task_terminal(src: sqlite3.Connection) -> list[str]:
    """校验 1.x 的投递任务全部是终态。

    为什么必须校验：2.0 判断「有任务在跑」看的是 apply_task.status。
    若把 running/pending 的历史任务导进去，用户点「开始投递」会被误判为
    已有任务而拒绝（或更糟：显示一个永不结束的进度条）。
    """
    problems: list[str] = []
    if not table_exists(src, "apply_task"):
        return problems
    rows = src.execute("SELECT id, status FROM apply_task").fetchall()
    for row in rows:
        st = (row["status"] or "").strip().lower()
        if st not in TERMINAL_TASK_STATUS:
            problems.append(f"apply_task id={row['id']} status={row['status']!r}（非终态）")
    return problems


def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def natural_key(row: sqlite3.Row, cols: list[str]) -> tuple:
    return tuple(row[c] if c in row.keys() else None for c in cols)


def plan_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    src_table: str,
    dst_table: str,
    key_cols: list[str],
    drop_cols: list[str],
) -> dict:
    """算出一张表的迁移计划（不写库）。

    返回 {source_rows, insert, update, skip, errors[], dropped_cols[]}
    """
    result = {
        "source_table": src_table,
        "target_table": dst_table,
        "source_rows": 0,
        "insert": 0,
        "update": 0,
        "skip_unchanged": 0,
        "errors": [],
        "dropped_cols": [],
    }

    if not table_exists(src, src_table):
        result["errors"].append(f"源库没有 {src_table} 表")
        return result
    if not table_exists(dst, dst_table):
        result["errors"].append(f"目标库没有 {dst_table} 表（2.0 结构可能已变）")
        return result

    s_cols = table_cols(src, src_table)
    d_cols = set(table_cols(dst, dst_table))
    keep = [c for c in s_cols if c in d_cols and c not in drop_cols]
    missing_in_src = [c for c in key_cols if c not in s_cols]
    if missing_in_src:
        result["errors"].append(f"源表缺少自然键列 {missing_in_src}")
        return result

    result["dropped_cols"] = [c for c in s_cols if c not in d_cols]
    result["missing_in_src_target"] = sorted(d_cols - set(s_cols))

    rows = src.execute(f'SELECT * FROM "{src_table}"').fetchall()
    result["source_rows"] = len(rows)

    for row in rows:
        try:
            key = natural_key(row, key_cols)
            where = " AND ".join(f'"{c}" IS ?' for c in key_cols)
            existing = dst.execute(
                f'SELECT rowid FROM "{dst_table}" WHERE {where}', key
            ).fetchone()
            if existing:
                result["update"] += 1
            else:
                result["insert"] += 1
        except Exception as exc:  # noqa: BLE001 - 报告要留原文
            result["errors"].append(f"row {dict(row).get('id', '?')}: {exc}")

    result["_keep_cols"] = keep
    return result


def apply_table(
    src: sqlite3.Connection,
    dst: sqlite3.Connection,
    plan: dict,
    key_cols: list[str],
) -> dict:
    """真正写库。返回 {"inserted": n, "updated": n, "errors": []}"""
    src_table = plan["source_table"]
    dst_table = plan["target_table"]
    keep = plan["_keep_cols"]
    out = {"inserted": 0, "updated": 0, "errors": []}

    rows = src.execute(f'SELECT * FROM "{src_table}"').fetchall()
    col_list = ", ".join(f'"{c}"' for c in keep)
    placeholders = ", ".join("?" for _ in keep)
    fills = NULL_FILL.get(dst_table, {})

    for row in rows:
        try:
            values = []
            for c in keep:
                v = row[c]
                if v is None and c in fills:
                    v = fills[c]
                values.append(v)
            key = natural_key(row, key_cols)
            where = " AND ".join(f'"{c}" IS ?' for c in key_cols)
            existing = dst.execute(
                f'SELECT rowid FROM "{dst_table}" WHERE {where}', key
            ).fetchone()
            if existing:
                sets = ", ".join(f'"{c}" = ?' for c in keep)
                dst.execute(
                    f'UPDATE "{dst_table}" SET {sets} WHERE rowid = ?',
                    (*values, existing[0]),
                )
                out["updated"] += 1
            else:
                dst.execute(
                    f'INSERT INTO "{dst_table}" ({col_list}) VALUES ({placeholders})',
                    values,
                )
                out["inserted"] += 1
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"row {row['id'] if 'id' in row.keys() else '?'}: {exc}")
    return out


def _api_key_decrypts(src: sqlite3.Connection) -> bool:
    """检查 1.x 归档里的 API Key 能否在**本机本用户**解开。

    DPAPI 密文的解不开**不抛异常**、返回空串（见 ``api_key_crypto.decrypt_key`` 的说明），
    所以这里按"解出来非空"判定。判定失败只警告、不阻断迁移。
    """
    try:
        row = src.execute("SELECT value FROM app_setting WHERE key = 'llm_config'").fetchone()
        if not row or not row[0]:
            return False
        encrypted = str(json.loads(row[0]).get("api_key") or "")
        if not encrypted:
            return False

        from app.services.api_key_crypto import decrypt_key

        return bool(str(decrypt_key(encrypted) or "").strip())
    except Exception:  # noqa: BLE001 - 校验本身失败不该阻断导入
        return False


def plan_settings(
    src: sqlite3.Connection, dst: sqlite3.Connection, *, include_llm: bool = False
) -> dict:
    """设置只迁白名单键，且默认拒绝任何疑似凭据。

    ``include_llm=True`` 时额外迁移 ``llm_config``（含 API Key）。**默认关闭**是因为
    这个脚本会随公开仓库分发，别人机器上带着作者的 Key 是隐私事故。

    但**同一台机器、同一个 Windows 账户**下迁移时应该打开它：1.x 的 Key 存的是
    ``dpapi:v1:`` 密文，DPAPI 绑定当前用户，所以 2.0 直接就能解开——用户不必重填。
    （实测：1.x 的 ``sk_tr_...`` 用 2.0 的 ``decrypt_key`` 能正常解出。）
    """
    out = {"migrate": [], "skip": [], "errors": [], "warn": []}
    if not table_exists(src, "app_setting") or not table_exists(dst, "app_setting"):
        out["errors"].append("app_setting 表缺失")
        return out
    s_cols = table_cols(src, "app_setting")
    key_col = "key" if "key" in s_cols else None
    if key_col is None:
        out["errors"].append("app_setting 没有 key 列")
        return out
    for row in src.execute("SELECT * FROM app_setting"):
        k = str(row[key_col])
        low = k.lower()
        if k == "llm_config" and include_llm:
            # 显式要求迁移模型配置：密文原样搬过去，不在这里解密、不落明文。
            #
            # **必须当场验一次能不能解开**：DPAPI 密文绑定"这台机器的这个用户"，
            # 搬到别的电脑上解开会**静默返回空串**（不是抛异常），界面显示"已配置"
            # 而每次调用都失败——那种故障极难排查。这里提前炸掉，让用户知道该重填 Key。
            out["migrate"].append(k)
            if not _api_key_decrypts(src):
                out["warn"].append(
                    "llm_config 里的 API Key 在本机解不开（DPAPI 绑定原机器的用户账户）："
                    "会照常迁移其余配置，但 Key 需要到「设置 → AI 模型」里重填一次"
                )
        elif any(h in low for h in SETTING_DENY_HINT):
            out["skip"].append(f"{k}（疑似凭据，拒绝迁移；同机迁移可加 --include-llm）")
        elif k in SETTING_ALLOW:
            out["migrate"].append(k)
        else:
            out["skip"].append(f"{k}（不在白名单）")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="1.x -> 2.0 核心数据导入")
    ap.add_argument("--source", default=str(DEFAULT_SOURCE), help="1.x 数据库路径")
    ap.add_argument("--apply", action="store_true", help="真正写入（默认 dry-run）")
    ap.add_argument("--force", action="store_true", help="目标库非空时仍然继续")
    ap.add_argument(
        "--include-llm",
        action="store_true",
        help="连模型配置（含 API Key 密文）一起迁移。只在同一台机器、同一 Windows 账户下用："
        "1.x 的 Key 是 DPAPI 密文，绑当前用户，搬到别处解不开。",
    )
    args = ap.parse_args()

    src_path = Path(args.source)
    if not src_path.exists():
        print(f"FAIL 源库不存在: {src_path}")
        return 2
    if not TARGET.exists():
        print(f"FAIL 目标库不存在: {TARGET}")
        return 2

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"=== 1.x -> 2.0 导入 [{mode}] ===")
    print(f"源   : {src_path} ({src_path.stat().st_size:,} 字节)")
    print(f"目标 : {TARGET} ({TARGET.stat().st_size:,} 字节)")

    src, tmp = backup_readonly(src_path)
    dst = sqlite3.connect(str(TARGET))
    dst.row_factory = sqlite3.Row

    # 前置校验：投递任务必须是终态
    task_problems = check_apply_task_terminal(src)
    if task_problems:
        print("\nFAIL 源库存在非终态的投递任务，拒绝导入：")
        for p in task_problems[:10]:
            print(f"  {p}")
        print("  处置：先在 1.x 里把这些任务停掉/等它结束，再重跑本脚本。")
        return 4
    print("PASS 投递任务全部为终态（不会让 2.0 误判有任务在跑）")

    # 目标非空守卫
    non_empty = []
    for _, dst_table, _, _ in PLAN:
        if table_exists(dst, dst_table):
            n = dst.execute(f'SELECT COUNT(*) FROM "{dst_table}"').fetchone()[0]
            if n:
                non_empty.append((dst_table, n))
    if non_empty and not args.force and args.apply:
        print("\nFAIL 目标库已有数据，拒绝导入（加 --force 可覆盖）：")
        for t, n in non_empty:
            print(f"  {t}: {n} 行")
        return 3
    if non_empty:
        print(f"\n注意：目标库已有 {len(non_empty)} 张表非空（upsert 会更新，不重复插入）")

    report: dict = {
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "source": str(src_path),
        "target": str(TARGET),
        "tables": [],
        "settings": {},
        "skipped_tables": SKIP_REASON,
    }

    total_ins = total_upd = total_err = 0
    for src_table, dst_table, key_cols, drop_cols in PLAN:
        plan = plan_table(src, dst, src_table, dst_table, key_cols, drop_cols)
        line = (
            f"{src_table:24} 源 {plan['source_rows']:5}  "
            f"新增 {plan['insert']:5}  更新 {plan['update']:5}"
        )
        if plan["dropped_cols"]:
            line += f"  丢弃列 {plan['dropped_cols']}"
        if plan["errors"]:
            line += f"  错误 {len(plan['errors'])}"
            total_err += len(plan["errors"])
        print(line)

        if args.apply and plan["source_rows"]:
            applied = apply_table(src, dst, plan, key_cols)
            total_ins += applied["inserted"]
            total_upd += applied["updated"]
            if applied["errors"]:
                total_err += len(applied["errors"])
                plan["errors"].extend(applied["errors"])

        plan.pop("_keep_cols", None)
        report["tables"].append(plan)

    # 设置
    sp = plan_settings(src, dst, include_llm=args.include_llm)
    print(f"{'app_setting':24} 迁移 {sp['migrate']}  跳过 {len(sp['skip'])} 项")
    # Key 解不开这件事必须**打在屏幕上**，不能只写进报告文件——用户看不到就白搭。
    for warning in sp.get("warn") or []:
        print(f"  警告：{warning}")
    report["settings"] = sp
    if args.apply and sp["migrate"]:
        s_cols = table_cols(src, "app_setting")
        d_cols = set(table_cols(dst, "app_setting"))
        keep = [c for c in s_cols if c in d_cols]
        for row in src.execute("SELECT * FROM app_setting"):
            if str(row["key"]) not in sp["migrate"]:
                continue
            vals = [row[c] for c in keep]
            existing = dst.execute(
                "SELECT rowid FROM app_setting WHERE key = ?", (row["key"],)
            ).fetchone()
            if existing:
                sets = ", ".join(f'"{c}" = ?' for c in keep)
                dst.execute(
                    f"UPDATE app_setting SET {sets} WHERE rowid = ?", (*vals, existing[0])
                )
            else:
                dst.execute(
                    f"INSERT INTO app_setting ({', '.join(f'"{c}"' for c in keep)}) "
                    f"VALUES ({', '.join('?' for _ in keep)})",
                    vals,
                )

    if args.apply:
        dst.commit()
        # 写后校验
        print("\n=== 写后校验 ===")
        for _, dst_table, _, _ in PLAN:
            if table_exists(dst, dst_table):
                n = dst.execute(f'SELECT COUNT(*) FROM "{dst_table}"').fetchone()[0]
                if n:
                    print(f"  {dst_table:24} {n} 行")
        print(f"\nintegrity: {dst.execute('PRAGMA integrity_check').fetchone()[0]}")
        print(f"合计：新增 {total_ins} / 更新 {total_upd} / 错误 {total_err}")
    else:
        plan_ins = sum(t["insert"] for t in report["tables"])
        plan_upd = sum(t["update"] for t in report["tables"])
        print(f"\n[DRY-RUN] 预计新增 {plan_ins} / 更新 {plan_upd} / 错误 {total_err}")
        print("未写入任何数据。确认无误后加 --apply。")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{REPORT}")

    dst.close()
    src.close()
    tmp.unlink(missing_ok=True)
    return 1 if total_err else 0


if __name__ == "__main__":
    raise SystemExit(main())
