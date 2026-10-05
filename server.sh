#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
PYTHON="$BACKEND_DIR/.venv/bin/python"
PORT="${SCANNY_PORT:-8000}"
WEB_PORT="${SCANNY_WEB_PORT:-5173}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Missing backend virtual environment. Run the backend setup steps in README.md first." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Missing frontend dependencies. Run: cd frontend && npm install" >&2
  exit 1
fi

LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
if [[ -z "$LAN_IP" ]]; then
  LAN_IP="$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" && $2 !~ /^169\.254\./ { print $2; exit }')"
fi

cleanup() {
  trap - EXIT INT TERM
  kill "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
  wait "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Scanny is starting for devices on your local network."
if [[ -n "$LAN_IP" ]]; then
  echo "iPhone app server: http://$LAN_IP:$PORT"
  echo "Web UI:            http://$LAN_IP:$WEB_PORT"
else
  echo "Could not detect a LAN IP. Check this Mac's Wi-Fi settings for its IP address." >&2
fi
echo "API documentation: http://127.0.0.1:$PORT/docs"
echo "Press Ctrl+C to stop both services."

cd "$BACKEND_DIR"
"$PYTHON" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$PORT" &
BACKEND_PID=$!

cd "$FRONTEND_DIR"
npm run dev -- --host 0.0.0.0 --port "$WEB_PORT" &
FRONTEND_PID=$!

# macOS includes Bash 3.2, so avoid the newer `wait -n` option.
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

echo "A Scanny service stopped; shutting down the other one." >&2
exit 1
