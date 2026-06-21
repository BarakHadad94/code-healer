import pathlib
from typing import Any, Optional

from .sandbox import run_in_sandbox

_workspace_root: Optional[pathlib.Path] = None


def set_workspace(path: str) -> None:
    global _workspace_root
    _workspace_root = pathlib.Path(path).resolve()


def _safe_path(relative: str) -> pathlib.Path:
    """Resolve a workspace-relative path, rejecting any escape attempts."""
    if _workspace_root is None:
        raise RuntimeError("Workspace not set — call set_workspace() first")
    resolved = (_workspace_root / relative).resolve()
    if not str(resolved).startswith(str(_workspace_root)):
        raise ValueError(f"Path escape rejected: {relative!r}")
    return resolved


# ── Tool definitions (sent to Claude) ────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read the full content of a file in the workspace. "
            "Always call this before modifying a file."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Overwrite a file in the workspace with new content. "
            "Use this to apply your fix. Always run tests afterwards."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
                "content": {"type": "string", "description": "Full new content of the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories inside a workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Workspace-relative directory path (use '.' for root)",
                },
            },
            "required": ["directory"],
        },
    },
    {
        "name": "run_tests",
        "description": (
            "Run the pytest test suite for a file or directory inside a Docker sandbox. "
            "Returns stdout/stderr. Use this to verify your fix is correct."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Workspace-relative path to test file or directory",
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "run_linter",
        "description": "Run ruff linter on a file inside a Docker sandbox. Returns any lint errors.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
            },
            "required": ["path"],
        },
    },
]


# ── Tool implementations ──────────────────────────────────────────────────────

async def _read_file(path: str) -> str:
    target = _safe_path(path)
    if not target.exists():
        return f"ERROR: File not found: {path}"
    return target.read_text(encoding="utf-8")


async def _write_file(path: str, content: str) -> str:
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"OK: wrote {len(content)} chars to {path}"


async def _list_files(directory: str) -> str:
    target = _safe_path(directory)
    if not target.is_dir():
        return f"ERROR: Not a directory: {directory}"
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
    lines = [f"{'DIR ' if e.is_dir() else 'FILE'} {e.name}" for e in entries]
    return "\n".join(lines) if lines else "(empty directory)"


async def _run_tests(target: str) -> str:
    if _workspace_root is None:
        return "ERROR: Workspace not set"
    command = [
        "pytest", target,
        "-v", "--no-header", "--tb=short",
        "-p", "no:cacheprovider",
    ]
    return await run_in_sandbox(command, str(_workspace_root))


async def _run_linter(path: str) -> str:
    if _workspace_root is None:
        return "ERROR: Workspace not set"
    return await run_in_sandbox(["ruff", "check", path], str(_workspace_root))


_TOOL_MAP = {
    "read_file": _read_file,
    "write_file": _write_file,
    "list_files": _list_files,
    "run_tests": _run_tests,
    "run_linter": _run_linter,
}


async def execute_tool(name: str, inputs: dict[str, Any]) -> str:
    handler = _TOOL_MAP.get(name)
    if handler is None:
        return f"ERROR: Unknown tool: {name}"
    try:
        return await handler(**inputs)
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
