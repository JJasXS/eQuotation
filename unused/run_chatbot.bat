@echo off
setlocal

set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"

REM Check for installed Python
if exist "%PYTHON_EXE%" (
  set "PYTHON_CMD=%PYTHON_EXE%"
  goto :check_deps
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  set "PYTHON_CMD=python"
  goto :check_deps
)

echo Python was not found.
echo Install Python 3.12 or newer, then re-run this script.
exit /b 1

:check_deps
REM Quick check if flask is installed
%PYTHON_CMD% -c "import flask" >nul 2>&1
if %ERRORLEVEL% neq 0 (
  echo Installing required packages...
  %PYTHON_CMD% -m pip install -r "%~dp0requirements.txt"
  if %ERRORLEVEL% neq 0 (
    echo Failed to install dependencies.
    exit /b 1
  )
)

:run_app
echo Starting chatbot server...
%PYTHON_CMD% "%~dp0main.py"
