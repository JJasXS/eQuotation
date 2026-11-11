@echo off
net stop ProAcc_eQuotation
timeout /t 3 /nobreak >nul
net start ProAcc_eQuotation
