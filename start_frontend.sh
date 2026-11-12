#!/bin/sh
# ==============================================================================
# Startup Script: Streamlit Frontend Web App
# Runs on: Alpine-Linux-New (10.240.109.201)
# Port: 8501 (Accessible from other laptops across network)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtualenv if present
if [ -d "venv" ]; then
    . venv/bin/activate
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
export BACKEND_API_URL="http://10.240.109.201:5000/api"

echo "=================================================="
echo "Starting Xen E-Learning Streamlit Frontend..."
echo "Binding Address: 0.0.0.0 | Port: 8501"
echo "Backend API Target: $BACKEND_API_URL"
echo "Accessible at: http://10.240.109.201:8501"
echo "=================================================="

exec streamlit run frontend/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false

