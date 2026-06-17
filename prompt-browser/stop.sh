#!/bin/bash

echo "Stopping AI4RSE Prompt Browser Server..."

# Kill any process matching "python3 server.py"
pkill -f "python3 server.py"
killed_python=$?

# Also kill any process lingering on port 8080 just to be safe
lsof -ti:8080 | xargs kill -9 2>/dev/null
killed_port=$?

if [ $killed_python -eq 0 ] || [ $killed_port -eq 0 ]; then
    echo "Server successfully stopped!"
else
    echo "Server was not running."
fi
