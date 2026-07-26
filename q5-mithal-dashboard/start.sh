#!/bin/sh
# Entrypoint: run the collector in the background, serve the dashboard in the
# foreground. The collector writes into the served directory, so the page can
# fetch data/metrics.json from the same origin — no CORS, no second service.
set -eu

WEB_ROOT="${WEB_ROOT:-/app/dashboard}"
PORT="${PORT:-8080}"

mkdir -p "$WEB_ROOT/data"

# Keep the collector alive: if it ever exits, restart it after a short pause
# rather than leaving the dashboard serving frozen data.
(
  while true; do
    python /app/collector/collect.py || echo "[start.sh] collector exited, restarting in 10s" >&2
    sleep 10
  done
) &
COLLECTOR_PID=$!

# Stop both processes on SIGTERM/SIGINT so the container shuts down promptly.
trap 'kill "$COLLECTOR_PID" 2>/dev/null || true; exit 0' TERM INT

echo "[start.sh] serving $WEB_ROOT on port $PORT"
exec python -m http.server "$PORT" --directory "$WEB_ROOT" --bind 0.0.0.0
