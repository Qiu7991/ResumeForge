@echo off
title 工作通 (2.0 二开 + BossHunter) - 8012
setlocal
rem Dedicated ports 8012/5176: avoids clashing with 简历通 2.0 (8010/5174).
rem Data dir is isolated by default: DATA_DIR points at this repo's backend/data.
rem
rem NOTE: keep every `rem` line here ASCII-only. This file is UTF-8 without BOM,
rem and cmd.exe decodes batch files with the OEM code page (cp936 on a Chinese
rem Windows). A multi-byte Chinese character whose trailing byte happens to be
rem 0x0A/0x0D can swallow the line ending, so the tail of the comment gets
rem executed as a command ("'绂伙：DATA_DIR' 不是内部或外部命令").
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-ResumeForge.ps1" -BackendPort 8012 -FrontendPort 5176 -NoBrowser %*
if errorlevel 1 pause
