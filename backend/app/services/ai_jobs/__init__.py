# SPDX-License-Identifier: Apache-2.0
"""AI 求职适配层：把 BossHunter sidecar（独立进程）接入简历通。

分层：``settings``（配置 KV）→ ``client``（HTTP 客户端）→ ``manager``（进程生命周期）
→ ``status``（聚合状态/预检）→ ``api/ai_jobs``（路由）。本包不复制 BossHunter 源码；
BossHunter 由用户自行安装，作为本地外部依赖经 loopback HTTP 调用。
"""
