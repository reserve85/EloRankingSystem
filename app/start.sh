#!/bin/bash
set -e

# Run Alembic migrations before starting the application
echo "Running database migrations..."
alembic upgrade head
echo "Migrations complete."

# Start the application
echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000