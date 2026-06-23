import asyncio
import difflib
import hashlib
import hmac
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

# Run uvicorn from the project root so these imports resolve:
#   uvicorn backend.main:app --reload
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from agent.agent import run_healing_agent
from backend.activation import ActivationReason, activation_label, decide_activation
from backend.config_loader import get_model
from backend.database import SessionLocal, create_tables
from backend.git_pushback import create_fix_branch, git_diff
from backend.models import HealingRun
from backend.precheck import run_pytest_precheck, run_ruff_precheck
from backend.pricing import estimate_cost

app = FastAPI(title="code-healer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Maps run_id → asyncio.Queue of log messages.
# Each message: {"type": "log"|"diff"|"done"|"error", "message": str}
_log_queues: Dict[str, asyncio.Queue] = {}

_STALE_QUEUE_TTL = 600  # seconds — cleanup if no WebSocket ever connects


async def _cleanup_stale_queue(run_id: str, delay: int = _STALE_QUEUE_TTL) -> None:
    """Drop orphaned queues when the client never opens a WebSocket."""
    await asyncio.sleep(delay)
    _log_queues.pop(run_id, None)


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    create_tables()


# ── Request / Response models ────────────────────────────────────────────────

class TriggerRequest(BaseModel):
    repo: str                       # e.g. "my-org/my-repo"
    file_path: str                  # workspace-relative path to the broken file
    error_log: str = ""             # optional; pre-check captures pytest output when tests fail
    workspace: str                  # absolute path to the local workspace directory
    changed_files: list[str] = []   # used for Scenario B (critical-path detection)


class TriggerResponse(BaseModel):
    run_id: str
    ws_url: str
    message: str


class RunSummary(BaseModel):
    id: str
    repo: str
    file_path: str
    status: str
    activation_reason: Optional[str] = None
    iterations: Optional[int]
    fix_branch: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ── Routes ───────────────────────────────────────────────────────────────────

def _queue_healing_run(
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
    message: str,
) -> TriggerResponse:
    run_id = str(uuid.uuid4())
    _log_queues[run_id] = asyncio.Queue()
    background_tasks.add_task(_healing_task, run_id, body)
    return TriggerResponse(run_id=run_id, ws_url=f"/ws/logs/{run_id}", message=message)


@app.post("/trigger", response_model=TriggerResponse)
async def trigger_healing(body: TriggerRequest, background_tasks: BackgroundTasks):
    """
    Manual entry point — used by the dashboard form to simulate a CI failure.
    Returns immediately with a run_id; connect to ws_url to stream live logs.
    """
    return _queue_healing_run(body, background_tasks, "Healing task queued")


@app.post("/webhook/github", response_model=TriggerResponse)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
):
    """
    Real entry point for CI — a GitHub Actions workflow step POSTs here on test
    failure (see .github/workflows/notify-code-healer.yml). Verifies an HMAC-SHA256
    signature over the raw body, the same convention GitHub itself uses for webhooks.
    """
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="GITHUB_WEBHOOK_SECRET not configured on the server")

    raw_body = await request.body()

    if not x_hub_signature_256:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        body = TriggerRequest.model_validate_json(raw_body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid payload: {e}")

    return _queue_healing_run(body, background_tasks, "Healing task queued via GitHub webhook")


@app.get("/runs", response_model=list[RunSummary])
def list_runs():
    """Return all healing runs ordered newest-first (used by the dashboard history table)."""
    with SessionLocal() as db:
        return db.query(HealingRun).order_by(HealingRun.created_at.desc()).all()


@app.get("/runs/{run_id}", response_model=RunSummary)
def get_run(run_id: str):
    with SessionLocal() as db:
        run = db.get(HealingRun, run_id)
        if run is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Run not found")
        return run


@app.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str):
    """Return the raw unified diff for a completed run."""
    with SessionLocal() as db:
        run = db.get(HealingRun, run_id)
        if run is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Run not found")
        return {"diff": run.fix_diff}


@app.websocket("/ws/logs/{run_id}")
async def websocket_logs(websocket: WebSocket, run_id: str):
    """
    Streams structured log messages for a healing run.
    Closes automatically when the agent emits a "done" or "error" message.
    """
    await websocket.accept()

    if run_id not in _log_queues:
        await websocket.send_json({"type": "error", "message": f"Unknown run_id: {run_id}"})
        await websocket.close()
        return

    queue = _log_queues[run_id]
    try:
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
            if msg.get("type") in ("done", "error", "skipped"):
                await websocket.close(code=1000)
                break
    except WebSocketDisconnect:
        pass
    finally:
        _log_queues.pop(run_id, None)


