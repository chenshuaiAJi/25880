# 新电脑部署方案（本机 Windows 服务）

目标：安装后开机自动运行，浏览器打开 **http://127.0.0.1:8787** 即可。只监听本机。

所有运维脚本集中在主目录下的 **`windows-service\`**。

---

## 1. 必装软件

1. **PostgreSQL 16**（Windows 服务，启动类型：自动）
2. **Python 3.12+**（勾选 Add to PATH）
3. **Node.js 20 LTS + pnpm**（仅首次构建前端需要）

```powershell
npm install -g pnpm
```

---

## 2. 新电脑一次做完（推荐）

把项目拷到例如 `D:\JL-AUTO`，**管理员** PowerShell：

```powershell
cd D:\JL-AUTO\windows-service
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\install.ps1
.\open-ui.ps1
```

完成后：

- Windows 服务名：`JL-AUTO`（显示名「JL-AUTO 门店对账」）
- 启动类型：自动
- 依赖：检测到的 PostgreSQL 服务（如 `postgresql-x64-16`）
- 日志：`windows-service\logs\`

---

## 3. 配置

`backend\.env`（`setup.ps1` 会自动生成）：

```env
DATABASE_URL=postgresql://postgres:jlauto_dev@127.0.0.1:5432/jlauto
HOST=127.0.0.1
PORT=8787
```

正式环境请改掉弱密码。服务启动时会自动建库 `jlauto` 并跑迁移。

---

## 4. 日常命令

```powershell
cd D:\JL-AUTO\windows-service
.\status.ps1
.\stop.ps1
.\start.ps1
.\backup.ps1 -BackupDir E:\JL-AUTO-backup
.\uninstall.ps1
```

改代码 / 改前端后：

```powershell
.\setup.ps1
.\stop.ps1
.\start.ps1
```

---

## 5. 迁旧账

旧机：

```powershell
$env:PGPASSWORD = "你的密码"
pg_dump -h 127.0.0.1 -U postgres -d jlauto -F c -f E:\jlauto.dump
```

新机装好服务后：

```powershell
$env:PGPASSWORD = "你的密码"
pg_restore -h 127.0.0.1 -U postgres -d jlauto --clean --if-exists E:\jlauto.dump
```

并拷贝 `file\` 目录。

---

## 6. 目录结构

```
JL-AUTO/
├── windows-service/     ← 本机服务与运维脚本（主入口）
├── backend/             ← API + 内嵌 frontend/dist
├── frontend/            ← 源码；setup 时 build 到 dist
├── database/migrations/ ← 自动迁移
└── file/                ← Excel 与银行上传留存
```

详细说明见 [windows-service/README.md](./windows-service/README.md)。

---

## 7. 常见问题

| 现象 | 处理 |
| --- | --- |
| install 提示需要管理员 | 右键 PowerShell → 以管理员身份运行 |
| 服务起不来 | 看 `windows-service\logs\`；确认 PostgreSQL 已启动、`.env` 密码正确 |
| 8787 白屏 | 再跑 `.\setup.ps1` 生成 `frontend\dist`，然后 `.\stop.ps1`；`.\start.ps1` |
| 找不到 PostgreSQL 依赖 | `.\install.ps1 -PgServiceName 你的服务名`（在 `services.msc` 里查） |
| WinSW 下载失败 | 手动下载 [WinSW-x64.exe](https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe) 放到 `windows-service\` 后再 `.\install.ps1` |
