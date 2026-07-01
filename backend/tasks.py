import asyncio
import difflib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from agent.agent import run_healing_agent
from backend.activation import ActivationReason, activation_label, decide_activation
from backend.config_loader import get_max_iterations, get_model
from backend.database import SessionLocal
from backend.git_pushback import create_fix_branch, git_diff
from backend.models import HealingRun
from backend.precheck import run_pytest_precheck, run_ruff_precheck
from backend.pricing import estimate_cost

# Maps run_id → asyncio.Queue of log messages.
# Each message: {"type": "log"|"diff"|"done"|"error"|"skipped", "message": str}
_log_queues: Dict[str, asyncio.Queue] = {}

_STALE_QUEUE_TTL = 600  # seconds — cleanup if no WebSocket ever connects


async def _cleanup_stale_queue(run_id: str, delay: int = _STALE_QUEUE_TTL) -> None:
    """Drop orphaned queues when the client never opens a WebSocket."""
    await asyncio.sleep(delay)
    _log_queues.pop(run_id, None)


async def _keepalive_loop(log_callback, interval: int = 10) -> None:
    """Send a no-op heartbeat so the WebSocket doesn't drop during long Anthropic API calls."""
    try:
        while True:
            await asyncio.sleep(interval)
            await log_callback({"type": "keepalive"})
    except asyncio.CancelledError:
        pass


async def run_healing_task(run_id: str, body) -> None:
    queue = _log_queues.get(run_id)
    if queue is None:
        return

    async def log_callback(msg: dict) -> None:
        if run_id in _log_queues:
            await queue.put(msg)

    _db_create_run(run_id, body)

    # ── pytest pre-check (cheap gate before LLM) ────────────────────────────
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
        await log_callback({"type": "history-ready"})
        asyncio.create_task(_cleanup_stale_queue(run_id))
        return

    # ── ruff pre-check (runs alongside pytest, before activation) ───────────
    await log_callback({"type": "log", "message": "Running ruff pre-check…"})
    lint_precheck = await run_ruff_precheck(body.workspace)

    lint_display = (
        lint_precheck.output if len(lint_precheck.output) <= 800
        else lint_precheck.output[:800] + "\n…(truncated)"
    )
    await log_callback({"type": "log", "message": f"[Lint]\n{lint_display}"})

    # Negative exit_code marks an infra issue (ruff missing, timeout) — don't
    # block the gate on that; only real lint violations (exit_code >= 0) count.
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
    await log_callback({"type": "activation", "message": activation.value})
    await log_callback({
        "type": "log",
        "message": f"Activation: {activation_label(activation.value)}",
    })

    if activation == ActivationReason.SKIPPED:
        await log_callback({
            "type": "skipped",
            "message": "Pre-check passed — no sensitive paths touched, agent not invoked",
        })
        _db_complete_run(run_id, {"status": "skipped", "iterations": None}, None)
        await log_callback({"type": "history-ready"})
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

    # Keepalive: send a heartbeat every 25 s so the WebSocket doesn't drop
    # during the long pauses while the agent waits for Anthropic API responses.
    keepalive = asyncio.create_task(_keepalive_loop(log_callback))
    result = {"status": "failed", "iterations": None}
    try:
        result = await run_healing_agent(
            file_path=body.file_path,
            error_log=body.error_log,
            workspace=body.workspace,
            log_callback=log_callback,
            mode=agent_mode,
            sensitive_files=sensitive_hits if agent_mode == "deep_review" else None,
            max_iterations=get_max_iterations(),
        )
    except Exception as e:
        keepalive.cancel()
        result = {"status": "failed", "iterations": None}
        await log_callback({"type": "error", "message": f"Agent error: {e}"})
        _db_complete_run(run_id, result, None)
        await log_callback({"type": "history-ready"})
        asyncio.create_task(_cleanup_stale_queue(run_id))
        return
    keepalive.cancel()

    # Compute diff BEFORE emitting the terminal message so the WebSocket is still open.
    # git diff covers multiple changed files natively; fall back to a single-file
    # difflib comparison for non-git workspaces or if the agent reported no files.
    files_changed: list[str] = result.get("files_changed") or []
    diff = await asyncio.to_thread(git_diff, body.workspace, files_changed) if files_changed else None
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
        pushback = await asyncio.to_thread(
            create_fix_branch,
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

    try:
        _db_complete_run(
            run_id, result, diff,
            error_log=body.error_log,
            fix_branch=fix_branch,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )
    except Exception as db_err:
        logging.getLogger(__name__).error("_db_complete_run failed for %s: %s", run_id, db_err)

    # Signal the browser to refresh history — DB is committed at this point.
    await log_callback({"type": "history-ready"})

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


def _db_create_run(run_id: str, body) -> None:
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
