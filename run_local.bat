@echo off
REM Local Run Script for RN Contrast Checker (Windows)
REM This script helps you run the app locally on Windows

echo 🚀 Starting RN Contrast Checker locally...
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python is not installed or not in PATH. Please install Python 3 first.
    pause
    exit /b 1
)

REM Check if virtual environment exists, create if not
if not exist "venv" (
    echo 📦 Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
echo 🔧 Activating virtual environment...
call venv\Scripts\activate.bat

REM Install/update dependencies
echo 📥 Installing dependencies...
python -m pip install -q --upgrade pip
pip install -q -r requirements.txt

REM Check if .streamlit directory exists
if not exist ".streamlit" (
    echo 📁 Creating .streamlit directory...
    mkdir .streamlit
)

REM Check if secrets.toml exists
if not exist ".streamlit\secrets.toml" (
    echo ⚠️  Warning: .streamlit\secrets.toml not found!
    echo    For full functionality, you'll need to set up Google Sheets authentication.
    echo    You can still run the app, but some features may not work.
    echo.
    echo    To set up secrets.toml, copy your Google Service Account credentials.
    echo    See README.md for instructions.
    echo.
    pause
)

REM Run Streamlit with authentication disabled for local development
echo.
echo ✅ Starting Streamlit app (authentication disabled for local testing)...
echo    The app will open in your browser automatically.
echo    Press Ctrl+C to stop the server.
echo.
set STREAMLIT_SKIP_AUTH=true
streamlit run rn_contrast_checker_app.py

pause

