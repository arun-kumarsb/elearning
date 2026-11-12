#!/bin/sh
# ==============================================================================
# Startup Script: Flask REST API Backend
# Runs on: Alpine-Linux-New (10.240.109.201)
# Port: 5000
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtualenv if present
if [ -d "venv" ]; then
    . venv/bin/activate
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
export FLASK_HOST="0.0.0.0"
export FLASK_PORT="5000"

echo "=================================================="
echo "Starting Xen E-Learning Flask API Backend..."
echo "Host: $FLASK_HOST | Port: $FLASK_PORT"
echo "Target DB: 10.240.109.248:3306"
echo "=================================================="

exec python3 backend/app.py

