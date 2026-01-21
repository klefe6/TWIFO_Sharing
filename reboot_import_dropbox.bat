@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM reboot_import_dropbox.bat
REM Launches import_dropbox.py using Streamlit from within TWIFO_Sharing's .venv13
REM Must be run from the folder where this .bat lives.
REM ─────────────────────────────────────────────────────────────────────────────

REM ─── Configuration ─────────────────────────────────────────────
REM Use TWIFO_Sharing's own venv instead of HomePage's venv
set "PROJECT_ROOT=C:\Program Files\Coding Projects\TWIFO_Sharing"
set "VENV=%PROJECT_ROOT%\.venv13"
set "PY=%VENV%\Scripts\python.exe"
set "STREAMLIT=%VENV%\Scripts\streamlit.exe"

REM ─── Sanity check ──────────────────────────────────────────────
if not exist "%PY%" (
  echo ERROR: Could not find Python at "%PY%".
  echo Did you create your .venv13 in %PROJECT_ROOT%?
  pause
  exit /b 1
)

if not exist "%STREAMLIT%" (
  echo ERROR: Could not find Streamlit at "%STREAMLIT%".
  echo Please install streamlit in the venv: pip install streamlit
  pause
  exit /b 1
)

REM ─── Switch to TWIFO_Sharing folder ───────────────────────────
cd /d "%~dp0"

REM ─── Launch via Streamlit using venv's python ─────────────────
REM Using FIXED port 8001 (no auto-increment)
echo [INFO] Starting import_dropbox.py with Streamlit on port 8001...
"%STREAMLIT%" run import_dropbox.py --server.port 8001
if errorlevel 1 (
    echo [ERROR] Streamlit exited with an error.
    pause
    exit /b 1
)
