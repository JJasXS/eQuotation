@echo off
setlocal EnableExtensions
title Grant eQuotation restart rights

REM One-time / redeploy helper. Requires Administrator.
REM Saves the pre-elevation user, then grants start/stop on ProAcc_eQuotation.

set "APP_NAME=ProAcc_eQuotation"
set "MARKER=%TEMP%\ProAcc_eQuotation.restart-user.txt"
set "PS1=%~dp0grant-equotation-restart-rights.ps1"

if not exist "%MARKER%" (
  echo %USERDOMAIN%\%USERNAME%> "%MARKER%"
)

net session >nul 2>&1
if errorlevel 1 (
  echo Requesting Administrator to grant restart rights...
  (
    echo Set sh = CreateObject^("Shell.Application"^)
    echo sh.ShellExecute "cmd.exe", "/k cd /d ""%~dp0"" ^& call ""%~f0""", "%~dp0", "runas", 1
  ) > "%TEMP%\elevate_grant_equotation.vbs"
  wscript "%TEMP%\elevate_grant_equotation.vbs"
  exit /b 0
)

if not exist "%PS1%" (
  echo ERROR: missing %PS1%
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -ServiceName "%APP_NAME%"
set "ERR=%ERRORLEVEL%"
echo.
if "%ERR%"=="0" (
  echo Grant finished. Non-admin restart should work for the saved user.
) else (
  echo Grant FAILED with exit %ERR%.
)
pause
exit /b %ERR%
