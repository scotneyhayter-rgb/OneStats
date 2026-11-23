#!/bin/sh
# Apply database migrations, then serve the app (API + SPA) on one origin.
# Run from the backend dir so alembic.ini's relative script_location resolves.
set -e

cd /app/services/api

# Wait briefly for the database, then migrate to head (idempotent).
echo "OneStats: applying database migrations..."
alembic upgrade head

echo "OneStats: starting server on :${PORT:-8000}"
exec uvicorn onestats.main:app --host 0.0.0.0 --port "${PORT:-8000}"
