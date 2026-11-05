# SPDX-License-Identifier: Apache-2.0
"""BossHunter sidecar HTTP 客户端：超时、错误归一化、版本窗口检查。

只对幂等 GET 重试一次；POST 绝不自动重试（重复启动任务的代价远大于一次失败）。
所有请求带 ``X-Request-Id``；日志只记路径/状态/耗时，不记响应体（可能含 JD 全文）。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

import httpx

from ...schemas.ai_jobs import SidecarHealth

logger = logging.getLogger(__name__)

# 引擎版本窗口（§11：锁定 2.4.x，防 API 漂移）。窗口外降级只读。
ENGINE_VERSION_MIN = (2, 4, 0)
ENGINE_VERSION_MAX = (3, 0, 0)

# 超时分档：健康 2s / 读状态 5s / 任务启动 15s / 长操作 30s。
_TIMEOUTS = {"health": 2.0, "read": 5.0, "task": 15.0, "long": 30.0}


class SidecarError(Exception):
    """sidecar 调用失败，``code`` 供前端区分提示与降级行为。"""

    def __init__(self, message: str, code: str = "http_error"):
        super().__init__(message)
        self.message = message
        self.code = code


def parse_version(version: str) -> tuple[int, ...] | None:
    """把 "2.4.1" / "v2.4" 解析成元组；解析不了返回 None（按不匹配处理）。"""
    text = (version or "").strip().lstrip("vV")
    if not text:
        return None
    parts = text.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def version_in_window(version: str) -> bool:
    parsed = parse_version(version)
    if parsed is None:
        return False
    # 按位补零比较（2.4 == (2,4) < (2,4,0) 是错的；补齐成同长度再比）。
    width = max(len(parsed), 3)
    normalized = parsed + (0,) * (width - len(parsed))
    lo = ENGINE_VERSION_MIN + (0,) * (width - 3)
    hi = ENGINE_VERSION_MAX + (0,) * (width - 3)
    return lo <= normalized < hi


class SidecarClient:
    """sidecar 的单点 HTTP 入口。地址来自 ``ai_jobs_config``，默认 127.0.0.1:8687。"""

    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(transport=transport)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: str = "read",
    ) -> Any:
        url = f"{self._base_url}{path}"
        budget = _TIMEOUTS[timeout]
        attempts = 2 if method == "GET" else 1
        last_error: SidecarError | None = None
        for attempt in range(attempts):
            request_id = uuid.uuid4().hex
            started = time.monotonic()
            try:
                response = self._client.request(
                    method,
                    url,
                    json=json_body,
                    params=params,
                    headers={"X-Request-Id": request_id},
                    timeout=budget,
                )
            except httpx.ConnectError as exc:
                raise SidecarError("sidecar 未运行，请先启动引擎服务", "not_running") from exc
            except httpx.HTTPError as exc:
                last_error = SidecarError(f"sidecar 请求超时或连接中断（{exc.__class__.__name__}）", "timeout")
            else:
                elapsed = time.monotonic() - started
                logger.info("sidecar %s %s -> %s %.0fms", method, path, response.status_code, elapsed * 1000)
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise SidecarError("sidecar 返回了非 JSON 响应", "bad_response") from exc
                detail = _extract_error(response)
                if response.status_code < 500:
                    raise SidecarError(detail, "http_error")
                last_error = SidecarError(detail, "http_error")
            if attempt + 1 < attempts:
                continue
        raise last_error or SidecarError("sidecar 请求失败", "http_error")

    def health(self) -> SidecarHealth:
        """健康检查 + 版本窗口判定（窗口外 ``version_ok=False`` 并给原因）。"""
        try:
            data = self._request("GET", "/api/health", timeout="health")
        except SidecarError as exc:
            return SidecarHealth(reachable=False, reason=exc.message)
        version = str(data.get("version") or "") if isinstance(data, dict) else ""
        ok = version_in_window(version)
        reason = ""
        if not ok:
            reason = (
                f"BossHunter 版本 {version or '未知'} 不在支持范围（{ENGINE_VERSION_MIN[0]}."
                f"{ENGINE_VERSION_MIN[1]}.x），请升级或降级引擎后重试"
            )
        return SidecarHealth(
            reachable=True,
            status=str(data.get("status") or "") if isinstance(data, dict) else "",
            version=version,
            version_ok=ok,
            reason=reason,
        )

    def get(self, path: str, params: dict[str, Any] | None = None, timeout: str = "read") -> Any:
        return self._request("GET", path, params=params, timeout=timeout)

    def post(self, path: str, body: dict[str, Any] | None = None, timeout: str = "task") -> Any:
        return self._request("POST", path, json_body=body, timeout=timeout)

    def post_multipart(
        self,
        path: str,
        files: dict[str, tuple[str, bytes, str]],
        timeout: str = "long",
    ) -> Any:
        """multipart 上传（简历文件等）；复用同一套错误归一化与请求头。"""
        url = f"{self._base_url}{path}"
        started = time.monotonic()
        try:
            response = self._client.post(
                url,
                files=files,
                headers={"X-Request-Id": uuid.uuid4().hex},
                timeout=_TIMEOUTS[timeout],
            )
        except httpx.ConnectError as exc:
            raise SidecarError("sidecar 未运行，请先启动引擎服务", "not_running") from exc
        except httpx.HTTPError as exc:
            raise SidecarError(f"sidecar 请求超时或连接中断（{exc.__class__.__name__}）", "timeout") from exc
        logger.info("sidecar POST %s -> %s %.0fms", path, response.status_code, (time.monotonic() - started) * 1000)
        if response.status_code >= 400:
            raise SidecarError(_extract_error(response), "http_error")
        try:
            return response.json()
        except ValueError as exc:
            raise SidecarError("sidecar 返回了非 JSON 响应", "bad_response") from exc


def _extract_error(response: httpx.Response) -> str:
    """从 sidecar 错误响应里取人话；BossHunter 统一 ``{"error": "..."}``。"""
    try:
        data = response.json()
    except ValueError:
        return f"sidecar 返回 {response.status_code}"
    if isinstance(data, dict):
        for key in ("error", "message", "detail"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return f"sidecar 返回 {response.status_code}"
