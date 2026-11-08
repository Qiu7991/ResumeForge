"""抓取 BOSS 薪资字体文件（用于收敛剩余 4 个未定符号）。

背景
----
BOSS 列表页薪资是 PUA 码点（U+E031..U+E03A）经自定义字体映射后的文本。已知 6 个符号
靠「详情页明文对照 + 区间约束」确定，剩余 4 个（U+E036/37/38/3A）候选集多解，必须拿到
**真实字体文件**做字形轮廓比对才能收敛。

做法
----
用投递台已启动的专用浏览器（9333），打开 BOSS 搜索页，监听 ``Network.responseReceived``，
筛出 ``font`` 类型资源，逐个 ``Network.getResponseBody`` 拿下 base64 内容，存到
``docs/job-hunt-fixtures/boss_font_<hash>.woff``（或 ttf）。

不改任何页面状态、不点击、不提交。

用法
----
    backend/.venv/Scripts/python.exe -I scripts/capture_boss_font.py
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.browser.cdp_client import WebsocketCdpClient  # noqa: E402

OUT = ROOT / "docs" / "job-hunt-fixtures"
CDP_HTTP = "http://127.0.0.1:9333"
SEARCH_URL = "https://www.zhipin.com/web/geek/jobs?query=AI&cityName=%E5%B9%BF%E5%B7%9E"


def _target_id() -> str:
    tabs = json.load(urllib.request.urlopen(f"{CDP_HTTP}/json/list", timeout=10))
    pages = [t for t in tabs if t.get("type") == "page" and "zhipin" in (t.get("url") or "")]
    if not pages:
        pages = [t for t in tabs if t.get("type") == "page"]
    if not pages:
        raise SystemExit("没有打开的页面")
    return pages[0]["id"]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    target = _target_id()
    print(f"目标标签: {target}")

    client = WebsocketCdpClient(port=9333, target_id=target)
    try:
        # 订阅网络响应事件（域启用是幂等的）
        client.start_event_capture(["Network.responseReceived"])
        print(f"导航到搜索页：{SEARCH_URL}")
        client.navigate(SEARCH_URL)

        # 等页面渲染 + 字体加载（字体通常在列表渲染后按需加载，多等一会）
        for _ in range(20):
            if client.evaluate("document.readyState") == "complete":
                break
            time.sleep(0.5)
        time.sleep(5)

        events = client.drain_events()
        client.stop_event_capture()
        print(f"捕获 {len(events)} 帧网络事件")

        font_urls: list[str] = []
        for ev in events:
            params = ev.get("params") or {}
            resp = params.get("response") or {}
            rtype = (resp.get("type") or "").lower()
            url = resp.get("url") or ""
            if rtype == "font" or any(url.lower().endswith(ext) for ext in (".woff", ".woff2", ".ttf", ".otf")):
                if url and url not in font_urls:
                    font_urls.append(url)

        print(f"字体资源 {len(font_urls)} 个：")
        for u in font_urls:
            print(f"  {u[:110]}")

        if not font_urls:
            print("\nFAIL 没拦到字体。可能原因：")
            print("  1. 页面用了缓存（字体不再请求）→ 在浏览器里 Ctrl+Shift+R 强刷后重跑")
            print("  2. 字体走 CSS @font-face 内联 base64（不是网络请求）→ 从页面 CSS 里取")
            return 2

        saved = 0
        for url in font_urls:
            try:
                # 用页内 fetch 取（同源、带 cookie），转 base64 传回
                expr = (
                    "fetch(%s).then(r => r.arrayBuffer())"
                    ".then(b => btoa(String.fromCharCode(...new Uint8Array(b))))"
                    % json.dumps(url)
                )
                b64 = client.evaluate(expr)
                if not isinstance(b64, str) or not b64:
                    print(f"  跳过（取不到内容）: {url[:80]}")
                    continue
                raw = base64.b64decode(b64)
                digest = hashlib.sha1(raw).hexdigest()[:10]
                ext = ".woff2" if "woff2" in url else ".woff" if "woff" in url else ".ttf"
                path = OUT / f"boss_font_{digest}{ext}"
                path.write_bytes(raw)
                print(f"  已保存 {path.name} ({len(raw):,} 字节)")
                saved += 1
            except Exception as exc:  # noqa: BLE001
                print(f"  失败 {url[:60]}: {type(exc).__name__}: {exc}")

        print(f"\n共保存 {saved} 个字体文件到 {OUT}")
        return 0 if saved else 3
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
