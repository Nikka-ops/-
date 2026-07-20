# One-time setup: create venv + install deps. ASCII-only so Windows
# PowerShell 5.1 parses it regardless of system codepage.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

# Pick a Python >= 3.11, fail early with a clear message otherwise.
function Get-Python {
    foreach ($cmd in @("python", "python3", "py")) {
        $exe = (Get-Command $cmd -ErrorAction SilentlyContinue).Source
        if (-not $exe) { continue }
        try {
            & $exe -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        } catch { continue }
        if ($LASTEXITCODE -eq 0) { return $exe }
    }
    return $null
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    $py = Get-Python
    if (-not $py) {
        Write-Host "[X] Need Python 3.11+. Please install it from https://www.python.org/downloads/ and re-run." -ForegroundColor Red
        exit 1
    }
    Write-Host "Creating .venv with $py ..."
    & $py -m venv .venv
}

& ".\.venv\Scripts\python.exe" -m pip install -U pip -q
& ".\.venv\Scripts\python.exe" -m pip install -e ".[dev]" -q

Write-Host ""
Write-Host "Installed. Start the app by double-clicking start.bat"
