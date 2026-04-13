@echo off
REM === Automated Nginx Reverse Proxy Setup for eQuotation ===
REM Run this script as Administrator!

REM 1. Download Nginx
set ZIPURL=https://nginx.org/download/nginx-1.26.2.zip
set ZIPPATH=%TEMP%\nginx.zip
set NGINXROOT=C:\nginx

if exist %ZIPPATH% del /f /q %ZIPPATH%
if exist %NGINXROOT% rmdir /s /q %NGINXROOT%

curl -o %ZIPPATH% %ZIPURL%
cd C:\
tar -xf %ZIPPATH%
for /d %%i in (nginx-*) do ren "%%i" nginx

REM 2. Copy your config
copy "C:\nginx\nginx.windows.conf" "C:\nginx\conf\nginx.conf" /Y

REM 3. Test and start Nginx
cd \nginx
nginx.exe -t
nginx.exe

REM 4. Download NSSM (manual step)
echo.
echo === MANUAL STEP: Download NSSM from https://nssm.cc/download and extract to C:\nssm ===
echo === Then run the following command to install Nginx as a service: ===
echo C:\nssm\win64\nssm.exe install nginx

echo.
echo In the NSSM dialog:
echo   Path: C:\nginx\nginx.exe
echo   Startup directory: C:\nginx
echo   Click "Install service"
echo.
echo === Then run these commands to start and set auto-start: ===
echo net start nginx
echo sc config nginx start= auto

echo.
echo === To test: ===
echo curl -I http://localhost/
echo curl http://localhost/openapi.json

echo.
echo === Script complete. ===
pause
