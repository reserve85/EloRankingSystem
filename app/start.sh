#!/bin/bash
set -e

# Database migrations are handled automatically by the application on startup.
# See app/core/database.py init_db() for migration logic.

# Start the application
echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
