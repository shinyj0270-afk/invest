@echo off
setlocal
chcp 65001 >nul
for %%I in ("%~dp0..") do set "INVESTMENT_MOBILE_ROOT=%%~fI"
"%INVESTMENT_MOBILE_ROOT%\.venv\Scripts\python.exe" -B "%INVESTMENT_MOBILE_ROOT%\scripts\mobile_dashboard.py" %*
if errorlevel 1 pause
