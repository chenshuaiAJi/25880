# 首次准备：后端 venv + 前端构建 + .env
. "$PSScriptRoot\_common.ps1"

Write-Host "==> 后端虚拟环境" -ForegroundColor Cyan
Set-Location $BackendDir
if (-not (Test-Path $PythonExe)) {
    python -m venv .venv
}
& $PythonExe -m pip install --upgrade pip
& (Join-Path $BackendDir ".venv\Scripts\pip.exe") install -r (Join-Path $BackendDir "requirements.txt")

$envExample = Join-Path $BackendDir ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $envExample) {
        Copy-Item $envExample $EnvFile
    } else {
        $content = "DATABASE_URL=postgresql://postgres:jlauto_dev@127.0.0.1:5432/jlauto`r`nHOST=127.0.0.1`r`nPORT=8787`r`n"
        $utf8 = New-Object System.Text.UTF8Encoding $false
        [System.IO.File]::WriteAllText($EnvFile, $content, $utf8)
    }
    Write-Host "已创建 backend\.env，正式环境请改掉弱密码" -ForegroundColor Yellow
}

Write-Host "==> 前端依赖与构建" -ForegroundColor Cyan
Set-Location $FrontendDir
if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
    throw "未找到 pnpm。请先安装 Node.js 20，再执行: npm install -g pnpm"
}
pnpm install
pnpm build
if (-not (Test-Path $DistIndex)) {
    throw "前端构建失败：找不到 frontend\dist\index.html"
}

Ensure-LogsDir
Write-Host ""
Write-Host "准备完成。接下来（管理员）执行: .\install.ps1" -ForegroundColor Green
