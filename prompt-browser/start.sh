#!/bin/bash

echo "Starting AI4RSE Prompt Browser Server..."

# Check if port 8080 is already in use
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo "Warning: Port 8080 is already in use. The server might already be running."
    echo "You can run ./stop.sh to kill it first."
    exit 1
fi

# Detect Python executable (prefer virtual environment)
PYTHON_EXEC="python3"
if [ -f "../.venv/bin/python3" ]; then
    PYTHON_EXEC="../.venv/bin/python3"
fi

# Run the server in the background and redirect output to server.log
nohup $PYTHON_EXEC server.py > server.log 2>&1 &

echo "Server started successfully in the background!"
echo "You can now open http://localhost:8080/prompt-browser/ in your browser."
echo "To see the server logs, run: tail -f server.log"
