@echo off
title Tinka SEO Dashboard
cd /d "%~dp0"
echo ====================================
echo  Tinka SEO Dashboard - Local Launcher
echo ====================================
echo.
echo Starting dashboard at http://localhost:8510
echo This window must stay open while the dashboard runs.
echo Close this window to stop the dashboard.
echo.
echo First time: installing dependencies...
uv pip install -r requirements.txt >nul 2>&1
echo.
echo Launching dashboard...
uv run streamlit run dashboard.py --server.headless true --server.port 8510 --server.address 0.0.0.0
pause
