#!/bin/sh
# ==============================================================================
# Setup & Dependency Installation Script for Alpine Linux 3.24
# Target VM: Alpine-Linux-New (10.240.109.201)
# ==============================================================================

set -e

echo "=== [1/4] Updating Alpine package repositories ==="
apk update

echo "=== [2/4] Installing system build dependencies and Python packages ==="
apk add --no-cache \
    python3 \
    py3-pip \
    py3-virtualenv \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    mariadb-client \
    curl \
    nginx

echo "=== [3/4] Creating Python 3.14 Virtual Environment ==="
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

. venv/bin/activate

echo "=== [4/4] Installing Python dependencies via pip ==="
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt

chmod +x start_backend.sh start_frontend.sh database/apply_migrations.py

echo ""
echo "=================================================================="
echo "Setup successfully completed!"
echo "Next Steps:"
echo "1. Run database migration: python3 database/apply_migrations.py"
echo "2. Start Backend:          ./start_backend.sh"
echo "3. Start Frontend:         ./start_frontend.sh"
echo "=================================================================="

