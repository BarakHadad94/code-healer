# code-healer — Project Context

## What This Is

`code-healer` is a portfolio project built to demonstrate enterprise-grade AI agent architecture.
It acts as an autonomous "Gatekeeper" for code repositories: when a CI check fails (or when
sensitive code paths change), instead of just blocking the PR, the agent intercepts the failure,
reasons over the error, rewrites the faulty code in an isolated sandbox, re-runs tests to verify
the fix, and pushes the repaired code back.

**CV angle:** Shows full-stack + AI agent depth — async backend, real-time WebSocket UI,
Docker sandboxing, LLM tool-use orchestration, risk-based cost optimization.

---

## Architecture (3 Components)

### 1. The Watcher — Backend API (`/backend`)
- **FastAPI** server that receives webhook triggers (simulates GitHub push/PR webhooks)
- Tasks run asynchronously via **FastAPI Background Tasks** (upgrade path: Celery + Redis)
- Exposes REST endpoints + WebSocket endpoint for real-time log streaming
- **SQLite** (via SQLAlchemy) stores healing runs, diffs, outcomes — powers the dashboard history
- **Pre-check gate:** runs pytest on the host before invoking the LLM (Phase 2)

### 2. The Brain — AI Agent Engine (`/agent`)
- Built directly on the **Anthropic Python SDK** (not LangChain) — uses native tool use API
- Model: `claude-sonnet-4-6` (configurable via `config.yaml` — Phase 3)
- Agent loop: receives error context → calls tools → observes result → iterates until tests pass or max retries hit
- **Two modes:** self-heal (Scenario A) and deep review (Scenario B)
- **Tools available to the agent:**
  - `read_file(path)` — read source file content
  - `write_file(path, content)` — overwrite a file on the host workspace
  - `run_tests(target)` — execute pytest inside a Docker sandbox, return stdout/stderr
  - `run_linter(path)` — run ruff inside sandbox
  - `list_files(dir)` — explore repo structure
- Agent streams its reasoning steps back to the Watcher via a callback, which forwards over WebSocket

### 3. The Dashboard — Frontend UI (`/frontend`)
- Minimal **React** app (Vite)
- WebSocket connection shows real-time agent reasoning steps ("thinking logs") as they happen
- Side-by-side **Before/After diff view** of the healed file
- Run history table with status and activation reason (reads from SQLite via REST)

---

## Critical Logic: Risk-Based Activation

Running an LLM on every push is expensive. Two activation scenarios:

| Scenario | Trigger | Cost |
|---|---|---|
| **A — Self-Healing** | Local pytest/linter fails | Agent activates only on failure |
| **B — Deep Review** | Tests pass BUT changes touch sensitive paths (`auth/`, `payments/`, `db/queries/`) | Agent performs semantic review even on green builds |
| **Skipped** | Tests pass AND no sensitive paths touched | No LLM call |

Sensitive paths are configurable via `config.yaml` at the repo root.

---

## Infrastructure

