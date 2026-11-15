#!/bin/sh
# ==============================================================================
# Startup Script: Streamlit Frontend Web App
# Runs on: Application VM (Alpine-Linux)
# Port: 8501 (Accessible from other laptops across network)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Source environment variables if .env exists
if [ -f ".env" ]; then
    set -a
    . ./.env
    set +a
fi

# Activate virtualenv if present
if [ -d "venv" ]; then
    . venv/bin/activate
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
export BACKEND_API_URL="${BACKEND_API_URL:-http://127.0.0.1:5000/api}"
APP_HOST="${APP_VM_IP:-10.189.191.51}"

echo "=================================================="
echo "Starting Xen E-Learning Streamlit Frontend..."
echo "Binding Address: 0.0.0.0 | Port: 8501"
echo "Backend API Target: $BACKEND_API_URL"
echo "Accessible at: http://${APP_HOST}:8501"
echo "=================================================="

exec streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false
