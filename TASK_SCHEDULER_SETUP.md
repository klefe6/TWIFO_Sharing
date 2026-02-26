# Task Scheduler Setup for Midnight db_filter_autorun

## Overview
Automated daily execution of `db_filter_autorun.py` at 12:05 AM using Windows Task Scheduler.

## Files Created
- **`run_db_filter_midnight.bat`** - Batch script that calculates yesterday's date and runs the Python script
- **`logs/midnight_run.log`** - Execution log (created automatically on first run)

## Task Scheduler Configuration

### Option 1: Using Task Scheduler GUI

1. Open **Task Scheduler** (search in Start Menu)

2. Click **"Create Basic Task"** in the right panel

3. **Name**: `TWIFO DB Filter - Midnight Run`
   **Description**: `Automated daily processing of TWIFO database filter at 12:05 AM`

4. **Trigger**: Daily
   - Start date: Tomorrow (or desired start date)
   - Recur every: 1 days
   - Time: **12:05:00 AM**

5. **Action**: Start a program
   - Program/script: `C:\Coding Projects\TWIFO_Sharing\run_db_filter_midnight.bat`
   - Start in: `C:\Coding Projects\TWIFO_Sharing`

6. **Finish** and check "Open Properties dialog"

7. In **Properties** > **General** tab:
   - ✅ Run whether user is logged on or not
   - ✅ Run with highest privileges
   - Configure for: Windows 10

8. In **Properties** > **Settings** tab:
   - ✅ Allow task to be run on demand
   - ✅ If the task fails, restart every: 10 minutes, attempt to restart up to: 3 times
   - ⬜ Stop the task if it runs longer than: (unchecked - let it complete)

9. **OK** to save (may prompt for password)

### Option 2: Using PowerShell Command

Run this in **PowerShell as Administrator**:

```powershell
$action = New-ScheduledTaskAction -Execute "C:\Coding Projects\TWIFO_Sharing\run_db_filter_midnight.bat" -WorkingDirectory "C:\Coding Projects\TWIFO_Sharing"
$trigger = New-ScheduledTaskTrigger -Daily -At 12:05AM
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType S4U -RunLevel Highest

Register-ScheduledTask -TaskName "TWIFO DB Filter - Midnight Run" -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Automated daily processing of TWIFO database filter at 12:05 AM"
```

## Testing the Task

### Test the Batch File Manually
```cmd
cd "C:\Coding Projects\TWIFO_Sharing"
run_db_filter_midnight.bat
```

### Test via Task Scheduler
1. Open Task Scheduler
2. Find your task in the task list
3. Right-click > **Run**
4. Check `logs\midnight_run.log` for output

## What the Script Does

1. **Calculates yesterday's date** using PowerShell (YYYY-MM-DD format)
2. **Navigates** to the TWIFO_Sharing directory
3. **Runs** `db_filter_autorun.py` with:
   - Yesterday's date as the target date
   - Default settings (does NOT bypass duplicate checks)
   - Automated response to the "Bypass duplicate checks?" prompt (answers 'N')
4. **Logs** all output to `logs\midnight_run.log` with timestamps
5. **Exits** with the Python script's exit code (for Task Scheduler monitoring)

## Expected Behavior

The script will:
- ✅ Process PDFs from yesterday's date automatically
- ✅ Skip duplicates (normal behavior)
- ✅ Generate summaries for new PDFs
- ✅ Update the website (if configured)
- ✅ Log all activity to `logs\midnight_run.log`

**No user interaction required** - designed for unattended execution.

## Monitoring & Troubleshooting

### Check Execution Status
```cmd
type "C:\Coding Projects\TWIFO_Sharing\logs\midnight_run.log"
```

### View Task History
1. Open Task Scheduler
2. Select your task
3. Click **History** tab (enable if disabled)

### Common Issues

**Issue**: Task runs but nothing happens
- **Solution**: Check that Python is in PATH for the SYSTEM account
- **Test**: Run `python --version` in a CMD window opened as SYSTEM

**Issue**: Permission errors
- **Solution**: Ensure task is set to "Run with highest privileges"

**Issue**: Script can't find files/modules
- **Solution**: Verify "Start in" directory is set to `C:\Coding Projects\TWIFO_Sharing`

**Issue**: Date calculation fails
- **Solution**: Test PowerShell command manually:
  ```powershell
  (Get-Date).AddDays(-1).ToString('yyyy-MM-dd')
  ```

## Customization

### Change Run Time
Edit the trigger time in Task Scheduler properties, or modify the PowerShell command.

### Change Date Offset
Edit line 15 in `run_db_filter_midnight.bat`:
```batch
REM For 2 days ago:
for /f "tokens=*" %%a in ('powershell -command "(Get-Date).AddDays(-2).ToString('yyyy-MM-dd')"') do set YESTERDAY=%%a
```

### Enable Duplicate Bypass
Change line 28 in `run_db_filter_midnight.bat`:
```batch
REM From:
(echo N) | python db_filter_autorun.py %YESTERDAY% >> "logs\midnight_run.log" 2>&1

REM To:
(echo Y) | python db_filter_autorun.py %YESTERDAY% >> "logs\midnight_run.log" 2>&1
```

---

**Author**: Kevin Lefebvre  
**Last Updated**: 2026-02-16
