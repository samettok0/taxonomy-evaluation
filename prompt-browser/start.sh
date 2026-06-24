#!/bin/bash

echo "Starting AI4RSE Prompt Browser Server..."
# Change to the directory where this script is located
cd "$(dirname "$0")"

echo "Starting AI4RSE Prompt Browser via FastAPI..."

# Check if port 8080 is already in use
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo "Warning: Port 8080 is already in use. The server might already be running."
    echo "You can run ./stop.sh to kill it first."
    exit 1
fi

# Run uvicorn in the background, logging to server.log
nohup ../.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8080 > server.log 2>&1 &
echo $! > server.pid

echo "Server started successfully in the background!"
echo "You can now open http://localhost:8080/ in your browser."
echo "To see the server logs, run: tail -f prompt-browser/server.log"
echo "To stop the server, run: ./stop.sh"
