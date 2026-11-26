@echo off
title JobForge - 8013
setlocal
rem Dedicated ports 8013/5176: avoids clashing with 1.0 (8005) and 2.0 (8010/5174).
rem Data dir is isolated by default: DATA_DIR points at this repo's backend/data.
rem
rem NOTE: keep every `rem` line here ASCII-only. This file is UTF-8 without BOM,
rem and cmd.exe decodes batch files with the OEM code page (cp936 on a Chinese
rem Windows). A multi-byte Chinese character whose trailing byte happens to be
rem 0x0A/0x0D can swallow the line ending, so the tail of the comment gets
rem executed as a command.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-ResumeForge.ps1" -BackendPort 8013 -FrontendPort 5176 -NoBrowser %*
if errorlevel 1 pause
