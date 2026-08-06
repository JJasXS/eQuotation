@echo off
setlocal EnableExtensions EnableDelayedExpansion
title ProAcc eQuotation Deploy

REM =============================================================================
REM ProAcc eQuotation -- full Windows deploy
REM Double-click OK -- auto-elevates. Collects .env FIRST (Notepad), then deploy.
REM
REM Required .env keys:
REM   TENANT_CODE
REM   AWS_REGION
REM   AWS_ACCESS_KEY_ID
REM   AWS_SECRET_ACCESS_KEY
REM
REM Keep validate-env.ps1 in the SAME folder as this .cmd
REM =============================================================================

REM ------------ EDIT FOR EACH CLIENT ------------
set "APP_NAME=ProAcc_eQuotation"
set "REPO_URL=https://github.com/JJasXS/eQuotation.git"
set "GIT_BRANCH=main"

set "WORK_DIR=C:\Deploy\eQuotation"
set "APP_DIR=C:\Apps\eQuotation"
set "FLASK_PORT=8880"
set "PYTHON_TAG=3.11"
set "FW_RULE_NAME=eQuote %FLASK_PORT%"
set "ENV_PREP=%TEMP%\ProAcc_eQuotation.env.prepared"
set "ENV_BACKUP=%TEMP%\ProAcc_eQuotation_env_backup.bak"
REM ----------------------------------------------

REM --- Auto-elevate (first window closes; a new Admin window opens) ---
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo This window is not Administrator.
  echo Requesting UAC elevation -- click YES...
  echo A NEW Admin window will open with cmd /k ^(stays open^).
  echo.
  (
    echo Set sh = CreateObject^("Shell.Application"^)
    echo sh.ShellExecute "cmd.exe", "/k cd /d ""%~dp0"" ^& call ""%~f0""", "%~dp0", "runas", 1
  ) > "%TEMP%\elevate_equotation.vbs"
  wscript "%TEMP%\elevate_equotation.vbs"
  if errorlevel 1 (
    echo.
    echo ERROR: Could not request elevation.
    echo Right-click this file -^> Run as administrator
    pause
    exit /b 1
  )
  echo.
  echo If no Admin window appeared, right-click this file and choose "Run as administrator".
  pause
  exit /b 0
)

cd /d "%~dp0"
echo.
echo [%DATE% %TIME%] eQuotation deploy (Administrator)
echo Script: %~f0
echo Folder: %~dp0
echo.

if not exist "C:\Temp" mkdir "C:\Temp"

REM =============================================================================
REM STEP 0 -- Enter .env FIRST (Notepad). Deploy starts only after Save + Close.
REM =============================================================================
echo ========== STEP 0 / ENV ==========
echo Fill these 4 values, Save, then CLOSE Notepad:
echo   TENANT_CODE=...
echo   AWS_REGION=ap-southeast-1
echo   AWS_ACCESS_KEY_ID=...
echo   AWS_SECRET_ACCESS_KEY=...
echo.
echo Tip: AWS keys are usually the same for every client; only TENANT_CODE changes.
echo.

if exist "%APP_DIR%\.env" (
  copy /Y "%APP_DIR%\.env" "%ENV_PREP%" >nul
  echo Prefill: copied from %APP_DIR%\.env
) else if exist "%ENV_BACKUP%" (
  copy /Y "%ENV_BACKUP%" "%ENV_PREP%" >nul
  echo Prefill: copied from %ENV_BACKUP%
) else if exist "C:\Temp\eQuotation.env.backup" (
  copy /Y "C:\Temp\eQuotation.env.backup" "%ENV_PREP%" >nul
  echo Prefill: copied from C:\Temp\eQuotation.env.backup
) else (
  (
    echo # ProAcc eQuotation - required for tenant/Secrets Manager
    echo TENANT_CODE=
    echo AWS_REGION=ap-southeast-1
    echo AWS_ACCESS_KEY_ID=
    echo AWS_SECRET_ACCESS_KEY=
  ) > "%ENV_PREP%"
  echo Prefill: new template created
)

