# 卸载 Windows 服务（保留数据库与 file\）
. "$PSScriptRoot\_common.ps1"
Assert-Admin

$existing = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
if ($null -eq $existing) {
    Write-Host "服务 $ServiceId 不存在，无需卸载。" -ForegroundColor Yellow
    exit 0
}

if (-not (Test-Path $ServiceExe)) {
    Ensure-WinSw
}
if (-not (Test-Path $ServiceXml)) {
    Write-ServiceXml -PgServiceName (Get-PgServiceName)
}

Write-Host "停止并卸载 $ServiceId ..." -ForegroundColor Cyan
& $ServiceExe stop 2>$null
Start-Sleep -Seconds 1
& $ServiceExe uninstall
if ($LASTEXITCODE -ne 0) {
    throw "卸载失败，exit=$LASTEXITCODE"
}
Write-Host "已卸载服务。数据库与 file\ 仍保留。" -ForegroundColor Green
