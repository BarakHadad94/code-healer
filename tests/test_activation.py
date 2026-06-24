from unittest.mock import patch

from backend.activation import (
    ActivationReason,
    activation_label,
    decide_activation,
    find_sensitive_matches,
)

# --- find_sensitive_matches ---

def test_exact_match():
    assert find_sensitive_matches(["auth/session.py"], ["auth/"]) == ["auth/session.py"]


def test_prefix_match():
    assert find_sensitive_matches(["auth/utils/helper.py"], ["auth/"]) == ["auth/utils/helper.py"]


def test_no_match():
    assert find_sensitive_matches(["src/utils.py"], ["auth/", "payments/"]) == []


def test_windows_backslash_normalized():
    assert find_sensitive_matches(["auth\\session.py"], ["auth/"]) == ["auth\\session.py"]


def test_dotslash_prefix_stripped():
    assert find_sensitive_matches(["./auth/session.py"], ["auth/"]) == ["./auth/session.py"]


def test_multiple_files_partial_match():
    files = ["auth/session.py", "src/utils.py", "payments/process.py"]
    result = find_sensitive_matches(files, ["auth/", "payments/"])
    assert "auth/session.py" in result
    assert "payments/process.py" in result
    assert "src/utils.py" not in result


def test_prefix_without_trailing_slash():
    # Sensitive path listed without trailing slash still matches
    assert find_sensitive_matches(["auth/session.py"], ["auth"]) == ["auth/session.py"]


# --- decide_activation ---

def test_self_heal_when_tests_fail():
    with patch("backend.activation.get_sensitive_paths", return_value=["auth/"]):
        reason, _ = decide_activation(False, ["src/utils.py"], "src/utils.py")
    assert reason == ActivationReason.SELF_HEAL


def test_deep_review_when_tests_pass_and_sensitive():
    with patch("backend.activation.get_sensitive_paths", return_value=["auth/"]):
        reason, hits = decide_activation(True, ["auth/session.py"], "auth/session.py")
    assert reason == ActivationReason.DEEP_REVIEW
    assert "auth/session.py" in hits


def test_skipped_when_green_and_not_sensitive():
    with patch("backend.activation.get_sensitive_paths", return_value=["auth/"]):
        reason, hits = decide_activation(True, ["src/utils.py"], "src/utils.py")
    assert reason == ActivationReason.SKIPPED
    assert hits == []


def test_self_heal_takes_priority_over_sensitive_path():
    # Tests fail + sensitive path → SELF_HEAL, not DEEP_REVIEW
    with patch("backend.activation.get_sensitive_paths", return_value=["auth/"]):
        reason, _ = decide_activation(False, ["auth/session.py"], "auth/session.py")
    assert reason == ActivationReason.SELF_HEAL


def test_falls_back_to_file_path_when_no_changed_files():
    with patch("backend.activation.get_sensitive_paths", return_value=["auth/"]):
        reason, hits = decide_activation(True, [], "auth/session.py")
    assert reason == ActivationReason.DEEP_REVIEW


# --- activation_label ---

def test_label_self_heal():
    assert "Self-heal" in activation_label("self_heal")


def test_label_deep_review():
    assert "Deep review" in activation_label("deep_review")


def test_label_skipped():
    assert "Skipped" in activation_label("skipped")


def test_label_unknown_returns_raw():
    assert activation_label("mystery") == "mystery"


def test_label_empty_returns_dash():
    assert activation_label("") == "—"
