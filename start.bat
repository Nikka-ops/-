@echo off
setlocal
set ROOT=%~dp0
cd /d "%ROOT%"

if not exist ".venv\Scripts\python.exe" (
  echo First run - installing...
  powershell -ExecutionPolicy Bypass -File "%ROOT%install.ps1"
  if errorlevel 1 exit /b 1
)

set PORT=8765
if not "%~1"=="" set PORT=%~1

start "" "http://127.0.0.1:%PORT%/"
call ".venv\Scripts\python.exe" -m scripts.api.server --port %PORT%
