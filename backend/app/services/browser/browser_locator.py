"""浏览器安装位置与显示名：从 browser_manager 拆出的纯数据部分。

这些常量只描述"常见安装在哪、路径像哪个浏览器"，不含任何启动/CDP 逻辑，
单独成文件既方便测试，也让管理器本体留在行数预算内。
"""

from __future__ import annotations

from pathlib import Path

# 常见安装位置（按"优先 Chrome、其次 Edge"的顺序排列）。用环境变量拼，避免把某个
# 用户的绝对路径写死；Windows 之外的平台退回 PATH 查找。
CHROME_RELATIVE = (
    ("PROGRAMFILES", r"Google\Chrome\Application\chrome.exe"),
    ("PROGRAMFILES(X86)", r"Google\Chrome\Application\chrome.exe"),
    ("LOCALAPPDATA", r"Google\Chrome\Application\chrome.exe"),
)
EDGE_RELATIVE = (
    ("PROGRAMFILES(X86)", r"Microsoft\Edge\Application\msedge.exe"),
    ("PROGRAMFILES", r"Microsoft\Edge\Application\msedge.exe"),
    ("LOCALAPPDATA", r"Microsoft\Edge\Application\msedge.exe"),
)
# Ego Lite（Citro Labs 的 Chromium 分支）：安装目录带空格，且版本号在子目录里，
# 但 Application 下有一份与 Chrome 同构的 ego.exe，直接指向它即可。
EGO_RELATIVE = (
    ("PROGRAMFILES", r"Citro Labs\ego lite\Application\ego.exe"),
    ("PROGRAMFILES(X86)", r"Citro Labs\ego lite\Application\ego.exe"),
    ("LOCALAPPDATA", r"Programs\ego lite\Application\ego.exe"),
)

_CHROME_NAME = "Google Chrome"
_EDGE_NAME = "Microsoft Edge"
_EGO_NAME = "Ego Lite（Chromium）"
_CUSTOM_NAME = "自定义浏览器"


def browser_display_name(path: str | Path | None) -> str:
    """由可执行文件路径推断人类可读的浏览器名。"""
    if not path:
        return ""
    name = Path(path).name.casefold()
    parent = Path(path).parent.as_posix().casefold()
    # Ego Lite 的主程序叫 ego.exe，靠名字就够；额外认一下安装目录，兼容它改名的情况。
    if name in ("ego.exe", "ego-browser.exe") or "citro labs" in parent:
        return _EGO_NAME
    if "msedge" in name or "edge" in name:
        return _EDGE_NAME
    if "chrome" in name:
        return _CHROME_NAME
    return _CUSTOM_NAME


def bundled_extension_arguments(extension_dir: Path) -> list[str]:
    """随应用分发的扩展的启动参数；目录里没有 manifest 时返回空列表。"""
    if not (extension_dir / "manifest.json").is_file():
        return []
    return [
        f"--load-extension={extension_dir}",
        f"--disable-extensions-except={extension_dir}",
        "--disable-features=DisableLoadExtensionCommandLineSwitch",
    ]


__all__ = [
    "CHROME_RELATIVE",
    "EDGE_RELATIVE",
    "EGO_RELATIVE",
    "bundled_extension_arguments",
    "browser_display_name",
]
