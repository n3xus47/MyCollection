#!/bin/bash
# Script to run the FastAPI server

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check if port 8000 is already in use
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "Port 8000 is already in use. Killing existing process..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    sleep 1
fi

# Run the server
echo "Starting FastAPI server on http://0.0.0.0:8000"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
