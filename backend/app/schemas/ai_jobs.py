# SPDX-License-Identifier: Apache-2.0
"""AI 求职（BossHunter sidecar）Schema：连接配置与引擎侧数据的对前端投影。

安全边界：这里**不出现**任何 API Key、Token、Cookie。引擎的 AI 凭据由后端从
简历通全局 LLM Profile 同步给 sidecar（config_sync），前端永远只拿到只读引用。
"""

from pydantic import BaseModel, Field


class AiJobsConfig(BaseModel):
    """``AppSetting`` key ``ai_jobs_config`` 的结构（按数据集隔离，无需迁移）。

    ``engine_python`` / ``engine_repo`` 是用户自行安装的 BossHunter 引擎位置；
    简历通不打包、不分发 BossHunter（许可证边界见 docs/ai-jobs-integration.md）。
    """

    enabled: bool = True
    # 引擎可执行文件（python.exe）与引擎仓库根目录；空 = 未配置，状态页提示去填。
    engine_python: str = Field(default="", max_length=1024)
    engine_repo: str = Field(default="", max_length=1024)
    # sidecar Web/API 端口（避开独立 BossHunter 的 8686/3456）、CDP 代理端口、
    # 共用的简历通专用浏览器端口。
    engine_port: int = Field(default=8687, ge=1, le=65535)
    proxy_port: int = Field(default=3457, ge=1, le=65535)
    browser_port: int = Field(default=9333, ge=1, le=65535)
    # 简历通启动时是否自动拉起 sidecar（默认关：用户手动启动更可控）。
    auto_start: bool = False
    # AI 配置唯一来源是简历通全局 LLM Profile；关闭则引擎用自己的 config。
    use_resumeforge_llm: bool = True
    # 采集/评分完成后是否自动把 ready 及以上岗位导入简历通岗位池。
    auto_import_ready_jobs: bool = True
    # 运行时记录：上次成功连接的数据集与引擎版本（仅诊断展示用）。
    last_dataset_id: str = Field(default="", max_length=64)
    engine_version: str = Field(default="", max_length=32)


class SidecarHealth(BaseModel):
    """``GET /api/health`` 的归一化结果（``version_ok`` 由后端按版本窗口计算）。"""

    reachable: bool = False
    status: str = ""
    version: str = ""
    version_ok: bool = False
    # 版本窗口外时后端降级只读，reason 给出可操作的提示文案。
    reason: str = ""
