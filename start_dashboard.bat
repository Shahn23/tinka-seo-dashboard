@echo off
REM Tinka SEO Dashboard — Launch script
REM Opens the dashboard in your browser and starts the Streamlit server.
cd /d "%~dp0"
echo Starting Tinka SEO Dashboard...
echo Opening browser to http://localhost:8510
start "" http://localhost:8510
uv run streamlit run seo_dashboard.py --server.headless true --server.port 8510
pause
