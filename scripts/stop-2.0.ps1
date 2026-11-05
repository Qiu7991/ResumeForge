# SPDX-License-Identifier: Apache-2.0
# 只按本目录 runtime\*.json 的 PID 记录停止，绝不扫描端口、绝不按进程名匹配。
# 原因：上游 Stop-ResumeForge.ps1 的兜底会枚举所有监听端口并用
# "uvicorn app.main:app" 匹配，1.x 与 2.0 都满足该条件，会互相误杀。
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDirectory = Join-Path $ProjectRoot "runtime"

function Stop-ByRecord {
    param([string]$DisplayName, [string]$RecordPath, [string]$Pattern)

    if (-not (Test-Path -LiteralPath $RecordPath)) {
        Write-Host "${DisplayName}：没有启动记录，跳过。"
        return
    }
    $record = Get-Content -LiteralPath $RecordPath -Raw -Encoding utf8 | ConvertFrom-Json
    $processId = [int]$record.process_id

    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Host "${DisplayName}：记录已过期（进程不存在），清理记录。"
        Remove-Item -LiteralPath $RecordPath -Force -ErrorAction SilentlyContinue
        return
    }

    $info = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
    if ($null -eq $info) {
        Write-Host "${DisplayName}：无法读取进程信息，跳过（不冒险）。"
        return
    }
    if ([string]$info.CommandLine -notmatch $Pattern) {
        Write-Host "${DisplayName}：命令行不匹配，跳过（防止 PID 复用误杀）。"
        return
    }

    & taskkill.exe /PID $processId /T /F | Out-Null
    Write-Host "${DisplayName}：已停止（PID $processId）。"
    Remove-Item -LiteralPath $RecordPath -Force -ErrorAction SilentlyContinue
}

Write-Host "正在停止简历通 2.0 ..."
Stop-ByRecord -DisplayName "前端" -RecordPath (Join-Path $RuntimeDirectory "frontend.json") -Pattern "npm\.cmd.*\brun\s+dev"
Stop-ByRecord -DisplayName "后端" -RecordPath (Join-Path $RuntimeDirectory "backend.json") -Pattern "uvicorn\s+app\.main:app"
Write-Host "已完成。数据库与配置没有被修改。"
