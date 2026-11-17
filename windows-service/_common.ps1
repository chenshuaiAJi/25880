# 公共路径与工具（被其它脚本点源）
$ErrorActionPreference = "Stop"

$Script:ServiceDir = $PSScriptRoot
$Script:RepoRoot = Split-Path -Parent $PSScriptRoot
$Script:BackendDir = Join-Path $RepoRoot "backend"
$Script:FrontendDir = Join-Path $RepoRoot "frontend"
$Script:PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$Script:DistIndex = Join-Path $FrontendDir "dist\index.html"
$Script:EnvFile = Join-Path $BackendDir ".env"
$Script:WinSwDownload = Join-Path $ServiceDir "WinSW-x64.exe"
$Script:ServiceExe = Join-Path $ServiceDir "JL-AUTO.exe"
$Script:ServiceXml = Join-Path $ServiceDir "JL-AUTO.xml"
$Script:ServiceId = "JL-AUTO"
$Script:LogsDir = Join-Path $ServiceDir "logs"
$Script:WinSwUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "请用「以管理员身份运行」的 PowerShell 执行本脚本"
    }
}

function Ensure-LogsDir {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}

function Get-PgServiceName {
    param([string]$Override = "")
    if ($Override -ne "") {
        return $Override
    }
    $candidates = @(
        "postgresql-x64-16",
        "postgresql-x64-17",
        "postgresql-x64-15",
        "postgresql-x64-14"
    )
    foreach ($name in $candidates) {
        $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
        if ($null -ne $svc) {
            return $name
        }
    }
    $found = Get-Service | Where-Object { $_.Name -like "postgresql*" } | Select-Object -First 1
    if ($null -ne $found) {
        return $found.Name
    }
    return ""
}

function Assert-RuntimeReady {
    if (-not (Test-Path $PythonExe)) {
        throw "找不到后端虚拟环境：$PythonExe`n请先运行 .\setup.ps1"
    }
    if (-not (Test-Path $DistIndex)) {
        throw "找不到前端构建产物：$DistIndex`n请先运行 .\setup.ps1"
    }
    if (-not (Test-Path $EnvFile)) {
        throw "找不到 backend\.env，请先运行 .\setup.ps1"
    }
}

function Ensure-WinSw {
    if (-not (Test-Path $WinSwDownload)) {
        Write-Host "下载 WinSW ..." -ForegroundColor Cyan
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $WinSwUrl -OutFile $WinSwDownload -UseBasicParsing
        if (-not (Test-Path $WinSwDownload)) {
            throw "WinSW 下载失败，请手动把 WinSW-x64.exe 放到：$ServiceDir"
        }
    }
    Copy-Item -Force $WinSwDownload $ServiceExe
}

function Write-ServiceXml {
    param([string]$PgServiceName)

    Ensure-LogsDir
    $exe = $PythonExe
    $work = $BackendDir
    $log = $LogsDir
    $dependXml = ""
    if ($PgServiceName -ne "") {
        $dependXml = "  <depend>$PgServiceName</depend>"
    }

    $xml = @"
<service>
  <id>$ServiceId</id>
  <name>JL-AUTO 门店对账</name>
  <description>门店对账本机服务。浏览器访问 http://127.0.0.1:8787</description>
  <executable>$exe</executable>
  <arguments>-m app.main</arguments>
  <workingdirectory>$work</workingdirectory>
$dependXml
  <startmode>Automatic</startmode>
  <logpath>$log</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
  <onfailure action="restart" delay="10 sec"/>
  <onfailure action="restart" delay="20 sec"/>
  <onfailure action="restart" delay="30 sec"/>
  <resetfailure>1 hour</resetfailure>
</service>
"@
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($ServiceXml, $xml, $utf8)
}

function Invoke-ServiceExe {
    param([Parameter(Mandatory = $true)][string]$Command)
    Assert-RuntimeReady
    if (-not (Test-Path $ServiceExe)) {
        throw "找不到 $ServiceExe，请先运行 .\install.ps1"
    }
    if (-not (Test-Path $ServiceXml)) {
        throw "找不到 $ServiceXml，请先运行 .\install.ps1"
    }
    & $ServiceExe $Command
    return $LASTEXITCODE
}
