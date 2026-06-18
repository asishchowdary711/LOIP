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

# --- Frontend npm -----------------------------------------------------------
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT/frontend" && npm install -q)
fi

# --- Kill stale processes ---------------------------------------------------
pkill -f "uvicorn loip.web.api" 2>/dev/null || true
pkill -f "vite --port" 2>/dev/null || true
sleep 1

# --- Start backend ----------------------------------------------------------
echo "Starting backend on :8000..."
PYTHONPATH="$ROOT" "$VENV/bin/uvicorn" loip.web.api:app \
  --host 0.0.0.0 --port 8000 > /tmp/loip_server.log 2>&1 &
BACKEND_PID=$!

# --- Start frontend ---------------------------------------------------------
echo "Starting frontend..."
(cd "$ROOT/frontend" && npx vite --port 3000 --host > /tmp/loip_frontend.log 2>&1) &
FRONTEND_PID=$!

# --- Wait for startup -------------------------------------------------------
echo "Waiting for servers..."
for i in $(seq 1 15); do
  if curl -s -o /dev/null http://localhost:8000/ 2>/dev/null; then break; fi
  sleep 1
done

echo ""
echo "=== LOIP Demo Ready ==="
echo "  Landing page:     http://localhost:8000/"
echo "  Loan application: http://localhost:8000/apply"
echo "  Admin console:    http://localhost:8000/ui"
echo "  React frontend:   http://localhost:3000/"
echo ""
echo "  Backend PID:  $BACKEND_PID  (log: /tmp/loip_server.log)"
echo "  Frontend PID: $FRONTEND_PID (log: /tmp/loip_frontend.log)"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Servers stopped.'" EXIT
wait
