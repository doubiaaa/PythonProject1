# SMTP：仅用环境变量（不改 replay_config.json）

`resolve_email_config` 会**优先读环境变量**，再读 `replay_config.json`。下列变量一旦设置且非空，即覆盖配置文件中的同名项。

## 变量一览

| 环境变量 | 含义 | 示例 |
|----------|------|------|
| `SMTP_HOST` | SMTP 服务器 | `smtp.qq.com` |
| `SMTP_PORT` | 端口 | `465` 或 `587` |
| `SMTP_USER` | 登录账号（通常即邮箱） | `123456@qq.com` |
| `SMTP_PASSWORD` | **授权码**（非邮箱登录密码） | （QQ 邮箱设置里生成） |
| `SMTP_FROM` | 发件人显示地址，可空（默认同 `SMTP_USER`） | `123456@qq.com` |
| `MAIL_TO` | 收件人，多个用英文逗号 | `a@qq.com,b@163.com` |
| `SMTP_SSL` | 是否 **SMTPS**（SSL） | `1` / `true` / `yes` 为开启 |

- **465 + SSL**：`SMTP_SSL=1`，端口 `465`。  
- **587 + STARTTLS**：不设或 `SMTP_SSL=0`，端口 `587`（代码里会 `starttls()`）。

## PowerShell（当前终端会话有效）

在项目根目录执行前先设置（请改成你的真实邮箱与授权码）：

```powershell
$env:SMTP_HOST = "smtp.qq.com"
$env:SMTP_PORT = "465"
$env:SMTP_USER = "你的QQ号@qq.com"
$env:SMTP_PASSWORD = "你的SMTP授权码"
$env:SMTP_FROM = "你的QQ号@qq.com"
$env:MAIL_TO = "1961141860@qq.com"
$env:SMTP_SSL = "1"
```

然后：

```powershell
cd d:\Code\PythonProject1
python scripts\test_email_ui.py --to 1961141860@qq.com
```

`--to` 会**覆盖**本次发送的收件人；若只设了 `MAIL_TO`，也可直接 `python scripts\test_email_ui.py`。

## 一次性单行（便于复制）

把占位符换掉后整段粘贴：

```powershell
$env:SMTP_HOST="smtp.qq.com"; $env:SMTP_PORT="465"; $env:SMTP_USER="你的QQ号@qq.com"; $env:SMTP_PASSWORD="授权码"; $env:SMTP_FROM="你的QQ号@qq.com"; $env:MAIL_TO="1961141860@qq.com"; $env:SMTP_SSL="1"; cd d:\Code\PythonProject1; python scripts\test_email_ui.py --to 1961141860@qq.com
```

## 说明

- 关闭终端后，这些 `$env:...` 会失效；需要每次开终端重新设，或改用「系统环境变量」持久化（Windows：**设置 → 系统 → 关于 → 高级系统设置 → 环境变量**）。  
- **不要**把授权码提交到 Git；`replay_config.json` 若在 `.gitignore` 外，也不要写入密码。  
- 更完整说明见仓库根目录 `ARCHITECTURE.md` 附录环境变量表。
