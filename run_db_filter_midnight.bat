@echo off
REM Purpose: Automated daily run for db_filter_autorun.py via Task Scheduler at 12:05 AM
REM Author: Kevin Lefebvre
REM Last Updated: 2026-02-16
REM
REM This script runs db_filter_autorun.py with yesterday's date automatically.
REM No manual input required - designed for unattended Task Scheduler execution.

setlocal enabledelayedexpansion

REM Calculate yesterday's date in YYYY-MM-DD format
for /f "tokens=*" %%a in ('powershell -command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"') do set YESTERDAY=%%a

REM Set working directory to script location
cd /d "C:\Coding Projects\TWIFO_Sharing"

REM Create log directory if it doesn't exist
if not exist "logs" mkdir "logs"

REM Run Python script with yesterday's date
REM Pass 'N' to the duplicate bypass prompt via echo pipe
REM Redirect output to both console and log file
echo ====================================== >> "logs\midnight_run.log"
echo [%date% %time%] Starting db_filter_autorun.py for %YESTERDAY% >> "logs\midnight_run.log"
echo ====================================== >> "logs\midnight_run.log"

(echo N) | python db_filter_autorun.py %YESTERDAY% >> "logs\midnight_run.log" 2>&1

REM Check exit code
if %ERRORLEVEL% EQU 0 (
    echo [%date% %time%] SUCCESS: Completed for %YESTERDAY% >> "logs\midnight_run.log"
) else (
    echo [%date% %time%] ERROR: Failed with exit code %ERRORLEVEL% for %YESTERDAY% >> "logs\midnight_run.log"
)

endlocal
exit /b %ERRORLEVEL%
