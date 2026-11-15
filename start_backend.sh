#!/bin/sh
# ==============================================================================
# Startup Script: Flask REST API Backend
# Runs on: Application VM (Alpine-Linux)
# Port: 5000
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
export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5000}"

DB_TARGET="${DB_HOST:-10.189.191.248}:${DB_PORT:-3306}"

echo "=================================================="
echo "Starting Xen E-Learning Flask API Backend..."
echo "Host: $FLASK_HOST | Port: $FLASK_PORT"
echo "Target Database: $DB_TARGET"
echo "=================================================="

exec python3 backend/app.py
