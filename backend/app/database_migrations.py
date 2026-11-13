# SPDX-License-Identifier: Apache-2.0
"""Database migration orchestration and safe SQLite backups."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, inspect, text

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
# 2.0 基线：纯 CREATE 语句、无存在性判断，结构自检重放时必须跳过它。
# 与 tests/migration_refs.py 的 BASELINE_REVISION 同值；这里不能从 tests 导入。
_BASELINE_REVISION = "0001_baseline_v2"


def application_tables() -> tuple[str, ...]:
    """当前代码认识的全部业务表。

    从 ``Base.metadata`` 推导而不是手写清单：手写清单只要漏掉一张新表，
    **自己导出的备份就会因为"缺少数据表"被拒收**，而这类故障只有用户真去恢复
    数据时才会暴露。改成由模型注册表生成后，加表这件事自动生效。
    """
    from . import models  # noqa: F401 - 导入以注册全部模型
    from .database import Base

    return tuple(sorted(Base.metadata.tables))


_APPLICATION_TABLES = application_tables()
# 版本标记表不是用户数据：全新空库迁移完成后 app_schema_epoch 恰好有一行（epoch=2），
# 若把它算进来，每次首次迁移都会白做一份"迁移前快照"（之后没有任何东西引用它）。
# 排除只影响"要不要备份"，不影响备份包/表覆盖清单（那份仍由 _APPLICATION_TABLES 推导）。
_USER_DATA_TABLES = tuple(name for name in _APPLICATION_TABLES if name != "app_schema_epoch")


def build_alembic_config(bind: Engine) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # SQLAlchemy 2.1 起 render_as_string 会把路径百分号编码（空格 -> %20、% -> %25），
    # 而 alembic 的 configparser 读回时会做 % 插值——不把 % 转义成 %% 就会直接抛
    # InterpolationSyntaxError。转义后 get_main_option 拿回的是还原过的原串，两条
    # 消费路径（attributes["connection"] 与 engine_from_config）都安全。
    url_string = str(bind.url.render_as_string(hide_password=False))
    config.set_main_option("sqlalchemy.url", url_string.replace("%", "%%"))
    return config


def _database_has_user_data(bind: Engine) -> bool:
    tables = set(inspect(bind).get_table_names())
    with bind.connect() as connection:
        for table_name in _USER_DATA_TABLES:
            if table_name not in tables:
                continue
            quoted = bind.dialect.identifier_preparer.quote(table_name)
            if connection.execute(text(f"SELECT 1 FROM {quoted} LIMIT 1")).first() is not None:
                return True
    return False


def _database_has_application_tables(bind: Engine) -> bool:
    """库是否已经包含当前模型认识的业务表（用于拒绝未版本化的库）。"""
    return bool(set(inspect(bind).get_table_names()).intersection(_APPLICATION_TABLES))


def _replay_idempotent_migrations(bind: Engine, scripts: ScriptDirectory) -> None:
    """按链顺序重放 0002 起全部迁移的 ``upgrade()``，跳过基线。

    为什么不是 ``command.upgrade``：alembic 只看版本号，版本号已是 head 时它什么都不做，
    而这里要修的正是"版本号说没问题、结构有问题"。所以直接调用迁移模块的 ``upgrade()``，
    靠各迁移自带的存在性判断做到幂等。

    为什么跳过 ``0001_baseline_v2``：它是纯 ``CREATE TABLE``（无存在性判断），重放必炸；
    而走到本函数的前提是基线已经跑过（否则启动闸门会先拦成 ARCHIVE_AND_RESET 或 FRESH）。

    顺序按 ``scripts.walk_revisions()`` 反转为从旧到新：迁移之间有真实依赖
    （0010 的表引用 0008 的列），乱序会在中途撞 FK/缺列。
    """
    ordered = [
        revision
        for revision in scripts.walk_revisions()
        if revision.revision != _BASELINE_REVISION
    ]
    ordered.reverse()  # walk_revisions() 是 head → base，反转成 base → head

    with bind.begin() as connection:
        context = MigrationContext.configure(connection)
        # 迁移模块里写的是 `from alembic import op; op.xxx()`，那个 op 是**按上下文取实例**
        # 的代理。`Operations.context()` 是公开 API：在当前线程压入一条 Operations，
        # 让各迁移模块里的 op.* 落到这条连接上；退出时自动弹出。
        with Operations.context(context):
            for revision in ordered:
                module = revision.module
                upgrade = getattr(module, "upgrade", None)
                if upgrade is None:
                    continue
                logger.info("重放迁移 %s", revision.revision)
                upgrade()


def _assert_schema_complete(bind: Engine, before: list[str]) -> None:
    """重放后复核：原本缺的项必须全部补上，否则大声失败而不是带病启动。

    失败时把**仍然缺失**的清单写进异常：这东西一旦只剩前半句（"数据库结构不完整"），
    排查又要重新做一遍"到底缺什么"。
    """
    still_missing = _missing_schema_objects(bind)
    if still_missing:
        raise RuntimeError(
            "数据库结构自检修复失败：重放幂等迁移后仍有 "
            f"{len(still_missing)} 项缺失（修复前 {len(before)} 项）："
            f"{'、'.join(still_missing[:10])}。"
            "这说明某个迁移不是幂等的，或模型里引用了没有迁移覆盖的列。"
            "请把这条消息连同 data/logs/backend.log 一起报告，库已被备份。"
        )

    """库是否已经包含当前模型认识的业务表（用于拒绝未版本化的库）。"""
    return bool(set(inspect(bind).get_table_names()).intersection(_APPLICATION_TABLES))


def _missing_schema_objects(bind: Engine) -> list[str]:
    """模型里有、库里没有的表与列（只读自检，返回 ``表`` / ``表.列`` 描述）。

    **为什么需要它**：``alembic_version`` 只是一个字符串，它能被写错、被沿用，
    也可能因为迁移重编号而与新 head 恰好同名（2026-11-13 合并上游 2.1.0 的真实事故）。
    只比"版本号等不等于 head"会发现不了这种情况——版本号说"已是最新"，库里却缺一半结构，
    启动能过、请求一到就 500。

    比对范围是**当前模型声明的一切**：表必须先存在，列再逐个核。索引与外键不比——
    它们的差异不影响 ORM 能否查询，而迁移链里的索引名有历史包袱，逐条比会误报。

    只读：只用 ``inspect()`` 读元数据，绝不写库、不创建任何东西。
    """
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    from . import models  # noqa: F401 - 导入以注册全部模型
    from .database import Base

    missing: list[str] = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            missing.append(table_name)
            continue
        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name not in existing_columns:
                missing.append(f"{table_name}.{column.name}")
    return missing


def snapshot_sqlite_file(source: Path, destination: Path) -> None:
    """把一个 SQLite 文件按 ``sqlite3.backup`` 复制成一致快照。

    导出活动数据集、导出其余数据集、迁移前备份都走这一份实现：三处各写一遍的下场是
    某一处忘了关闭连接，备份文件在 Windows 上一直被占着，调用方既删不掉也替换不了。
    """
    # sqlite3 连接的上下文管理器只提交事务、不关闭连接；这里必须显式关闭。
    with (
        closing(sqlite3.connect(source)) as source_db,
        closing(sqlite3.connect(destination)) as target_db,
    ):
        source_db.backup(target_db)
        target_db.commit()


def _strip_optimizer_stat_tables(path: Path) -> None:
    """从快照里删掉 SQLite 优化器统计表（``sqlite_stat1`` 等）。

    ``PRAGMA optimize``/ANALYZE 会在库里维护 ``sqlite_stat*`` 统计表：它们是引擎
    内部状态而不是用户数据，但留在快照里会被**旧版本**的导入白名单当成"不认识的
    表"拒收，备份因此失去跨版本兼容。统计信息在恢复后的库里由 optimize 重建，
    备份里不需要带着。DROP 在 SQLite 里对 stat 表是合法操作。
    """
    with closing(sqlite3.connect(path)) as connection:
        names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        stat_tables = sorted(name for name in names if name.startswith("sqlite_stat"))
        for name in stat_tables:
            connection.execute(f'DROP TABLE "{name}"')
        if stat_tables:
            connection.commit()


def backup_sqlite_database(bind: Engine, output_dir: Path | None = None) -> Path | None:
    """Create a consistent SQLite backup and return its path.

    Non-SQLite databases are expected to use their platform backup tooling.
    """
    if bind.dialect.name != "sqlite" or not bind.url.database:
        return None
    source = Path(bind.url.database).resolve()
    if not source.exists():
        return None
    destination_dir = output_dir or source.parent / "backups"
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = destination_dir / f"{source.stem}-{timestamp}{source.suffix or '.db'}"
    snapshot_sqlite_file(source, destination)
    _strip_optimizer_stat_tables(destination)
    logger.info("SQLite 备份已创建 path=%s", destination)
    return destination

def run_database_migrations(bind: Engine, *, backup: bool = True) -> Path | None:
    """把当前库升级到 Alembic head；迁移前如有用户数据先做一次 SQLite 快照。

    职责只有两件：迁移前快照 + ``upgrade head``。它不判定库的版本、不归档 pre-2.0
    库、不建空库、不兼容建表——那些都属于启动闸门（``schema_epoch.decide()`` 与
    ``startup_gate.enforce()``）。启动顺序（不能调换）：判定 →（必要时）归档并建空库
    → 本函数 → SQLite 例行维护。

    ``backup=False`` is for migrating a throwaway copy of somebody else's data:
    the archive validation path in ``services/data_backup`` extracts a candidate
    and migrates it only to see whether the archive is importable. Backing that
    up would drop a full copy of the user's database into a staging directory
    that nothing ever prunes.
    """
    config = build_alembic_config(bind)
    scripts = ScriptDirectory.from_config(config)
    head_revision = scripts.get_current_head()
    with bind.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision == head_revision:
        # **版本号等于 head 不代表结构就是 head。** 2026-11-13 合并上游 2.1.0 时踩到过：
        # 二开的迁移从 `0002`/`0003` 重编号成 `0018`/`0019`，但 revision **内部标识**沿用了
        # 旧值，于是老库里记着的 `0019_candidate_job_score` 恰好等于新 head——这里直接
        # return，上游 `0002`–`0017` 一条都没执行，启动后首页当场 500
        # （`no such column: job.favorited_at`）。
        #
        # 所以续跑之前先做一次结构自检：代码认识的表/列在库里缺失，就说明版本号说谎。
        # 自检只读，不写库。
        missing_schema = _missing_schema_objects(bind)
        if not missing_schema:
            return None
        logger.warning(
            "版本号已是 head（%s）但结构与代码不符，重放迁移补齐：缺 %d 项，例如 %s",
            head_revision,
            len(missing_schema),
            "、".join(missing_schema[:5]),
        )
        # **不能直接 command.upgrade**：alembic 看到版本号已是 head 就不会执行任何东西。
        # 定向重放幂等迁移的 upgrade()（0002 起全部幂等，0001 基线是纯 CREATE 只能跳过），
        # 顺序即链顺序，缺的表/列会被补齐，已存在的由各自的存在性判断跳过。
        backup_path = (
            backup_sqlite_database(bind) if backup and _database_has_user_data(bind) else None
        )
        _replay_idempotent_migrations(bind, scripts)
        _assert_schema_complete(bind, missing_schema)
        logger.info("结构自检修复完成 revision=%s", head_revision)
        return backup_path
    if current_revision is None and _database_has_application_tables(bind):
        # 走到这里说明启动闸门的顺序错了：pre-2.0 库本应在 schema_epoch.decide() 里
        # 判成 ARCHIVE_AND_RESET、由 startup_gate 整包归档后建空库，再进迁移。2.0 不再
        # 兼容建表、也不再给旧库 stamp 基线——大声失败比把一份读不懂的库硬升成半新半旧
        # 安全（原始库此时一个字节都没被改）。
        raise RuntimeError(
            "数据库已有业务表但没有版本号：启动闸门未先归档旧库，已拒绝迁移。"
            "这属于启动顺序错误，请报告维护者；原始库未被修改。"
        )
    backup_path = (
        backup_sqlite_database(bind) if backup and _database_has_user_data(bind) else None
    )
    # Reuse the application's connection so sqlite:///:memory: is migrated in
    # place instead of creating and discarding a second in-memory database.
    with bind.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    logger.info("数据库迁移完成 revision=%s", head_revision)
    return backup_path
