# 独立进程重建题库 — 不随终端/会话退出而被杀。
# 用法:  powershell -File scripts\tools\rebuild-detached.ps1 [-RoleId data] [-Refresh]
# 日志:  corpus_cache\daily\rebuild.log（实时 tail: Get-Content -Wait）
param(
    [string]$RoleId = "data",
    [switch]$Refresh
)

$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$py = Join-Path $root ".venv\Scripts\python.exe"
$log = Join-Path $root "corpus_cache\daily\rebuild.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null

$argList = @("-m", "scripts.run", "--role-id", $RoleId, "--xhs-deep", "--json")
if ($Refresh) { $argList += "--refresh" } else { $argList += "--rebuild-only" }

$env:PYTHONIOENCODING = "utf-8"
$p = Start-Process -FilePath $py -ArgumentList $argList -WorkingDirectory $root `
    -RedirectStandardOutput $log -RedirectStandardError "$log.err" `
    -WindowStyle Hidden -PassThru

Write-Host "重建已在独立进程启动 PID=$($p.Id)"
Write-Host "日志: $log"
Write-Host "查看进度: Get-Content `"$log`" -Wait -Tail 20"
