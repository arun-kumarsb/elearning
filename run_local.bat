@echo off
title Xen E-Learning Platform - Local Runner
echo ====================================================================
echo Starting Xen E-Learning Platform locally on Windows...
echo ====================================================================

:: Set working directory
cd /d "%~dp0"

:: Start Flask Backend in background window
echo [1/2] Starting Flask Backend API on http://127.0.0.1:5000 ...
start "Xen Flask Backend (Port 5000)" cmd /k "python backend/app.py"

:: Wait 3 seconds for backend initialization
timeout /t 3 /nobreak >nul

:: Start Streamlit Frontend
echo [2/2] Starting Streamlit Frontend on http://localhost:8501 ...
echo App will open automatically in your default browser.
echo ====================================================================
python -m streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0
pause

