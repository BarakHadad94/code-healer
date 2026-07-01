#!/usr/bin/env bash
# code-healer — start backend (and optionally frontend) dev servers
# Usage: ./start.sh [--backend-only] [--frontend-only]
#
# --reload-dir backend --reload-dir agent  ← REQUIRED: limits uvicorn's file
# watcher to source-code only.  Without these flags uvicorn will also watch
# demo/broken_code/ and restart itself the moment the agent writes the fix,
# killing the run at the write_file step (iteration 3).

BACKEND_ONLY=0
FRONTEND_ONLY=0

for arg in "$@"; do
  case $arg in
    --backend-only)  BACKEND_ONLY=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ "$FRONTEND_ONLY" -eq 0 ]; then
  echo "Starting backend…"
  uvicorn backend.main:app --reload \
    --reload-dir backend --reload-dir agent \
    --port 8000 &
  BACKEND_PID=$!
fi

if [ "$BACKEND_ONLY" -eq 0 ]; then
  echo "Starting frontend…"
  (cd "$ROOT/frontend" && npm run dev) &
  FRONTEND_PID=$!
fi

echo "Dashboard: http://localhost:5173"
wait
