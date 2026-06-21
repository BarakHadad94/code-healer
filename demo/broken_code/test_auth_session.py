from auth.session import create_session, validate_session


def test_create_and_validate_session():
    token = create_session("alice", "s3cret")
    assert validate_session(token) == "alice"


def test_token_does_not_contain_credentials():
    """The token must be an opaque handle — never embed user_id or password."""
    token = create_session("alice", "s3cret")
    assert "alice" not in token, "user_id must not appear in token"
    assert "s3cret" not in token, "password must never appear in token"


def test_token_is_unique():
    """Every call must produce a distinct token (no deterministic/reused tokens)."""
    tokens = {create_session("alice", "s3cret") for _ in range(50)}
    assert len(tokens) == 50, "tokens must be unique across calls"


def test_invalid_token_returns_none():
    """An unknown token must return None, not raise or return a default user."""
    assert validate_session("not-a-real-token") is None