# ── Background healing task ──────────────────────────────────────────────────

async def _healing_task(run_id: str, body: TriggerRequest) -> None:
    queue = _log_queues.get(run_id)
    if queue is None:
        return

    async def log_callback(msg: dict) -> None:
        if run_id in _log_queues:
            await queue.put(msg)

    _db_create_run(run_id, body)

    # ── Phase 2: pytest pre-check (cheap gate before LLM) ───────────────────
    await log_callback({"type": "log", "message": "Running pytest pre-check…"})
    precheck = await run_pytest_precheck(body.workspace)

    display = precheck.output if len(precheck.output) <= 800 else precheck.output[:800] + "\n…(truncated)"
    await log_callback({"type": "log", "message": f"[Pre-check]\n{display}"})

    if precheck.exit_code < 0 and precheck.output.startswith("ERROR:"):
        await log_callback({
            "type": "error",
            "message": f"Pre-check could not run: {precheck.output}",
        })
        _db_set_activation(run_id, None)
        _db_complete_run(run_id, {"status": "failed", "iterations": None}, None)
        asyncio.create_task(_cleanup_stale_queue(run_id))
        return

    # ── Phase 3: ruff pre-check (runs alongside pytest, before activation) ──
    await log_callback({"type": "log", "message": "Running ruff pre-check…"})
    lint_precheck = await run_ruff_precheck(body.workspace)

    lint_display = (
        lint_precheck.output if len(lint_precheck.output) <= 800
        else lint_precheck.output[:800] + "\n…(truncated)"
    )
    await log_callback({"type": "log", "message": f"[Lint]\n{lint_display}"})

    # An infra-level lint failure (ruff missing, timeout) shouldn't block the gate —
    # only real lint violations do. Negative exit_code marks an infra issue.
    lint_failed = not lint_precheck.passed and lint_precheck.exit_code >= 0
    if not lint_precheck.passed and lint_precheck.exit_code < 0:
        await log_callback({
            "type": "log",
            "message": f"Lint pre-check could not run, ignoring: {lint_precheck.output}",
        })

    combined_passed = precheck.passed and not lint_failed
    combined_output = precheck.output
    if lint_failed:
        combined_output = (combined_output + "\n\n[Lint failures]\n" + lint_precheck.output).strip()

    activation, sensitive_hits = decide_activation(
        tests_passed=combined_passed,
        changed_files=body.changed_files,
        file_path=body.file_path,
    )
    _db_set_activation(run_id, activation.value)
    await log_callback({
        "type": "log",
        "message": f"Activation: {activation_label(activation.value)}",
    })

    if activation == ActivationReason.SKIPPED:
        avg_cost = _average_agent_run_cost()
        if avg_cost:
            await log_callback({
                "type": "log",
                "message": f"Estimated savings: ~${avg_cost:.4f} (avg. cost of past agent runs, not spent)",
            })
        await log_callback({
            "type": "skipped",
            "message": "Pre-check passed — no sensitive paths touched, agent not invoked",
        })
        _db_complete_run(run_id, {"status": "skipped", "iterations": None}, None)
        asyncio.create_task(_cleanup_stale_queue(run_id))
        return

    if activation == ActivationReason.SELF_HEAL:
        await log_callback({
            "type": "log",
            "message": "Pre-check failed — activating self-heal agent…",
        })
        body = body.model_copy(update={"error_log": combined_output})
        agent_mode = "self_heal"
    else:
        await log_callback({
            "type": "log",
            "message": (
                f"Sensitive paths touched: {', '.join(sensitive_hits)} "
                "— activating deep-review agent…"
            ),
        })
        agent_mode = "deep_review"

    # Snapshot the file before the agent touches it so we can compute a diff later
    target_path = Path(body.workspace) / body.file_path
    original_content = _read_file_safe(target_path)

    result = {"status": "failed", "iterations": None}
    try:
        result = await run_healing_agent(
            file_path=body.file_path,
            error_log=body.error_log,
            workspace=body.workspace,
            log_callback=log_callback,
            mode=agent_mode,
            sensitive_files=sensitive_hits if agent_mode == "deep_review" else None,
        )
    except Exception as e:
        result = {"status": "failed", "iterations": None}
        await log_callback({"type": "error", "message": f"Unexpected agent error: {e}"})
        _db_complete_run(run_id, result, None)
        asyncio.create_task(_cleanup_stale_queue(run_id))
        return

    # Compute diff BEFORE emitting the terminal message so the WebSocket is still open.
    # git diff covers multiple changed files natively; fall back to a single-file
    # difflib comparison for non-git workspaces or if the agent reported no files.
    files_changed: list[str] = result.get("files_changed") or []
    diff = git_diff(body.workspace, files_changed) if files_changed else None
    if diff is None:
        modified_content = _read_file_safe(target_path)
        diff = _compute_diff(original_content, modified_content, body.file_path)
        if diff and not files_changed:
            files_changed = [body.file_path]

    if diff:
        await log_callback({"type": "diff", "message": diff})
    if len(files_changed) > 1:
        await log_callback({"type": "log", "message": f"[Files changed] {', '.join(files_changed)}"})

    input_tokens = result.get("input_tokens", 0)
    output_tokens = result.get("output_tokens", 0)
    cost = estimate_cost(get_model(), input_tokens, output_tokens)
    await log_callback({
        "type": "log",
        "message": f"[Token usage] input={input_tokens} output={output_tokens} est. cost=${cost:.4f}",
    })

    fix_branch = None
    if result.get("status") == "success" and diff and files_changed:
        pushback = create_fix_branch(
            workspace=body.workspace,
            file_paths=files_changed,
            run_id=run_id,
            summary=result.get("summary", ""),
        )
        fix_branch = pushback.branch
        await log_callback({"type": "log", "message": f"[Git push-back] {pushback.message}"})

    if result.get("status") == "success":
        await log_callback({"type": "done", "message": "Agent finished successfully"})
    else:
        await log_callback({
            "type": "error",
            "message": f"Could not fix automatically after {result.get('iterations', '?')} iterations",
        })

    _db_complete_run(
        run_id, result, diff,
        error_log=body.error_log,
        fix_branch=fix_branch,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
    )
    # Keep the queue alive until the WebSocket drains it (avoids a race where
    # the background task finishes before the browser connects).
    asyncio.create_task(_cleanup_stale_queue(run_id))


