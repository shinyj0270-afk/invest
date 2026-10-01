@echo off
setlocal
for %%I in ("%~dp0..") do set "INVESTMENT_ROOT=%%~fI"
"%INVESTMENT_ROOT%\.venv\Scripts\python.exe" "%INVESTMENT_ROOT%\tools\open_dashboard.py"
if errorlevel 1 pause
