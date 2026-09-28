@echo off
REM Suit-O setup. Safe to run again at any time.
REM Puts Suit-O on Python 3.11 (voice cloning needs it), installs the base
REM requirements, and opens Suit-O on the Installations window so you can tick
REM the optional parts. Your settings and voices are kept.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\install.ps1" %*
if errorlevel 1 (
    echo.
    echo Setup did not finish. Read the message above, then run this file again.
    pause
    exit /b 1
)
