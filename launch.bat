@echo off
REM Launch script for readmarkable on Windows

REM Get the directory of this script
set SCRIPT_DIR=%~dp0

REM Change to resources directory
cd /d "%SCRIPT_DIR%resources"

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed
    echo Please install Python 3 from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check if virtual environment exists, create if not
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Install requirements if needed
if exist "requirements.txt" (
    echo Checking dependencies...
    pip install -q -r requirements.txt 2>nul || (
        echo Installing required packages...
        pip install -r requirements.txt
    )
)

REM Launch the application
echo Starting readmarkable...
python main.py

REM Deactivate virtual environment when done
call venv\Scripts\deactivate.bat

pause