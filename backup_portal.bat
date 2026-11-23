@echo off
setlocal
cd /d "%~dp0"
if not defined BROKER_PORTAL_DATA set "BROKER_PORTAL_DATA=%~dp0data"
".venv\Scripts\python.exe" "%~dp0backup_portal.py"
exit /b %errorlevel%
