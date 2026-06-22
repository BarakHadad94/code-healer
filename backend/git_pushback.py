import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_TIMEOUT = 30  # seconds, per git command


@dataclass
class PushbackResult:
    branch: Optional[str]
    message: str


def create_fix_branch(
    workspace: str,
    file_path: str,
    run_id: str,
    summary: str = "",
) -> PushbackResult:
    """
    Commit the already-written fix onto a new local branch, then restore the
    base branch in the working tree so the next demo run starts clean again.

    Never raises — git/workspace problems are reported in PushbackResult.message
    and must not fail the overall healing run.
    """
    root = Path(workspace).resolve()
    if not (root / ".git").is_dir():
        return PushbackResult(branch=None, message="Workspace is not a git repo — skipped push-back")

    base_branch = _run_git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    if base_branch is None:
        return PushbackResult(branch=None, message="Could not determine current branch — skipped push-back")
    base_branch = base_branch.strip()

    branch = f"fix/code-healer-{run_id[:8]}"

    if _run_git(root, ["checkout", "-b", branch]) is None:
        return PushbackResult(branch=None, message=f"Could not create branch {branch}")

    if _run_git(root, ["add", file_path]) is None:
        _run_git(root, ["checkout", base_branch])
        _run_git(root, ["branch", "-D", branch])
        return PushbackResult(branch=None, message=f"Could not stage {file_path}")

    staged = _run_git(root, ["diff", "--cached", "--name-only"])
    if not staged or not staged.strip():
        _run_git(root, ["checkout", base_branch])
        _run_git(root, ["branch", "-D", branch])
        return PushbackResult(
            branch=None,
            message=f"No git-trackable change — the fix matches what's already committed on "
                    f"{base_branch} (nothing to push back)",
        )

    commit_message = f"code-healer: fix {file_path} (run {run_id[:8]})"
    if summary.strip():
        commit_message += f"\n\n{summary.strip()}"

    commit_result = _run_git(root, ["commit", "-m", commit_message])
    if commit_result is None:
        _run_git(root, ["checkout", base_branch])
        _run_git(root, ["branch", "-D", branch])
        return PushbackResult(branch=None, message="Commit failed — skipped push-back")

    if _run_git(root, ["checkout", base_branch]) is None:
        return PushbackResult(
            branch=branch,
            message=f"Committed to {branch}, but could not switch back to {base_branch} "
                    "— workspace left on the fix branch",
        )

    return PushbackResult(branch=branch, message=f"Committed fix to local branch {branch} (not pushed)")


def _run_git(root: Path, args: list[str]) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout
