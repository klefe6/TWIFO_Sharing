@echo off
REM Purpose: Test run_db_filter_midnight.bat without waiting until midnight
REM Author: Kevin Lefebvre
REM Last Updated: 2026-02-16

echo ========================================
echo Testing Midnight Run Script
echo ========================================
echo.

REM Show calculated date
for /f "tokens=*" %%a in ('powershell -command "(Get-Date).AddDays(-1).ToString('yyyy-MM-dd')"') do (
    echo Calculated yesterday's date: %%a
    set TESTDATE=%%a
)
echo.

echo This will run db_filter_autorun.py with date: %TESTDATE%
echo.
echo Press Ctrl+C to cancel, or any key to continue...
pause > nul

echo.
echo Running script...
echo ========================================
call run_db_filter_midnight.bat

echo.
echo ========================================
echo Test complete!
echo Check logs\midnight_run.log for output
echo ========================================
pause
