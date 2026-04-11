# 注册 Windows 任务计划：每周六 09:00（本地时区）运行「五人理论温习」邮件。
# 需以管理员身份运行 PowerShell 执行本脚本；并先配置 SMTP 环境变量或 replay_config.json。
# 用法： .\scripts\register_weekly_theory_review_task.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Error "未找到 python，请先安装 Python 并加入 PATH"
}
$ScriptPath = Join-Path $RepoRoot "scripts\weekly_theory_review_email.py"
$TaskName = "PythonProject1-WeeklyTheoryReview"

$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$ScriptPath`"" -WorkingDirectory $RepoRoot
# 每周六 09:00，本地时区
$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 9:00AM
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force
Write-Host "已注册计划任务: $TaskName （每周六 09:00）"
Write-Host "查看: Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "删除: Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
