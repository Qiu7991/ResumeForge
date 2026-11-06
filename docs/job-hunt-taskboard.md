# 自研 AI 求职任务板（分支 feat/gongzuotong）

> 恢复规则：新会话第一件事读本文件，找到第一个非 [x] 项继续。
> 计划文档：`D:\飞牛文件同步\工作\工作通-自研求职复刻计划.md`（§8 任务卡 / §2 红线）。
> 夹具：`docs/job-hunt-fixtures/`（7 份真实页面 HTML，**不进 git**，缺 job51_detail）。

| 任务 | 状态 | 结论 / commit | 备注 |
|---|---|---|---|
| J0 骨架与开关 | [ ] | | base/registry/设置/phase_10/三件套 |
| J1 夹具采集 | [ ] | | 已由用户采好，本卡=核对+加载器+登记缺失 |
| J2 BOSS 字体解密 | [ ] | | 最关键；夹具 boss_list.html 里有编码薪资 |
| J3 采集器抽象层 | [ ] | | runner：翻页/去重/进度 |
| J4 智联采集 | [ ] | | 夹具 zhilian_list/detail.html |
| J5 51job 采集 | [ ] | | 只有列表夹具，详情 BLOCKED |
| J6 猎聘采集 | [ ] | | 夹具 liepin_list/detail.html |
| J7 断点续采 | [ ] | | 游标存 app_setting KV |
| J8 回复监测 | [ ] | | 只读不发送 |
| J9 前端切换 | [ ] | | 开关 job_hunt_backend，默认 sidecar |
| J10 全量闸门与报告 | [ ] | | 必做；晨间报告 docs/job-hunt-morning-report.md |
