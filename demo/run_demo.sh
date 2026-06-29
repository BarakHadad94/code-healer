#!/usr/bin/env bash
# code-healer Demo Script — Scenario A: Self-Heal
#
# Usage:
#   ./demo/run_demo.sh          # Scenario A (self-heal, default)
#   ./demo/run_demo.sh B        # Scenario B (deep review)
#   ./demo/run_demo.sh C        # Scenario C (skip / green path)

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCENARIO="${1:-A}"

ok()   { echo "  OK   $1"; }
err()  { echo "  FAIL $1" >&2; }
info() { echo "  -->  $1"; }
banner() { echo ""; echo "$1"; printf '%.0s─' $(seq 1 ${#1}); echo ""; }

banner "code-healer demo — Scenario $SCENARIO"

# ── 1. .env ──────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
    err ".env not found at repo root."
    info "Create it: cp .env.example .env  then add your ANTHROPIC_API_KEY"
    exit 1
fi
if ! grep -qE "ANTHROPIC_API_KEY\s*=\s*sk-" "$ROOT/.env"; then
    err "ANTHROPIC_API_KEY looks missing or invalid in .env"
    exit 1
fi
ok ".env found with API key"

# ── 2. Docker ─────────────────────────────────────────────────────────────────
if ! docker info &>/dev/null; then
    err "Docker is not running."
    info "Start Docker Desktop, wait for it to finish, then re-run."
    exit 1
fi
ok "Docker is running"

# ── 3. Sandbox image ──────────────────────────────────────────────────────────
if ! docker image inspect code-healer-sandbox &>/dev/null; then
    err "Sandbox image 'code-healer-sandbox' not found."
    info "Build it once: docker build -t code-healer-sandbox ./sandbox-image"
    exit 1
fi
ok "Sandbox image exists"

# ── 4. Backend ────────────────────────────────────────────────────────────────
if ! curl -sf --max-time 3 "http://localhost:8000/runs" -o /dev/null; then
    err "Backend is not responding on port 8000."
    info "Start it: uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --port 8000"
    exit 1
fi
ok "Backend is up (port 8000)"

# ── 5. Frontend ───────────────────────────────────────────────────────────────
if ! curl -sf --max-time 3 "http://localhost:5173" -o /dev/null; then
    err "Frontend is not responding on port 5173."
    info "Start it: cd frontend && npm run dev"
    exit 1
fi
ok "Frontend is up (port 5173)"

# ── 6. Reset workspace ────────────────────────────────────────────────────────
if [ "$SCENARIO" = "A" ]; then
    echo ""
    echo "  Resetting demo/broken_code to broken state..."
    git -C "$ROOT/demo/broken_code" checkout HEAD -- calculator.py
    ok "calculator.py reset (add bug re-injected)"
fi

# ── 7. Open browser ───────────────────────────────────────────────────────────
echo ""
echo "  Opening http://localhost:5173 ..."
if command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:5173" &
elif command -v open &>/dev/null; then
    open "http://localhost:5173"
else
    echo "  (could not detect a browser opener — open http://localhost:5173 manually)"
fi

# ── 8. Demo guide ─────────────────────────────────────────────────────────────
banner "READY — follow these steps"

case "$SCENARIO" in
A)
    echo "  Scenario A — Self-Heal (broken calculator)"
    echo ""
    echo "  1. Click the  [⚡ Self-heal]  preset button"
    echo "  2. Click  [Start Healing]"
    echo "  3. Watch Agent Reasoning:"
    echo "       • pytest runs and fails on the broken add() function"
    echo "       • Agent activates, reads the file, rewrites the fix"
    echo "       • Tests re-run inside Docker — pass"
    echo "       • Fix committed to a new git branch"
    echo "  4. Code Diff panel shows the before/after change"
    ;;
B)
    echo "  Scenario B — Deep Review (sensitive auth path)"
    echo ""
    echo "  1. Click the  [🔍 Deep review]  preset button"
    echo "  2. Click  [Start Healing]"
    echo "  3. Watch Agent Reasoning:"
    echo "       • pytest runs and passes (code is clean)"
    echo "       • auth/session.py triggers deep-review activation"
    echo "       • Agent reviews the file semantically, reports findings"
    ;;
C)
    echo "  Scenario C — Skip (green build, no sensitive paths)"
    echo ""
    echo "  1. Click the  [✓ Skip]  preset button"
    echo "  2. Click  [Start Healing]"
    echo "  3. Watch Agent Reasoning:"
    echo "       • pytest runs and passes"
    echo "       • No sensitive paths touched — agent skipped entirely"
    echo "       • Zero API tokens used"
    ;;
*)
    echo "  Unknown scenario '$SCENARIO'. Use A, B, or C."
    exit 1
    ;;
esac

echo ""
