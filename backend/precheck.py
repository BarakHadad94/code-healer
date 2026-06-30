import asyncio
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_DEFAULT_TIMEOUT = 120  # seconds


@dataclass
class PrecheckResult:
    passed: bool
    output: str
    exit_code: int


async def run_pytest_precheck(workspace: str, timeout: int = _DEFAULT_TIMEOUT) -> PrecheckResult:
    """
    Run pytest in the workspace on the host (no Docker, no LLM).
    Used as a cheap gate before invoking the healing agent.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_pytest_sync(workspace, timeout),
    )


def _run_pytest_sync(workspace: str, timeout: int) -> PrecheckResult:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return PrecheckResult(
            passed=False,
            output=f"ERROR: Workspace not found: {workspace}",
            exit_code=-1,
        )

    command = [
        sys.executable, "-m", "pytest", ".",
        "-v", "--no-header", "--tb=short",
        "-p", "no:cacheprovider",
    ]

    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return PrecheckResult(
            passed=False,
            output=f"ERROR: pytest timed out after {timeout}s",
            exit_code=-1,
        )
    except FileNotFoundError:
        return PrecheckResult(
            passed=False,
            output="ERROR: Python interpreter not found",
            exit_code=-1,
        )

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return PrecheckResult(passed=True, output=output, exit_code=0)

    return PrecheckResult(
        passed=False,
        output=output,
        exit_code=result.returncode,
    )


async def run_ruff_precheck(workspace: str, timeout: int = _DEFAULT_TIMEOUT) -> PrecheckResult:
    """
    Run ruff in the workspace on the host (no Docker, no LLM).
    Runs alongside the pytest pre-check, before the activation decision.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_ruff_sync(workspace, timeout),
    )


def _run_ruff_sync(workspace: str, timeout: int) -> PrecheckResult:
    root = Path(workspace).resolve()
    if not root.is_dir():
        return PrecheckResult(
            passed=False,
            output=f"ERROR: Workspace not found: {workspace}",
            exit_code=-1,
        )

    command = [sys.executable, "-m", "ruff", "check", "."]

    try:
        result = subprocess.run(
            command,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return PrecheckResult(
            passed=False,
            output=f"ERROR: ruff timed out after {timeout}s",
            exit_code=-1,
        )
    except FileNotFoundError:
        return PrecheckResult(
            passed=False,
            output="ERROR: ruff not found — is it installed on the host?",
            exit_code=-1,
        )

    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode == 0:
        return PrecheckResult(passed=True, output=output, exit_code=0)

    return PrecheckResult(
        passed=False,
        output=output,
        exit_code=result.returncode,
    )
