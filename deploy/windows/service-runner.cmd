@echo off
REM Runs beside main.py. Windows Service binPath should invoke:
REM   cmd.exe /c "C:\Apps\eQuotation\service-runner.cmd"
cd /d "%~dp0"
if exist "%~dp0service-env.cmd" call "%~dp0service-env.cmd"
set PYTHONUNBUFFERED=1
if not exist ".venv\Scripts\python.exe" (
  echo [.venv missing] Run deploy script or: py -3.11 -m venv .venv ^&^& pip install -r requirements.txt
  exit /b 1
)
".venv\Scripts\python.exe" "%~dp0main.py"
