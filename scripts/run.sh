#!/usr/bin/env bash
# Run the vectorizer app server (binds 0.0.0.0 for the Arena preview proxy).
set -e
cd "$(dirname "$0")/.."
PYTHONPATH=vendor:$(pwd) exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
