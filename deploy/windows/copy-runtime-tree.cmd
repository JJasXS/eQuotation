@echo off
setlocal EnableExtensions
REM =====================================================================
REM Copy only files needed to RUN the app (smaller C:\Apps\eQuotation).
REM This does NOT encrypt or compile code — .py stays readable. To hide
REM logic you need Nuitka/PyArmor/etc. (separate build step).
REM
REM Excludes: .git, venv, caches, tests (if present), training, docs, IDE,
REM           _staged_unused_review (tests + unused + archived scripts), etc.
REM Usage:   copy-runtime-tree.cmd SOURCE_REPO_ROOT DEST_APP_ROOT
REM Example: copy-runtime-tree.cmd C:\eQuotation C:\Apps\eQuotation
REM =====================================================================

set "SRC=%~1"
set "DST=%~2"
if "%SRC%"=="" goto usage
if "%DST%"=="" goto usage

if not exist "%SRC%\main.py" (
  echo ERROR: SOURCE must be the repo root and contain main.py
  echo        Got: %SRC%
  exit /b 1
)

if not exist "%DST%" mkdir "%DST%"

REM Robocopy: 0-7 = success (with various copy states); 8+ = failure
robocopy "%SRC%" "%DST%" /E /COPY:DAT /R:2 /W:2 ^
  /XD .git .venv __pycache__ .pytest_cache tests training docs _staged_unused_review .cursor .idea .vscode node_modules ai_models_disabled .github ^
  /NFL /NDL /NJH /NS /NC /NP

set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 (
  echo ERROR: robocopy failed ^(exit %RC%^)
  exit /b 1
)

echo OK: runtime tree copied to "%DST%" ^(dev folders excluded^).
exit /b 0

:usage
echo Usage: %~nx0 SOURCE_REPO_ROOT DEST_APP_ROOT
exit /b 1
