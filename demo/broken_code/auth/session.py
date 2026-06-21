"""Session helpers for the demo auth module."""

import secrets
from typing import Optional

# Maps opaque session token -> user_id.
# NOTE: In-process dict only; use a server-side store (Redis, DB) in production.
_active_sessions: dict[str, str] = {}


def create_session(user_id: str, password: str) -> str:  # noqa: ARG001  (password unused by design)
    """Create a session for *user_id*.

    The caller is responsible for validating the password **before** calling
    this function.  The password is intentionally not stored or embedded in
    the token — the token is an opaque, cryptographically random handle.

    Args:
        user_id: Authenticated user identifier.
        password: Accepted but never persisted/embedded; here only so callers
                  do not have to change their call-site signatures during
                  migration.

    Returns:
        A 32-byte (256-bit) URL-safe token string.
    """
    token = secrets.token_urlsafe(32)
    _active_sessions[token] = user_id
    return token


def validate_session(token: str) -> Optional[str]:
    """Return the user_id bound to *token*, or None if the token is invalid."""
    return _active_sessions.get(token)
