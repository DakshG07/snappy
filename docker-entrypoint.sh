#!/usr/bin/env sh
set -eu

mkdir -p "$(dirname "${DATABASE_PATH:-/data/scanny.db}")"
mkdir -p "${DOCUMENT_STORAGE_PATH:-/data/documents}"
mkdir -p "${PADDLE_CACHE_PATH:-/data/paddle}"

exec python -m uvicorn app.main:app \
  --app-dir /app/backend \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips="*"
