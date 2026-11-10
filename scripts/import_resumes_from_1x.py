# SPDX-License-Identifier: Apache-2.0
"""把 1.x 里指定的简历按新 id 追加进 2.0（2026-11-09）。

为什么单独一个脚本而不是复用 `scripts/import_from_1x.py`：那个脚本是**整库首次搬迁**
用的（按业务键 upsert 全表），这里要的是"补几份刚在 1.x 新建的简历"，语义不同——
按 id 定位、追加、绝不覆盖 2.0 已有记录。

安全口径（与仓库其它导入脚本一致）：
- 1.x 库**只读**打开（``mode=ro``），绝不写；
- 2.0 库先 ``sqlite3.backup()`` 备份再写（WAL 下 ``cp`` 会拿到不一致快照）；
- 默认 **dry-run**：只打印将要发生什么，``--commit`` 才真的写；
- 两边的 ``content`` 都是 v2 文档的 JSON 字符串，原样搬运，不做"聪明"的字段改写；
- 2.0 多出的 ``document_version`` 固定填 2（与库内现有 57 条一致）。

用法：
    python -X utf8 scripts/import_resumes_from_1x.py            # 预览
    python -X utf8 scripts/import_resumes_from_1x.py --commit    # 落库
    python -X utf8 scripts/import_resumes_from_1x.py --ids 53,54,55 --commit
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_1X = REPO.parent / "简历通" / "backend" / "data" / "resume_forge.db"
DEFAULT_2X = REPO / "backend" / "data" / "resume_forge.db"

# 从 1.x 搬到 2.0 的列（两边同名）。`id` 不搬——由 2.0 分配新 id。
# `document_version` 不在 1.x 里，写入时固定 2。
COPY_COLUMNS: tuple[str, ...] = (
    "title",
    "job_id",
    "job_title",
    "company",
    "content",
    "warnings",
    "source",
    "favorite",
    "draft",
    "revision",
    "document_mode",
    "model",
    "tone",
    "enhancement_enabled",
    "enhancement_level",
    "template",
    "format_name",
    "format_config",
    "page_limit",
    "font_scale",
    "language",
    "custom_instruction",
    "note",
    "parse_error",
    "coverage_notes",
    "fact_annotations",
    "rationale",
    "created_at",
    "updated_at",
    "deleted_at",
    "parent_revision_id",
    "context_snapshot",
)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _load_1x(path: Path, ids: list[int]) -> list[dict]:
    """只读打开 1.x，取出指定 id 的行；缺哪条直接失败（不静默跳过）。"""
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        cols = _columns(conn, "resume_record")
        usable = [name for name in COPY_COLUMNS if name in cols]
        missing = sorted(set(COPY_COLUMNS) - set(usable))
        if missing:
            raise SystemExit(f"1.x 缺少这些列，脚本列清单过期了：{missing}")
        rows: list[dict] = []
        for rid in ids:
            row = conn.execute(
                f"SELECT {', '.join(usable)} FROM resume_record WHERE id = ?", (rid,)
            ).fetchone()
            if row is None:
                raise SystemExit(f"1.x 里没有 id={rid} 的简历")
            rows.append(dict(zip(usable, row)))
        return rows
    finally:
        conn.close()


def _validate_content(row: dict) -> str:
    """v2 文档必须是可解析的 JSON 字符串，且 version=2。

    两边都是 v2 是既有事实（实测 1.x/2.0 全部记录 version=2）。这里仍然校验一次：
    将来 1.x 若出现 v1 旧行，宁可让脚本停下来说清楚，也不要把它塞进 2.0 的 v2 列。
    """
    raw = row.get("content")
    if isinstance(raw, dict):
        doc = raw
    elif isinstance(raw, str):
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"「{row.get('title')}」的 content 不是合法 JSON：{exc}") from exc
    else:
        raise SystemExit(f"「{row.get('title')}」的 content 类型异常：{type(raw).__name__}")
    version = doc.get("version")
    if version != 2:
        raise SystemExit(f"「{row.get('title')}」的文档 version={version!r}，只支持 2")
    sections = [s.get("key") for s in (doc.get("sections") or [])]
    if not sections:
        raise SystemExit(f"「{row.get('title')}」的文档没有任何 sections")
    return raw if isinstance(raw, str) else json.dumps(doc, ensure_ascii=False)


def _backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.parent / "auto-backups" / f"pre-resume-import-{stamp}.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-1x", default=str(DEFAULT_1X), help="1.x 数据库路径（只读）")
    parser.add_argument("--to-2x", default=str(DEFAULT_2X), help="2.0 数据库路径")
    parser.add_argument("--ids", default="53,54,55", help="要搬的 1.x 简历 id，逗号分隔")
    parser.add_argument("--commit", action="store_true", help="真的写库（默认只预览）")
    args = parser.parse_args()

    ids = [int(part) for part in args.ids.split(",") if part.strip()]
    rows = _load_1x(Path(args.from_1x), ids)

    target = Path(args.to_2x)
    conn = sqlite3.connect(str(target))
    try:
        cols = _columns(conn, "resume_record")
        usable = [name for name in COPY_COLUMNS if name in cols]
        existing_titles = {
            (str(title), str(created)[:19])
            for title, created in conn.execute("SELECT title, created_at FROM resume_record")
        }

        print(f"待搬 {len(rows)} 份（目标库当前 "
              f"{conn.execute('SELECT COUNT(*) FROM resume_record').fetchone()[0]} 条）：")
        planned: list[dict] = []
        for row in rows:
            content = _validate_content(row)
            key = (str(row["title"]), str(row["created_at"])[:19])
            duplicate = key in existing_titles
            print(f"  - 1.x id={row.get('id', '?')} | {str(row['title'])[:52]} | "
                  f"revision={row.get('revision')} | {len(content)} 字节"
                  f"{'  ⚠ 目标库已有同标题同创建时间，跳过' if duplicate else ''}")
            if duplicate:
                continue
            planned.append({**row, "content": content})

        if not planned:
            print("没有需要搬的简历（全部已存在）。")
            return
        if not args.commit:
            print(f"\n[dry-run] 将追加 {len(planned)} 条到 {target}。加 --commit 才写入。")
            return

        backup = _backup(target)
        print(f"\n已备份：{backup}")
        insert_cols = [*usable, "document_version"]
        placeholders = ", ".join("?" for _ in insert_cols)
        new_ids: list[int] = []
        with conn:  # 单事务：要么全进，要么一条都不进
            for row in planned:
                values = [row[name] for name in usable] + [2]
                cur = conn.execute(
                    f"INSERT INTO resume_record ({', '.join(insert_cols)}) VALUES ({placeholders})",
                    values,
                )
                new_ids.append(int(cur.lastrowid))
        print(f"已写入，新 id：{new_ids}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
