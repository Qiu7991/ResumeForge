@echo off
title ResumeForge 2.0 (8010)
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-ResumeForge.ps1" -BackendPort 8010 -FrontendPort 5174 -NoBrowser %*
if errorlevel 1 pause
