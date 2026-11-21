#!/bin/bash
# Start the demo: ./run.sh  then open http://localhost:8000
cd "$(dirname "$0")"
set -a; [ -f .env ] && source .env; set +a
exec .venv/bin/uvicorn app.server:app --port 8000
