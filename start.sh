#!/bin/bash
set -e

echo "Starting AlphaGEX API (VALOR + crypto perpetuals)"
cd "$(dirname "$0")"

export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)"

echo "Git commit: $(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "Python version: $(python --version)"

python -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port ${PORT:-8000} \
  --workers ${WEB_CONCURRENCY:-2} \
  --log-level info \
  --access-log \
  --ws wsproto
