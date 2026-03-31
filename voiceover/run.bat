@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM Run from this script's directory
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Ensure venv exists (so dependencies like elevenlabs are available)
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

REM Detect provider from args (supports --provider qwen or --provider=qwen)
set "PROVIDER="
if "%*"=="" (
    echo.
    echo Select TTS provider:
    echo   1^) elevenlabs
    echo   2^) qwen
    set /p PROVIDER_CHOICE="Enter choice [1]: "
    if "!PROVIDER_CHOICE!"=="2" (set "PROVIDER=qwen") else (set "PROVIDER=elevenlabs")
) else (
    echo %* | findstr /I /C:"--provider=qwen" >nul && set "PROVIDER=qwen"
    echo %* | findstr /I /C:"--provider=elevenlabs" >nul && set "PROVIDER=elevenlabs"
    if not defined PROVIDER (
        for /f "tokens=1,2" %%A in ("%*") do (
            if /I "%%~A"=="--provider" set "PROVIDER=%%~B"
        )
    )
)

if not defined PROVIDER set "PROVIDER=elevenlabs"

set "PYTHON_EXE=.venv\Scripts\python.exe"
if /I "!PROVIDER!"=="qwen" (
    if exist "..\Qwen\qwen3tts-test\.venv\Scripts\python.exe" (
        set "PYTHON_EXE=..\Qwen\qwen3tts-test\.venv\Scripts\python.exe"
    ) else (
        echo.
        echo ERROR: Qwen provider selected but Qwen venv not found at ..\Qwen\qwen3tts-test\.venv\Scripts\python.exe
        echo Install Qwen dependencies or adjust the path in run.bat.
        pause
        exit /b 1
    )
)

REM If a local secrets helper exists, load it and then run.
if exist "set_env.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command ". '.\\set_env.ps1'; & '%PYTHON_EXE%' '.\\gen.py' @args" %* --provider %PROVIDER%
) else (
    %PYTHON_EXE% gen.py %* --provider %PROVIDER%
)
pause
