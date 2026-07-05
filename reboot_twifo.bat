@echo off
REM ─── TWIFO_Sharing venv (same pattern as reboot_import_dropbox.bat) ─
cd /d "%~dp0"
set "PROJECT_ROOT=%CD%"
set "VENV=%PROJECT_ROOT%\.venv13"
set "PY=%VENV%\Scripts\python.exe"

REM ─── Sanity check ──────────────────────────────────────────────
if not exist "%PY%" (
  echo ERROR: Could not find Python at "%PY%".
  echo Create .venv13 in TWIFO_Sharing or set VENV / PY before running this bat.
  pause
  exit /b 1
)

REM ─── Screenshot automation token (required by /screenshot route) ──────
set "SCREENSHOT_TOKEN=f235904d48684837b19f5e970314967afb3c8ae0133d40f494b170e7a0ed1bff"
set "PUBLIC_URL=http://127.0.0.1:8401"

REM ─── Control Center: GET /api/daily-summary (must be set before Python) ─
if not defined HCRESEARCH_API_KEY_FILE set "HCRESEARCH_API_KEY_FILE=%USERPROFILE%\.secrets\hcr_api_key_current.txt"
if not exist "%HCRESEARCH_API_KEY_FILE%" (
  echo ERROR: HCR API key file not found: %HCRESEARCH_API_KEY_FILE%
  pause
  exit /b 1
)

REM Werkzeug debug reloader can drop custom env on Windows child process; default off.
REM Set TWIFO_USE_RELOADER=1 before this bat if you want hot-reload while developing.
if not defined TWIFO_USE_RELOADER set "TWIFO_USE_RELOADER=0"

REM ─── Run your Dash app with the venv's python ─────────────────
echo Starting TWIFO Sharing app with venv…
"%PY%" "%~dp0scripts\run_twifo.py"

REM ─── Keep window open to see any errors ────────────────────────
echo.
echo Press any key to close…
pause >nul