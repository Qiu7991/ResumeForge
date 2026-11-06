# 采集夹具（真实页面样本）

> 2026-11-07 由登录态浏览器（CDP 抓取 `document.documentElement.outerHTML`）导出。
> **不进 git**（含真实岗位与公司信息），已在 `.gitignore` 排除 `*.html`。

## 已采集

| 文件 | 平台 | 类型 | 大小 | 岗位数 | 用途 |
|---|---|---|---|---|---|
| `boss_list.html` | BOSS直聘 | 搜索列表 | 246 KB | 15 张卡片 | 解析列表：标题/公司/薪资/地区 |
| `boss_detail.html` | BOSS直聘 | 岗位详情 | 77 KB | — | 解析 JD；**薪资是字体加密的** |
| `zhilian_list.html` | 智联 | 搜索结果 | 1.6 MB | 41 条链接 | 解析列表 |
| `zhilian_detail.html` | 智联 | 岗位详情 | 2.2 MB | — | 解析 JD（含完整职责/要求） |
| `job51_list.html` | 前程无忧 | 搜索结果 | 668 KB | 160 项 | 解析列表 |
| `liepin_list.html` | 猎聘 | 搜索结果 | 194 KB | 40 个链接 | 解析列表 |
| `liepin_detail.html` | 猎聘 | 岗位详情 | 210 KB | — | 解析 JD（含薪资、公司、职责） |

## 缺一个

**`job51_detail.html`**：51job 的岗位详情是 `.detail-wrapper` 抽屉，点击后弹出的是
「微信扫码与我聊聊」提示，没有正文。该平台详情页需要登录后才有完整内容。

→ 记入 `docs/job-hunt-blocked.md`，等人工补。

## 关键发现（给 J2 字体解密用）

BOSS 列表里的薪资是**字体编码的乱码**，实测样本：

```
\ue035-\ue03aK          ← 应为 8-12K
\ue035-\ue037K·\ue032\ue034薪
```

这证明 J2（BOSS 字体解密）是必须做的：不解密，采回来的薪资全是废数据。

## 怎么用

```python
from pathlib import Path
FIXTURES = Path(__file__).parents[2] / "docs" / "job-hunt-fixtures"

def load(name: str) -> str:
    p = FIXTURES / name
    if not p.exists():
        import pytest; pytest.skip(f"缺夹具 {name}")
    return p.read_text(encoding="utf-8")
```

## 怎么补新的

用登录态 Chrome + CDP：

```bash
chrome.exe --remote-debugging-port=9250 --user-data-dir=<独立profile> <搜索页URL>
# 登录后，从 /json/list 取 webSocketDebuggerUrl，
# Runtime.evaluate: document.documentElement.outerHTML
```
