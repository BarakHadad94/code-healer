import anthropic
from typing import Awaitable, Callable, Optional

from backend.config_loader import get_model
from .tools import TOOL_DEFINITIONS, execute_tool, set_workspace

LogCallback = Callable[[dict], Awaitable[None]]

_MAX_TOKENS = 4096

_SYSTEM_PROMPT_SELF_HEAL = """You are code-healer, an autonomous agent that diagnoses and fixes broken Python code.

You have been activated because a CI check failed. Work through the problem methodically:

1. Read the failing file with read_file — never modify code you haven't read
2. Analyse the error log the user provided and form a hypothesis
3. If the root cause lives in another file (a shared helper, an imported module, a config
   file), use list_files/read_file to find it and fix it there too — you are not limited
   to the single file that triggered the failure
4. Apply your fix with write_file (one call per file that needs changing)
5. Verify with run_tests — if tests still fail, analyse the new error and iterate
6. Once tests pass, write a concise summary of what you changed, in which files, and why

Rules:
- Read before you write — always
- After every write_file, call run_tests to confirm the fix
- Only touch files that are actually part of the fix — don't make unrelated edits
- If run_linter surfaces issues unrelated to the original error, leave them; stay focused
- If you genuinely cannot fix the issue, explain what you tried and why it is difficult
- Keep reasoning clear and brief — the developer is watching your steps in real time"""

_SYSTEM_PROMPT_DEEP_REVIEW = """You are code-healer in deep-review mode. Tests already pass, but changes touched
security-sensitive code paths (auth, payments, database queries, etc.).

Your job is a semantic security and correctness review — not fixing a failing test.

1. Read each flagged file with read_file
2. Look for security issues: credential handling, injection risks, missing validation,
   unsafe defaults, secrets in code, broken session/auth logic
3. Use run_linter on reviewed files when helpful
4. Run run_tests to confirm you have not broken the green build
5. If you find a clear, safe improvement, apply a minimal fix with write_file — across as many
   of the flagged files as genuinely need it — and re-run tests
6. End with a concise review summary: risks found, severity, and which files you changed

Rules:
- Do not make drive-by refactors — stay focused on security and correctness in sensitive code
- If tests pass and no fix is needed, say so clearly in your summary
- Keep reasoning clear and brief — the developer is watching your steps in real time"""


async def run_healing_agent(
    file_path: str,
    error_log: str,
    workspace: str,
    log_callback: LogCallback,
    mode: str = "self_heal",
    sensitive_files: Optional[list[str]] = None,
    max_iterations: int = 10,
) -> dict:
    """
    Run the autonomous healing loop.

    mode: "self_heal" (Scenario A) or "deep_review" (Scenario B)
    Streams structured log dicts to log_callback as it works.
    Returns {"status": "success"|"failed", "iterations": int}.
    """
    set_workspace(workspace)
    client = anthropic.AsyncAnthropic()
    model = get_model()

    if mode == "deep_review":
        system = _SYSTEM_PROMPT_DEEP_REVIEW
        flagged = sensitive_files or [file_path]
        file_list = "\n".join(f"- `{p}`" for p in flagged)
        user_content = (
            "CI tests passed, but this push touched sensitive paths.\n\n"
            f"**Files to review:**\n{file_list}\n\n"
            f"Primary file: `{file_path}`\n\n"
            "Perform a deep security review. Apply minimal safe fixes only if warranted."
        )
    else:
        system = _SYSTEM_PROMPT_SELF_HEAL
        user_content = (
            f"The file `{file_path}` caused a CI failure.\n\n"
            f"**Error log:**\n```\n{error_log}\n```\n\n"
            "Please diagnose and fix the issue."
        )

    messages: list[dict] = [
        {"role": "user", "content": user_content},
    ]

    total_input_tokens = 0
    total_output_tokens = 0
    files_written: list[str] = []

    for iteration in range(1, max_iterations + 1):
        await log_callback({"type": "log", "message": f"--- Iteration {iteration}/{max_iterations} ---"})

        try:
            response = await client.messages.create(
                model=model,
                max_tokens=_MAX_TOKENS,
                system=system,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            raise RuntimeError(
                "Anthropic API key is invalid or missing. "
                "Check ANTHROPIC_API_KEY in your .env file."
            )
        except anthropic.RateLimitError:
            raise RuntimeError(
                "Anthropic API rate limit reached. Wait a moment and try again."
            )
        except anthropic.APIConnectionError:
            raise RuntimeError(
                "Could not connect to Anthropic API. Check your internet connection."
            )
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Anthropic API error {e.status_code}: {e.message}")

        total_input_tokens += response.usage.input_tokens
        total_output_tokens += response.usage.output_tokens

        # Emit any reasoning text from the model
        texts = [block.text for block in response.content if block.type == "text" and block.text.strip()]
        for text in texts:
            await log_callback({"type": "log", "message": text})

        # No tool calls → agent has concluded; caller sends "done" after computing diff
        if response.stop_reason == "end_turn":
            return {
                "status": "success",
                "iterations": iteration,
                "summary": "\n\n".join(texts),
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "files_changed": list(dict.fromkeys(files_written)),
            }

        # Execute each tool call and collect results
        assistant_content = _serialize_content(response.content)
        tool_results = []

        for block in response.content:
            if block.type != "tool_use":
                continue

            await log_callback({
                "type": "log",
                "message": f"[Tool] {block.name}  args={block.input}",
            })

            if block.name == "write_file" and isinstance(block.input.get("path"), str):
                files_written.append(block.input["path"])

            result = await execute_tool(block.name, block.input)

            # Truncate long results in the display log but send full result to the model
            display = result if len(result) <= 600 else result[:600] + "\n…(truncated)"
            await log_callback({"type": "log", "message": f"[Result] {display}"})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    return {
        "status": "failed",
        "iterations": max_iterations,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "files_changed": list(dict.fromkeys(files_written)),
    }


def _serialize_content(blocks) -> list[dict]:
    """Convert SDK content block objects to plain dicts for the message history."""
    out = []
    for block in blocks:
        if block.type == "text":
            out.append({"type": "text", "text": block.text})
        elif block.type == "tool_use":
            out.append({
                "type": "tool_use",
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return out