echo.
echo Opening Notepad: %ENV_PREP%
echo After you Save and Close Notepad, deploy continues...
echo.
notepad "%ENV_PREP%"

set "ENV_VALIDATOR=%~dp0validate-env.ps1"
if not exist "%ENV_VALIDATOR%" set "ENV_VALIDATOR=C:\Temp\validate-eQuotation-env.ps1"
if not exist "%ENV_VALIDATOR%" set "ENV_VALIDATOR=C:\Temp\validate-env.ps1"
if not exist "%ENV_VALIDATOR%" (
  echo ERROR: validate-env.ps1 not found next to this script or in C:\Temp.
  echo Put validate-env.ps1 in the SAME folder as this .cmd
  goto :fail
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%ENV_VALIDATOR%" -EnvPath "%ENV_PREP%"
if errorlevel 1 (
  echo.
  echo .env is incomplete. Fix the 4 values and run this script again.
  goto :fail
)

copy /Y "%ENV_PREP%" "%ENV_BACKUP%" >nul
copy /Y "%ENV_PREP%" "C:\Temp\eQuotation.env.backup" >nul
echo Env saved. Starting deploy...
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo ERROR: Git not in PATH.
  goto :fail
)

where nssm >nul 2>&1
if errorlevel 1 (
  echo ERROR: nssm not in PATH. Install NSSM then retry.
  goto :fail
)

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: py launcher not found. Install Python %PYTHON_TAG%.
  goto :fail
)

echo [0/12] Firewall allow inbound TCP %FLASK_PORT%...
netsh advfirewall firewall show rule name="%FW_RULE_NAME%" >nul 2>&1
if errorlevel 1 (
  netsh advfirewall firewall add rule name="%FW_RULE_NAME%" dir=in action=allow protocol=TCP localport=%FLASK_PORT%
) else (
  echo   Rule already exists: %FW_RULE_NAME%
)

echo [1/12] Stop / remove old service...
sc query "%APP_NAME%" >nul 2>&1
if not errorlevel 1 (
  sc stop "%APP_NAME%" >nul 2>&1
  timeout /t 5 /nobreak >nul
)
nssm stop "%APP_NAME%" >nul 2>&1
nssm remove "%APP_NAME%" confirm >nul 2>&1
sc delete "%APP_NAME%" >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/12] Free port %FLASK_PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":%FLASK_PORT%" ^| findstr LISTENING') do (
  echo   Ending PID %%P
  taskkill /F /PID %%P >nul 2>&1
)
timeout /t 2 /nobreak >nul

echo [3/12] Keep prepared .env backup...
echo   Using %ENV_PREP%

echo [4/12] Wipe old folders...
for %%I in ("%WORK_DIR%\..") do set "WORK_PARENT=%%~fI"
if not exist "%WORK_PARENT%" mkdir "%WORK_PARENT%"
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%"
if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%"
timeout /t 1 /nobreak >nul
if not exist "%APP_DIR%" mkdir "%APP_DIR%"

echo [5/12] Clone GitHub...
set "GIT_BRANCH_ARG="
if defined GIT_BRANCH set "GIT_BRANCH_ARG=-b %GIT_BRANCH%"
git clone --depth 1 %GIT_BRANCH_ARG% "%REPO_URL%" "%WORK_DIR%"
if errorlevel 1 (
  echo ERROR: git clone failed.
  goto :fail
)
if not exist "%WORK_DIR%\main.py" (
  echo ERROR: clone missing main.py
  goto :fail
)
if not exist "%WORK_DIR%\deploy\windows\copy-runtime-tree.cmd" (
  echo ERROR: clone missing deploy\windows\copy-runtime-tree.cmd
  goto :fail
)

