@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =====================================================================
REM ProAcc eQuotation — fresh deploy + Windows Service (Administrator)
REM Full stack = python main.py (Flask + FastAPI on ONE port, default 8880)
REM DO NOT use: uvicorn api.app:app alone — that is API-only, no Flask UI.
REM =====================================================================

REM ------------ EDIT FOR EACH CLIENT ------------
set "APP_NAME=ProAcc_eQuotation"
set "REPO_URL=https://github.com/JJasXS/eQuotation.git"
set "GIT_BRANCH="
REM Leave GIT_BRANCH empty for default branch, or e.g. main

set "WORK_DIR=C:\Deploy\eQuotation"
set "APP_DIR=C:\Apps\eQuotation"
set "FLASK_PORT=8880"
set "PYTHON_TAG=3.11"
REM ----------------------------------------------

echo.
echo [%DATE% %TIME%] Starting deploy...

net session >nul 2>&1
if errorlevel 1 (
  echo ERROR: Run this script as Administrator ^(right-click ^> Run as administrator^).
  exit /b 1
)

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git is not in PATH. Install Git for Windows first.
  exit /b 1
)

echo [1/10] Stop existing service...
sc query "%APP_NAME%" >nul 2>&1
if not errorlevel 1 (
  sc stop "%APP_NAME%"
  echo Waiting for service to stop...
  timeout /t 8 /nobreak >nul
)

echo [2/10] Free port %FLASK_PORT% ^(listeners only; does NOT kill every python.exe^)...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%FLASK_PORT%" ^| findstr LISTENING') do (
  echo   Ending PID %%P
  taskkill /F /PID %%P >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [3/10] Backup existing .env if present...
set "ENV_BACKUP=%TEMP%\ProAcc_eQuotation_env_backup_%RANDOM%.bak"
if exist "%APP_DIR%\.env" (
  copy /Y "%APP_DIR%\.env" "!ENV_BACKUP!" >nul
  echo   Saved to !ENV_BACKUP!
)

echo [4/10] Remove old clone / app folders...
for %%I in ("%WORK_DIR%\..") do set "WORK_PARENT=%%~fI"
if not exist "%WORK_PARENT%" mkdir "%WORK_PARENT%"
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"

echo [5/10] Clone GitHub...
set "GIT_BRANCH_ARG="
if defined GIT_BRANCH set "GIT_BRANCH_ARG=-b %GIT_BRANCH%"
git clone --depth 1 %GIT_BRANCH_ARG% "%REPO_URL%" "%WORK_DIR%"
if errorlevel 1 (
  echo ERROR: git clone failed.
  exit /b 1
)

echo [6/10] Copy to APP_DIR...
xcopy /E /I /Y "%WORK_DIR%\*" "%APP_DIR%\"
if errorlevel 4 (
  echo ERROR: xcopy failed.
  exit /b 1
)

echo [7/10] Restore or create .env ^("publish" / production config^)...
if exist "!ENV_BACKUP!" (
  copy /Y "!ENV_BACKUP!" "%APP_DIR%\.env" >nul
  echo   Restored .env from backup.
) else if exist "%APP_DIR%\.env.example.api" (
  if not exist "%APP_DIR%\.env" (
    copy /Y "%APP_DIR%\.env.example.api" "%APP_DIR%\.env" >nul
    echo   CREATED .env from .env.example.api — EDIT %APP_DIR%\.env before production use ^(DB_PATH, keys, BASE_API_URL, etc.^).
  )
) else (
  echo   WARNING: No .env backup and no .env.example.api — create %APP_DIR%\.env manually.
)

echo [8/10] Python venv + pip...
pushd "%APP_DIR%"
where py >nul 2>&1
if not errorlevel 1 (
  py -%PYTHON_TAG% -m venv .venv
) else (
  python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Failed to create venv. Install Python %PYTHON_TAG% or adjust PYTHON_TAG.
  popd
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  popd
  exit /b 1
)
popd

echo [9/10] Install service-runner at app root + write service-env.cmd...
copy /Y "%APP_DIR%\deploy\windows\service-runner.cmd" "%APP_DIR%\service-runner.cmd" >nul
(
  echo set FLASK_HOST=0.0.0.0
  echo set FLASK_PORT=%FLASK_PORT%
  echo set PYTHONUNBUFFERED=1
) > "%APP_DIR%\service-env.cmd"

echo [10/10] Register Windows Service...
sc delete "%APP_NAME%" >nul 2>&1
timeout /t 2 /nobreak >nul

sc create "%APP_NAME%" binPath= "cmd.exe /c \"%APP_DIR%\service-runner.cmd\"" DisplayName= "ProAcc eQuotation" start= delayed-auto
if errorlevel 1 (
  echo ERROR: sc create failed.
  exit /b 1
)
sc description "%APP_NAME%" "ProAcc eQuotation unified server (Flask + FastAPI on port %FLASK_PORT%). Entry: python main.py"

sc failure "%APP_NAME%" reset= 86400 actions= restart/60000/restart/60000/restart/60000 >nul 2>&1

echo Starting service...
sc start "%APP_NAME%"
timeout /t 3 /nobreak >nul

echo.
echo ========== VERIFY ==========
sc query "%APP_NAME%"
echo.
echo Listening on %FLASK_PORT%:
netstat -ano | findstr ":%FLASK_PORT%"
echo.
echo Browser: http://localhost:%FLASK_PORT%/
echo API docs: http://localhost:%FLASK_PORT%/eq-sql-api/docs
echo.
echo Optional inbound firewall ^(run once if clients need LAN access^):
echo   netsh advfirewall firewall add rule name="ProAcc eQuotation %FLASK_PORT%" dir=in action=allow protocol=TCP localport=%FLASK_PORT%
echo.
endlocal
exit /b 0