# ── DB helpers (sync — SQLite latency is negligible) ─────────────────────────

def _db_set_activation(run_id: str, reason: Optional[str]) -> None:
    with SessionLocal() as db:
        run = db.get(HealingRun, run_id)
        if run is None:
            return
        run.activation_reason = reason
        db.commit()


def _db_create_run(run_id: str, body: TriggerRequest) -> None:
    with SessionLocal() as db:
        db.add(HealingRun(
            id=run_id,
            repo=body.repo,
            file_path=body.file_path,
            error_log=body.error_log or "(pending pre-check)",
            status="running",
            created_at=datetime.utcnow(),
        ))
        db.commit()


def _db_complete_run(
    run_id: str,
    result: dict,
    diff: Optional[str],
    error_log: Optional[str] = None,
    fix_branch: Optional[str] = None,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
) -> None:
    with SessionLocal() as db:
        run = db.get(HealingRun, run_id)
        if run is None:
            return
        run.status = result.get("status", "failed")
        run.iterations = result.get("iterations")
        run.fix_diff = diff or None
        run.fix_branch = fix_branch
        run.input_tokens = input_tokens
        run.output_tokens = output_tokens
        run.estimated_cost_usd = estimated_cost_usd
        run.completed_at = datetime.utcnow()
        if result.get("status") == "skipped":
            run.error_log = "Pre-check passed — agent not invoked"
        elif error_log:
            run.error_log = error_log
        db.commit()


def _average_agent_run_cost() -> Optional[float]:
    """Average estimated_cost_usd across past runs that actually invoked the agent."""
    with SessionLocal() as db:
        costs = [
            c for (c,) in db.query(HealingRun.estimated_cost_usd)
                .filter(HealingRun.estimated_cost_usd.isnot(None))
                .filter(HealingRun.estimated_cost_usd > 0)
                .all()
        ]
        return sum(costs) / len(costs) if costs else None


# ── Utilities ────────────────────────────────────────────────────────────────

def _read_file_safe(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _compute_diff(original: str, modified: str, filename: str) -> str:
    if original == modified:
        return ""
    lines_a = original.splitlines(keepends=True)
    lines_b = modified.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))
