#!/bin/sh
set -e

echo "Running Alembic migrations..."
python -m alembic upgrade head

PORT="${PORT:-8080}"
echo "Starting uvicorn on port ${PORT}..."
exec uvicorn teacher_helper.main:app \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --workers 1
