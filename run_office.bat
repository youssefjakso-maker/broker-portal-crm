@echo off
setlocal
cd /d "%~dp0"
if not defined BROKER_PORTAL_HOST set "BROKER_PORTAL_HOST=0.0.0.0"
if not defined PORT set "PORT=5000"
if not exist "data\logs" mkdir "data\logs"
:loop
".venv\Scripts\python.exe" "app.py" >> "data\logs\portal.log" 2>&1
timeout /t 5 /nobreak >nul
goto loop
