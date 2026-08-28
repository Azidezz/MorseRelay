@echo off
title MorseRelay Setup
echo =========================================
echo        MorseRelay Dependency Setup
echo =========================================
echo.
echo Checking for Python and required packages...
echo.

:: Check if python is installed
python --version >nul 2>&1
IF ERRORLEVEL 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python from https://python.org and check "Add to PATH".
    echo.
    pause
    exit /b
)

pip install -r requirements.txt

echo.
echo =========================================
echo Setup Complete! Dependencies are installed.
echo You can now use START.vbs to run the app.
echo =========================================
echo.
pause