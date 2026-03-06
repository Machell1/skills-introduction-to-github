#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Install dependencies if needed
pip install -e ".[dev]" --quiet 2>/dev/null

# Initialize database with seed data if it doesn't exist
if [ ! -f "data/fnid.db" ]; then
    echo "Seeding database..."
    PYTHONPATH=src python -c "from fnid_portal import create_app; app = create_app(); app.app_context().push()"
fi

echo "Starting FNID Portal at http://localhost:5000"
PYTHONPATH=src flask --app fnid_portal run --debug --host 0.0.0.0 --port 5000
