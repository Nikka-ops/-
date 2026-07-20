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

REM 停掉占用该端口的旧服务进程,确保每次启动都是最新代码
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  echo Stopping old server (PID %%p) ...
  taskkill /F /PID %%p >nul 2>&1
)

start "" "http://127.0.0.1:%PORT%/"
call ".venv\Scripts\python.exe" -m scripts.api.server --port %PORT%
