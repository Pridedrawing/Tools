@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "QWEN_PYTHON=%SCRIPT_DIR%..\Qwen\qwen3tts-test\.venv\Scripts\python.exe"

if not exist "%QWEN_PYTHON%" (
    echo ERROR: Qwen venv not found at:
    echo   %QWEN_PYTHON%
    pause
    exit /b 1
)

echo Starting Qwen TTS Web UI...
echo Browser will open automatically.
echo Press Ctrl+C to stop.
echo.

"%QWEN_PYTHON%" "%SCRIPT_DIR%web_tts.py"
pause
