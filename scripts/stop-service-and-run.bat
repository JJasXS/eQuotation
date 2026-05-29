@echo off
REM Stop Windows service and run dev server (UAC admin required).
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"\"%~dp0stop-service-and-run.ps1\"\"'"
