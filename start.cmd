@echo off
title 求职通 (JobForge) - 8013
setlocal
rem This filename is inherited from upstream (whose start.cmd defaults to 8005).
rem Here it points at JobForge's own ports so it never collides with 1.0 (8005)
rem or 2.0 (8010).
rem
rem NOTE: keep every `rem` line ASCII-only -- see the same note in start-jobforge.cmd.
call "%~dp0start-jobforge.cmd" %*
