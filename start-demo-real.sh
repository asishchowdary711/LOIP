#!/usr/bin/env bash
# Identical to start-demo.sh but forces REAL document-intelligence models
# (Qwen2.5-VL via Ollama, real OCR + classifier wrappers) instead of the
# deterministic mock pipeline. Liveness (InsightFace) is already real in both.
#
# External clients (CIBIL/UIDAI/NSDL/DigiLocker bureau APIs) remain mocked
# in both scripts — there are no real endpoints configured.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/loip/.venv"
OLLAMA_HOST="${LOIP_OLLAMA_HOST:-http://127.0.0.1:11434}"
OLLAMA_MODEL="${LOIP_QWEN_OLLAMA_MODEL:-qwen2.5vl:3b}"

# --- Python venv -----------------------------------------------------------
if [ ! -d "$VENV" ]; then
  echo "Creating Python venv..."
  python3 -m venv "$VENV"
fi

echo "Installing Python dependencies..."
"$VENV/bin/pip" install -q -e "$ROOT/loip[dev]" insightface onnxruntime 2>&1 | tail -1

# --- Ollama daemon ---------------------------------------------------------
if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama not installed. Install from https://ollama.com and re-run."
  exit 1
fi

if ! curl -s -m 2 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  echo "Starting Ollama daemon..."
  nohup ollama serve > /tmp/loip_ollama.log 2>&1 &
  OLLAMA_PID=$!
  for i in $(seq 1 20); do
    if curl -s -m 1 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then break; fi
    sleep 1
  done
  if ! curl -s -m 2 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
    echo "ERROR: Ollama did not become reachable at $OLLAMA_HOST. See /tmp/loip_ollama.log"
    exit 1
  fi
  echo "  Ollama up (PID $OLLAMA_PID, log: /tmp/loip_ollama.log)"
else
  echo "Ollama already running at $OLLAMA_HOST"
fi

# --- Ensure model is pulled -----------------------------------------------
if ! curl -s "$OLLAMA_HOST/api/tags" | grep -q "\"$OLLAMA_MODEL\""; then
  echo "Pulling $OLLAMA_MODEL (this is a one-time download, ~3 GB)..."
  ollama pull "$OLLAMA_MODEL"
else
  echo "Model $OLLAMA_MODEL already pulled"
fi

# --- Kill stale processes ---------------------------------------------------
pkill -f "uvicorn loip.web.api" 2>/dev/null || true
sleep 1

# --- Real-mode environment for the backend --------------------------------
export LOIP_DEMO_REAL_MODELS=1
export LOIP_OLLAMA_HOST="$OLLAMA_HOST"
export LOIP_QWEN_OLLAMA_MODEL="$OLLAMA_MODEL"
export LOIP_QWEN_BACKEND="${LOIP_QWEN_BACKEND:-ollama}"

# --- Start backend (logs streamed to this terminal, prefixed) --------------
echo "Starting backend on :8000 (REAL document models)..."
( PYTHONPATH="$ROOT" \
  PYTHONUNBUFFERED=1 \
  LOIP_DEMO_REAL_MODELS=1 \
  LOIP_OLLAMA_HOST="$OLLAMA_HOST" \
  LOIP_QWEN_OLLAMA_MODEL="$OLLAMA_MODEL" \
  LOIP_QWEN_BACKEND="${LOIP_QWEN_BACKEND}" \
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

echo "Confirming real-models mode..."
curl -s http://localhost:8000/apply/mode || true
echo ""

echo ""
echo "=== LOIP Demo Ready (REAL models) ==="
echo "  Landing page:     http://localhost:8000/"
echo "  Loan application: http://localhost:8000/apply"
echo "  Admin console:    http://localhost:8000/ui"
echo ""
echo "  Doc intelligence: REAL  (Qwen2.5-VL via Ollama @ $OLLAMA_HOST, model=$OLLAMA_MODEL)"
echo "  Liveness:         REAL  (InsightFace buffalo_l, warm)"
echo "  External bureaus: MOCK  (no real CIBIL/UIDAI/NSDL/DigiLocker endpoints)"
echo "  Logs:             streamed below ([BACKEND])"
echo ""
echo "Press Ctrl+C to stop the server (Ollama keeps running)."
echo ""

cleanup() {
  echo ""
  echo "Stopping server..."
  pkill -P $BACKEND_PID 2>/dev/null || true
  kill $BACKEND_PID 2>/dev/null || true
  pkill -f "uvicorn loip.web.api" 2>/dev/null || true
  echo "Server stopped. (Ollama daemon left running — kill with: pkill ollama)"
}
trap cleanup INT TERM EXIT

wait
