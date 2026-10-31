#!/usr/bin/env python
"""把本地二开库（0046→0047_usage_ledger/0048_ai_task）迁到上游迁移链 head。

**背景**：二开分支从上游 0046 分叉，新增了 `0047_usage_ledger` / `0048_ai_task`
两个本地 revision；上游同期从 0046 继续走到 0068。两套 revision 名字不同但
`llm_usage_record` / `usage_pricing_record` / `ai_task` 三张表的列基本一致，
所以不需要删表重建：

1. 先把 `alembic_version` 改回 `0046_search_fts`；
2. 再跑上游 0047→head 的迁移；
3. 上游 0067/0068 看到三张表已存在会跳过创建，只补缺失列，数据原样保留。

**安全**：脚本先对目标库做一份同目录备份，再动 `alembic_version`；任何一步失败都
把备份路径打印出来。默认只接受本地二开的两个 revision 或 0046，遇到别的版本直接
报错退出，避免误伤未知库。

用法（在仓库根执行）：
    backend/.venv/Scripts/python.exe scripts/migrate_local_db_to_upstream.py \
        backend/data/resume_forge.db
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

LOCAL_REVISIONS = {"0046_search_fts", "0047_usage_ledger", "0048_ai_task"}
UPSTREAM_HEAD = "0068_ai_tasks"
# 迁移前后的业务表抽查：行数必须完全一致（迁移只加列/加表，不删业务行）。
CHECK_TABLES = (
    "resume_record",
    "job",
    "application_track",
    "apply_queue_item",
    "claim_record",
    "material",
    "knowledge_entry",
)


def _read_revision(connection: sqlite3.Connection) -> str:
    row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    return str(row[0]) if row else ""


def _counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in CHECK_TABLES:
        try:
            counts[table] = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        except sqlite3.DatabaseError:
            counts[table] = -1
    return counts


def migrate(database: Path) -> int:
    if not database.is_file():
        print(f"[FAIL] 数据库不存在：{database}", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database.with_name(f"{database.name}.pre-upstream-{stamp}.bak")
    shutil.copy2(database, backup)
    print(f"[1/4] 已备份：{backup}")

    with sqlite3.connect(database) as connection:
        revision = _read_revision(connection)
        before = _counts(connection)
    print(f"[2/4] 当前 revision：{revision or '(空)'}")

    if revision == UPSTREAM_HEAD:
        print("[OK] 已经是上游 head，无需迁移。")
        return 0
    if revision not in LOCAL_REVISIONS:
        print(
            f"[FAIL] 不认识的 revision：{revision!r}；本脚本只处理 0046/本地 0047/0048。",
            file=sys.stderr,
        )
        return 2

    # 本地 0047/0048 与上游 0047 之后是两条分叉；把版本改回共同祖先 0046。
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE alembic_version SET version_num = '0046_search_fts'")
        connection.commit()
    print("[3/4] 已把 alembic_version 对齐到共同祖先 0046_search_fts")

    from alembic import command
    from sqlalchemy import create_engine

    from app.database_migrations import build_alembic_config

    engine = create_engine(f"sqlite:///{database.resolve().as_posix()}")
    try:
        command.upgrade(build_alembic_config(engine), "head")
    finally:
        engine.dispose()
    print("[4/4] 上游迁移链执行完成")

    with sqlite3.connect(database) as connection:
        final_revision = _read_revision(connection)
        after = _counts(connection)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]

    print(f"最终 revision：{final_revision}")
    print(f"integrity_check：{integrity}")
    changed = {table: (before[table], after[table]) for table in before if before[table] != after[table]}
    if changed:
        print(f"[FAIL] 业务表行数发生变化：{changed}", file=sys.stderr)
        print(f"       请用备份回滚：{backup}", file=sys.stderr)
        return 1
    if integrity != "ok":
        print(f"[FAIL] 数据库完整性校验失败；备份：{backup}", file=sys.stderr)
        return 1
    if final_revision != UPSTREAM_HEAD:
        print(f"[FAIL] 未到达上游 head：{final_revision}；备份：{backup}", file=sys.stderr)
        return 1

    print(f"[OK] 迁移完成，业务表行数未变；备份在：{backup}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法：python scripts/migrate_local_db_to_upstream.py <数据库路径>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(migrate(Path(sys.argv[1])))
