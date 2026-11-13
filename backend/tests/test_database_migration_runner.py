# SPDX-License-Identifier: Apache-2.0
"""数据库迁移执行器（2.0 收缩后）测试：只做快照 + upgrade，不判定/不归档/不建空库。

2.0 起 pre-2.0 库由启动闸门先整包归档再建空库，执行器只面对"空库或合法 2.0 库"。
这里钉住三条边界：空库一次建全；有用户数据才快照（app_schema_epoch 播种行不算用户
数据）；无版本号但有业务表时大声失败，而不是像 1.x 那样兼容建表后 stamp 基线。
"""

import pytest
from app.database_migrations import run_database_migrations
from app.models import Job
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from tests.test_database import _assert_head_schema


class _FakeScripts:
    """把 head 报成"未来版本"的 ScriptDirectory 替身（只替换执行器自己的查询）。

    不 monkeypatch 真实的 ScriptDirectory：command.upgrade 内部也要用真实 head，
    两边一起被换掉会去解析一个不存在的 revision。"head 比当前库新"是迁移前快照
    分支的唯一触发条件，而单基线形态下真实链里没有更早的 2.0 revision，只能这样构造。
    """

    def __init__(self, head: str) -> None:
        self._head = head

    @classmethod
    def from_config(cls, _config):
        return cls("future_head")

    def get_current_head(self) -> str:
        return self._head


def _empty_engine(tmp_path, name: str):
    return create_engine(f"sqlite:///{(tmp_path / name).as_posix()}")


def test_migration_runner_builds_schema_from_empty_database(tmp_path):
    engine = _empty_engine(tmp_path, "runner-empty.db")
    try:
        assert run_database_migrations(engine) is None
        _assert_head_schema(engine)
    finally:
        engine.dispose()


def test_migration_runner_supports_in_memory_database():
    engine = create_engine("sqlite:///:memory:")
    try:
        assert run_database_migrations(engine) is None
        _assert_head_schema(engine)
    finally:
        engine.dispose()


def test_migration_runner_creates_no_snapshot_for_empty_database(tmp_path, monkeypatch):
    from app import database_migrations as runner

    engine = _empty_engine(tmp_path, "runner-no-snapshot.db")
    try:
        assert run_database_migrations(engine) is None
        assert not (tmp_path / "backups").exists()
        monkeypatch.setattr(runner, "ScriptDirectory", _FakeScripts)
        assert run_database_migrations(engine) is None, "已到 head 时没有可执行的升级"
        assert not (tmp_path / "backups").exists(), "空库（含 epoch 播种行）不应产生迁移前快照"
    finally:
        engine.dispose()


def test_migration_runner_snapshots_user_data_before_upgrade(tmp_path, monkeypatch):
    from app import database_migrations as runner

    engine = _empty_engine(tmp_path, "runner-snapshot.db")
    try:
        assert run_database_migrations(engine) is None
        with Session(engine) as session:
            session.add(Job(title="门店店长"))
            session.commit()
        monkeypatch.setattr(runner, "ScriptDirectory", _FakeScripts)
        backup = run_database_migrations(engine)
        assert backup is not None and backup.exists()
        assert backup.parent.name == "backups"
        backup_engine = create_engine(f"sqlite:///{backup.as_posix()}")
        try:
            with backup_engine.connect() as connection:
                titles = [row[0] for row in connection.execute(text("SELECT title FROM job"))]
        finally:
            backup_engine.dispose()
        assert titles == ["门店店长"]
    finally:
        engine.dispose()


def test_migration_runner_refuses_unversioned_database_with_tables(tmp_path):
    engine = _empty_engine(tmp_path, "runner-unversioned.db")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE education (id INTEGER PRIMARY KEY)")
        with pytest.raises(RuntimeError, match="启动闸门"):
            run_database_migrations(engine)
    finally:
        engine.dispose()


def test_migration_runner_repairs_schema_when_revision_says_head(tmp_path):
    """版本号等于 head 但结构缺表缺列时，仍然执行迁移补齐。

    2026-11-13 合并上游 2.1.0 的真实事故：二开的迁移从 0002/0003 重编号成 0018/0019，
    但 revision **内部标识**沿用了旧值，老库里记着的字符串恰好等于新 head，执行器在前面
    直接 return，上游 0002–0017 一条都没跑。启动是通的，首页一请求就 500
    （`no such column: job.favorited_at`）。

    这里构造的就是那个状态：迁移到 head 之后**手工删掉**一列，再跑一次执行器。
    版本号没变，只有结构被破坏——修复必须来自结构自检，而不是版本号比较。
    """
    engine = _empty_engine(tmp_path, "runner-head-but-broken.db")
    try:
        assert run_database_migrations(engine) is None
        _assert_head_schema(engine)

        # 造出「版本号已是 head、结构却缺东西」的状态（与事故现场同形）。
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE job DROP COLUMN favorited_at")

        assert run_database_migrations(engine) is None
        _assert_head_schema(engine)
    finally:
        engine.dispose()


def test_repair_schema_off_leaves_structure_alone(tmp_path):
    """`repair_schema=False` 时不得自愈：备份导入路径靠它把"被改过的包"交给上层拒收。

    两条路径的语义截然不同，必须钉住：
    - 启动：库是本机真实数据，版本号说谎就补结构（默认 `repair_schema=True`）；
    - 备份导入：库是别人给的包解出来的副本，版本号与结构不符 = 包被改过，
      **拒收**才是正确行为。自愈会把篡改抹平——那正是整包校验要防的事。
    """
    engine = _empty_engine(tmp_path, "runner-no-repair.db")
    try:
        assert run_database_migrations(engine) is None
        with engine.begin() as connection:
            connection.exec_driver_sql("ALTER TABLE job DROP COLUMN favorited_at")

        # 关掉自愈：什么都不做，缺失原样保留（上层据此拒收）。
        assert run_database_migrations(engine, repair_schema=False) is None
        from app.database_migrations import _missing_schema_objects

        still_missing = _missing_schema_objects(engine)
        assert "job.favorited_at" in still_missing, "repair_schema=False 时不该补结构"

        # 再开着自愈跑一次：应当补齐（证明开关真的只是开关，不是坏了）。
        assert run_database_migrations(engine) is None
        _assert_head_schema(engine)
    finally:
        engine.dispose()
