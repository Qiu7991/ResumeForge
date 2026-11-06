# SPDX-License-Identifier: Apache-2.0
"""``ai_jobs_config`` 读写：默认值、往返、脏数据回退、端口边界。"""


from app.schemas.ai_jobs import AiJobsConfig
from app.services.ai_jobs.settings import get_ai_jobs_config, save_ai_jobs_config


def test_missing_config_returns_defaults(db_session):
    config = get_ai_jobs_config(db_session)
    assert config.enabled is True
    assert config.engine_port == 8687
    assert config.proxy_port == 3457
    assert config.browser_port == 9333
    assert config.engine_python == ""


def test_config_roundtrip(db_session):
    saved = save_ai_jobs_config(
        db_session,
        AiJobsConfig(
            engine_python=r"C:\engines\bosshunter\.venv\Scripts\python.exe",
            engine_repo=r"C:\engines\bosshunter",
            engine_port=8700,
        ),
    )
    loaded = get_ai_jobs_config(db_session)
    assert loaded == saved
    assert loaded.engine_port == 8700


def test_corrupt_config_falls_back_to_defaults(db_session):
    from app.models.setting import AppSetting

    db_session.add(AppSetting(key="ai_jobs_config", value="{not json"))
    db_session.commit()
    config = get_ai_jobs_config(db_session)
    assert config == AiJobsConfig()


def test_config_stores_no_secrets(db_session):
    """配置结构里不允许出现 Key/Token/Cookie 字段（安全边界钉死）。"""
    stored = get_ai_jobs_config(db_session).model_dump().keys()
    banned = {"api_key", "token", "cookie", "secret", "password"}
    assert not banned & set(stored)
