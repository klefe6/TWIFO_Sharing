@echo off
setlocal ENABLEEXTENSIONS

REM --- Use the venv python in this project (recommended) ---
set "PYTHON_EXE=C:\Program Files\Coding Projects\TWIFO_Sharing\.venv13\Scripts\python.exe"

REM --- Script path (your renamed script) ---
set "SCRIPT=C:\Program Files\Coding Projects\TWIFO_Sharing\db_filter_autorun.py"

REM --- Log directory (in user temp to avoid permission issues) ---
set "LOGDIR=%TEMP%\TWIFO_logs"

REM --- Ensure log folder exists ---
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

REM --- Timestamp (simple + safe) ---
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "TS=%%i"
set "LOG=%LOGDIR%\db_filter_%TS%.log"

REM --- Hard checks ---
if not exist "%PYTHON_EXE%" (
  echo [FATAL] Python exe not found: %PYTHON_EXE%
  echo The system cannot find the path specified.
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo [FATAL] Script not found: %SCRIPT%
  echo The system cannot find the path specified.
  exit /b 1
)

REM --- Run script with console output ---
echo Running TWIFO Dropbox filter...
echo Start time: %DATE% %TIME%
echo.
"%PYTHON_EXE%" "%SCRIPT%"
echo.
echo Done. End time: %DATE% %TIME%

REM --- Optional: Save last run info to log (simple append) ---
echo [%DATE% %TIME%] Script executed >> "%LOG%" 2>nul

endlocal
