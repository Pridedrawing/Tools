@echo off
REM Get the directory of the currently executing .bat file
SET script_dir=%~dp0

REM Change directory to the script's directory
cd /d "%script_dir%"

REM Execute the Python script
python missing_files.py

pause
