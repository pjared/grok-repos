@echo off
REM Opens the Suit-O window without leaving a console behind. Uses pythonw.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Could not find .venv\Scripts\pythonw.exe
    echo Create the virtual environment first. See README.md.
    pause
    exit /b 1
)
start "" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" -m suit_o.gui
