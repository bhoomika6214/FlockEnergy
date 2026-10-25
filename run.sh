#!/usr/bin/env bash
set -e

echo "=========================================================="
echo "  Flock Energy — Urja Meter Ops API Service"
echo "=========================================================="

# Check if .venv exists, if not create and install dependencies
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment .venv..."
    python3 -m venv .venv
    ./.venv/bin/pip install --upgrade pip
    ./.venv/bin/pip install -r requirements.txt
fi

echo "Starting FastAPI Server on http://127.0.0.1:8000..."
echo "  - Interactive Swagger Docs: http://127.0.0.1:8000/docs"
echo "  - ReDoc Documentation:     http://127.0.0.1:8000/redoc"
echo "  - Modern Web Dashboard:    http://127.0.0.1:8000/"
echo "  - OpenAPI Specification:   http://127.0.0.1:8000/openapi.json"
echo "=========================================================="

exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
