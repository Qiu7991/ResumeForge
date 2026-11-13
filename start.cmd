@echo off
title 工作通 (2.0 二开 + 求职采集, 8012)
setlocal
rem This filename is inherited from upstream (whose start.cmd defaults to 8005).
rem Here it points at 工作通's own ports so it never collides with 简历通 1.0
rem (8005) or 简历通 2.0 (8010).
rem
rem NOTE: keep every `rem` line ASCII-only — see the same note in start-gzt.cmd.
call "%~dp0start-gzt.cmd" %*