echo [6/12] Copy runtime tree...
call "%WORK_DIR%\deploy\windows\copy-runtime-tree.cmd" "%WORK_DIR%" "%APP_DIR%"
if errorlevel 1 (
  echo ERROR: copy-runtime-tree failed.
  goto :fail
)
if not exist "%APP_DIR%\main.py" (
  echo ERROR: main.py missing after copy - abort.
  goto :fail
)
if not exist "%APP_DIR%\requirements.txt" (
  echo ERROR: requirements.txt missing after copy - abort.
  goto :fail
)

echo [7/12] Install prepared .env...
copy /Y "%ENV_PREP%" "%APP_DIR%\.env" >nul
if not exist "%APP_DIR%\.env" (
  echo ERROR: failed to write %APP_DIR%\.env
  goto :fail
)

echo [8/12] Python venv + pip...
pushd "%APP_DIR%"
py -%PYTHON_TAG% -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: venv create failed.
  popd
  goto :fail
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  popd
  goto :fail
)
python -c "import flask; print('Flask OK')"
if errorlevel 1 (
  echo ERROR: Flask import failed.
  popd
  goto :fail
)
popd

echo [9/12] service-env for port/host...
(
  echo set FLASK_HOST=0.0.0.0
  echo set FLASK_PORT=%FLASK_PORT%
  echo set PYTHONUNBUFFERED=1
) > "%APP_DIR%\service-env.cmd"
if exist "%APP_DIR%\deploy\windows\service-runner.cmd" (
  copy /Y "%APP_DIR%\deploy\windows\service-runner.cmd" "%APP_DIR%\service-runner.cmd" >nul
)

echo [10/12] NSSM install...
nssm install "%APP_NAME%" "%APP_DIR%\.venv\Scripts\python.exe" "%APP_DIR%\main.py"
if errorlevel 1 (
  echo ERROR: nssm install failed.
  goto :fail
)
nssm set "%APP_NAME%" AppDirectory "%APP_DIR%"
nssm set "%APP_NAME%" AppStdout "%APP_DIR%\service-output.log"
nssm set "%APP_NAME%" AppStderr "%APP_DIR%\service-error.log"
nssm set "%APP_NAME%" AppEnvironmentExtra "PYTHONUNBUFFERED=1" "FLASK_HOST=0.0.0.0" "FLASK_PORT=%FLASK_PORT%"
nssm set "%APP_NAME%" AppExit Default Restart
nssm set "%APP_NAME%" AppRestartDelay 5000
nssm set "%APP_NAME%" Start SERVICE_AUTO_START
nssm set "%APP_NAME%" DisplayName "ProAcc eQuotation"
nssm set "%APP_NAME%" Description "ProAcc eQuotation unified server (Flask + FastAPI on port %FLASK_PORT%)."

echo [11/12] Start service...
nssm start "%APP_NAME%"
timeout /t 8 /nobreak >nul

echo [12/12] Verify...
echo.
echo ========== VERIFY ==========
nssm status "%APP_NAME%"
sc query "%APP_NAME%"
echo.
echo Listening on %FLASK_PORT%:
netstat -ano | findstr ":%FLASK_PORT%"
echo.
if exist "%APP_DIR%\main.py" (echo main.py: OK) else (echo main.py: MISSING)
if exist "%APP_DIR%\.env" (echo .env: OK) else (echo .env: MISSING)
if exist "%APP_DIR%\.venv\Scripts\python.exe" (echo .venv: OK) else (echo .venv: MISSING)
echo.
echo Browser:  http://127.0.0.1:%FLASK_PORT%/
echo API docs: http://127.0.0.1:%FLASK_PORT%/eq-sql-api/docs
echo Logs:     %APP_DIR%\service-error.log
echo.
start "" "http://127.0.0.1:%FLASK_PORT%/"
echo Done. Press any key to close.
pause
endlocal
exit /b 0

:fail
echo.
echo Deploy FAILED. Press any key to close.
pause
endlocal
exit /b 1