- **Server:** Same Linux VPS as the apartment rental site (shared host, separate Caddy site block)
- **Subdomain:** `healer.<existing-domain>` via Caddy reverse proxy (Caddy already runs on this VPS for the rental site and handles Let's Encrypt automatically)
- **Sandbox:** Agent tools execute inside ephemeral **Docker containers** — never touching host filesystem for test/lint execution
  - Containers are spun up per-run, destroyed after
  - Prevents any destructive/malicious code execution
- **Local dev:** Backend + Vite frontend run directly on host; sandbox image built once (`code-healer-sandbox`)
- **API billing:** Healing uses Anthropic API credits (`.env`); Claude Pro subscription does not cover custom app API calls
- **GitHub Integration path:** Dashboard/form simulates webhooks locally → real GitHub webhook in Phase 3 (should-have)

---

## Tech Stack

| Layer | Tech | Notes |
|---|---|---|
| Backend | Python 3.12, FastAPI | Async, WebSocket support |
| Agent | Anthropic SDK (`claude-sonnet-4-6`) | Native tool use, no LangChain overhead |
| Sandbox | Docker (Python slim image) | Ephemeral per-run containers |
| DB | SQLite + SQLAlchemy | Persist run history; swap to Postgres later |
| Frontend | React + Vite | Minimal — focus is backend/agent |
| Config | `config.yaml` + `.env` | Sensitive paths, model; API key in `.env` only |
| Infra | Caddy, shared VPS | Subdomain proxy alongside apartment site |
| CI sim | Demo script (browser) | Phase 6; later GitHub webhook |

---

## Project Phases / TODO

**Execution order (do not reorder without reason):**

```
Phase 1–2 (done) → 3 Features → 4 Engineering → 5 UI Polish → 6 Demo Script
  → 7 Dockerize → 8 README → 9 Deploy
```


### Phase 1 — Core Loop (MVP) ✅
- [x] Scaffold FastAPI backend with `/trigger` endpoint and WebSocket `/ws/logs`
- [x] Build agent engine: Anthropic SDK tool-use loop
- [x] Implement `read_file`, `write_file`, `run_tests` tools (Docker sandbox)
- [x] Wire agent callbacks → WebSocket log stream
- [x] SQLite schema: `healing_runs` table (id, repo, file, error, fix_diff, status, created_at)
- [x] Basic React dashboard: live log feed + diff view

### Phase 2 — Risk-Based Activation ✅
- [x] Add pre-check step: run pytest locally before invoking agent
- [x] Add sensitive-path detection from `config.yaml`
- [x] Scenario B: deep review prompt for critical-path changes
- [x] Dashboard: show activation reason (self-heal vs deep review)
- [x] `activation_reason` column in DB; demo `auth/session.py` for Scenario B

---

### Phase 3 — Features

#### Must-have
- [x] **Git push-back** — after a successful heal, commit the fix to a local branch (completes the original gatekeeper story; scoped to demo/broken_code for now, push to GitHub remains manual)
- [x] **Wire `config.yaml` → agent** — read `model` from config instead of hardcoding in `agent.py`
- [x] **Linter in pre-check gate** — run ruff on the host (or sandbox) alongside pytest before activation decision

#### Should-have
- [x] **Multi-file fix support** — agent can modify more than one file per run
- [x] **Token usage tracking per run** — log input/output tokens and estimated cost; show savings from skipped runs
- [x] **GitHub webhook trigger** — `POST /webhook/github` with HMAC-SHA256 signature verification, queues the same healing pipeline as the dashboard form; sample CI workflow in `.github/workflows/notify-code-healer.yml` (not wired to a public deployment yet — see Phase 9)

---

### Phase 4 — Engineering (non-UI, non-deploy)

Code quality, security, and structure. No dashboard work, no servers.

- [x] **Unit tests** for `precheck.py`, `activation.py`, `config_loader.py`
- [x] **`tasks.py` refactor** — move orchestration out of `main.py` (matches target file structure)
- [x] **Trigger auth** — API key or secret on `/trigger` (required before public deploy)
- [x] **Error handling pass** — clear messages when pytest missing, Docker down, bad workspace path, API errors
- [x] **Config audit** — ensure sensitive paths and model settings all flow from `config.yaml` (no stray hardcoded values)

---

### Phase 5 — UI Polish

Dashboard improvements only.

- [x] **Click run history → load diff** — reopen past runs from the history table
- [x] **Show activation reason on live run** — not only in history after completion
- [x] **Form presets** — quick buttons for demo scenarios (calculator self-heal, auth deep review, green skip)
- [x] **Empty / loading / error states** — WebSocket lost, no runs yet, pre-check in progress
- [x] **Visual pass** — spacing, typography, status colors (light polish)

---

### Phase 6 — Demo Script (browser walkthrough)

Runs **after** Phase 5 so the dashboard is demo-ready.

- [x] **`demo/run_demo.ps1` and `demo/run_demo.sh`** — break sample code, open dashboard URL, guide user through form + **Start Healing**
- [x] **Scenario B variant** — flag or second script for `auth/session.py` deep review
- [x] **Prereq checks** — Docker Desktop running, backend + frontend up, `.env` present, sandbox image built

---

### Phase 7 — Dockerize

Local production-like setup before writing deploy docs.

- [x] **Backend `Dockerfile`**
- [x] **`docker-compose.yml`** — backend, frontend, sandbox image build
- [x] **Volume mounts** — workspace, SQLite DB, Docker socket (for sandbox from inside backend container)
- [x] **`.env.example`** — document all env vars for compose

---

### Phase 8 — README & Documentation

Written after Docker so instructions match the final run path.

- [x] **`README.md`** — project overview, local setup, docker-compose usage, demo instructions
- [x] **Keep `CLAUDE.md` in sync** with implementation as phases complete

---

### Phase 9 — Deploy

Final technical step. **Same VPS as the apartment rental site** — new Caddy site block, no shared app process.

- [x] **Deploy containers to VPS** (or backend + static frontend build) — backend + frontend running via `docker compose` on the VPS; verified with a real end-to-end healing run.
- [x] **Caddy** reverse proxy for `healer.<domain>` — new site block added to the shared Caddyfile alongside the rental site's; verified the rental site is unaffected.
- [x] **HTTPS** via Let's Encrypt — Caddy issued this automatically in the same step as the reverse-proxy config above (no separate certbot/manual step needed); verified with a real cert check against the live site.
- [x] **Production secrets** — API keys, trigger auth; never committed to git — server `.env` locked to `600`, audited git history (never committed, no leaked values), confirmed no key leakage in Caddy/backend logs, spending limit set on the Anthropic Console.
- [x] **GitHub webhook** (if not done in Phase 3) — pointed `.github/workflows/notify-code-healer.yml` at the deployed instance via real repo secrets; verified with a live run — GitHub Actions signed and posted to production, which activated self-heal, fixed `calculator.py`, and pushed a real fix branch. Also caught and fixed an unrelated stale test assertion (`tests/test_precheck.py`) that was failing independently of this work.

---


## Key Design Decisions & Rationale

- **Anthropic SDK over LangChain:** Fewer dependencies, demonstrates deeper understanding of LLM
  tool use. LangChain abstracts away the details that interviewers ask about.
- **SQLite over in-memory:** Healing history persists across restarts; dashboard has real data to show.
- **Docker sandbox per run:** Security story is real, not theoretical — important for "enterprise-grade" claim.
- **WebSocket over polling:** Shows understanding of real-time architectures.
- **Host pytest pre-check before LLM:** Cheap gate; skipped runs cost nothing in API tokens.
- **Pro vs API billing:** Claude Pro covers Claude Code / claude.ai; this app's healing button uses
  Anthropic Console API credits via `ANTHROPIC_API_KEY` in `.env`.
- **Deploy last:** Features and polish locally first; Docker and VPS are finishing touches.

---

## File Structure

```
code-healer/
├── CLAUDE.md                 ← this file
├── config.yaml               ← sensitive paths, model settings
├── .env                      ← ANTHROPIC_API_KEY (gitignored)
├── .env.example
├── backend/
│   ├── main.py               ← FastAPI app, routes, WebSocket
│   ├── models.py             ← SQLAlchemy models
│   ├── database.py           ← SQLite + schema migration
│   ├── precheck.py           ← host pytest gate (Phase 2)
│   ├── activation.py         ← self-heal / deep review / skip decision (Phase 2)
│   ├── config_loader.py      ← loads config.yaml
│   ├── tasks.py              ← background orchestration (Phase 4 refactor)
│   └── requirements.txt
├── agent/
│   ├── agent.py              ← agent loop (self-heal + deep review modes)
│   ├── tools.py              ← tool implementations
│   └── sandbox.py            ← Docker container management
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── LogFeed.jsx
│   │   └── DiffView.jsx
│   └── package.json
├── sandbox-image/
│   └── Dockerfile            ← Python slim + pytest + ruff
└── demo/
    ├── broken_code/          ← sample code + tests for demos
    │   ├── calculator.py
    │   ├── auth/session.py   ← Scenario B sensitive-path demo
    │   └── ...
    ├── run_demo.ps1          ← browser walkthrough (Phase 6)
    └── run_demo.sh
```

---

## Local Dev Quick Reference

```powershell
# Terminal 1 — backend (loads .env automatically)
cd code-healer
uvicorn backend.main:app --reload --reload-dir backend --reload-dir agent --port 8000

# Terminal 2 — frontend
cd code-healer/frontend
npm run dev

# One-time: sandbox image
docker build -t code-healer-sandbox ./sandbox-image
```

`--reload-dir backend --reload-dir agent` scopes the file watcher to source code only.
Without it, uvicorn also watches `demo/broken_code/`, and since both the demo bug
injection and the agent's `write_file` tool edit `.py` files there, a healing run can
trigger a server restart mid-run — silently dropping the WebSocket and freezing the
dashboard's live log feed, even though the run completes successfully in the background.

Dashboard: http://localhost:5173 — API proxied to http://localhost:8000
