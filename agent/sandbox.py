import asyncio
from pathlib import Path

import docker
import docker.errors

_IMAGE = "code-healer-sandbox"
_DEFAULT_TIMEOUT = 60  # seconds per container run


async def run_in_sandbox(
    command: list[str],
    workspace: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """
    Run a command inside an ephemeral Docker container with the workspace
    mounted read-only. Returns combined stdout+stderr as a string.

    The container is always removed after the run, even on error.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: _run_container_sync(command, workspace, timeout),
    )


def _run_container_sync(command: list[str], workspace: str, timeout: int) -> str:
    client = docker.from_env()
    container = None

    # Resolve to absolute path so Docker mount works on all platforms
    abs_workspace = str(Path(workspace).resolve())

    try:
        container = client.containers.create(
            image=_IMAGE,
            command=command,
            volumes={abs_workspace: {"bind": "/workspace", "mode": "ro"}},
            working_dir="/workspace",
            mem_limit="256m",
            cpu_period=100_000,
            cpu_quota=50_000,   # cap at 50 % of one CPU
            network_disabled=True,
            environment={
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUNBUFFERED": "1",
            },
        )
        container.start()

        exit_info = container.wait(timeout=timeout)
        logs = container.logs(stdout=True, stderr=True).decode("utf-8")
        exit_code = exit_info.get("StatusCode", -1)

        # Prefix non-zero exits so the agent understands the test failed
        return (f"[exit {exit_code}]\n" if exit_code != 0 else "") + logs

    except docker.errors.ImageNotFound:
        return (
            f"ERROR: Docker image '{_IMAGE}' not found.\n"
            "Build it first:\n"
            "  docker build -t code-healer-sandbox ./sandbox-image"
        )
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}"
    finally:
        if container is not None:
            try:
                container.remove(force=True)
            except Exception:
                pass
