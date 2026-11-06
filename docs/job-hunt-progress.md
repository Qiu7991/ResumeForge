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
