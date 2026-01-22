@echo off
setlocal

REM One-click setup: prompts for API keys and stores them in Windows user env vars.
REM This does NOT print keys.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%setup_keys.ps1"
echo.
echo Done. You can now run:
echo   voiceover\run.bat
echo   Language Detection\run.bat
pause
