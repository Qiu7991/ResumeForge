# AI 求职适配 · 阻塞清单

> 格式：任务号 | 现象 | 已试方案 | 证据 | 建议。空 = 无阻塞。

---

（暂无）
## 【A3，2026-11-06 夜】

- SK-1 | 1.x 测试 `test_ai_jobs_redteam_fixes.py::test_deliver_allowed_when_env_absent` 断言「环境变量未设置 → 投递 200」，与 2.0 红线 4/8（发送总闸默认关、未设置必须 403）直接冲突 | 按 E4 不改断言；按红线 6 豁免路径对该用例加 `@pytest.mark.skip` 并引用本条；2.0 语义由新增 `test_ai_jobs_send_gate.py`（A4 卡）正向覆盖（默认关/显式开/显式 0 三态） | 1.x api/ai_jobs.py:153 的 `== "0"` 形态=默认放行；计划红线与 phase_8 检查 5 均要求默认关 | 若用户要 1.x 语义，需同时改红线 4/8、phase_8 检查 5（E10 已冻结）与本测试——属产品决策，夜间不擅自做
- NOTE-1 | 发送总闸落点：计划 §10.1 写「gate.py、delivery.py」，实际定稿在 **API 层**（api/ai_jobs.py deliver 端点调 `delivery.send_gate_open()`） | 1.x 架构即 API 层环境闸；若放服务层 `deliver()` 内，1.x 的服务级直调测试（`test_deliver_success_returns_task` 等无环境设置直接调 `delivery.deliver` 期望成功/409 语义）必然全红，E4 禁改断言 → 只能维持 API 层 | phase_8 检查 5 的判定域包含 api/ai_jobs.py（A0 冻结时已写入），PASS 不受影响 | 无（防御层次：API 层 403 + 引擎侧二次校验仍都在）
- NOTE-3 | A8 的 `-k "ai_jobs or apply"` 联合选择器下，`test_dataset_scope.py::test_apply_task_runner_holds_a_lease_for_the_task_duration` 失败（leases_pending==2） | 根因是测试间全局态污染，非产品缺陷：`test_ai_jobs_tasks.py` 与 e2e 全流程用例启动 AI 任务后不在用例内停止，`ai-jobs` 数据集租约悬挂到 `dataset_scope._leases`；1.x 同样泄漏，只是 1.x 从未跑过这个联合选择器（A8 新增口径）。处置（不动任何断言，E4）：给 `test_ai_jobs_tasks.py` 的既有 autouse `_reset_busy` 补租约释放一行；给 e2e `sidecar` fixture 加 teardown 释放 busy+租约 | 复现：两用例最小组合 + 全量 union 均稳定复现；修复后 567 passed / 1 skipped | 无
