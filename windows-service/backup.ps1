# 备份 jlauto 库
param(
    [string]$BackupDir = "E:\JL-AUTO-backup",
    [string]$DatabaseUrl = ""
)

. "$PSScriptRoot\_common.ps1"

if ($DatabaseUrl -eq "" -and (Test-Path $EnvFile)) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*DATABASE_URL\s*=\s*(.+)\s*$') {
            $DatabaseUrl = $Matches[1].Trim()
        }
    }
}
if ($DatabaseUrl -eq "") {
    $DatabaseUrl = "postgresql://postgres:jlauto_dev@127.0.0.1:5432/jlauto"
}

if ($DatabaseUrl -notmatch '^postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/([^/?]+)') {
    throw "DATABASE_URL 无法解析: $DatabaseUrl"
}
$user = $Matches[1]
$password = $Matches[2]
$hostName = $Matches[3]
$port = $Matches[4]
$db = $Matches[5]

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$outFile = Join-Path $BackupDir "jlauto-$stamp.dump"

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if ($null -ne $pgDump) {
    $pgDumpPath = $pgDump.Source
} else {
    $guess = "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe"
    if (-not (Test-Path $guess)) {
        throw "找不到 pg_dump，请把 PostgreSQL\bin 加入 PATH"
    }
    $pgDumpPath = $guess
}

$env:PGPASSWORD = $password
& $pgDumpPath -h $hostName -p $port -U $user -d $db -F c -f $outFile
if ($LASTEXITCODE -ne 0) {
    throw "pg_dump 失败，exit=$LASTEXITCODE"
}
Write-Host "备份完成: $outFile" -ForegroundColor Green
