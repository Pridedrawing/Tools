@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Run from this script's directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Ensure venv exists (clean_unused.py needs no TTS deps, but keep one python)
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Creating virtual environment and installing dependencies...
    call setup.bat
)

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo ERROR: .venv was not created; cannot run.
    echo Install Python 3.12 or 3.11, then run: py -0p
    echo After that, re-run setup.bat.
    pause
    exit /b 1
)

REM Dry run by default; pass --delete to actually remove unused voicelines.
.venv\Scripts\python.exe clean_unused.py %*
pause
