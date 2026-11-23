@echo off
setlocal EnableExtensions
cd /d "%~dp0"
REM One-click: first-time setup (venv + packages) then serves the portal to the office network.
set "BROKER_PORTAL_HOST=0.0.0.0"
if not defined PORT set "PORT=5000"
set "BROKER_PORTAL_NO_PAUSE=1"

set "PYTHON="
where python >nul 2>nul && python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYTHON=python"
if not defined PYTHON where py >nul 2>nul && py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set "PYTHON=py -3"
if not defined PYTHON (
  echo [ERROR] Python 3.10+ not found. Install it and tick "Add python.exe to PATH".
  pause & exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo [SETUP] Creating .venv ...
  %PYTHON% -m venv .venv || (echo [ERROR] venv failed & pause & exit /b 1)
)

if not exist ".venv\.deps_ok" (
  echo [SETUP] Installing packages ^(needs internet, first run only^) ...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt || (echo [ERROR] pip install failed & pause & exit /b 1)
  echo ok> ".venv\.deps_ok"
)

if not exist "data\logs" mkdir "data\logs"
echo.
echo ============================================================
echo  Broker Portal is starting on port %PORT%
echo  Team URL:  http://THIS-PC-IP:%PORT%     (find IP with: ipconfig)
echo  This PC:   http://127.0.0.1:%PORT%
echo  Keep this window open. Auto-restarts if it crashes.
echo ============================================================
:loop
".venv\Scripts\python.exe" app.py >> "data\logs\portal.log" 2>&1
echo [%date% %time%] portal stopped, restarting in 5s... 
timeout /t 5 /nobreak >nul
goto loop
