# SPDX-License-Identifier: Apache-2.0
"""修正「采集进来的岗位全被标成校招」的历史数据（2026-11-12）。

## 问题

用户反馈：岗位广场里采集来的岗位**全部显示「校招」**，包括「AI视频制作师」
「运维开发工程师」这种明显不是校招的。

## 根因（两层）

1. `api/job_hunt_tasks.py` 的 `_stage_results` 用 `getattr(stub, "job_type", "")` 取类型，
   而 `JobStub` **根本没有这个字段** —— 恒为空串。
2. 候选导入时 `job_type_from_title(title) or candidate.job_type or "校招"`，前两项都空
   就落 **"校招" 兜底**。采集来的标题普遍不含类型词，于是全部变成校招。

## 这个脚本修什么

只修**确定由该缺陷造成**的行，判定是三条同时成立：

- `recognition_source = '岗位采集'`（不是手工录入、不是助手录入）
- `job_type = '校招'`
- **标题里没有任何校招/实习字样**（`job_type_from_title(title) is None`）

第三条是关键：标题真的写了「应届」「20xx 届」的，标校招是对的，不能动。
来源不明的（`recognition_source` 为空的历史行）也**不动** —— 没有证据说明它们是
这个缺陷造成的，宁可不修也不误改。

## 改法

走 service 层（`Job` 模型 + `db.commit()`），不直接拼 SQL：`job_type` 的合法性由
模型层维护，绕过它以后加约束就会漏。

## 用法（在仓库根目录执行）

    backend/.venv/Scripts/python.exe scripts/fix_collected_job_type.py            # 只预览
    backend/.venv/Scripts/python.exe scripts/fix_collected_job_type.py --apply    # 真改

默认 dry-run；`--apply` 前会先做 `sqlite3.Connection.backup()`（WAL 库不能 cp）。
"""

from __future__ import annotations

import argparse
import datetime
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_DB = BACKEND_ROOT / "data" / "resume_forge.db"

# 受影响的 recognition_source 取值。
#
# - ``岗位采集``：自研采集直落（job_hunt）。
# - ``备选岗位导入``：候选导入岗位广场（`services/candidate_jobs.py:366` 的兜底分支）。
#   这两条走的是**同一个缺陷**——候选的 job_type 为空就落 "校招"。
#
# **不含 BossHunter**：那条链路的外来数据本来就采自「校园招聘」渠道，标校招是对的。
AFFECTED_SOURCES = ("岗位采集", "备选岗位导入")


def _backup(db_path: Path) -> Path:
    """WAL 库必须用 Connection.backup()，cp 会拿到不完整快照。"""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = db_path.parent / "backups" / f"before_jobtype_fix_{stamp}.db"
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="真的写库（默认只预览）")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.models.job import Job
    from app.services.job_parser.metadata import job_type_from_title

    session = SessionLocal()
    try:
        rows = (
            session.query(Job)
            .filter(
                Job.deleted_at.is_(None),
                Job.job_type == "校招",
                Job.recognition_source.in_(AFFECTED_SOURCES),
            )
            .all()
        )
        # 标题里真的写了校招/实习字样的不动 —— 那些标校招是对的。
        targets = [row for row in rows if job_type_from_title(row.title) is None]

        print(f"采集/候选导入来源且标「校招」的岗位：{len(rows)} 条")
        print(f"其中标题推不出校招（应改为社招）：{len(targets)} 条")
        for row in targets:
            print(f"  #{row.id} {row.title}")

        if not targets:
            print("没有需要修正的数据。")
            return 0
        if not args.apply:
            print("\n（预览模式，未写库。加 --apply 才真改。）")
            return 0

        backup = _backup(args.db)
        print(f"\n已备份：{backup}")
        for row in targets:
            row.job_type = "社招"
        session.commit()
        print(f"已把 {len(targets)} 条改为「社招」。")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
