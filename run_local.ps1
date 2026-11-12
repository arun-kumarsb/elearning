# Xen E-Learning Platform - Local PowerShell Launcher
Write-Host "====================================================================" -ForegroundColor Cyan
Write-Host "Starting Xen E-Learning Platform locally on Windows..." -ForegroundColor Cyan
Write-Host "====================================================================" -ForegroundColor Cyan

Set-Location $PSScriptRoot

# Start Flask Backend in new PowerShell window
Write-Host "[1/2] Starting Flask Backend API on http://127.0.0.1:5000 ..." -ForegroundColor Green
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PSScriptRoot'; python backend/app.py"

Start-Sleep -Seconds 3

# Start Streamlit Frontend
Write-Host "[2/2] Starting Streamlit Frontend on http://localhost:8501 ..." -ForegroundColor Green
python -m streamlit run frontend/app.py --server.port 8501 --server.address 0.0.0.0

