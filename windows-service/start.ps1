# 启动 Windows 服务
. "$PSScriptRoot\_common.ps1"
Assert-Admin
$code = Invoke-ServiceExe start
if ($code -ne 0) {
    throw "启动失败，exit=$code。请查看 windows-service\logs\"
}
Write-Host "已启动。http://127.0.0.1:8787" -ForegroundColor Green
