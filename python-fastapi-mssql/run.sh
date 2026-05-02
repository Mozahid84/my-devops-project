#!/bin/bash
# FastAPI server startup script

set -e

echo "Starting MSSQL Deployment FastAPI Service..."

# Check if running in development mode
if [ "$ENV" = "development" ]; then
    echo "Running in DEVELOPMENT mode with auto-reload"
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
else
    echo "Running in PRODUCTION mode"
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
fi
