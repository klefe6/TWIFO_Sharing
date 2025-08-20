@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM reboot_import_dropbox.bat
REM Launches import_dropbox.py using Streamlit from within .venv13
REM Must be run from the folder where this .bat lives.
REM ─────────────────────────────────────────────────────────────────────────────

REM 1) Jump to the folder containing this script (handles spaces in path)
pushd "%~dp0"

REM 2) Verify the virtual‑env activation script exists
if not exist ".venv13\Scripts\activate.bat" (
    echo [ERROR] Virtual environment activation script not found!
    echo Looking for: %~dp0.venv13\Scripts\activate.bat
    pause
    popd
    exit /b 1
)

REM 3) Activate the venv
echo [INFO] Activating .venv13...
call ".venv13\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate .venv13.
    pause
    popd
    exit /b 1
)

REM 4) Launch via Streamlit (not python)
echo [INFO] Starting import_dropbox.py with Streamlit...
streamlit run import_dropbox.py
if errorlevel 1 (
    echo [ERROR] Streamlit exited with an error.
    pause
    popd
    exit /b 1
)

REM 5) Return to original directory
popd
