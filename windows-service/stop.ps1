# 停止 Windows 服务
. "$PSScriptRoot\_common.ps1"
Assert-Admin
$code = Invoke-ServiceExe stop
if ($code -ne 0) {
    throw "停止失败，exit=$code"
}
Write-Host "已停止。" -ForegroundColor Green
