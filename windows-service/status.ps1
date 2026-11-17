# 查看服务状态
. "$PSScriptRoot\_common.ps1"

$svc = Get-Service -Name $ServiceId -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    Write-Host "服务未安装（$ServiceId）" -ForegroundColor Yellow
    Write-Host "请管理员执行: .\install.ps1"
    exit 1
}

Write-Host ("Windows 服务: {0} / {1}" -f $svc.Name, $svc.Status)
if (Test-Path $ServiceExe) {
    $winsw = & $ServiceExe status 2>$null
    Write-Host "WinSW 状态: $winsw"
}
Write-Host "页面: http://127.0.0.1:8787"
Write-Host "日志: $LogsDir"
