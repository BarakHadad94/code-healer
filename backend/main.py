import asyncio
import hashlib
import hmac
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Run uvicorn from the project root so these imports resolve:
#   uvicorn backend.main:app --reload
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

from backend.database import SessionLocal, create_tables
from backend.models import HealingRun
from backend.tasks import _log_queues, run_healing_task

app = FastAPI(title="code-healer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    create_tables()
    _mark_stale_runs_failed()


def _mark_stale_runs_failed() -> None:
    """Any run still 'running' when the server starts was interrupted by a restart."""
    with SessionLocal() as db:
        stale = db.query(HealingRun).filter(HealingRun.status == "running").all()
        for run in stale:
            run.status = "failed"
            run.completed_at = datetime.utcnow()
        if stale:
            db.commit()


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


# ── Auth ─────────────────────────────────────────────────────────────────────

def _require_trigger_key(x_api_key: Optional[str] = Header(None)) -> None:
    """
    Enforces X-API-Key on /trigger when TRIGGER_API_KEY is set in the environment.
    Skipped in local dev (no env var configured) so the dashboard works without setup.
    """
    configured_key = os.environ.get("TRIGGER_API_KEY", "")
    if not configured_key:
        return
    if not x_api_key or not hmac.compare_digest(configured_key, x_api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


# ── Routes ───────────────────────────────────────────────────────────────────

def _queue_healing_run(
    body: TriggerRequest,
    background_tasks: BackgroundTasks,
    message: str,
) -> TriggerResponse:
    run_id = str(uuid.uuid4())
    _log_queues[run_id] = asyncio.Queue()
    background_tasks.add_task(run_healing_task, run_id, body)
    return TriggerResponse(run_id=run_id, ws_url=f"/ws/logs/{run_id}", message=message)


@app.post("/trigger", response_model=TriggerResponse, dependencies=[Depends(_require_trigger_key)])
async def trigger_healing(body: TriggerRequest, background_tasks: BackgroundTasks):
    """
    Manual entry point — used by the dashboard form to simulate a CI failure.
    Returns immediately with a run_id; connect to ws_url to stream live logs.
    Requires X-API-Key header when TRIGGER_API_KEY is set in the environment.
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


@app.get("/demo/workspaces")
def demo_workspaces():
    """Absolute paths to the two demo workspaces — used by the dashboard form presets."""
    return {
        "broken": str(_PROJECT_ROOT / "demo" / "broken_code"),
        "clean":  str(_PROJECT_ROOT / "demo" / "clean_code"),
    }


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
            raise HTTPException(status_code=404, detail="Run not found")
        return run


@app.get("/runs/{run_id}/diff")
def get_run_diff(run_id: str):
    """Return the raw unified diff for a completed run."""
    with SessionLocal() as db:
        run = db.get(HealingRun, run_id)
        if run is None:
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
            if msg.get("type") == "history-ready":
                await websocket.close(code=1000)
                break
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _log_queues.pop(run_id, None)
