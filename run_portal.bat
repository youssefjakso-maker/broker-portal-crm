@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  Broker Portal - local startup
echo ============================================

REM ---- 1. Locate a supported Python interpreter -------------------------
set "PYTHON="
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON=py -3"
    )
)
if not defined PYTHON (
    echo [ERROR] Python 3.10 or newer was not found.
    echo         Install Python 3.10+ and enable "Add python.exe to PATH",
    echo         or install the Python launcher and try again.
    goto :fail
)

REM ---- 2. Create the virtual environment if it is missing ---------------
if not exist ".venv\Scripts\python.exe" (
    echo [SETUP] Creating .venv with %PYTHON% ...
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment in .venv
        echo         Check that you can write to this folder and try again.
        goto :fail
    )
)

REM ---- 3. Verify the virtual environment interpreter actually runs ------
".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] .venv\Scripts\python.exe cannot run on this computer.
    echo         The folder may have been copied from another PC.
    echo         Rename .venv to .venv.broken and run this file again.
    goto :fail
)

REM ---- 4. Install or refresh dependencies -------------------------------
echo [SETUP] Installing dependencies from requirements.txt ...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    echo         Check the network connection and the messages above.
    goto :fail
)

REM ---- 5. Verify the timezone database is available ---------------------
".venv\Scripts\python.exe" -c "from zoneinfo import ZoneInfo; ZoneInfo('Africa/Cairo')" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Timezone data is missing. The 'tzdata' package is required on Windows.
    echo         Try: ".venv\Scripts\python.exe" -m pip install tzdata
    goto :fail
)

REM ---- 6. Start the portal ----------------------------------------------
if not defined BROKER_PORTAL_HOST set "BROKER_PORTAL_HOST=127.0.0.1"
if not defined PORT set "PORT=5000"
echo [START] Broker Portal: http://%BROKER_PORTAL_HOST%:%PORT%
echo         Press Ctrl+C to stop.
".venv\Scripts\python.exe" app.py
set "EXITCODE=%errorlevel%"
if not "%EXITCODE%"=="0" (
    echo.
    echo [ERROR] The portal stopped with exit code %EXITCODE%.
    echo         If the port is already in use, close the other instance or set PORT=5001.
)
goto :done

:fail
set "EXITCODE=1"

:done
if not defined BROKER_PORTAL_NO_PAUSE pause
exit /b %EXITCODE%
