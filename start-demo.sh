#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/loip/.venv"

# --- Python venv -----------------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "Creating Python venv..."
  python3 -m venv "$VENV"
fi

echo "Installing Python dependencies..."
"$VENV/bin/pip" install -q -e "$ROOT/loip[dev]" insightface onnxruntime 2>&1 | tail -1

# --- Kill stale processes ---------------------------------------------------
pkill -f "uvicorn loip.web.api" 2>/dev/null || true
sleep 1

# --- Start backend (logs streamed to this terminal, prefixed) --------------
echo "Starting backend on :8000..."
( PYTHONPATH="$ROOT" \
  PYTHONUNBUFFERED=1 \
  "$VENV/bin/uvicorn" loip.web.api:app \
    --host 0.0.0.0 --port 8000 \
    --log-level info \
    --access-log \
    2>&1 | awk '{ print "[BACKEND] " $0; fflush() }' ) &
BACKEND_PID=$!

# --- Wait for backend, then warm up liveness model -------------------------
echo "Waiting for backend..."
for i in $(seq 1 30); do
  if curl -s -o /dev/null http://localhost:8000/ 2>/dev/null; then break; fi
  sleep 1
done

echo "Warming up liveness model (InsightFace buffalo_l)..."
curl -s -o /dev/null http://localhost:8000/apply/liveness/warmup || true

echo ""
echo "=== LOIP Demo Ready ==="
echo "  Landing page:     http://localhost:8000/"
echo "  Loan application: http://localhost:8000/apply"
echo "  Admin console:    http://localhost:8000/ui"
echo ""
echo "  Liveness:         InsightFace buffalo_l (warm)"
echo "  Logs:             streamed below ([BACKEND])"
echo ""
echo "Press Ctrl+C to stop the server."
echo ""

cleanup() {
  echo ""
  echo "Stopping server..."
  pkill -P $BACKEND_PID 2>/dev/null || true
  kill $BACKEND_PID 2>/dev/null || true
  pkill -f "uvicorn loip.web.api" 2>/dev/null || true
  echo "Server stopped."
}
trap cleanup INT TERM EXIT

wait
