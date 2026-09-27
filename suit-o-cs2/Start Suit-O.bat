@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Could not find .venv\Scripts\python.exe
    echo Create the virtual environment first. See README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m suit_o
if errorlevel 1 pause
