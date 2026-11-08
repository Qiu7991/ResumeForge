@echo off
title 工作通 (2.0 二开 + BossHunter) - 8012
setlocal
rem 独立端口 8012/5176，避免与正在使用的简历通 2.0（8010/5174）冲突。
rem 数据目录天然隔离：DATA_DIR 默认绑定各自 backend/data。
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-ResumeForge.ps1" -BackendPort 8012 -FrontendPort 5176 -NoBrowser %*
if errorlevel 1 pause
