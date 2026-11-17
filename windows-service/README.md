# Windows 服务（本机开机自启）

本目录把对账程序注册成 Windows 服务。日常只需浏览器打开：

**http://127.0.0.1:8787**

## 目录说明

| 文件 | 作用 |
| --- | --- |
| `setup.ps1` | 首次准备：venv、依赖、前端 build、`.env` |
| `install.ps1` | 下载 WinSW、注册并启动 Windows 服务（需管理员） |
| `start.ps1` / `stop.ps1` / `status.ps1` / `uninstall.ps1` | 服务启停与卸载 |
| `backup.ps1` | `pg_dump` 备份数据库 |
| `open-ui.ps1` | 打开本机页面 |
| `JL-AUTO.xml` | 由 `install.ps1` 生成，勿手改路径 |
| `WinSW-x64.exe` | 首次安装时自动下载，可提交到本目录免下载 |
| `logs\` | 服务日志 |

服务名：`JL-AUTO`（服务管理器里显示「JL-AUTO 门店对账」）

## 新电脑一次做完

1. 安装 **PostgreSQL 16**（服务自动启动）、**Python 3.12+**、**Node.js 20 + pnpm**
2. 以**管理员**打开 PowerShell：

```powershell
cd D:\JL-AUTO\windows-service
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\install.ps1
.\open-ui.ps1
```

之后重启电脑也会自动起来，不必再开黑窗口。

## 常用命令

```powershell
cd D:\JL-AUTO\windows-service
.\status.ps1
.\stop.ps1
.\start.ps1
.\backup.ps1 -BackupDir E:\JL-AUTO-backup
.\uninstall.ps1   # 卸载服务，保留数据库与 file\
```

## 注意

- `install` / `uninstall` 必须管理员权限
- 依赖 PostgreSQL 服务（默认探测 `postgresql-x64-16`，可用 `-PgServiceName` 覆盖）
- 改代码或前端后：先 `.\setup.ps1`，再 `.\stop.ps1`；`.\start.ps1`
