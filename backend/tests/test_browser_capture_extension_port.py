"""页内收录扩展必须指向当前同源前端（8005）。

2026-10-31 切换到上游架构后，前端不再由 Vite 的 5173 提供；扩展仍写 5173 会让
「收录到简历通」打开 ERR_CONNECTION_REFUSED 的弹窗。这里钉住唯一来源。
"""

from pathlib import Path

EXTENSION = Path(__file__).resolve().parents[1] / "app/services/browser/extension"


def test_capture_extension_points_at_the_same_origin_app():
    content = (EXTENSION / "content.js").read_text(encoding="utf-8")
    assert 'const APP_ORIGIN = "http://127.0.0.1:8005"' in content
    assert "127.0.0.1:5173" not in content
    # 应用弹窗加载后先发 started，扩展据此把等待上限从 12 秒放宽到 120 秒。
    assert "resumeforge-import-started" in content


def test_capture_extension_manifest_is_reloaded_by_version_bump():
    manifest = (EXTENSION / "manifest.json").read_text(encoding="utf-8")
    assert '"version": "1.1.6"' in manifest
