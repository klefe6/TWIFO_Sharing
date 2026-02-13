@echo off
REM ─── Configuration ─────────────────────────────────────────────
set "PROJECT_ROOT=C:\Coding Projects\HomePage"
set "VENV=%PROJECT_ROOT%\.venv13"
set "PY=%VENV%\Scripts\python.exe"

REM ─── Sanity check ──────────────────────────────────────────────
if not exist "%PY%" (
  echo ERROR: Could not find Python at "%PY%".
  echo Did you create your .venv13 in %PROJECT_ROOT%?
  pause
  exit /b 1
)

REM ─── Switch to TWIFO_Sharing folder ───────────────────────────
cd /d "%~dp0"

REM ─── Run your Dash app with the venv’s python ─────────────────
echo Starting TWIFO Sharing app with venv…
"%PY%" "twifo.py"

REM ─── Keep window open to see any errors ────────────────────────
echo.
echo Press any key to close…
pause >nul