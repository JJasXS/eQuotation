@echo off
setlocal EnableExtensions
title Restart ProAcc eQuotation

REM =============================================================================
REM Restart after copying files to C:\Apps\eQuotation.
REM Tries WITHOUT Admin first (works after deploy-time ACL grant).
REM Elevates only if restart is denied.
REM =============================================================================

set "APP_NAME=ProAcc_eQuotation"
set "APP_DIR=C:\Apps\eQuotation"

if not exist "%APP_DIR%\main.py" (
  echo ERROR: missing %APP_DIR%\main.py -- copy runtime first.
  pause
  exit /b 1
)

where nssm >nul 2>&1
if errorlevel 1 (
  set "PATH=%PATH%;%ProgramFiles%\nssm;%ProgramFiles(x86)%\nssm;%LOCALAPPDATA%\Microsoft\WinGet\Links"
)
where nssm >nul 2>&1
if errorlevel 1 (
  echo ERROR: nssm not found on PATH.
  pause
  exit /b 1
)

echo.
echo [%DATE% %TIME%] Restarting %APP_NAME% ^(non-admin first^)...
nssm restart "%APP_NAME%" >nul 2>&1
if not errorlevel 1 goto :ok

echo Non-admin restart failed. Trying stop/start...
nssm stop "%APP_NAME%" >nul 2>&1
timeout /t 2 /nobreak >nul
nssm start "%APP_NAME%" >nul 2>&1
if not errorlevel 1 goto :ok

net session >nul 2>&1
if not errorlevel 1 goto :admin_restart

echo.
echo Still Access denied. Requesting Administrator once...
echo Tip: next full deploy grants your user restart rights so this UAC is not needed.
(
  echo Set sh = CreateObject^("Shell.Application"^)
  echo sh.ShellExecute "cmd.exe", "/k cd /d ""%~dp0"" ^& call ""%~f0""", "%~dp0", "runas", 1
) > "%TEMP%\elevate_restart_equotation.vbs"
wscript "%TEMP%\elevate_restart_equotation.vbs"
exit /b 0

:admin_restart
echo Running elevated restart...
nssm restart "%APP_NAME%"
if errorlevel 1 (
  nssm stop "%APP_NAME%"
  timeout /t 2 /nobreak >nul
  nssm start "%APP_NAME%"
)
if exist "%~dp0grant-equotation-restart-rights.ps1" (
  echo Ensuring restart rights for the original user...
  if not exist "%TEMP%\ProAcc_eQuotation.restart-user.txt" (
    echo %USERDOMAIN%\%USERNAME%> "%TEMP%\ProAcc_eQuotation.restart-user.txt"
  )
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0grant-equotation-restart-rights.ps1" -ServiceName "%APP_NAME%"
)

:ok
timeout /t 2 /nobreak >nul
nssm status "%APP_NAME%"
echo.
echo Done. Open View e-PR Approved and confirm line items load.
echo Log: %APP_DIR%\service-output.log
pause
exit /b 0
