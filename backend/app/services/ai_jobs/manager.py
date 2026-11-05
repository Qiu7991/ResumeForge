# SPDX-License-Identifier: Apache-2.0
"""sidecar 进程生命周期：发现、启动、停止、端口选择、所有权、日志。

**所有权口径**：只有本进程内经 :meth:`SidecarManager.start` 启动的 ``Popen`` 句柄
才允许停止（句柄指向内核进程对象，天然免疫 PID 复用）；从磁盘 ``sidecar.json``
恢复的记录只用于展示与复用，**永不杀**——用户手动启动的实例、上次会话遗留的
实例都只复用。

**运行时目录**：``DATA_DIR/ai-jobs/<dataset_id>/engine/``，BossHunter 强依赖自身
CWD（CLI 会 ``os.chdir(base_dir)``），所以子进程 ``cwd`` 必须是该目录。
"""

from __future__ import annotations

import json
import logging
import socket
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ...config import DATA_DIR
from ...runtime.dataset_scope import current_dataset_id
from ...schemas.ai_jobs import AiJobsConfig, SidecarHealth
from .client import SidecarClient

logger = logging.getLogger(__name__)

# 启动后健康等待：BossHunter 冷启动（导入浏览器依赖）可能要几秒。
_HEALTH_ATTEMPTS = 30
_HEALTH_INTERVAL = 0.5
# 端口被占用时向后尝试的数量（8687 → 8697）。
_PORT_PROBES = 10

_STATE_FILE = "sidecar.json"


@dataclass
class StartResult:
    ok: bool
    port: int = 0
    pid: int | None = None
    owned: bool = False
    error: str = ""
    health: SidecarHealth | None = None


@dataclass
class RuntimeState:
    """磁盘态：只用于展示/复用，不作为停止依据（见模块 docstring 的所有权口径）。"""

    pid: int | None = None
    port: int = 0
    owner_token: str = ""
    started_at: float = 0.0
    command: list[str] = field(default_factory=list)


def build_sidecar_command(config: AiJobsConfig, runtime_dir: Path, port: int) -> list[str]:
    """sidecar 启动命令。BossHunter 的 CLI 形态见其 ``bosshunter web --help``。"""
    return [
        config.engine_python,
        "-m",
        "bosshunter.main",
        "--config",
        str(runtime_dir / "config.yaml"),
        "web",
        "--no-open",
        "--port",
        str(port),
    ]


