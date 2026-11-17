# 控制台临时启动（非 Windows 服务）。正式环境请用 windows-service\install.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$Dist = Join-Path $Root "frontend\dist\index.html"
if (-not (Test-Path $Python)) { throw "请先运行 windows-service\setup.ps1" }
if (-not (Test-Path $Dist)) { throw "请先运行 windows-service\setup.ps1 完成前端构建" }
Write-Host "控制台模式启动（关掉窗口即停止）。开机自启请用 windows-service\install.ps1" -ForegroundColor Yellow
Set-Location $Backend
& $Python -m app.main
