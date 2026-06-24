#!/bin/bash
cd "$(dirname "$0")"
echo "Stopping AI4RSE Prompt Browser Server..."
if [ -f "server.pid" ]; then
    kill $(cat server.pid) 2>/dev/null
    rm -f server.pid
fi
lsof -ti:8080 | xargs kill -9 2>/dev/null
echo "Server successfully stopped!"
