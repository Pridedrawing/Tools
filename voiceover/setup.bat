@echo off
setlocal

REM Creates a local virtualenv for this tool (recommended)
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if %errorlevel%==0 (
        REM Prefer Python 3.12, then 3.11
        py -3.12 -m venv .venv 2>nul
        if not exist ".venv\Scripts\python.exe" py -3.11 -m venv .venv 2>nul
    ) else (
        python -m venv .venv
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Failed to create .venv.
    echo Install Python 3.12 or 3.11 and ensure the py launcher can see it: py -0p
    exit /b 1
)

REM Install dependencies into the venv explicitly
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt

echo.
echo Setup complete. You can now run run.bat