# 自研 AI 求职任务板（分支 feat/gongzuotong）

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 项继续。
> 计划文档：`D:\飞牛文件同步\工作\工作通-自研求职复刻计划.md`（§8 任务卡 / §2 红线）。
> 夹具：`docs/job-hunt-fixtures/`（7 份真实页面 HTML，**不进 git**，缺 job51_detail）。

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| J0 骨架与开关 | [x] | 4664557 | 自身 11 项 PASS/SKIP；唯一 FAIL=1.x 库尺寸基线（存量环境，见 blocked） |
| J1 夹具采集 | [x] | 8617b5e | 七件套齐全；job51_detail 缺失已登记 |
| J2 BOSS 字体解密 | [x] | 00b23e5 | 三路映射；6/10 符号实证钉死，4 个候选诚实留白 |
| J3 采集器抽象层 | [x] | 427ab86 | runner 翻页/去重/五档停止语义；cdp_fetcher 复用现有浏览器管理 |
| J4 智联采集 | [x] | d47a09c | 列表 20 条+详情全字段实证；URL 未实测→blocked |
| J5 51job 采集 | [x] | 485d117 | 只列表（20/20 卡）；详情 BLOCKED-FIXTURE-JOB51 |
| J6 猎聘采集 | [x] | 485d117 | 列表 40/40+详情全字段；URL 未实测→blocked |
| J7 断点续采 | [x] | 1cf41b0 | 游标 KV 持久化（未建表）；中断→恢复不重抓已测 |
| J8 回复监测 | [x] | 1cf41b0 | 意向分类+汇总（只读红线自检）；抓取侧 BLOCKED-REPLIES-FIXTURE |
| J9 前端切换 | [ ] | | /api/job-hunt/* + 设置页开关卡，默认 sidecar |
| J10 全量闸门与报告 | [ ] | | 必做；晨间报告 docs/job-hunt-morning-report.md |
