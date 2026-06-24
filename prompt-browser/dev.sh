#!/bin/bash
cd "$(dirname "$0")"
echo "🚀 Starting FastAPI in DEV mode (Hot-reload enabled)..."
echo "Press Ctrl+C to stop."
../.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080 --reload