def find_free_port(start: int, probes: int = _PORT_PROBES) -> int | None:
    """从 ``start`` 起找第一个可绑定的 loopback 端口；全占返回 None。"""
    for candidate in range(start, start + probes + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.bind(("127.0.0.1", candidate))
            except OSError:
                continue
        return candidate
    return None


class SidecarManager:
    """按数据集管理 sidecar 进程。进程内单例（``get_sidecar_manager``）。"""

    def __init__(
        self,
        runtime_root: Path | None = None,
        *,
        health_attempts: int = _HEALTH_ATTEMPTS,
        health_interval: float = _HEALTH_INTERVAL,
    ):
        self._runtime_root = runtime_root
        self._health_attempts = health_attempts
        self._health_interval = health_interval
        self._process: subprocess.Popen[bytes] | None = None
        self._process_port = 0
        self._owner_token = uuid.uuid4().hex
        self._lock = threading.Lock()

    # ---- 路径 ----

    def runtime_dir(self, dataset_id: str | None = None) -> Path:
        dataset = dataset_id or current_dataset_id()
        root = self._runtime_root or (DATA_DIR / "ai-jobs")
        return root / dataset / "engine"

    def _state_path(self, dataset_id: str | None = None) -> Path:
        return self.runtime_dir(dataset_id) / _STATE_FILE

    # ---- 磁盘状态 ----

    def read_state(self, dataset_id: str | None = None) -> RuntimeState:
        path = self._state_path(dataset_id)
        if not path.is_file():
            return RuntimeState()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return RuntimeState()
        return RuntimeState(
            pid=raw.get("pid"),
            port=int(raw.get("port") or 0),
            owner_token=str(raw.get("owner_token") or ""),
            started_at=float(raw.get("started_at") or 0.0),
            command=list(raw.get("command") or []),
        )

    def _write_state(self, state: RuntimeState, dataset_id: str | None = None) -> None:
        path = self._state_path(dataset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "pid": state.pid,
                    "port": state.port,
                    "owner_token": state.owner_token,
                    "started_at": state.started_at,
                    "command": state.command,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    # ---- 启动/停止 ----

    def validate_engine(self, config: AiJobsConfig) -> str:
        """返回空串表示引擎配置可用；否则给可操作的错误提示。"""
        if not config.engine_python or not config.engine_repo:
            return "尚未配置引擎位置：请在设置里填写 BossHunter 的安装目录与 Python 路径"
        if not Path(config.engine_python).is_file():
            return f"引擎 Python 不存在：{config.engine_python}"
        if not Path(config.engine_repo).is_dir():
            return f"引擎目录不存在：{config.engine_repo}"
        return ""

    def start(self, config: AiJobsConfig, dataset_id: str | None = None) -> StartResult:
        """启动 sidecar（只启动自己拥有的进程）；已在跑或磁盘状态端口有存活引擎则复用。"""
        error = self.validate_engine(config)
        if error:
            return StartResult(ok=False, error=error)
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                health = self._probe_health(self._process_port)
                return StartResult(
                    ok=health.reachable and health.version_ok,
                    port=self._process_port,
                    pid=self._process.pid,
                    owned=True,
                    error="" if health.version_ok else health.reason,
                    health=health,
                )
            runtime_dir = self.runtime_dir(dataset_id)
            runtime_dir.mkdir(parents=True, exist_ok=True)
            # 复用（F2）：磁盘状态端口上有健康引擎（上次会话或用户手动启动）→ 采纳，
            # 不再拉第二个实例——两个 sidecar 会抢同一个浏览器、双 CDP proxy。
            state = self.read_state(dataset_id)
            if state.port:
                adopted_health = self._probe_health(state.port)
                if adopted_health.reachable and adopted_health.version_ok:
                    logger.info("采纳已有 sidecar port=%s pid=%s", state.port, state.pid)
                    return StartResult(
                        ok=True, port=state.port, pid=state.pid, owned=False, health=adopted_health
                    )
            self._ensure_runtime_config(config, runtime_dir)
            port = find_free_port(config.engine_port)
            if port is None:
                return StartResult(ok=False, error=f"端口 {config.engine_port} 起连续 {_PORT_PROBES + 1} 个都被占用")
            command = build_sidecar_command(config, runtime_dir, port)
            logger.info("启动 sidecar port=%s cwd=%s", port, runtime_dir)
            try:
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
                process = subprocess.Popen(  # noqa: S603 - 命令由本函数拼装，路径来自用户配置
                    command,
                    cwd=str(runtime_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
            except OSError as exc:
                return StartResult(ok=False, error=f"无法启动引擎进程：{exc}")
            self._process = process
            self._process_port = port
            health = self._wait_healthy(port)
            if not (health.reachable and health.version_ok):
                # 健康检查不过 = 启动失败：立刻收掉自己刚拉起的进程，不留孤儿；
                # 不写状态文件（F8）：死 pid/port 会干扰下一次的复用探测。
                self._terminate_locked()
                return StartResult(ok=False, port=port, pid=process.pid, owned=True, error=health.reason or "sidecar 启动后健康检查未通过", health=health)
            self._write_state(
                RuntimeState(
                    pid=process.pid,
                    port=port,
                    owner_token=self._owner_token,
                    started_at=time.time(),
                    command=command,
                ),
                dataset_id,
            )
            return StartResult(ok=True, port=port, pid=process.pid, owned=True, health=health)

    def _ensure_runtime_config(self, config: AiJobsConfig, runtime_dir: Path) -> None:
        """runtime 目录没有 config.yaml 时写一份**最小**配置（F1）。

        不写的话引擎回退 DEFAULTS：CDP 代理绑 3456（撞独立 BossHunter）、
        chrome_ports 含 9222（可能附着到错误浏览器）。这里按用户的端口配置
        固化 browser 段；其余配置由引擎自己的 ``POST /api/config`` 升级此文件。
        """
        path = runtime_dir / "config.yaml"
        if path.is_file():
            return
        content = (
            "# 由简历通生成的最小 sidecar 配置：只固化浏览器端口，其余经 /api/config 同步。\n"
            "browser:\n"
            "  runtime: builtin\n"
            "  proxy_host: 127.0.0.1\n"
            f"  proxy_port: {config.proxy_port}\n"
            f"  chrome_ports: [{config.browser_port}]\n"
            "  auto_start_proxy: true\n"
            "  enable_port_guard: true\n"
        )
        path.write_text(content, encoding="utf-8")
        logger.info("已写入 sidecar 最小配置 %s", path)

    def stop(self) -> bool:
        """停止自己启动的 sidecar；没有则返回 False（不动别人的进程）。"""
        with self._lock:
            if self._process is None:
                return False
            return self._terminate_locked()

    def _terminate_locked(self) -> bool:
        process = self._process
        self._process = None
        self._process_port = 0
        if process is None:
            return False
        if process.poll() is not None:
            return True
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        logger.info("sidecar 进程已停止 pid=%s", process.pid)
        return True

    # ---- 健康与状态 ----

    def _probe_health(self, port: int) -> SidecarHealth:
        client = SidecarClient(f"http://127.0.0.1:{port}")
        try:
            return client.health()
        except Exception as exc:  # noqa: BLE001 - 健康探测失败统一降级
            return SidecarHealth(reachable=False, reason=str(exc))

    def _wait_healthy(self, port: int) -> SidecarHealth:
        health = SidecarHealth(reachable=False, reason="健康检查超时")
        for _ in range(self._health_attempts):
            if self._process is not None and self._process.poll() is not None:
                return SidecarHealth(reachable=False, reason=f"sidecar 进程启动后立即退出（exit={self._process.returncode}）")
            health = self._probe_health(port)
            if health.reachable:
                return health
            time.sleep(self._health_interval)
        return health

    def client_for(self, port: int) -> SidecarClient:
        return SidecarClient(f"http://127.0.0.1:{port}")

    def log_tail(self, dataset_id: str | None = None, lines: int = 50) -> list[str]:
        """引擎日志末尾 N 行；文件不存在返回空（未启动过）。"""
        path = self.runtime_dir(dataset_id) / "logs" / "web.log"
        if not path.is_file():
            return []
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return []
        return content.splitlines()[-lines:]

    def is_owned_running(self) -> bool:
        return self._process is not None and self._process.poll() is None


_manager = SidecarManager()
_manager_lock = threading.Lock()


def get_sidecar_manager() -> SidecarManager:
    """进程内单例。测试用 ``manager._manager`` 替换或直接构造新实例。"""
    return _manager


__all__ = [
    "RuntimeState",
    "SidecarManager",
    "StartResult",
    "build_sidecar_command",
    "find_free_port",
    "get_sidecar_manager",
]
