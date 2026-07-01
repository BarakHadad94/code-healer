#!/usr/bin/env bash
# code-healer — launch backend + frontend
# Usage: ./start.sh [--backend-only] [--frontend-only] [--dev]
#
# IMPORTANT: --reload is intentionally OFF by default.
# uvicorn's file-watcher triggers a server reload when it detects any .py
# change inside the watched dirs. On Windows that can include __pycache__
# churn from the pytest precheck, which kills the background task mid-run
# and leaves the run stuck as "running".
#
# Use --dev only while actively editing backend code (not during demo runs).

BACKEND_ONLY=0
FRONTEND_ONLY=0
DEV_MODE=0

for arg in "$@"; do
  case $arg in
    --backend-only)  BACKEND_ONLY=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
    --dev)           DEV_MODE=1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ "$FRONTEND_ONLY" -eq 0 ]; then
  echo "Starting backend…"
  if [ "$DEV_MODE" -eq 1 ]; then
    uvicorn backend.main:app --reload \
      --reload-dir backend --reload-dir agent \
      --port 8000 &
  else
    uvicorn backend.main:app --port 8000 &
  fi
  BACKEND_PID=$!
fi

if [ "$BACKEND_ONLY" -eq 0 ]; then
  echo "Starting frontend…"
  (cd "$ROOT/frontend" && npm run dev) &
  FRONTEND_PID=$!
fi

echo "Dashboard: http://localhost:5173"
[ "$DEV_MODE" -eq 1 ] && echo "(Dev mode: backend will reload on .py changes in backend/ and agent/)"
wait
