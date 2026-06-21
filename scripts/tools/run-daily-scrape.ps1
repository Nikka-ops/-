# InterviewRadar daily scrape runner (Windows)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    & (Join-Path $Root "install.ps1")
}

& $Py -m scripts.tools.run_daily_scrape @args
