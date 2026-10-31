"""Ego Lite 与随应用扩展的启动参数（本地二开回放）。"""

from __future__ import annotations

from pathlib import Path

from test_apply_browser_manager import FakePopen, _manager, _transport

from app.services.browser.browser_manager import BrowserManager, browser_display_name


def test_locate_browser_uses_ego_lite_when_chosen(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _name: None)
    program_files = tmp_path / "pf"
    ego_dir = program_files / "Citro Labs" / "ego lite" / "Application"
    ego_dir.mkdir(parents=True)
    ego = ego_dir / "ego.exe"
    ego.write_text("")
    chrome_dir = program_files / "Google" / "Chrome" / "Application"
    chrome_dir.mkdir(parents=True)
    (chrome_dir / "chrome.exe").write_text("")

    manager = BrowserManager(
        profile_dir=tmp_path / "profile",
        browser_path=None,
        browser_choice="ego",
        env={"PROGRAMFILES": str(program_files)},
        popen=FakePopen(),
        http_transport=_transport(),
    )

    assert manager._locate_browser() == ego


def test_ego_lite_has_its_own_chinese_name():
    assert browser_display_name(r"C:\Program Files\Citro Labs\ego lite\Application\ego.exe") == (
        "Ego Lite（Chromium）"
    )


def test_start_arguments_load_the_bundled_capture_extension(tmp_path):
    from app.services.browser import browser_manager

    extension_dir = Path(browser_manager.__file__).resolve().parent / "extension"
    assert (extension_dir / "manifest.json").is_file()

    manager, _popen = _manager(tmp_path)
    args = manager._start_arguments(tmp_path / "chrome.exe")

    assert any(str(arg).startswith("--load-extension=") for arg in args)
    assert any(str(arg).startswith("--disable-extensions-except=") for arg in args)
    assert args[-1] == "about:blank"
