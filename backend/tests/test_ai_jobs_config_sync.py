# SPDX-License-Identifier: Apache-2.0
"""LLM 配置同步（P3-2）：映射口径、会话密钥阻断、Key 不出现在响应。"""

import pytest
from app.schemas.setting import LLMConfig
from app.services.ai_jobs import config_sync
from app.services.ai_jobs.config_sync import build_engine_ai_config
from app.services.llm_settings import save_llm_config
from tests.ai_jobs_fakes import fake_sidecar_manager, patch_manager


def _save_llm(db_session, **overrides):
    fields = {
        "base_url": "https://api.example.com/v1",
        "model": "test-model",
        "api_key": "sk-test-123",
        "api_style": "openai",
    }
    fields.update(overrides)
    save_llm_config(db_session, LLMConfig(**fields))


def test_build_engine_ai_config_openai_mapping(db_session):
    _save_llm(db_session)
    section = build_engine_ai_config(db_session)
    assert section["service"] == "custom"
    assert section["provider"] == "openai_compatible"
    assert section["base_url"] == "https://api.example.com/v1"
    assert section["model"] == "test-model"
    assert section["api_key"] == "sk-test-123"


def test_build_engine_ai_config_anthropic_mapping(db_session):
    _save_llm(db_session, api_style="anthropic")
    section = build_engine_ai_config(db_session)
    assert section["service"] == "anthropic"
    assert section["provider"] == "anthropic"


def test_build_engine_ai_config_blocks_missing_key(db_session):
    _save_llm(db_session, api_key="")
    with pytest.raises(config_sync.TaskGateError) as excinfo:
        build_engine_ai_config(db_session)
    assert "API Key" in excinfo.value.message


def test_sync_merges_into_engine_config(db_session, monkeypatch, tmp_path):
    _save_llm(db_session)
    manager = fake_sidecar_manager(tmp_path)
    patch_manager(monkeypatch, manager)
    client = manager.client_for(8687)
    result = config_sync.sync_llm_to_engine(db_session, client)
    assert result["synced"] is True
    assert result["model"] == "test-model"
