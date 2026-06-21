# One-time setup: venv + pip install -e .
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating .venv …"
    python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install -U pip -q
& .\.venv\Scripts\pip.exe install -e ".[dev]" -q

Write-Host ""
Write-Host "Installed. Run:"
Write-Host "  .\.venv\Scripts\python.exe -m scripts.tools.run_daily_scrape"
Write-Host "  python -m scripts.tools.install_daily_schedule"
