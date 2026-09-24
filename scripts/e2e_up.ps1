#Requires -Version 5.1
<#
E2E 一键入口（Windows）：
  1. 准备隔离库 .e2e/query.db（拷贝演示库，不碰 data/query.db）
  2. 签发测试 Key，注入 E2E_API_KEY
  3. 起 Playwright（自动拉起 8001 后端 + 5174 前端）并跑完全部用例
用法：powershell -ExecutionPolicy Bypass -File scripts/e2e_up.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

New-Item -ItemType Directory -Path ".e2e" -Force | Out-Null
if (Test-Path ".e2e/query.db") { Remove-Item ".e2e/query.db" -Force }
Copy-Item "data/query.db" ".e2e/query.db"
Write-Host "e2e db prepared (fresh copy)"
$Key = (python scripts/manage_keys.py --db .e2e/query.db create --name e2e | Select-Object -Last 1).Trim()
if (-not $Key.StartsWith("dqc_")) { throw "key issue failed: $Key" }
$env:E2E_API_KEY = $Key
Write-Host "E2E_API_KEY ready"

Set-Location (Join-Path $Root "frontend")
npx playwright test
