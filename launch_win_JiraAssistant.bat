@echo off
echo Jira Assistant — Local Launcher
echo ─────────────────────────────────

where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Install from https://python.org
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -q -r requirements.txt

echo.
echo Starting Jira Assistant at http://localhost:8501
echo    Press Ctrl+C to stop.
echo.
streamlit run JiraAssistant.py --server.port 8501
pause
