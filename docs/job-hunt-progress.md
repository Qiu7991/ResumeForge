# 自研 AI 求职 · 进度日志（追加式）

> 规则：每张卡结束追加一节：闸门输出摘要 → 结论 → commit。

## J0 骨架与开关（进行中）

- 新增 `backend/app/services/job_hunt/`：`base.py`（JobSiteAdapter/JobStub/JobDetail/HuntCriteria/JobParseError）、`registry.py`（JobHuntRegistry，照 sites/registry.py 模式）、`settings.py`（job_hunt_config KV 读写，照 ai_jobs/settings.py 模式）、`__init__.py`
- 新增 `backend/app/schemas/job_hunt.py`：`job_hunt_backend`，默认 `sidecar`，可选 `native`
- `scripts/fork_gate.py` 新增 `phase_10()`（12 项检查，未开工卡输出 SKIP；带 `_IN_PHASE_10` 重入保护，phase 0–9 未动一字）
- 建三件套 docs/job-hunt-taskboard.md / progress.md / blocked.md；登记 BLOCKED-FIXTURE-JOB51
- L1 导入检查：import OK，默认配置 `job_hunt_backend='sidecar'`
- 闸门 phase_10 首跑：见下

（待填：闸门输出）

**phase_10 首跑输出（J0，2026-11-07 夜）**：

```
PASS services/job_hunt/ 目录存在 — backend\app\services\job_hunt
PASS base.py 定义 JobSiteAdapter — backend\app\services\job_hunt\base.py
PASS registry.py 有注册表 — backend\app\services\job_hunt\registry.py
PASS 设置项 job_hunt_backend 默认 sidecar — 字段=True 默认sidecar=True
PASS job_hunt_config 设置值合法 — 未设置（默认 sidecar 生效）
SKIP BOSS 字体解密存在 — J2 未完成（sites/boss_font.py 不存在）
SKIP runner.py 存在 — J3 未完成
SKIP application_routers 注册 job_hunt — J9 未完成（默认走 sidecar 旧路径）
SKIP pytest -k job_hunt 全绿 — 尚无 test_job_hunt_*.py 测试
PASS job_hunt 无 BossHunter 代码混入 — polyform 命中=无，import 命中=无
PASS pytest -k ai_jobs 全绿（旧路径未破坏） — returncode=0；125 passed, 1 skipped in 68.47s
PASS dist 比 src 新 — dist mtime=1793987589.24 src mtime=1793987310.39
FAIL 前 9 阶段复跑无 FAIL — 复跑 FAIL=2（根因：1.x 库 167444480B ≠ 冻结基线 160989184B，存量环境问题，见 blocked.md BLOCKED-GATE-1X-DBSIZE）

汇总：PASS=8 FAIL=1 SKIP=4
```

**结论**：J0 自身 11 项全 PASS/SKIP；唯一 FAIL 为继承的 1.x 库尺寸基线问题（非本轮
造成，证据见 blocked.md）。按 E8 不重试，J0 完成。

## J2 BOSS 薪资字体解密（commit 待填）

**夹具实证（boss_list.html + boss_detail.html）**：
- 列表 15 张卡薪资全部是 U+E031–U+E03A 的 PUA 编码；夹具里**没有字体文件**
  （无 @font-face、唯一 base64 块是 PNG）；
- **详情页主岗位薪资是明文**（`<span class="salary">8-12K</span>` + meta + JS 三处），
  与列表第一张卡同岗位（AI人工智能技术员（服装方向））→ 得到 ground-truth 对照对
  `[E039]-[E032][E033]K == 8-12K`；
- 跨平台（智联/猎聘/51job）无同名岗位，交叉匹配路径穷尽。

**实现**（`services/job_hunt/sites/boss_font.py`，全部自写）：
1. `build_digit_map_from_font`：fontTools 读 glyf 轮廓 → 包围盒归一化量化签名 →
   与同字体数字字形比对（支持复合字形展开）；woff2 缺 brotli 时诚实降级；
2. `mapping_from_pairs`：明文对照逐位对齐 + 多数票（生产上每打开一个详情页就多一对）；
3. `mapping_from_constraints`：整页区间「左<右 + 一一对应 + 量级合理」穷举，**只输出
   全部可行解中取值唯一的符号**（18 个可行解，宁缺毋假）；
4. `decode_salary`：纯替换，映射缺失保留原字符并标 `ok=False`，永不抛异常。

**解密成果**：6/10 符号有实证钉死（E032=1/E033=2/E039=8 来自明文对照；
E031=0/E034=3/E035=4 为约束唯一解）；E036/E037/E038/E03A 候选 ⊆ {5,6,7,9} 且多解，
**老实留在候选集**（真实字体文件或更多详情页明文可收敛）。4 张卡完整还原：
8-12K / 8-13K×2 / 12-24K（字符集 ⊆ 已钉死符号）。

**闸门（J2 后 --phase 10）**：检查 5「BOSS 字体解密存在」PASS；检查 8「pytest -k
job_hunt 全绿」PASS（21 passed in 4.33s）；其余同 J0（唯一 FAIL 仍为 1.x 库尺寸存量问题）。

**测试**：21 例全绿（decode 边界 / 对照对 / 约束求解 / 合成字体含复合字形 / 真夹具断言）。
fontTools 实测坑已记录：fontBuilder 编译 cmap format 4 会丢 glyphId=1 的映射（合成字体
用垫片字形绕开）；`endPtsOfContours` 存终点索引而非计数。

## J3 采集器抽象层（commit 待填）

**实现**（`services/job_hunt/runner.py`）：
- `JobHuntRunner.run(criteria, fetch=, on_progress=)`：拼 URL → 取页面 → 解析 → 翻页 →
  URL 去重（fragment 归一）→ `HuntReport`（stubs/pages_fetched/duplicates/stopped_reason/
  errors/visited_pages，visited_pages 留给 J7 游标）；
- 停止语义五档：max_pages / no_results / repeated_page（整页全重复，站点循环推送）/
  stopped（on_progress 返回 False）/ parse_error+fetch_error（记账即停）；
- 抓取器注入：生产 `cdp_fetcher(client)` 复用既有 CdpClient.navigate + page_ready
  轮询原语 + outerHTML（不自建浏览器管理）；无 fetcher 快速失败（防止被逐页 except
  吞成 fetch_error）；测试注入假抓取器（E17 夜间不连真实网站）。

**测试**：14 例（翻页/跨页去重/上限/整页重复早停/解析与抓取错误记账/进度喊停/
criteria 归一化/无链卡片丢弃/fragment 去重/假 CDP 客户端消息编排/超时大声失败/空页）。

**闸门（J3 后 --phase 10）**：检查 6「runner.py 存在」PASS；检查 8 PASS（35 passed in
5.26s）；其余同前（唯一 FAIL 仍为 1.x 库尺寸存量问题）。
