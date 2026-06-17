#!/bin/bash

echo "Starting AI4RSE Prompt Browser Server..."

# Check if port 8080 is already in use
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null ; then
    echo "Warning: Port 8080 is already in use. The server might already be running."
    echo "You can run ./stop.sh to kill it first."
    exit 1
fi

# Run the server in the background and redirect output to server.log
nohup python3 server.py > server.log 2>&1 &

echo "Server started successfully in the background!"
echo "You can now open http://localhost:8080/prompt-browser/ in your browser."
echo "To see the server logs, run: tail -f server.log"
