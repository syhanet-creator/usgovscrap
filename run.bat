@echo off
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed.
    echo Install it from https://www.python.org/downloads/
    echo ^(check "Add python.exe to PATH" during setup^), then run this again.
    pause
    exit /b 1
)

python run_all.py
pause
