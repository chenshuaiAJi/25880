# 注册并启动 Windows 服务（需管理员）
param(
    [string]$PgServiceName = ""
)

. "$PSScriptRoot\_common.ps1"
Assert-Admin
Assert-RuntimeReady

$pg = Get-PgServiceName -Override $PgServiceName
if ($pg -eq "") {
    Write-Host "未检测到 PostgreSQL Windows 服务，将不写服务依赖。请确认数据库已安装并可连接。" -ForegroundColor Yellow
} else {
    Write-Host "依赖 PostgreSQL 服务: $pg" -ForegroundColor Cyan
    $svc = Get-Service -Name $pg
    if ($svc.Status -ne "Running") {
        Start-Service -Name $pg
        Write-Host "已启动 $pg" -ForegroundColor Cyan
    }
}

Ensure-WinSw
Write-ServiceXml -PgServiceName $pg

$existing = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
if ($null -ne $existing) {
    Write-Host "服务已存在，先停止并刷新配置..." -ForegroundColor Yellow
    & $ServiceExe stop 2>$null
    Start-Sleep -Seconds 1
    & $ServiceExe uninstall
    Start-Sleep -Seconds 1
}

Write-Host "安装服务 $ServiceId ..." -ForegroundColor Cyan
& $ServiceExe install
if ($LASTEXITCODE -ne 0) {
    throw "WinSW install 失败，exit=$LASTEXITCODE"
}

& $ServiceExe start
if ($LASTEXITCODE -ne 0) {
    throw "服务启动失败，exit=$LASTEXITCODE。请查看 windows-service\logs\"
}

Start-Sleep -Seconds 2
$status = & $ServiceExe status
Write-Host "服务状态: $status" -ForegroundColor Green
Write-Host "浏览器打开: http://127.0.0.1:8787" -ForegroundColor Green
Write-Host "也可执行: .\open-ui.ps1"
