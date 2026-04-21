#!/bin/sh
set -e

echo "Running Alembic migrations..."
python -m alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn teacher_helper.main:app \
    --host 0.0.0.0 \
    --port 8080 \
    --workers 1
